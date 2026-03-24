from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost as _xgb_module
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.orm import Session
from xgboost import XGBClassifier, XGBRegressor

# Running library versions — embedded into every saved artifact.
_SKLEARN_VERSION: str = sklearn.__version__
_XGBOOST_VERSION: str = _xgb_module.__version__

from app.services.feature_extractor import (
    CLUSTERING_FEATURES,
    ROLE_ENCODING,
    ROLLING_FEATURES,
    TIMELINE_FEATURES,
    get_all_rolling_features_bulk,
    get_champion_stats,
    get_clustering_features,
    get_rolling_features,
    get_timeline_features,
    get_win_prediction_features,
)

logger = logging.getLogger(__name__)

ML_MODELS_DIR = Path(__file__).parent.parent.parent / "ml_models"
ML_MODELS_DIR.mkdir(exist_ok=True)

# Module-level model cache — loaded once per process
_model_cache: dict[str, dict] = {}

# Maps internal artifact key → the URL path segment used in /ai/train/<slug>.
# Keep this in sync with app/api/routes/ai.py.
_ARTIFACT_ROUTE_SLUG: dict[str, str] = {
    "playstyle_kmeans":    "playstyle",
    "win_predictor":       "win-prediction",
    "kda_regressor":       "kda-regression",
    "cs_regressor":        "cs-regression",
    "earlygame_predictor": "early-game",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InsufficientDataError(Exception):
    """Raised when not enough data exists to train a model."""
    pass


class ModelNotTrainedError(Exception):
    """Raised when inference is attempted on a model that has not been trained."""
    pass


# ---------------------------------------------------------------------------
# Cluster label auto-assignment
# ---------------------------------------------------------------------------

# Canonical archetype definitions keyed on feature signals.
# Each archetype has a PRIMARY discriminating feature (highest centroid value
# among all clusters) and a SECONDARY confirming feature.
# Auto-labeling compares normalized centroid ranks for each feature, so
# assignment is robust to changes in scale or sample size.
_ARCHETYPE_SIGNALS: list[dict] = [
    {
        "label":     "carry",
        "primary":   "avg_gold_per_min",      # sustained resource generation
        "secondary": "avg_damage_share",       # converts gold into team damage
        "tertiary":  "avg_cs_per_min",         # farms well
        "description": "High gold/min, damage share, and CS. Consistent scaling carry.",
    },
    {
        "label":     "skirmisher",
        "primary":   "avg_kills",              # high raw kills
        "secondary": "first_blood_rate",       # fights early and often
        "tertiary":  "avg_deaths",             # accepts trades, dies more
        "description": "High kills and first-blood rate. Aggressive, early-fight focus.",
    },
    {
        "label":     "support_utility",
        "primary":   "avg_vision_per_min",     # ward-heavy
        "secondary": "avg_assists",            # participates without killing
        "tertiary":  "avg_wards_placed",       # active warding behaviour
        "description": "Top vision control and assists. Ward-heavy utility player.",
    },
    {
        "label":     "farm_efficiency",
        "primary":   "avg_cs_per_min",         # highest CS rate
        "secondary": "avg_kda",                # stays alive to keep farming
        "tertiary":  "avg_gold_per_min",       # converts CS to gold
        "description": "Highest CS/min with low death rate. Passive farming style.",
    },
]


def _auto_label_clusters(centroid_df: pd.DataFrame) -> dict[int, str]:
    """Assign archetype labels to KMeans cluster IDs from centroid data.

    Method:
      For each archetype, identify which cluster has the highest *combined*
      rank score across its primary / secondary / tertiary features.
      Greedy assignment: once a cluster is claimed it is not reassigned.
      Any unclaimed cluster falls back to ``"cluster_N"``.

    Args:
        centroid_df: DataFrame with one row per cluster (index = cluster id)
                     and one column per feature.  Use
                     ``scaler.inverse_transform(model.cluster_centers_)``.

    Returns:
        dict mapping cluster_id (int) → label string.
    """
    # Rank each column: 0 = lowest centroid value, n_clusters-1 = highest.
    # Higher rank = stronger signal for that feature.
    ranked = centroid_df.rank(axis=0)  # per-column rank across clusters

    n_clusters = len(centroid_df)
    assigned: dict[int, str] = {}
    claimed_clusters: set[int] = set()

    for archetype in _ARCHETYPE_SIGNALS:
        if len(claimed_clusters) >= n_clusters:
            break

        weights = {archetype["primary"]: 3.0, archetype["secondary"]: 2.0}
        tertiary = archetype.get("tertiary")
        if tertiary:
            weights[tertiary] = 1.0

        scores: dict[int, float] = {}
        for cluster_id in range(n_clusters):
            if cluster_id in claimed_clusters:
                continue
            s = 0.0
            for feat, w in weights.items():
                if feat in ranked.columns:
                    s += float(ranked.loc[cluster_id, feat]) * w
            scores[cluster_id] = s

        best_cluster = max(scores, key=lambda k: scores[k])
        assigned[best_cluster] = archetype["label"]
        claimed_clusters.add(best_cluster)
        logger.info(
            "Cluster %d → '%s'  (score=%.1f)  | %s",
            best_cluster,
            archetype["label"],
            scores[best_cluster],
            archetype["description"],
        )

    # Fall back for any unclaimed clusters (e.g. if n_clusters != 4)
    for cluster_id in range(n_clusters):
        if cluster_id not in assigned:
            assigned[cluster_id] = f"cluster_{cluster_id}"
            logger.warning(
                "Cluster %d has no matching archetype — using fallback label 'cluster_%d'",
                cluster_id, cluster_id,
            )

    return assigned


# Module-level cluster labels — populated by train_playstyle_model() and
# restored from the saved artifact at load time.
# NEVER edit by index; use _auto_label_clusters() output instead.
CLUSTER_LABELS: dict[int, str] = {}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# Required keys that every saved artifact dict must contain.
_ARTIFACT_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"model", "feature_cols", "model_type", "trained_at",
     "sklearn_version", "xgboost_version"}
)


def _route_slug(artifact_key: str) -> str:
    """Return the URL slug for an artifact key, falling back to the key itself."""
    return _ARTIFACT_ROUTE_SLUG.get(artifact_key, artifact_key)


def _load_model(name: str) -> dict:
    """Load and validate a model artifact from disk with version compatibility check.

    Version mismatch policy:
    - Major sklearn version difference → ``ModelNotTrainedError`` (retrain required).
    - Minor version difference → warning only; inference proceeds.
    - Missing version metadata (legacy artifact) → warning + retrain recommended.

    Raises:
        ModelNotTrainedError: if the file is missing, the artifact schema is
            invalid, or a major sklearn version mismatch is detected.
    """
    if name not in _model_cache:
        path = ML_MODELS_DIR / f"{name}.joblib"
        if not path.exists():
            slug = _route_slug(name)
            raise ModelNotTrainedError(
                f"Model '{name}' has not been trained yet. "
                f"POST /ai/train/{slug} to train it."
            )

        artifact: dict = joblib.load(path)

        # --- Schema validation -----------------------------------------------
        missing = _ARTIFACT_REQUIRED_KEYS - artifact.keys()
        if missing:
            raise ModelNotTrainedError(
                f"Artifact '{name}' is missing required keys: {sorted(missing)}. "
                f"POST /ai/train/{_route_slug(name)} to retrain."
            )

        # --- sklearn version check --------------------------------------------
        saved_sklearn: str = artifact["sklearn_version"]
        saved_major, saved_minor = _parse_version(saved_sklearn)
        curr_major, curr_minor = _parse_version(_SKLEARN_VERSION)

        if saved_major != curr_major:
            _model_cache.pop(name, None)  # do not cache incompatible artifact
            raise ModelNotTrainedError(
                f"Model '{name}' was trained on sklearn {saved_sklearn} but "
                f"the runtime has sklearn {_SKLEARN_VERSION}. "
                f"Major version mismatch — POST /ai/train/{_route_slug(name)} to retrain."
            )

        if saved_minor != curr_minor:
            logger.warning(
                "Model '%s': sklearn minor version mismatch (saved=%s, runtime=%s). "
                "Predictions may differ slightly. Schedule a retrain.",
                name, saved_sklearn, _SKLEARN_VERSION,
            )

        # --- XGBoost version check (warn only) --------------------------------
        saved_xgb: str = artifact.get("xgboost_version", "unknown")
        if saved_xgb != _XGBOOST_VERSION:
            logger.warning(
                "Model '%s': xgboost version mismatch (saved=%s, runtime=%s). "
                "Output scores for XGBoost models may differ.",
                name, saved_xgb, _XGBOOST_VERSION,
            )

        _model_cache[name] = artifact
        logger.info(
            "Loaded model '%s' — sklearn=%s xgboost=%s",
            name, saved_sklearn, artifact.get("xgboost_version", "n/a"),
        )
        # Restore cluster labels into the module-level dict on load so
        # inference works correctly without a retrain in the current process.
        if name == "playstyle_kmeans" and "cluster_labels" in artifact:
            CLUSTER_LABELS.clear()
            CLUSTER_LABELS.update({int(k): v for k, v in artifact["cluster_labels"].items()})
    return _model_cache[name]


def _parse_version(version_str: str) -> tuple[int, int]:
    """Parse 'MAJOR.MINOR[.PATCH]' into (major, minor) ints. Returns (0, 0) on failure."""
    try:
        parts = version_str.split(".")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError, AttributeError):
        return 0, 0


def invalidate_model_cache(name: str | None = None) -> None:
    """Evict one or all entries from the in-process model cache.

    Call this after a retrain so the next inference request reloads from disk.
    """
    if name is None:
        _model_cache.clear()
        logger.info("Model cache cleared (all entries evicted)")
    else:
        _model_cache.pop(name, None)
        logger.info("Model cache evicted: '%s'", name)


# ---------------------------------------------------------------------------
# Function 1: train_playstyle_model
# ---------------------------------------------------------------------------


def train_playstyle_model(db: Session) -> dict:
    """
    Train KMeans playstyle clustering on all ingested players.

    Data gate: raises InsufficientDataError if fewer than 20 players
    have >= 10 matches each.

    Cluster labels are assigned automatically via ``_auto_label_clusters()``
    by matching centroid feature patterns to known archetypes.  The global
    ``CLUSTER_LABELS`` dict is updated in-process after every training run.

    Returns:
        dict with n_players, inertia, silhouette_score, cluster_labels, centroids.
    """
    df = get_clustering_features(db)

    eligible = df[df["games_played"] >= 10] if "games_played" in df.columns else df
    if len(eligible) < 20:
        raise InsufficientDataError(
            f"Need 20 players with 10+ matches for clustering. "
            f"Currently have {len(eligible)}. Ingest more players."
        )

    X = eligible[CLUSTERING_FEATURES].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = KMeans(n_clusters=4, random_state=42, n_init=10)
    model.fit(X_scaled)

    labels = model.labels_
    sil = float(silhouette_score(X_scaled, labels)) if len(set(labels)) > 1 else 0.0

    centroid_df = pd.DataFrame(
        scaler.inverse_transform(model.cluster_centers_),
        columns=CLUSTERING_FEATURES,
    )

    # Auto-assign archetype labels from centroid feature patterns.
    # This replaces ad-hoc manual index→label mapping.
    cluster_labels = _auto_label_clusters(centroid_df)
    CLUSTER_LABELS.clear()
    CLUSTER_LABELS.update(cluster_labels)

    artifact = {
        "model":           model,
        "scaler":          scaler,
        "encoder":         None,
        "feature_cols":    CLUSTERING_FEATURES,
        "model_type":      "kmeans",
        "trained_at":      datetime.now(timezone.utc).isoformat(),
        "n_samples":       len(eligible),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "cluster_labels":  cluster_labels,
        "metrics": {
            "silhouette_score": sil,
            "inertia":          float(model.inertia_),
            "n_clusters":       4,
        },
        "centroids": centroid_df.to_dict(),
    }

    path = ML_MODELS_DIR / "playstyle_kmeans.joblib"
    joblib.dump(artifact, path)
    # Evict then re-cache so the in-process copy has version metadata too
    invalidate_model_cache("playstyle_kmeans")
    _model_cache["playstyle_kmeans"] = artifact
    logger.info("Saved playstyle_kmeans.joblib — silhouette=%.3f sklearn=%s", sil, _SKLEARN_VERSION)

    return {
        "status":           "trained",
        "n_players":        len(eligible),
        "silhouette_score": sil,
        "inertia":          float(model.inertia_),
        "cluster_labels":   cluster_labels,
        "centroids":        centroid_df.round(3).to_dict(),
    }


# ---------------------------------------------------------------------------
# Function 2: get_player_playstyle
# ---------------------------------------------------------------------------


def get_player_playstyle(db: Session, puuid: str) -> dict:
    """
    Predict playstyle cluster for one player.

    Returns:
        dict with cluster_id, playstyle_label, feature_snapshot.
        Returns insufficient_data label if player has < 10 matches.

    Raises:
        ModelNotTrainedError if playstyle_kmeans has not been trained.
    """
    artifact = _load_model("playstyle_kmeans")
    model: KMeans = artifact["model"]
    scaler: StandardScaler = artifact["scaler"]
    feature_cols: list[str] = artifact["feature_cols"]
    # Use labels embedded in the artifact — never rely on module-global alone
    # so that multi-worker deployments are consistent.
    artifact_labels: dict[int, str] = {
        int(k): v for k, v in artifact.get("cluster_labels", {}).items()
    } or CLUSTER_LABELS

    df = get_clustering_features(db)
    player_row = df[df["puuid"] == puuid]

    if player_row.empty:
        return {
            "puuid":            puuid,
            "cluster_id":       -1,
            "playstyle_label":  "insufficient_data",
            "message":          "Player not found or fewer than 5 ranked matches.",
            "meets_min_sample": False,
        }

    games = int(player_row["games_played"].iloc[0]) if "games_played" in player_row.columns else 0
    if games < 10:
        return {
            "puuid":            puuid,
            "cluster_id":       -1,
            "playstyle_label":  "insufficient_data",
            "message":          f"Player has {games} matches. Need 10+ for reliable clustering.",
            "meets_min_sample": False,
            "games_played":     games,
        }

    X = player_row[feature_cols].values
    X_scaled = scaler.transform(X)
    cluster_id = int(model.predict(X_scaled)[0])
    label = artifact_labels.get(cluster_id, f"cluster_{cluster_id}")

    # Distance to cluster center (lower = more typical of that playstyle)
    center = model.cluster_centers_[cluster_id]
    distance = float(np.linalg.norm(X_scaled[0] - center))

    feature_snapshot = {
        col: round(float(player_row[col].iloc[0]), 3)
        for col in feature_cols
    }

    return {
        "puuid":                   puuid,
        "riot_id":                 str(player_row["riot_id"].iloc[0]) if "riot_id" in player_row.columns else None,
        "cluster_id":              cluster_id,
        "playstyle_label":         label,
        "meets_min_sample":        True,
        "games_played":            games,
        "cluster_center_distance": round(distance, 4),
        "feature_snapshot":        feature_snapshot,
        "model_trained_at":        artifact["trained_at"],
    }


# ---------------------------------------------------------------------------
# Function 3: get_champion_recommendations
# ---------------------------------------------------------------------------


def get_champion_recommendations(
    db: Session,
    puuid: str,
    top_n: int = 10,
    role_filter: Optional[str] = None,
) -> list[dict]:
    """
    Return ranked champion recommendations for one player.

    Uses Bayesian-smoothed win rate + normalized KDA/CS scoring.
    No ML model required — pure SQL aggregation + Python scoring.

    Args:
        top_n: Maximum recommendations to return (capped at 20).
        role_filter: Optional role string e.g. 'MIDDLE', 'BOTTOM'.

    Returns:
        Sorted list of recommendation dicts (empty list if no data).
    """
    df = get_champion_stats(db, puuid)
    if df.empty:
        return []

    if role_filter:
        df = df[df["role"].str.upper() == role_filter.upper()]
        if df.empty:
            return []

    global_avg_wr = float(df["win_rate"].mean()) if len(df) > 0 else 0.5
    # Use global max (all players' games on that champ) isn't available here
    # so cap exp_weight at a fixed reference point instead of using the
    # player's own max_games — avoids inflating one-trick picks.
    EXP_REFERENCE = 50  # games needed to reach full experience weight

    # Role-aware CS normalization caps per role
    # An ADC hitting 10 cs/min is excellent; a Support at 10 is anomalous.
    _CS_CAP_BY_ROLE: dict[str, float] = {
        "BOTTOM":  9.0,
        "MIDDLE":  8.0,
        "TOP":     7.5,
        "JUNGLE":  6.0,
        "UTILITY": 2.5,
        "SUPPORT": 2.5,
    }

    # Attempt to resolve champion names from the ddragon cache.
    try:
        from app.services.ddragon import get_champion_name  # type: ignore[attr-defined]
    except ImportError:
        try:
            from app.services import ddragon as _ddragon

            def get_champion_name(cid: int) -> Optional[str]:  # type: ignore[misc]
                return _ddragon._champion_map.get(cid)
        except Exception:
            def get_champion_name(cid: int) -> Optional[str]:  # type: ignore[misc]
                return None

    # Recency: unix-ms timestamp of most recent game on this champion
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    _RECENCY_HALF_LIFE_MS = 90 * 24 * 3600 * 1000  # 90 days

    K = 5  # Bayesian prior strength

    scored: list[dict] = []
    for _, row in df.iterrows():
        games = int(row["games_played"])
        total_wins = (
            int(row["total_wins"])
            if "total_wins" in row.index
            else int(round(float(row["win_rate"]) * games))
        )

        # --- Win rate: Bayesian-smoothed ---
        smoothed_wr = (total_wins + K * global_avg_wr) / (games + K)

        # --- KDA: normalized to role-typical ceiling (5.0 for carries) ---
        norm_kda = min(float(row["avg_kda"]) / 5.0, 1.0)

        # --- CS: role-aware cap so utility roles aren't penalized ---
        role_str = str(row["role"]).upper() if row["role"] is not None else ""
        cs_cap = _CS_CAP_BY_ROLE.get(role_str, 8.0)
        norm_cs = min(float(row["avg_cs_per_min"]) / cs_cap, 1.0)

        # --- Experience: log-scale capped at reference (avoids one-trick inflation) ---
        exp_weight = math.log1p(min(games, EXP_REFERENCE)) / math.log1p(EXP_REFERENCE)

        # --- Recency: exponential decay. Champions played recently score higher. ---
        last_ts = float(row.get("last_played_ts") or 0)
        age_ms = max(now_ms - last_ts, 0.0)
        recency_weight = math.exp(-age_ms / _RECENCY_HALF_LIFE_MS) if last_ts > 0 else 0.5

        # --- Final composite score ---
        score = (
            smoothed_wr    * 0.38
            + norm_kda     * 0.22
            + norm_cs      * 0.18
            + exp_weight   * 0.12
            + recency_weight * 0.10
        )

        champion_id = (
            int(row["champion_id"])
            if "champion_id" in row.index and row["champion_id"] is not None
            else None
        )
        resolved_name = get_champion_name(champion_id) if champion_id is not None else None

        scored.append({
            "champion":          str(row["champion"]),
            "champion_id":       champion_id,
            "champion_name":     resolved_name or str(row["champion"]),
            "role":              str(row["role"]) if row["role"] is not None else None,
            "score":             round(score, 4),
            "games_played":      games,
            "win_rate":          round(float(row["win_rate"]), 4),
            "smoothed_win_rate": round(smoothed_wr, 4),
            "avg_kda":           round(float(row["avg_kda"]), 3),
            "avg_cs_per_min":    round(float(row["avg_cs_per_min"]), 3),
            "recency_weight":    round(recency_weight, 3),
            "last_played_ts":    int(last_ts) if last_ts > 0 else None,
            "score_breakdown": {
                "win_rate":  round(smoothed_wr * 0.38, 4),
                "kda":       round(norm_kda * 0.22, 4),
                "cs":        round(norm_cs * 0.18, 4),
                "experience": round(exp_weight * 0.12, 4),
                "recency":   round(recency_weight * 0.10, 4),
            },
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top_n = min(top_n, 20)

    for i, rec in enumerate(scored[:top_n]):
        rec["rank"] = i + 1

    return scored[:top_n]


# ---------------------------------------------------------------------------
# Function 4: train_win_predictor
# ---------------------------------------------------------------------------


def train_win_predictor(db: Session) -> dict:
    """
    Train win prediction classifier on all ingested player match history.

    Trains Logistic Regression (baseline) and XGBoost, then saves the
    better model (by ROC-AUC) to win_predictor.joblib.

    Data gate: raises InsufficientDataError if < 100 labeled rows.
    Temporal split: oldest 80% = train, newest 20% = test. Never shuffle.

    Returns:
        dict with model_type, accuracy, roc_auc, top_factors.
    """
    _t0 = time.time()
    df_all = get_all_rolling_features_bulk(db)
    logger.info("Bulk feature fetch: %.1f seconds", time.time() - _t0)

    if len(df_all) < 100:
        raise InsufficientDataError(
            f"Need 100+ labeled training rows. Have {len(df_all)}. "
            "Ingest more players with more match history."
        )

    df_all = df_all.dropna(subset=["win"])
    df_all = df_all.sort_values("game_creation").reset_index(drop=True)

    FEATURE_COLS = [
        "win_rate_20",
        "avg_kda_20",
        "avg_cs_per_min_20",
        "avg_gold_per_min_20",
        "avg_kill_part_20",
        "win_streak",
        "death_rate_20",      # rolling avg deaths/game — tilting signal
        "vision_per_min_20",  # rolling vision habit
        "kda_std_10",         # KDA consistency — volatile players are riskier
        "cs_trend_10",        # improving farm trajectory
        "team_avg_win_rate_20",
        "team_avg_kda_20",
        "team_avg_cs_min_20",
        "team_gold_diff_prior",
        "patch_version_float",
        "role_encoded",
    ]

    available_cols = [c for c in FEATURE_COLS if c in df_all.columns]

    # --- Median imputation: compute on full labeled set, store for inference ---
    # Using fillna(0) causes train/test distribution skew.
    # Medians are stored in the artifact so predict_win applies the same fill.
    train_medians: dict[str, float] = {
        col: float(df_all[col].median()) for col in available_cols
    }
    for col in available_cols:
        df_all[col] = df_all[col].fillna(train_medians[col])

    X = df_all[available_cols].values
    y = df_all["win"].astype(int).values

    # Temporal split — never shuffle time-series data
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # Guard: test set must have both classes for a meaningful AUC
    if len(set(y_test)) < 2:
        raise InsufficientDataError(
            f"Test split (n={len(y_test)}) has only one class "
            f"(all {'wins' if y_test[0] == 1 else 'losses'}). "
            "Ingest more diverse match history to get a balanced test set."
        )

    # Baseline: Logistic Regression
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    lr = LogisticRegression(max_iter=500, random_state=42)
    lr.fit(X_train_s, y_train)
    lr_auc = roc_auc_score(y_test, lr.predict_proba(X_test_s)[:, 1])
    lr_acc = accuracy_score(y_test, lr.predict(X_test_s))

    # Production: XGBoost
    xgb = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    xgb.fit(X_train, y_train)
    xgb_auc = roc_auc_score(y_test, xgb.predict_proba(X_test)[:, 1])
    xgb_acc = accuracy_score(y_test, xgb.predict(X_test))

    logger.info("LogReg:  acc=%.3f  auc=%.3f", lr_acc, lr_auc)
    logger.info("XGBoost: acc=%.3f  auc=%.3f", xgb_acc, xgb_auc)

    # Save the better model (XGBoost wins ties)
    if xgb_auc >= lr_auc:
        best_model, best_scaler, best_type = xgb, None, "xgboost"
        best_auc, best_acc = xgb_auc, xgb_acc
    else:
        best_model, best_scaler, best_type = lr, scaler, "logistic"
        best_auc, best_acc = lr_auc, lr_acc

    # Feature importance
    if best_type == "xgboost":
        importances = best_model.feature_importances_
    else:
        importances = abs(best_model.coef_[0])

    top_factors = sorted(
        zip(available_cols, importances),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    trained_at = datetime.now(timezone.utc).isoformat()

    artifact = {
        "model":           best_model,
        "scaler":          best_scaler,
        "encoder":         None,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "model_type":      best_type,
        "trained_at":      trained_at,
        "n_samples":       len(X),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "metrics": {
            "accuracy": best_acc,
            "roc_auc":  best_auc,
            "n_train":  len(X_train),
            "n_test":   len(X_test),
        },
        "top_factors": [
            {"feature": f, "importance": round(float(i), 4)}
            for f, i in top_factors
        ],
    }

    path = ML_MODELS_DIR / "win_predictor.joblib"
    joblib.dump(artifact, path)

    # Write human-readable metadata sidecar (no sklearn objects — JSON-safe)
    meta = {
        "model_type":      best_type,
        "trained_at":      trained_at,
        "n_samples":       len(X),
        "n_train":         len(X_train),
        "n_test":          len(X_test),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "metrics": {
            "accuracy": round(best_acc, 4),
            "roc_auc":  round(best_auc, 4),
            "lr_auc":   round(lr_auc, 4),
            "xgb_auc":  round(xgb_auc, 4),
        },
        "top_factors": [
            {"feature": f, "importance": round(float(i), 4)}
            for f, i in top_factors
        ],
    }
    meta_path = ML_MODELS_DIR / "win_predictor_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Evict then re-cache so the in-process copy has version metadata too
    invalidate_model_cache("win_predictor")
    _model_cache["win_predictor"] = artifact
    logger.info("Saved win_predictor.joblib — %s  auc=%.3f sklearn=%s", best_type, best_auc, _SKLEARN_VERSION)

    return {
        "status":      "trained",
        "model_type":  best_type,
        "accuracy":    round(best_acc, 4),
        "roc_auc":     round(best_auc, 4),
        "n_train":     len(X_train),
        "n_test":      len(X_test),
        "top_factors": [
            {"feature": f, "importance": round(float(i), 4)}
            for f, i in top_factors
        ],
        "lr_auc":      round(lr_auc, 4),
        "xgb_auc":     round(xgb_auc, 4),
    }


# ---------------------------------------------------------------------------
# Function 5: predict_win
# ---------------------------------------------------------------------------


def predict_win(db: Session, puuid: str, match_id: str) -> dict:
    """
    Predict win probability for a player in a given match.

    Uses that player's rolling history before the match as features.
    Leakage guard: uses match game_creation as the before_ts cutoff.

    Confidence tiers:
        high   — >= 10 prior games
        medium — 5–9 prior games
        low    — < 5 prior games (returns win_probability=None)

    Returns:
        dict always (never raises ModelNotTrainedError to callers).
        model_trained=False if win_predictor has not been trained yet.
    """
    try:
        artifact = _load_model("win_predictor")
    except ModelNotTrainedError:
        return {
            "model_trained": False,
            "reason":        "Run POST /ai/train/win-prediction first.",
        }

    model      = artifact["model"]
    scaler     = artifact["scaler"]
    feat_cols  = artifact["feature_cols"]
    model_type = artifact["model_type"]
    # Use training medians for imputation — consistent with how the model was trained
    train_medians: dict[str, float] = artifact.get("train_medians", {})

    meta = db.execute(
        text("SELECT game_creation FROM matches WHERE match_id = :mid"),
        {"mid": match_id},
    ).mappings().first()

    if not meta:
        return {"error": "match_not_found", "match_id": match_id}

    rolling = get_rolling_features(db, puuid, meta["game_creation"])
    games   = rolling.get("games_in_window", 0)
    confidence = "high" if games >= 10 else "medium" if games >= 5 else "low"

    if games < 5:
        return {
            "puuid":           puuid,
            "match_id":        match_id,
            "model_trained":   True,
            "confidence":      "low",
            "games_in_window": games,
            "message":         "Fewer than 5 prior games. Prediction unreliable.",
            "win_probability": None,
        }

    # Build feature row — missing values filled with training medians (not 0)
    row = {
        col: rolling.get(col, train_medians.get(col, 0.0))
        for col in feat_cols
    }

    X_new = pd.DataFrame([row])[feat_cols].values

    if scaler is not None:
        X_new = scaler.transform(X_new)

    proba = float(model.predict_proba(X_new)[0][1])

    # Top contributing features
    if model_type == "xgboost":
        importances = model.feature_importances_
    else:
        importances = abs(model.coef_[0])

    top_factors = sorted(
        zip(feat_cols, importances),
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    return {
        "puuid":           puuid,
        "match_id":        match_id,
        "model_trained":   True,
        "win_probability": round(proba, 4),
        "confidence":      confidence,
        "games_in_window": games,
        "model_type":      model_type,
        "top_factors": [
            {
                "feature":   f,
                "direction": "positive" if proba > 0.5 else "negative",
            }
            for f, _ in top_factors
        ],
    }


# ---------------------------------------------------------------------------
# Function 6: train_kda_regressor
# ---------------------------------------------------------------------------

# Feature columns shared by both regression models.
# Identical to win_predictor FEATURE_COLS with win_rate_20 and win_streak
# removed: both encode match outcomes directly, which would leak the target
# distribution for KDA/CS regression.
_REGRESSION_FEATURE_COLS: list[str] = [
    "avg_kda_20",
    "avg_cs_per_min_20",
    "avg_gold_per_min_20",
    "avg_kill_part_20",
    "death_rate_20",
    "vision_per_min_20",
    "kda_std_10",
    "cs_trend_10",
    "team_avg_win_rate_20",
    "team_avg_kda_20",
    "team_avg_cs_min_20",
    "team_gold_diff_prior",
    "patch_version_float",
    "role_encoded",
]


def _train_regression(
    db: Session,
    target_col: str,
    artifact_name: str,
    target_sql_col: str,
) -> dict:
    """Shared training logic for KDA and CS/min regression models.

    Args:
        target_col:     Name of the target column in the assembled DataFrame
                        (e.g. ``"target_kda"`` or ``"target_cs_per_min"``).
        artifact_name:  Stem for the .joblib and _meta.json files
                        (e.g. ``"kda_regressor"``).
        target_sql_col: Column name in ``derived_metrics`` to use as the target
                        (e.g. ``"kda"`` or ``"cs_per_min"``).

    Returns:
        Training summary dict.

    Raises:
        InsufficientDataError: fewer than 100 labeled rows.
    """
    _t0 = time.time()
    df_all = get_all_rolling_features_bulk(db)
    logger.info("Bulk feature fetch: %.1f seconds", time.time() - _t0)

    # The bulk DF carries the current-match target as a raw (un-shifted) column.
    # Rename to the target_col name expected by downstream code.
    # The rolling feature columns (avg_kda_20, avg_cs_per_min_20, …) are
    # computed from prior games only via shift(1) — no leakage.
    if target_sql_col in df_all.columns:
        df_all = df_all.rename(columns={target_sql_col: target_col})

    df_all = df_all.sort_values("game_creation").reset_index(drop=True)

    if len(df_all) < 100:
        raise InsufficientDataError(
            f"Need 100+ labeled training rows for {artifact_name}. "
            f"Have {len(df_all)}. Ingest more players with more match history."
        )

    df_all = df_all.dropna(subset=[target_col])
    available_cols = [c for c in _REGRESSION_FEATURE_COLS if c in df_all.columns]

    train_medians: dict[str, float] = {
        col: float(df_all[col].median()) for col in available_cols
    }
    for col in available_cols:
        df_all[col] = df_all[col].fillna(train_medians[col])

    X = df_all[available_cols].values
    y = df_all[target_col].values.astype(float)

    # Temporal split — never shuffle time-series data
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # Baseline: Ridge (needs its own scaler — separate from every other model)
    ridge_scaler = StandardScaler()
    X_train_s = ridge_scaler.fit_transform(X_train)
    X_test_s  = ridge_scaler.transform(X_test)

    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_s, y_train)
    ridge_pred  = ridge.predict(X_test_s)
    ridge_rmse  = float(np.sqrt(mean_squared_error(y_test, ridge_pred)))
    ridge_mae   = float(mean_absolute_error(y_test, ridge_pred))
    ridge_r2    = float(r2_score(y_test, ridge_pred))

    # Production: XGBRegressor (tree-based; no scaler)
    xgb_reg = XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        verbosity=0,
    )
    xgb_reg.fit(X_train, y_train)
    xgb_pred = xgb_reg.predict(X_test)
    xgb_rmse = float(np.sqrt(mean_squared_error(y_test, xgb_pred)))
    xgb_mae  = float(mean_absolute_error(y_test, xgb_pred))
    xgb_r2   = float(r2_score(y_test, xgb_pred))

    logger.info("Ridge:   rmse=%.3f  mae=%.3f  r2=%.3f", ridge_rmse, ridge_mae, ridge_r2)
    logger.info("XGBoost: rmse=%.3f  mae=%.3f  r2=%.3f", xgb_rmse, xgb_mae, xgb_r2)

    # Save the better model by R² — XGBoost wins ties
    if xgb_r2 >= ridge_r2:
        best_model, best_scaler, best_type = xgb_reg, None, "xgboost"
        best_rmse, best_mae, best_r2 = xgb_rmse, xgb_mae, xgb_r2
    else:
        best_model, best_scaler, best_type = ridge, ridge_scaler, "ridge"
        best_rmse, best_mae, best_r2 = ridge_rmse, ridge_mae, ridge_r2

    trained_at = datetime.now(timezone.utc).isoformat()

    artifact = {
        "model":           best_model,
        "scaler":          best_scaler,
        "encoder":         None,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "model_type":      best_type,
        "trained_at":      trained_at,
        "n_samples":       len(X),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "metrics": {
            "rmse":    round(best_rmse, 4),
            "mae":     round(best_mae, 4),
            "r2":      round(best_r2, 4),
            "n_train": len(X_train),
            "n_test":  len(X_test),
        },
    }

    joblib_path = ML_MODELS_DIR / f"{artifact_name}.joblib"
    joblib.dump(artifact, joblib_path)

    meta = {
        "model_type":      best_type,
        "trained_at":      trained_at,
        "n_samples":       len(X),
        "n_train":         len(X_train),
        "n_test":          len(X_test),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "metrics": {
            "rmse":     round(best_rmse, 4),
            "mae":      round(best_mae, 4),
            "r2":       round(best_r2, 4),
            "ridge_r2": round(ridge_r2, 4),
            "xgb_r2":   round(xgb_r2, 4),
        },
    }
    meta_path = ML_MODELS_DIR / f"{artifact_name}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    invalidate_model_cache(artifact_name)
    _model_cache[artifact_name] = artifact
    logger.info(
        "Saved %s.joblib — %s  r2=%.3f sklearn=%s",
        artifact_name, best_type, best_r2, _SKLEARN_VERSION,
    )

    return {
        "status":     "trained",
        "model_type": best_type,
        "rmse":       round(best_rmse, 4),
        "mae":        round(best_mae, 4),
        "r2":         round(best_r2, 4),
        "n_train":    len(X_train),
        "n_test":     len(X_test),
        "ridge_r2":   round(ridge_r2, 4),
        "xgb_r2":     round(xgb_r2, 4),
    }


def train_kda_regressor(db: Session) -> dict:
    """
    Train KDA regression model on all ingested player match history.

    Target: ``derived_metrics.kda`` (float) — the actual KDA achieved in the
    match.  Features are rolling prior-game stats only; current-game outcomes
    (kills, deaths, assists, gold_earned, total_damage) are never included.

    Trains Ridge(alpha=1.0) as baseline and XGBRegressor as production model.
    Saves the better model (by R²) to ``kda_regressor.joblib`` plus a
    human-readable sidecar at ``kda_regressor_meta.json``.

    Data gate: raises InsufficientDataError if < 100 labeled rows.
    Temporal split: oldest 80% = train, newest 20% = test. Never shuffle.
    """
    return _train_regression(
        db,
        target_col="target_kda",
        artifact_name="kda_regressor",
        target_sql_col="kda",
    )


# ---------------------------------------------------------------------------
# Function 7: train_cs_regressor
# ---------------------------------------------------------------------------


def train_cs_regressor(db: Session) -> dict:
    """
    Train CS/min regression model on all ingested player match history.

    Target: ``derived_metrics.cs_per_min`` — the actual CS per minute achieved
    in the match.  Identical pipeline to ``train_kda_regressor`` with a
    separate scaler, separate artifact, and separate output files.

    Saves to ``cs_regressor.joblib`` and ``cs_regressor_meta.json``.

    Data gate: raises InsufficientDataError if < 100 labeled rows.
    Temporal split: oldest 80% = train, newest 20% = test. Never shuffle.
    """
    return _train_regression(
        db,
        target_col="target_cs_per_min",
        artifact_name="cs_regressor",
        target_sql_col="cs_per_min",
    )


# ---------------------------------------------------------------------------
# Function 8: predict_kda
# ---------------------------------------------------------------------------


def predict_kda(db: Session, puuid: str, match_id: str) -> dict:
    """
    Predict expected KDA for a player in a given match.

    Uses that player's rolling history before the match as features.
    Leakage guard: uses match game_creation as the before_ts cutoff so
    the target match is never part of the rolling window.

    Confidence tiers:
        high   — >= 10 prior games
        medium — 5–9 prior games
        low    — < 5 prior games (returns expected_kda=None)

    Returns:
        dict always (never raises ModelNotTrainedError to callers).
        model_trained=False if kda_regressor has not been trained yet.
    """
    try:
        artifact = _load_model("kda_regressor")
    except ModelNotTrainedError:
        return {
            "model_trained": False,
            "reason":        "Run POST /ai/train/kda-regression first.",
        }

    model      = artifact["model"]
    scaler     = artifact["scaler"]
    feat_cols  = artifact["feature_cols"]
    train_medians: dict[str, float] = artifact.get("train_medians", {})

    meta = db.execute(
        text("SELECT game_creation FROM matches WHERE match_id = :mid"),
        {"mid": match_id},
    ).mappings().first()

    if not meta:
        return {"error": "match_not_found", "match_id": match_id}

    rolling  = get_rolling_features(db, puuid, meta["game_creation"])
    games    = rolling.get("games_in_window", 0)
    confidence = "high" if games >= 10 else "medium" if games >= 5 else "low"

    if games < 5:
        return {
            "puuid":           puuid,
            "match_id":        match_id,
            "model_trained":   True,
            "confidence":      "low",
            "games_in_window": games,
            "message":         "Fewer than 5 prior games. Prediction unreliable.",
            "expected_kda":    None,
        }

    row   = {col: rolling.get(col, train_medians.get(col, 0.0)) for col in feat_cols}
    X_new = pd.DataFrame([row])[feat_cols].values

    if scaler is not None:
        X_new = scaler.transform(X_new)

    expected_kda = float(model.predict(X_new)[0])

    return {
        "puuid":           puuid,
        "match_id":        match_id,
        "model_trained":   True,
        "expected_kda":    round(max(expected_kda, 0.0), 3),
        "confidence":      confidence,
        "games_in_window": games,
        "model_type":      artifact["model_type"],
    }


# ---------------------------------------------------------------------------
# Function 9: predict_cs
# ---------------------------------------------------------------------------


def predict_cs(db: Session, puuid: str, match_id: str) -> dict:
    """
    Predict expected CS per minute for a player in a given match.

    Identical inference pattern to ``predict_kda`` using the separate
    ``cs_regressor.joblib`` artifact.

    Confidence tiers:
        high   — >= 10 prior games
        medium — 5–9 prior games
        low    — < 5 prior games (returns expected_cs_per_min=None)

    Returns:
        dict always (never raises ModelNotTrainedError to callers).
        model_trained=False if cs_regressor has not been trained yet.
    """
    try:
        artifact = _load_model("cs_regressor")
    except ModelNotTrainedError:
        return {
            "model_trained": False,
            "reason":        "Run POST /ai/train/cs-regression first.",
        }

    model      = artifact["model"]
    scaler     = artifact["scaler"]
    feat_cols  = artifact["feature_cols"]
    train_medians: dict[str, float] = artifact.get("train_medians", {})

    meta = db.execute(
        text("SELECT game_creation FROM matches WHERE match_id = :mid"),
        {"mid": match_id},
    ).mappings().first()

    if not meta:
        return {"error": "match_not_found", "match_id": match_id}

    rolling  = get_rolling_features(db, puuid, meta["game_creation"])
    games    = rolling.get("games_in_window", 0)
    confidence = "high" if games >= 10 else "medium" if games >= 5 else "low"

    if games < 5:
        return {
            "puuid":              puuid,
            "match_id":           match_id,
            "model_trained":      True,
            "confidence":         "low",
            "games_in_window":    games,
            "message":            "Fewer than 5 prior games. Prediction unreliable.",
            "expected_cs_per_min": None,
        }

    row   = {col: rolling.get(col, train_medians.get(col, 0.0)) for col in feat_cols}
    X_new = pd.DataFrame([row])[feat_cols].values

    if scaler is not None:
        X_new = scaler.transform(X_new)

    expected_cs = float(model.predict(X_new)[0])

    return {
        "puuid":               puuid,
        "match_id":            match_id,
        "model_trained":       True,
        "expected_cs_per_min": round(max(expected_cs, 0.0), 3),
        "confidence":          confidence,
        "games_in_window":     games,
        "model_type":          artifact["model_type"],
    }


# ---------------------------------------------------------------------------
# Function 12: train_earlygame_model
# ---------------------------------------------------------------------------


def train_earlygame_model(db: Session) -> dict:
    """
    Train an early-game win-prediction model from T=10 and T=15 minute
    timeline differentials.

    Features are team-level gold/XP/level/CS diffs and first-objective flags
    from ``TIMELINE_FEATURES``.  One row = one match (team 100 perspective).
    Target: ``team100_won`` (int 0/1) from ``team_objectives``.

    Model: LogisticRegression(max_iter=500) only — interpretable and sufficient
    at this scale.

    Data gate: raises InsufficientDataError if fewer than 50 matches have
    timeline frame data.
    Temporal split: oldest 80 % = train, newest 20 % = test. Never shuffle.

    Saves artifact to ``earlygame_predictor.joblib`` and a human-readable
    sidecar to ``earlygame_predictor_meta.json``.
    """
    # ------------------------------------------------------------------
    # Step 1 — Collect match_ids that have frame data, ordered temporally
    # ------------------------------------------------------------------
    match_sql = text("""
        SELECT DISTINCT tpf.match_id, m.game_creation
        FROM timeline_participant_frames tpf
        JOIN matches m ON m.match_id = tpf.match_id
        ORDER BY m.game_creation ASC
    """)
    match_rows = db.execute(match_sql).mappings().all()
    match_ids = [r["match_id"] for r in match_rows]
    game_creation_map: dict[str, int] = {r["match_id"]: r["game_creation"] for r in match_rows}

    if len(match_ids) < 50:
        raise InsufficientDataError(
            f"Need 50+ matches with timeline data for early-game model. "
            f"Have {len(match_ids)}. Ingest more matches with fetch_timeline=true."
        )

    # ------------------------------------------------------------------
    # Step 2 — Build feature DataFrame via get_timeline_features
    # ------------------------------------------------------------------
    _t0 = time.time()
    df = get_timeline_features(db, match_ids)
    logger.info("Timeline feature fetch: %.1f seconds", time.time() - _t0)

    if df.empty:
        raise InsufficientDataError(
            "get_timeline_features returned an empty DataFrame. "
            "Check that timeline_participant_frames has T=10 min frame data."
        )

    # Merge game_creation for temporal ordering, then sort
    df["game_creation"] = df["match_id"].map(game_creation_map)
    df = df.sort_values("game_creation").reset_index(drop=True)
    df = df.dropna(subset=["team100_won"])

    if len(df) < 50:
        raise InsufficientDataError(
            f"Need 50+ labeled rows after filtering. Have {len(df)}. "
            "Ingest more matches that have team_objectives data."
        )

    # ------------------------------------------------------------------
    # Step 3 — Feature / target split
    # ------------------------------------------------------------------
    available_cols = [c for c in TIMELINE_FEATURES if c in df.columns]
    # get_timeline_features already applied _impute_medians; store medians
    # for single-match inference fallback (single-row imputation fails on NaN)
    train_medians: dict[str, float] = {
        col: float(df[col].median()) for col in available_cols
    }

    X = df[available_cols].values
    y = df["team100_won"].astype(int).values

    # Temporal split — never shuffle time-series data
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    if len(set(y_test)) < 2:
        raise InsufficientDataError(
            f"Test split (n={len(y_test)}) has only one class. "
            "Ingest more diverse match history."
        )

    # ------------------------------------------------------------------
    # Step 4 — Logistic Regression (interpretable; sufficient at this scale)
    # ------------------------------------------------------------------
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    lr = LogisticRegression(max_iter=500, random_state=42)
    lr.fit(X_train_s, y_train)
    lr_auc = roc_auc_score(y_test, lr.predict_proba(X_test_s)[:, 1])
    lr_acc = accuracy_score(y_test, lr.predict(X_test_s))

    logger.info("EarlyGame LogReg: acc=%.3f  auc=%.3f", lr_acc, lr_auc)

    importances = list(abs(lr.coef_[0]))
    top_factors = sorted(
        zip(available_cols, importances),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    trained_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Step 5 — Save artifact and metadata sidecar
    # ------------------------------------------------------------------
    artifact = {
        "model":           lr,
        "scaler":          scaler,
        "encoder":         None,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "model_type":      "logistic",
        "trained_at":      trained_at,
        "n_samples":       len(X),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "metrics": {
            "accuracy": lr_acc,
            "roc_auc":  lr_auc,
            "n_train":  len(X_train),
            "n_test":   len(X_test),
        },
        "top_factors": [
            {"feature": f, "importance": round(float(i), 4)}
            for f, i in top_factors
        ],
    }

    path = ML_MODELS_DIR / "earlygame_predictor.joblib"
    joblib.dump(artifact, path)

    meta = {
        "model_type":      "logistic",
        "trained_at":      trained_at,
        "n_samples":       len(X),
        "n_train":         len(X_train),
        "n_test":          len(X_test),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "metrics": {
            "accuracy": round(lr_acc, 4),
            "roc_auc":  round(lr_auc, 4),
        },
        "top_factors": [
            {"feature": f, "importance": round(float(i), 4)}
            for f, i in top_factors
        ],
    }
    meta_path = ML_MODELS_DIR / "earlygame_predictor_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    invalidate_model_cache("earlygame_predictor")
    _model_cache["earlygame_predictor"] = artifact
    logger.info(
        "Saved earlygame_predictor.joblib — acc=%.3f  auc=%.3f sklearn=%s",
        lr_acc, lr_auc, _SKLEARN_VERSION,
    )

    return {
        "status":     "trained",
        "model_type": "logistic",
        "accuracy":   round(lr_acc, 4),
        "roc_auc":    round(lr_auc, 4),
        "n_train":    len(X_train),
        "n_test":     len(X_test),
        "top_factors": [
            {"feature": f, "importance": round(float(i), 4)}
            for f, i in top_factors
        ],
    }


# ---------------------------------------------------------------------------
# Function 13: predict_earlygame
# ---------------------------------------------------------------------------


def predict_earlygame(db: Session, match_id: str) -> dict:
    """
    Predict the probability that team 100 wins based on T=10/15 min
    timeline differentials.

    Calls ``get_timeline_features`` for the single match.  If no frame data
    exists (match was not ingested with ``fetch_timeline=true``) returns an
    error dict instead of raising.

    Returns:
        dict always (never raises ModelNotTrainedError to callers).
        model_trained=False if earlygame_predictor has not been trained yet.
        error="no_timeline_data" if the match has no frame data.
    """
    try:
        artifact = _load_model("earlygame_predictor")
    except ModelNotTrainedError:
        return {
            "model_trained": False,
            "reason": "Run POST /ai/train/early-game first.",
        }

    model       = artifact["model"]
    scaler      = artifact["scaler"]
    feat_cols   = artifact["feature_cols"]
    train_medians: dict[str, float] = artifact.get("train_medians", {})

    df = get_timeline_features(db, [match_id])

    if df.empty:
        return {
            "model_trained": True,
            "error":   "no_timeline_data",
            "message": "Match was not ingested with fetch_timeline=true",
        }

    row_data = df.iloc[0]

    # Use train_medians as fallback for any NaN that single-row imputation
    # cannot fix (e.g. missing T=15min frame data).
    row: dict[str, float] = {}
    for col in feat_cols:
        val = row_data.get(col, np.nan) if hasattr(row_data, "get") else getattr(row_data, col, np.nan)
        if pd.isna(val):
            val = float(train_medians.get(col, 0.0))
        row[col] = float(val)

    X_new = pd.DataFrame([row])[feat_cols].values
    if scaler is not None:
        X_new = scaler.transform(X_new)

    proba = float(model.predict_proba(X_new)[0][1])

    features_snapshot = {
        col: round(row[col], 2) for col in feat_cols
    }

    return {
        "match_id":                 match_id,
        "model_trained":            True,
        "team_100_win_probability": round(proba, 4),
        "features":                 features_snapshot,
        "model_type":               artifact["model_type"],
    }


# ---------------------------------------------------------------------------
# Function 10: get_model_status
# ---------------------------------------------------------------------------


def get_model_status() -> dict:
    """
    Return training status for all models.
    Used by GET /ai/models/status endpoint.
    Does not require a DB session.
    """
    models = {
        "playstyle_kmeans":    "playstyle_kmeans.joblib",
        "win_predictor":       "win_predictor.joblib",
        "kda_regressor":       "kda_regressor.joblib",
        "cs_regressor":        "cs_regressor.joblib",
        "earlygame_predictor": "earlygame_predictor.joblib",
    }
    status: dict[str, dict] = {}
    for name, filename in models.items():
        path = ML_MODELS_DIR / filename
        if path.exists():
            try:
                artifact = _load_model(name)
                status[name] = {
                    "trained":    True,
                    "trained_at": artifact.get("trained_at"),
                    "n_samples":  artifact.get("n_samples"),
                    "metrics":    artifact.get("metrics"),
                    "model_type": artifact.get("model_type"),
                }
            except Exception as exc:
                status[name] = {"trained": False, "error": str(exc)}
        else:
            status[name] = {
                "trained": False,
                "reason":  f"POST /ai/train/{_route_slug(name)}",
            }
    return status


# ---------------------------------------------------------------------------
# Function 11: run_win_prediction_backtest
# ---------------------------------------------------------------------------


def run_win_prediction_backtest(db: Session, n_matches: int = 50) -> dict:
    """
    Evaluate the trained win-prediction model against held-out historical matches.

    Queries the most recent ``n_matches`` ranked matches for ingested players,
    runs ``predict_win()`` for each participant (leakage guard is built into
    ``predict_win`` via the ``game_creation`` cutoff), then compares predicted
    probability to the actual win/loss stored in ``participant_stats``.

    Only medium- and high-confidence predictions are included in the results.
    Low-confidence predictions (< 5 prior games) are skipped because the model
    itself flags them as unreliable.

    Brier score: mean((predicted_prob - actual_outcome)²)
        0.0 = perfect, 0.25 = random baseline (50/50 coin flip).

    Args:
        n_matches: Maximum number of recent matches to evaluate against.
                   Actual result set may be smaller after skipping low-confidence
                   and model-not-trained rows.

    Returns:
        dict with keys:
            model_trained (bool)
            summary       (accuracy, brier_score, etc.)
            calibration_buckets (10 %-wide buckets of predicted prob vs actual WR)
            match_results (per-participant prediction detail)

        Returns {"model_trained": False, ...} immediately if the model has
        not been trained yet.
    """
    # Fast-fail if model is not trained
    try:
        _load_model("win_predictor")
    except ModelNotTrainedError as exc:
        return {
            "model_trained": False,
            "reason": str(exc),
        }

    # ------------------------------------------------------------------
    # Fetch the most recent n_matches ranked matches for ingested players
    # ------------------------------------------------------------------
    matches_sql = text("""
        SELECT DISTINCT ps.match_id, m.game_creation
        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN matches m          ON m.match_id = ps.match_id
        JOIN derived_metrics dm ON dm.puuid = p.puuid AND dm.match_id = ps.match_id
        WHERE m.queue_id = 420
        ORDER BY m.game_creation DESC
        LIMIT :n_matches
    """)
    match_rows = db.execute(matches_sql, {"n_matches": n_matches}).mappings().all()

    if not match_rows:
        return {
            "model_trained": True,
            "summary": {
                "total": 0,
                "correct": 0,
                "accuracy": None,
                "mean_predicted_prob": None,
                "actual_win_rate": None,
                "brier_score": None,
            },
            "calibration_buckets": [],
            "match_results": [],
        }

    # Fetch actual outcomes for all participants in those matches
    match_id_list = [r["match_id"] for r in match_rows]
    outcomes_sql = text("""
        SELECT p.puuid, ps.match_id, ps.win
        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN derived_metrics dm ON dm.puuid = p.puuid AND dm.match_id = ps.match_id
        WHERE ps.match_id = ANY(:match_ids)
    """)
    outcome_rows = db.execute(outcomes_sql, {"match_ids": match_id_list}).mappings().all()

    # Build lookup: (match_id, puuid) → actual win (int)
    actuals: dict[tuple[str, str], int] = {
        (r["match_id"], r["puuid"]): int(r["win"]) if r["win"] is not None else -1
        for r in outcome_rows
    }

    # ------------------------------------------------------------------
    # Run predict_win for each (match_id, puuid) pair
    # ------------------------------------------------------------------
    match_results: list[dict] = []

    for mr in match_rows:
        mid = mr["match_id"]
        # All puuids active in this match (intersection with our actuals lookup)
        participants = [
            puuid for (m, puuid) in actuals if m == mid
        ]
        for puuid in participants:
            actual_win = actuals.get((mid, puuid), -1)
            if actual_win == -1:
                continue  # no outcome data — skip

            result = predict_win(db, puuid, mid)

            # Skip if model not trained or low confidence
            if not result.get("model_trained", False):
                continue
            if result.get("confidence") == "low":
                continue
            predicted_prob = result.get("win_probability")
            if predicted_prob is None:
                continue

            predicted_win = 1 if predicted_prob >= 0.5 else 0
            correct = predicted_win == actual_win

            match_results.append({
                "match_id":       mid,
                "puuid":          puuid,
                "predicted_prob": round(float(predicted_prob), 4),
                "actual_win":     actual_win,
                "correct":        correct,
                "confidence":     result.get("confidence"),
            })

    if not match_results:
        return {
            "model_trained": True,
            "summary": {
                "total": 0,
                "correct": 0,
                "accuracy": None,
                "mean_predicted_prob": None,
                "actual_win_rate": None,
                "brier_score": None,
            },
            "calibration_buckets": [],
            "match_results": [],
        }

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    total   = len(match_results)
    correct = sum(1 for r in match_results if r["correct"])
    probs   = [r["predicted_prob"] for r in match_results]
    wins    = [r["actual_win"]     for r in match_results]

    accuracy          = round(correct / total, 4)
    mean_predicted    = round(float(np.mean(probs)), 4)
    actual_win_rate   = round(float(np.mean(wins)), 4)
    brier_score       = round(
        float(np.mean([(p - a) ** 2 for p, a in zip(probs, wins)])), 4
    )

    # ------------------------------------------------------------------
    # Calibration buckets: 10 %-wide bins of predicted probability
    # ------------------------------------------------------------------
    bucket_edges = [(i / 10, (i + 1) / 10) for i in range(10)]
    calibration_buckets: list[dict] = []

    for lo, hi in bucket_edges:
        # Right-inclusive on the last bucket to capture exactly 1.0
        in_bucket = [
            r for r in match_results
            if (lo <= r["predicted_prob"] < hi)
            or (hi == 1.0 and r["predicted_prob"] == 1.0)
        ]
        n = len(in_bucket)
        bucket_wr = round(float(np.mean([r["actual_win"] for r in in_bucket])), 4) if n > 0 else None
        pct_lo = int(lo * 100)
        pct_hi = int(hi * 100)
        calibration_buckets.append({
            "bucket":          f"{pct_lo}-{pct_hi}%",
            "predicted_range": [lo, hi],
            "n_matches":       n,
            "actual_win_rate": bucket_wr,
        })

    return {
        "model_trained": True,
        "summary": {
            "total":              total,
            "correct":            correct,
            "accuracy":           accuracy,
            "mean_predicted_prob": mean_predicted,
            "actual_win_rate":    actual_win_rate,
            "brier_score":        brier_score,
        },
        "calibration_buckets": calibration_buckets,
        "match_results":       match_results,
    }
