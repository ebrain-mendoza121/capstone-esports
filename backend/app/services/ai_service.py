from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Heavy ML dependencies are loaded lazily on first use to avoid importing
# ~400 MB of numpy/pandas/sklearn/xgboost at app startup.
# Call _load_ml() at the top of any function that uses these libraries.
# ---------------------------------------------------------------------------
_ML_LOADED: bool = False

# Module-level placeholders — populated by _load_ml() on first call.
np = None  # type: ignore[assignment]
pd = None  # type: ignore[assignment]
joblib = None  # type: ignore[assignment]
KMeans = None  # type: ignore[assignment]
LogisticRegression = None  # type: ignore[assignment]
Ridge = None  # type: ignore[assignment]
StandardScaler = None  # type: ignore[assignment]
accuracy_score = None  # type: ignore[assignment]
mean_absolute_error = None  # type: ignore[assignment]
mean_squared_error = None  # type: ignore[assignment]
r2_score = None  # type: ignore[assignment]
roc_auc_score = None  # type: ignore[assignment]
silhouette_score = None  # type: ignore[assignment]
XGBClassifier = None  # type: ignore[assignment]
XGBRegressor = None  # type: ignore[assignment]
_SKLEARN_VERSION: str = "unknown"
_XGBOOST_VERSION: str = "unknown"


def _load_ml() -> None:
    """Import heavy ML libraries once and bind them as module globals."""
    global _ML_LOADED, np, pd, joblib
    global KMeans, LogisticRegression, Ridge, StandardScaler
    global accuracy_score, mean_absolute_error, mean_squared_error
    global r2_score, roc_auc_score, silhouette_score
    global XGBClassifier, XGBRegressor
    global _SKLEARN_VERSION, _XGBOOST_VERSION

    if _ML_LOADED:
        return

    import numpy as _np
    import pandas as _pd
    import joblib as _jb
    import sklearn as _sk
    import xgboost as _xgb_mod
    from sklearn.cluster import KMeans as _KM
    from sklearn.linear_model import LogisticRegression as _LR, Ridge as _Ri
    from sklearn.metrics import (
        accuracy_score as _acc,
        mean_absolute_error as _mae,
        mean_squared_error as _mse,
        r2_score as _r2,
        roc_auc_score as _roc,
        silhouette_score as _sil,
    )
    from sklearn.preprocessing import StandardScaler as _SS
    from xgboost import XGBClassifier as _XGBc, XGBRegressor as _XGBr

    np = _np
    pd = _pd
    joblib = _jb
    KMeans = _KM
    LogisticRegression = _LR
    Ridge = _Ri
    StandardScaler = _SS
    accuracy_score = _acc
    mean_absolute_error = _mae
    mean_squared_error = _mse
    r2_score = _r2
    roc_auc_score = _roc
    silhouette_score = _sil
    XGBClassifier = _XGBc
    XGBRegressor = _XGBr
    _SKLEARN_VERSION = _sk.__version__
    _XGBOOST_VERSION = _xgb_mod.__version__
    _ML_LOADED = True

from app.services.feature_extractor import (
    CLUSTERING_FEATURES,
    ROLE_ENCODING,
    ROLLING_FEATURES,
    TIMELINE_FEATURES,
    get_all_rolling_features_bulk,
    get_all_timeline_features_bulk,
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
    "champion_clusters":   "champion-clusters",
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


def _auto_label_clusters(centroid_df) -> dict[int, str]:
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
    _load_ml()
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
    _load_ml()
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
    _load_ml()
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

    Uses Bayesian-smoothed win rate + role-aware KDA/CS scoring +
    playstyle-cluster affinity boost.  No ML model required — pure SQL
    aggregation + Python scoring.

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

    # --- Playstyle affinity: boost champions that match the player's cluster ---
    # Maps archetype label → roles that naturally fit that playstyle.
    # Affinity boost is added to final composite score (+0.08 max).
    _PLAYSTYLE_ROLE_AFFINITY: dict[str, list[str]] = {
        "carry":           ["BOTTOM", "MIDDLE"],
        "skirmisher":      ["JUNGLE", "TOP"],
        "support_utility": ["UTILITY", "SUPPORT"],
        "farm_efficiency": ["BOTTOM", "MIDDLE", "TOP"],
    }
    player_playstyle: str = "unknown"
    try:
        ps = get_player_playstyle(db, puuid)
        player_playstyle = ps.get("playstyle_label", "unknown")
    except Exception:
        pass  # playstyle model not trained — affinity boost skipped
    affinity_roles: list[str] = _PLAYSTYLE_ROLE_AFFINITY.get(player_playstyle, [])
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

    # Resolve champion names from the module-level DDragon cache.
    # The cache is populated at server startup via the lifespan preload in main.py.
    # Sync-safe: reads the already-populated dict directly without awaiting.
    from app.services import ddragon as _ddragon

    def get_champion_name(cid: int) -> Optional[str]:
        return _ddragon._champion_map.get(cid)

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

        # --- KDA: role-aware ceiling — supports cap at 3.5, carries at 8.0 ---
        _KDA_CAP_BY_ROLE: dict[str, float] = {
            "BOTTOM":  8.0,
            "MIDDLE":  8.0,
            "TOP":     6.0,
            "JUNGLE":  6.0,
            "UTILITY": 3.5,
            "SUPPORT": 3.5,
        }
        role_str = str(row["role"]).upper() if row["role"] is not None else ""
        kda_cap = _KDA_CAP_BY_ROLE.get(role_str, 6.0)
        norm_kda = min(float(row["avg_kda"]) / kda_cap, 1.0)

        # --- CS: role-aware cap so utility roles aren't penalized ---
        cs_cap = _CS_CAP_BY_ROLE.get(role_str, 8.0)
        norm_cs = min(float(row["avg_cs_per_min"]) / cs_cap, 1.0)

        # --- Experience: log-scale capped at reference (avoids one-trick inflation) ---
        exp_weight = math.log1p(min(games, EXP_REFERENCE)) / math.log1p(EXP_REFERENCE)

        # --- Recency: exponential decay. Champions played recently score higher. ---
        last_ts = float(row.get("last_played_ts") or 0)
        age_ms = max(now_ms - last_ts, 0.0)
        recency_weight = math.exp(-age_ms / _RECENCY_HALF_LIFE_MS) if last_ts > 0 else 0.5

        # --- Playstyle affinity boost: +0.08 when role matches player's cluster ---
        affinity_boost = 0.08 if role_str in affinity_roles else 0.0
        playstyle_match = role_str in affinity_roles

        # --- Final composite score (weights sum to 1.0 before affinity) ---
        score = (
            smoothed_wr      * 0.38
            + norm_kda       * 0.22
            + norm_cs        * 0.18
            + exp_weight     * 0.12
            + recency_weight * 0.10
            + affinity_boost
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
            "playstyle_match":   playstyle_match,
            "player_playstyle":  player_playstyle,
            "score_breakdown": {
                "win_rate":        round(smoothed_wr * 0.38, 4),
                "kda":             round(norm_kda * 0.22, 4),
                "cs":              round(norm_cs * 0.18, 4),
                "experience":      round(exp_weight * 0.12, 4),
                "recency":         round(recency_weight * 0.10, 4),
                "playstyle_bonus": round(affinity_boost, 4),
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
    _load_ml()
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
        "avg_role_norm_kda_20",   # role-adjusted KDA z-score rolling average
        # Opponent team strength (tracked players on enemy team — NaN-imputed otherwise)
        "opp_avg_win_rate_20",
        "opp_avg_kda_20",
        "opp_avg_cs_min_20",
        # Differential features: team minus opponent rolling averages.
        # Relative strength is more predictive than absolute stats —
        # a +0.7 KDA edge over opponents matters more than KDA=3.5 alone.
        # NaN (stub opponents) imputed to 0.0 = no edge assumed.
        "win_rate_diff",
        "kda_diff",
        "cs_diff",
        "gold_diff_norm",
        # Blue side (team_id == 100): slight win-rate advantage in LoL
        # due to champion select order. Small but consistent signal.
        "blue_side",
    ]

    available_cols = [c for c in FEATURE_COLS if c in df_all.columns]

    # --- Median imputation: compute on full labeled set, store for inference ---
    # Using fillna(0) causes train/test distribution skew.
    # Medians are stored in the artifact so predict_win applies the same fill.
    # When a column is entirely NaN (e.g. opponent features when no tracked
    # opponents exist yet) we use a semantically correct neutral value from
    # _NEUTRAL_FALLBACKS rather than a blanket 0.0 which would bias the model
    # (opp_avg_win_rate_20=0.0 would mean "opponent wins 0 % of games").
    import pandas as _pd
    train_medians: dict[str, float] = {
        col: (m if _pd.notna(m := df_all[col].median()) else _NEUTRAL_FALLBACKS.get(col, 0.0))
        for col in available_cols
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
    _load_ml()
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
    "avg_role_norm_kda_20",   # role-adjusted KDA z-score — key signal for KDA regression
    # Opponent team strength
    "opp_avg_win_rate_20",
    "opp_avg_kda_20",
    "opp_avg_cs_min_20",
]

# Semantically correct neutral values for features that are all-NaN when no
# tracked opponents exist.  Used as fallback when column.median() is NaN.
#   opp_avg_win_rate_20 → 0.5   (unknown opponent assumed 50 % win rate)
#   opp_avg_kda_20      → 2.5   (≈ league-wide average KDA)
#   opp_avg_cs_min_20   → 7.0   (≈ league-wide average CS/min)
# All other all-NaN columns fall back to 0.0 (safe for z-score features etc.)
_NEUTRAL_FALLBACKS: dict[str, float] = {
    "opp_avg_win_rate_20": 0.5,
    "opp_avg_kda_20":      2.5,
    "opp_avg_cs_min_20":   7.0,
    # Differentials: 0.0 = no edge either way (safe neutral)
    "win_rate_diff":       0.0,
    "kda_diff":            0.0,
    "cs_diff":             0.0,
    "gold_diff_norm":      0.0,
    # Blue side: 0.5 = unknown side
    "blue_side":           0.5,
}


def _train_regression(
    db: Session,
    target_col: str,
    artifact_name: str,
    target_sql_col: str,
) -> dict:
    _load_ml()
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

    import pandas as _pd
    train_medians: dict[str, float] = {
        col: (m if _pd.notna(m := df_all[col].median()) else _NEUTRAL_FALLBACKS.get(col, 0.0))
        for col in available_cols
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
    _load_ml()
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
    _load_ml()
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
    _load_ml()
    """
    Train an early-game win-prediction model from T=10 and T=15 minute
    timeline differentials.

    Features are team-level gold/XP/level/CS diffs and first-objective flags
    from ``TIMELINE_FEATURES``.  One row = one match (team 100 perspective).
    Target: ``team100_won`` (int 0/1) from ``team_objectives``.

    Model: LogisticRegression(max_iter=500) only — interpretable and sufficient
    at this scale.  Coefficients are logged and stored in the artifact so
    they can be reported as a key finding.

    Data gate: raises InsufficientDataError if fewer than 50 matches have
    timeline frame data.
    Temporal split: oldest 80 % = train, newest 20 % = test. Never shuffle.

    Saves artifact to ``earlygame_predictor.joblib`` and a human-readable
    sidecar to ``earlygame_predictor_meta.json``.
    """
    # ------------------------------------------------------------------
    # Step 1 — Collect all timeline features in one call
    # ------------------------------------------------------------------
    _t0 = time.time()
    df = get_all_timeline_features_bulk(db)
    logger.info("Timeline feature fetch: %.1f seconds", time.time() - _t0)

    if len(df) < 50:
        raise InsufficientDataError(
            f"Need 50+ timeline matches. Have {len(df)}. "
            "Ingest more matches with fetch_timeline=true."
        )

    # ------------------------------------------------------------------
    # Step 2 — Attach game_creation for temporal ordering
    # ------------------------------------------------------------------
    gc_sql = text("""
        SELECT DISTINCT tpf.match_id, m.game_creation
        FROM timeline_participant_frames tpf
        JOIN matches m ON m.match_id = tpf.match_id
    """)
    gc_rows = db.execute(gc_sql).mappings().all()
    game_creation_map: dict[str, int] = {r["match_id"]: r["game_creation"] for r in gc_rows}

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
    train_medians: dict[str, float] = {
        col: float(df[col].median()) for col in available_cols
    }
    for col in available_cols:
        df[col] = df[col].fillna(train_medians[col])

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

    model = LogisticRegression(max_iter=500, random_state=42)
    model.fit(X_train_s, y_train)

    accuracy = accuracy_score(y_test, model.predict(X_test_s))
    roc_auc  = roc_auc_score(y_test, model.predict_proba(X_test_s)[:, 1])
    n_train, n_test = len(X_train), len(X_test)

    logger.info("EarlyGame LogReg: acc=%.3f  auc=%.3f", accuracy, roc_auc)

    # Log feature coefficients — key finding for the report
    for feat, coef in zip(available_cols, model.coef_[0]):
        logger.info("Feature %s: coefficient=%.4f", feat, coef)

    feature_coefficients = [
        {"feature": f, "coefficient": round(float(c), 4)}
        for f, c in zip(available_cols, model.coef_[0])
    ]

    trained_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Step 5 — Save artifact and metadata sidecar
    # ------------------------------------------------------------------
    artifact = {
        "model":           model,
        "scaler":          scaler,
        "encoder":         None,
        "feature_cols":    available_cols,
        "train_medians":   train_medians,
        "model_type":      "logistic",
        "trained_at":      trained_at,
        "n_samples":       len(df),
        "sklearn_version": _SKLEARN_VERSION,
        "xgboost_version": _XGBOOST_VERSION,
        "metrics": {
            "accuracy": accuracy,
            "roc_auc":  roc_auc,
            "n_train":  n_train,
            "n_test":   n_test,
        },
        "feature_coefficients": feature_coefficients,
    }

    path = ML_MODELS_DIR / "earlygame_predictor.joblib"
    joblib.dump(artifact, path)

    meta = {
        "model_type":           "logistic",
        "trained_at":           trained_at,
        "n_samples":            len(df),
        "n_train":              n_train,
        "n_test":               n_test,
        "sklearn_version":      _SKLEARN_VERSION,
        "xgboost_version":      _XGBOOST_VERSION,
        "feature_cols":         available_cols,
        "train_medians":        train_medians,
        "metrics": {
            "accuracy": round(accuracy, 4),
            "roc_auc":  round(roc_auc, 4),
        },
        "feature_coefficients": feature_coefficients,
    }
    meta_path = ML_MODELS_DIR / "earlygame_predictor_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    invalidate_model_cache("earlygame_predictor")
    _model_cache["earlygame_predictor"] = artifact
    logger.info(
        "Saved earlygame_predictor.joblib — acc=%.3f  auc=%.3f sklearn=%s",
        accuracy, roc_auc, _SKLEARN_VERSION,
    )

    return {
        "status":               "trained",
        "model_type":           "logistic",
        "accuracy":             round(accuracy, 4),
        "roc_auc":              round(roc_auc, 4),
        "n_train":              n_train,
        "n_test":               n_test,
        "feature_coefficients": feature_coefficients,
    }



# ---------------------------------------------------------------------------
# Function 13: predict_earlygame
# ---------------------------------------------------------------------------


def predict_earlygame(db: Session, match_id: str) -> dict:
    _load_ml()
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
            "message": "Match has no timeline frames. Ingest with fetch_timeline=true.",
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

    X_row_values = [row[col] for col in feat_cols]
    X_new = pd.DataFrame([row])[feat_cols].values
    if scaler is not None:
        X_new = scaler.transform(X_new)

    proba = float(model.predict_proba(X_new)[0][1])

    confidence = (
        "high"   if abs(proba - 0.5) > 0.15 else
        "medium" if abs(proba - 0.5) > 0.05 else
        "low"
    )

    return {
        "match_id":                 match_id,
        "model_trained":            True,
        "team_100_win_probability": round(proba, 4),
        "team_200_win_probability": round(1 - proba, 4),
        "prediction":               "team_100" if proba > 0.5 else "team_200",
        "confidence":               confidence,
        "features":                 {col: val for col, val in zip(feat_cols, X_row_values)},
        "model_trained_at":         artifact["trained_at"],
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
        "champion_clusters":   "champion_clusters.joblib",
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
    _load_ml()
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


# ---------------------------------------------------------------------------
# Function 12: train_champion_clusters
# ---------------------------------------------------------------------------


def train_champion_clusters(db: Session) -> dict:
    _load_ml()
    """
    Cluster champions by their aggregate stat profiles using KMeans.

    Features per champion (across all tracked matches):
      - avg_kda, avg_cs_per_min, avg_gold_per_min,
        avg_kill_participation, avg_vision_per_min,
        avg_damage_share, games_played

    Produces 4 clusters that roughly correspond to:
      farm-carry, skirmisher, utility/support, versatile

    The resulting artifact exposes ``get_champion_archetype(champion_id)``
    which the enhanced champion recommendations use to match player playstyle
    clusters to champion clusters.
    """
    # derived_metrics stores kda as a precomputed float — no need to
    # recalculate from kills/deaths/assists (those live in participant_stats).
    sql = text("""
        SELECT
            ps.champion_id,
            COUNT(*)                   AS games_played,
            AVG(dm.kda)                AS avg_kda,
            AVG(dm.cs_per_min)         AS avg_cs_per_min,
            AVG(dm.gold_per_min)       AS avg_gold_per_min,
            AVG(dm.kill_participation) AS avg_kill_part,
            AVG(dm.vision_per_min)     AS avg_vision,
            AVG(dm.damage_share)       AS avg_damage_share
        FROM participant_stats ps
        JOIN players p ON p.id = ps.player_id
        JOIN derived_metrics dm
          ON dm.match_id = ps.match_id AND dm.puuid = p.puuid
        WHERE ps.champion_id IS NOT NULL
        GROUP BY ps.champion_id
        HAVING COUNT(*) >= 3
    """)
    rows = db.execute(sql).mappings().all()
    if len(rows) < 8:
        raise InsufficientDataError(
            f"Need at least 8 distinct champions with 3+ games. Have {len(rows)}."
        )

    champ_feature_cols = [
        "avg_kda", "avg_cs_per_min", "avg_gold_per_min",
        "avg_kill_part", "avg_vision", "avg_damage_share",
    ]

    import pandas as _pd
    df = _pd.DataFrame([dict(r) for r in rows])
    df = df.dropna(subset=champ_feature_cols)

    if len(df) < 8:
        raise InsufficientDataError("Insufficient non-null champion data after cleaning.")

    X = df[champ_feature_cols].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(4, len(df))
    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    model.fit(X_scaled)

    df["cluster_id"] = model.labels_

    # Auto-label clusters by their dominant feature
    centroid_df = _pd.DataFrame(
        scaler.inverse_transform(model.cluster_centers_),
        columns=champ_feature_cols,
    )
    _CHAMP_ARCHETYPE_SIGNALS = [
        {"label": "farm_carry",   "primary": "avg_cs_per_min",   "secondary": "avg_gold_per_min"},
        {"label": "skirmisher",   "primary": "avg_kda",          "secondary": "avg_damage_share"},
        {"label": "utility",      "primary": "avg_vision",       "secondary": "avg_kill_part"},
        {"label": "versatile",    "primary": "avg_damage_share", "secondary": "avg_kda"},
    ]
    assigned: dict[int, str] = {}
    for sig in _CHAMP_ARCHETYPE_SIGNALS:
        scores = {}
        for cid in range(n_clusters):
            if cid in assigned.values():
                continue
            pri = float(centroid_df.at[cid, sig["primary"]]) if sig["primary"] in centroid_df.columns else 0.0
            sec = float(centroid_df.at[cid, sig["secondary"]]) if sig["secondary"] in centroid_df.columns else 0.0
            scores[cid] = pri * 3 + sec * 2
        if scores:
            best = max(scores, key=scores.get)
            assigned[best] = sig["label"]
    champion_cluster_labels = {
        int(cid): assigned.get(cid, f"cluster_{cid}")
        for cid in range(n_clusters)
    }

    # Build champion → cluster mapping
    champion_map: dict[int, dict] = {}
    for _, row in df.iterrows():
        cid = int(row["champion_id"])
        cluster = int(row["cluster_id"])
        champion_map[cid] = {
            "cluster_id":       cluster,
            "champion_archetype": champion_cluster_labels.get(cluster, f"cluster_{cluster}"),
            "games_played":     int(row["games_played"]),
            "avg_kda":          round(float(row["avg_kda"]), 3),
            "avg_cs_per_min":   round(float(row["avg_cs_per_min"]), 3),
        }

    sil = float(silhouette_score(X_scaled, model.labels_)) if len(set(model.labels_)) > 1 else 0.0
    trained_at = datetime.now(timezone.utc).isoformat()

    artifact = {
        "model":                model,
        "scaler":               scaler,
        "feature_cols":         champ_feature_cols,
        "cluster_labels":       champion_cluster_labels,
        "champion_map":         champion_map,
        "model_type":           "kmeans",
        "trained_at":           trained_at,
        "n_samples":            len(df),
        "sklearn_version":      _SKLEARN_VERSION,
        "metrics": {
            "silhouette_score": round(sil, 4),
            "n_clusters":       n_clusters,
            "n_champions":      len(df),
        },
    }

    path = ML_MODELS_DIR / "champion_clusters.joblib"
    joblib.dump(artifact, path)
    _model_cache["champion_clusters"] = artifact
    logger.info(
        "champion_clusters trained — %d champions, %d clusters, silhouette=%.3f",
        len(df), n_clusters, sil,
    )

    return {
        "status":           "trained",
        "n_champions":      len(df),
        "n_clusters":       n_clusters,
        "silhouette_score": round(sil, 4),
        "cluster_labels":   champion_cluster_labels,
        "trained_at":       trained_at,
    }


def get_champion_archetype(champion_id: int) -> Optional[str]:
    """
    Return the archetype label for a given champion_id.
    Returns None if champion_clusters has not been trained or champion unknown.
    """
    try:
        artifact = _load_model("champion_clusters")
        champion_map: dict = artifact.get("champion_map", {})
        entry = champion_map.get(int(champion_id))
        return entry["champion_archetype"] if entry else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Team composition analysis — used by /teams/build and /teams/matchup
# ---------------------------------------------------------------------------

# Playstyle → offensive profile mapping
_PLAYSTYLE_OFFENSE: dict[str, str] = {
    "carry":           "high_damage",
    "skirmisher":      "high_engage",
    "support_utility": "high_peel",
    "farm_efficiency": "high_scaling",
}

# Team DNA definitions: (label, emoji, tagline)
_TEAM_DNA_PROFILES: list[tuple] = [
    # condition fn receives playstyle_counts dict
    # order matters — first match wins
    ("Hyper Carry Squad",   "🔥", "Everyone wants kills. Snowball fast or lose."),
    ("Brawl Gang",          "⚔️",  "Always fighting, everywhere, all the time."),
    ("Protect the Carry",   "🛡️",  "Built to make one player untouchable."),
    ("The Farmers",         "🌾", "Outscale everything. Just don't fall behind early."),
    ("Glass Cannons",       "💥", "Massive damage, zero survivability."),
    ("Balanced Roster",     "⚖️",  "No obvious win condition — hard to read."),
]


def get_threat_weights(db: Session) -> dict:
    """
    Derive threat score weights from the trained win-prediction model's
    feature importances.  Falls back to hand-tuned defaults when the model
    is unavailable or its AUC is too low to be trusted (< 0.60).

    Returns a dict with keys:
        win_rate_weight   – multiplier applied to normalised win-rate  (default 4.0)
        kda_weight        – multiplier applied to normalised KDA        (default 4.0)
        source            – "model" | "default"
        model_auc         – AUC of the underlying model (None if default)
        feature_breakdown – full normalised importance per feature (or None)
    """
    DEFAULTS = {
        "win_rate_weight":   4.0,
        "kda_weight":        4.0,
        "source":            "default",
        "model_auc":         None,
        "feature_breakdown": None,
    }

    MIN_TRUSTED_AUC = 0.60   # below this, importances are noise
    BUDGET          = 8.0    # total pts available before confidence bonus

    try:
        artifact = _load_model("win_predictor")
    except Exception:
        return DEFAULTS

    model       = artifact.get("model")
    feature_cols = artifact.get("feature_cols", [])
    metrics     = artifact.get("metrics", {})
    model_auc   = metrics.get("roc_auc")

    if model is None or model_auc is None or model_auc < MIN_TRUSTED_AUC:
        result = dict(DEFAULTS)
        result["model_auc"] = model_auc
        return result

    # Pull raw importances from the trained model object
    try:
        raw = model.feature_importances_          # XGBoost / RandomForest
    except AttributeError:
        try:
            raw = abs(model.coef_[0])             # LogisticRegression
        except AttributeError:
            return dict(DEFAULTS) | {"model_auc": model_auc}

    total = sum(raw)
    if total == 0:
        return dict(DEFAULTS) | {"model_auc": model_auc}

    # Normalise so all importances sum to 1
    normalised = {col: float(imp) / total for col, imp in zip(feature_cols, raw)}

    # Map to threat score weights (scaled to BUDGET = 8 pts)
    win_rate_imp = normalised.get("win_rate_20", 0.0)
    kda_imp      = normalised.get("avg_kda_20",  0.0)

    # If both are zero (feature names differ), fall back to defaults
    if win_rate_imp == 0.0 and kda_imp == 0.0:
        return dict(DEFAULTS) | {"model_auc": model_auc, "feature_breakdown": normalised}

    win_rate_weight = round(win_rate_imp * BUDGET, 3)
    kda_weight      = round(kda_imp      * BUDGET, 3)

    return {
        "win_rate_weight":   win_rate_weight,
        "kda_weight":        kda_weight,
        "source":            "model",
        "model_auc":         round(model_auc, 4),
        "feature_breakdown": normalised,
    }


def _compute_threat_score(
    win_rate: float,
    kda: float,
    games: int,
    win_rate_weight: float = 4.0,
    kda_weight: float = 4.0,
) -> float:
    """
    0–10 threat score.

    Win rate and KDA are the primary contributors, weighted by either
    hand-tuned defaults (4 / 4) or importances extracted from the trained
    win-prediction model via get_threat_weights().

    Confidence bonus (up to 2 pts) rewards players with larger sample sizes
    so low-game-count stats don't inflate a threat score.

    Literary backing:
    - Win rate as the dominant weight mirrors Hollinger's PER and the
      Victory Contribution metric (Sharpe et al., 2026) which anchors
      individual stat weights to win-probability delta.
    - KDA normalisation by a ceiling (8) follows the percentile-scaling
      approach in PandaSkill (arXiv 2501.10049) to prevent outlier KDAs
      from dominating a composite.
    - Confidence bonus is a simplified Bayesian shrinkage term consistent
      with Miya (2024) Bayesian Performance Rating, which pulls low-sample
      estimates toward a prior rather than treating them at face value.
    """
    wr_score   = min(win_rate, 1.0) * win_rate_weight
    kda_score  = min(kda / 8.0, 1.0) * kda_weight
    confidence = min(games / 20.0, 1.0) * 2.0     # up to 2 pts for ≥ 20 games
    return round(wr_score + kda_score + confidence, 1)


def _team_dna(playstyle_labels: list[str]) -> dict:
    """
    Given the playstyle labels for up to 5 players, produce a team DNA block.
    Returns label, emoji, tagline, and a breakdown of archetypes present.
    """
    counts: dict[str, int] = {}
    for label in playstyle_labels:
        if label and label != "unknown" and label != "insufficient_data":
            counts[label] = counts.get(label, 0) + 1

    carry_n   = counts.get("carry", 0)
    skirmish_n = counts.get("skirmisher", 0)
    utility_n  = counts.get("support_utility", 0)
    farm_n     = counts.get("farm_efficiency", 0)
    total_known = sum(counts.values())

    # Pick DNA label
    if carry_n >= 3:
        label, emoji, tagline = _TEAM_DNA_PROFILES[0]
    elif skirmish_n >= 3:
        label, emoji, tagline = _TEAM_DNA_PROFILES[1]
    elif utility_n >= 2:
        label, emoji, tagline = _TEAM_DNA_PROFILES[2]
    elif farm_n >= 3:
        label, emoji, tagline = _TEAM_DNA_PROFILES[3]
    elif carry_n >= 2 and utility_n == 0 and farm_n == 0:
        label, emoji, tagline = _TEAM_DNA_PROFILES[4]
    else:
        label, emoji, tagline = _TEAM_DNA_PROFILES[5]

    return {
        "label":     label,
        "emoji":     emoji,
        "tagline":   tagline,
        "breakdown": counts,
        "players_classified": total_known,
    }


def analyze_team_composition(
    db: Session,
    player_stats: list[dict],
) -> dict:
    """
    Run AI analysis on a team of players.

    player_stats: list of stat dicts from riot_live_service.get_team_stats().
    Each dict must have: puuid, summoner_name, win_rate_20, avg_kda_20,
    avg_cs_per_min_20, games_in_window.

    Optional per-player keys (activate Phase-3 role-aware scoring):
      champion_id    — Riot numeric champion id
      champion_meta  — ChampionMeta dict from ddragon.get_champion_full_map()
      declared_role  — explicit role string for this draft slot
      avg_role_norm_kda_20 — rolling role-normalised KDA z-score (from
                             feature_extractor rolling window)

    Returns:
        team_dna          — archetype label + tagline
        threat_scores     — per-player 0–10 threat rating
        predicted_carry   — the player profile most likely to carry
        composition_archetype — Phase-3 comp style (present when champion
                                data is available for 3+ slots)
        role_fit_scores   — per-slot fit_score + fit_label (when
                            champion_meta and role are provided)
    """
    playstyle_labels: list[str] = []
    threat_scores: list[dict] = []
    carry_candidates: list[dict] = []

    # Phase-3 accumulation
    phase3_slots: list[dict] = []          # {champion_meta, role}
    role_fit_entries: list[dict] = []      # per-slot fit results

    # Pull model-backed weights once for the whole team.
    # Falls back to (4.0, 4.0) if the model is untrained or AUC < 0.60.
    weights = get_threat_weights(db)
    wr_w    = weights["win_rate_weight"]
    kda_w   = weights["kda_weight"]
    weight_source = weights["source"]       # "model" or "default"

    for p in player_stats:
        puuid  = p.get("puuid") or ""
        name   = p.get("summoner_name", "Unknown")
        wr     = float(p.get("win_rate_20")       or 0.5)
        kda    = float(p.get("avg_kda_20")        or 2.5)
        cs     = float(p.get("avg_cs_per_min_20") or 7.0)
        games  = int(p.get("games_in_window")     or 0)
        role   = str(p.get("declared_role") or p.get("primary_role") or "")

        # --- Phase-3: use role-normalised KDA as primary ranking signal when
        #     role is declared.  Falls back to raw avg_kda_20. ---
        role_norm_kda = p.get("avg_role_norm_kda_20")
        effective_kda = (
            float(role_norm_kda) + 2.5   # shift z-score to positive domain
            if role and role_norm_kda is not None
            else kda
        )

        # --- Playstyle from AI model ---
        ps_label = "unknown"
        if puuid:
            try:
                ps_result = get_player_playstyle(db, puuid)
                ps_label  = ps_result.get("playstyle_label", "unknown")
            except Exception:
                pass
        playstyle_labels.append(ps_label)

        # --- Phase-3: champion role fit ---
        champion_meta = p.get("champion_meta")
        fit_result: dict = {}
        if champion_meta and role:
            fit_result = analyze_role_champion_fit(champion_meta, role)
            role_fit_entries.append({
                "summoner_name": name,
                "champion_id":   champion_meta.get("id"),
                "champion_name": champion_meta.get("name"),
                "role":          role,
                **fit_result,
            })
            phase3_slots.append({"champion_meta": champion_meta, "role": role})
        elif champion_meta:
            phase3_slots.append({"champion_meta": champion_meta, "role": ""})

        # --- Threat score (effective KDA incorporates role-norm signal) ---
        threat = _compute_threat_score(wr, effective_kda, games, wr_w, kda_w)
        threat_entry: dict = {
            "summoner_name":  name,
            "threat_score":   threat,
            "role":           role or None,
            "playstyle":      ps_label,
            "win_rate_20":    round(wr, 3),
            "avg_kda_20":     round(kda, 3),
            "games":          games,
            "weight_source":  weight_source,
        }
        if fit_result:
            threat_entry["role_fit_score"] = fit_result["fit_score"]
            threat_entry["role_fit_label"] = fit_result["fit_label"]
        if role_norm_kda is not None and role:
            threat_entry["avg_role_norm_kda_20"] = round(float(role_norm_kda), 3)
            threat_entry["kda_signal"] = "role_normalised"
        threat_scores.append(threat_entry)

        # --- Carry score: when role signal is available, weight it higher ---
        carry_score = (
            min(wr, 1.0)                   * 0.40
            + min(effective_kda / 8.0, 1.0) * 0.35
            + min(cs / 9.0, 1.0)            * 0.25
        )
        # Boost carry score for native-fit carries; penalise off-meta
        if fit_result:
            carry_score += (fit_result["fit_score"] - 0.5) * 0.05
        carry_candidates.append({
            "summoner_name":     name,
            "carry_score":       round(carry_score, 4),
            "win_rate_20":       round(wr, 3),
            "avg_kda_20":        round(kda, 3),
            "avg_cs_per_min_20": round(cs, 3),
            "role":              role or None,
            "playstyle":         ps_label,
        })

    # Sort by threat descending
    threat_scores.sort(key=lambda x: x["threat_score"], reverse=True)

    # Predicted carry = highest carry score
    predicted_carry = max(carry_candidates, key=lambda x: x["carry_score"]) if carry_candidates else None

    # --- Phase-3: composition archetype (requires 3+ slots with champion data) ---
    comp_archetype: Optional[dict] = None
    if len(phase3_slots) >= 3:
        comp_archetype = score_composition_archetype(phase3_slots)

    # Build team_dna; if composition archetype is available, incorporate its
    # signal into the tagline / breakdown.
    dna = _team_dna(playstyle_labels)
    if comp_archetype:
        dna["composition_archetype"]  = comp_archetype["archetype"]
        dna["composition_description"] = comp_archetype["description"]
        dna["composition_tag_counts"] = comp_archetype["tag_counts"]
        dna["role_fit_avg"]           = comp_archetype["role_fit_avg"]

    result: dict = {
        "team_dna":             dna,
        "threat_scores":        threat_scores,
        "predicted_carry":      predicted_carry,
        "threat_weight_source": weight_source,
        "threat_weights": {
            "win_rate_weight": wr_w,
            "kda_weight":      kda_w,
            "model_auc":       weights.get("model_auc"),
        },
    }
    if role_fit_entries:
        result["role_fit_scores"] = role_fit_entries
    if comp_archetype:
        result["composition_archetype"] = comp_archetype

    return result


def role_matchup_breakdown(
    blue_stats: list[dict],
    red_stats: list[dict],
) -> list[dict]:
    """
    Head-to-head per-role comparison for a matchup.

    Priority for role resolution (highest → lowest):
      1. declared_role  — explicitly set by the caller via request body
      2. primary_role   — most common role from DB/live stats
      3. Unmatched      — shown as "UNASSIGNED" if no role info at all

    Players are matched across teams by their resolved role.  If both
    teams have a player for the same role, they get a head-to-head card.
    Players whose role doesn't match anyone on the other side appear as
    "No opponent" entries so the caller always gets the full picture.

    Phase-4 enhancements (activated when avg_role_norm_kda_20 is present):
      - KDA comparison uses the role-normalised z-score so a 3.0 KDA Support
        and a 3.0 KDA ADC are not treated as equivalent.
      - Each card gains a ``role_context`` block with per-side σ descriptions,
        e.g. "Blue TOP is 0.8 σ above average KDA for TOP laners".
    """
    _ROLE_ORDER = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

    def _resolve_role(p: dict) -> str:
        return (
            str(p.get("declared_role") or "").upper()
            or str(p.get("primary_role") or "").upper()
            or "UNASSIGNED"
        )

    # --- Phase-4 helpers ---

    def _sigma_phrase(z: float) -> str:
        """Convert a KDA z-score to a plain-English performance phrase."""
        if z >= 1.5:
            return "significantly above average"
        if z >= 0.5:
            return "above average"
        if z >= -0.5:
            return "near average"
        if z >= -1.5:
            return "below average"
        return "significantly below average"

    def _role_context_note(side: str, role: str, name: Optional[str], z: float) -> str:
        """Build the interpretive sentence for one player's role-normalised KDA."""
        player_label = name or side
        direction = "above" if z >= 0 else "below"
        abs_z = abs(round(z, 2))
        phrase = _sigma_phrase(z)
        return (
            f"{player_label} ({side} {role}) is {phrase} — "
            f"{abs_z} σ {direction} average KDA for {role} laners"
        )

    def _edge(b_val: float, r_val: float, label: str) -> dict:
        if b_val == 0 and r_val == 0:
            return {"metric": label, "winner": "even", "blue": 0, "red": 0, "delta": 0, "pct_diff": 0}
        pct = abs(b_val - r_val) / max((b_val + r_val) / 2, 0.001) * 100
        if pct < 5:
            winner = "even"
        elif b_val > r_val:
            winner = "blue"
        else:
            winner = "red"
        return {
            "metric":   label,
            "winner":   winner,
            "blue":     round(b_val, 3),
            "red":      round(r_val, 3),
            "delta":    round(abs(b_val - r_val), 3),
            "pct_diff": round(pct, 1),
        }

    def _sigma_edge(b_z: float, r_z: float) -> dict:
        """
        Edge dict for role-normalised KDA (z-score scale).
        Uses a 0.2 σ dead-zone instead of a percentage band since z-scores
        are already on a common scale across all roles.
        """
        delta = b_z - r_z
        if abs(delta) < 0.2:
            winner = "even"
        elif delta > 0:
            winner = "blue"
        else:
            winner = "red"
        return {
            "metric":  "role_norm_kda",
            "winner":  winner,
            "blue":    round(b_z, 3),
            "red":     round(r_z, 3),
            "delta":   round(abs(delta), 3),
            # express advantage as σ difference — more meaningful than %
            "sigma_diff": round(abs(delta), 3),
        }

    def _matchup_card(role: str, b: Optional[dict], r: Optional[dict]) -> dict:
        """Build one role matchup card. b or r may be None if unmatched."""
        b_wr  = float(b.get("win_rate_20")       or 0.5) if b else 0.5
        r_wr  = float(r.get("win_rate_20")       or 0.5) if r else 0.5
        b_kda = float(b.get("avg_kda_20")        or 2.5) if b else 2.5
        r_kda = float(r.get("avg_kda_20")        or 2.5) if r else 2.5
        b_cs  = float(b.get("avg_cs_per_min_20") or 7.0) if b else 7.0
        r_cs  = float(r.get("avg_cs_per_min_20") or 7.0) if r else 7.0

        # Phase-4: role-normalised KDA z-score (None when not provided)
        b_znorm = b.get("avg_role_norm_kda_20") if b else None
        r_znorm = r.get("avg_role_norm_kda_20") if r else None
        b_znorm = float(b_znorm) if b_znorm is not None else None
        r_znorm = float(r_znorm) if r_znorm is not None else None

        # Use z-score for composite if both sides have it; fall back to raw KDA
        have_znorm = b_znorm is not None and r_znorm is not None
        if have_znorm:
            # Map z-score (-3..+3) to 0..1 probability-like scale for composite
            b_kda_norm = max(min((b_znorm + 3) / 6, 1.0), 0.0)
            r_kda_norm = max(min((r_znorm + 3) / 6, 1.0), 0.0)
        else:
            b_kda_norm = min(b_kda / 8, 1.0)
            r_kda_norm = min(r_kda / 8, 1.0)

        if b is None:
            overall_edge, edge_label = "red",  "RED — no opponent"
        elif r is None:
            overall_edge, edge_label = "blue", "BLUE — no opponent"
        else:
            b_composite = b_wr * 0.45 + b_kda_norm * 0.35 + min(b_cs / 9, 1) * 0.20
            r_composite = r_wr * 0.45 + r_kda_norm * 0.35 + min(r_cs / 9, 1) * 0.20
            pct = abs(b_composite - r_composite) / max((b_composite + r_composite) / 2, 0.001) * 100
            if pct < 4:
                overall_edge, edge_label = "even", "EVEN"
            elif b_composite > r_composite:
                overall_edge = "blue"
                edge_label   = f"BLUE +{round(pct, 0):.0f}%"
            else:
                overall_edge = "red"
                edge_label   = f"RED +{round(pct, 0):.0f}%"

        b_name = b.get("summoner_name") if b else None
        r_name = r.get("summoner_name") if r else None

        card: dict = {
            "role":         role,
            "blue_player":  b_name,
            "red_player":   r_name,
            "overall_edge": overall_edge,
            "edge_label":   edge_label,
            "win_rate":     _edge(b_wr, r_wr, "win_rate"),
            "kda":          _edge(b_kda, r_kda, "kda"),
            "cs_per_min":   _edge(b_cs, r_cs, "cs_per_min"),
        }

        # Phase-4: include role-normalised KDA comparison and context notes
        if have_znorm:
            card["role_norm_kda"] = _sigma_edge(b_znorm, r_znorm)
            card["kda_metric_used"] = "role_normalised"
            card["role_context"] = {
                "blue": _role_context_note("Blue", role, b_name, b_znorm),
                "red":  _role_context_note("Red",  role, r_name, r_znorm),
                "blue_sigma": round(b_znorm, 3),
                "red_sigma":  round(r_znorm, 3),
            }
        elif b_znorm is not None or r_znorm is not None:
            # Only one side has the value — still emit individual context notes
            card["kda_metric_used"] = "mixed"
            ctx: dict = {}
            if b_znorm is not None:
                ctx["blue"] = _role_context_note("Blue", role, b_name, b_znorm)
                ctx["blue_sigma"] = round(b_znorm, 3)
            if r_znorm is not None:
                ctx["red"] = _role_context_note("Red", role, r_name, r_znorm)
                ctx["red_sigma"] = round(r_znorm, 3)
            card["role_context"] = ctx
        else:
            card["kda_metric_used"] = "raw"

        return card

    # Build role → player dict for each team (last write wins if duplicate roles)
    blue_by_role: dict[str, dict] = {}
    for p in blue_stats:
        blue_by_role[_resolve_role(p)] = p

    red_by_role: dict[str, dict] = {}
    for p in red_stats:
        red_by_role[_resolve_role(p)] = p

    # All roles present across both teams
    all_roles = list(dict.fromkeys(
        _ROLE_ORDER
        + [r for r in blue_by_role if r not in _ROLE_ORDER]
        + [r for r in red_by_role  if r not in _ROLE_ORDER]
    ))

    matchups = []
    for role in all_roles:
        b = blue_by_role.get(role)
        r = red_by_role.get(role)
        if b is None and r is None:
            continue  # role not present on either team — skip
        matchups.append(_matchup_card(role, b, r))

    return matchups


# ---------------------------------------------------------------------------
# Function: train_matchup_predictor
# ---------------------------------------------------------------------------

def train_matchup_predictor(db: Session) -> dict:
    """
    Train a match-level win-prediction model using team differential features.

    Unlike train_win_predictor (per-player rows), this model trains on one
    row per match. Features are team100's aggregate rolling stats minus
    team200's — directly modelling relative team strength rather than
    individual player history in isolation.

    Why this achieves higher AUC:
        The per-player model sees [PlayerA stats] -> won? and [PlayerA stats]
        -> lost? with identical features, because the opponent is invisible.
        This model sees [TeamA avg] vs [TeamB avg] -> outcome, where the
        difference between the teams explains the outcome. That is a real
        causal signal the model can learn.

    Model saved to: ML_MODELS_DIR / matchup_predictor.joblib
    """
    from app.services.feature_extractor import get_match_differential_features_bulk

    df = get_match_differential_features_bulk(db)

    if len(df) < 50:
        raise InsufficientDataError(
            f"Need 50+ unique matches. Have {len(df)}. Ingest more players."
        )

    FEATURE_COLS = [
        # Team 100 absolute stats
        "t100_win_rate_20", "t100_avg_kda_20", "t100_avg_cs_per_min_20",
        "t100_avg_gold_per_min_20", "t100_vision_per_min_20",
        "t100_avg_kill_part_20", "t100_avg_role_norm_kda_20",
        # Team 200 absolute stats
        "t200_win_rate_20", "t200_avg_kda_20", "t200_avg_cs_per_min_20",
        "t200_avg_gold_per_min_20", "t200_vision_per_min_20",
        # Differentials — the primary new signal
        "win_rate_diff", "kda_diff", "cs_diff", "gold_diff",
        "vision_diff", "kill_part_diff", "role_norm_kda_diff",
        # Context
        "patch_version_float", "t100_tracked", "t200_tracked",
    ]

    available_cols = [c for c in FEATURE_COLS if c in df.columns]

    df = df.dropna(subset=["team100_won"]).sort_values("match_id").reset_index(drop=True)

    import pandas as _pd
    train_medians: dict[str, float] = {
        col: (m if _pd.notna(m := df[col].median()) else 0.0)
        for col in available_cols
    }
    for col in available_cols:
        df[col] = df[col].fillna(train_medians[col])

    X = df[available_cols].values
    y = df["team100_won"].astype(int).values

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    if len(set(y_test)) < 2:
        raise InsufficientDataError(
            "Test set has only one class. Ingest more diverse match history."
        )

    # Logistic baseline
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    lr = LogisticRegression(max_iter=500, random_state=42)
    lr.fit(X_train_s, y_train)
    lr_auc = roc_auc_score(y_test, lr.predict_proba(X_test_s)[:, 1])
    lr_acc = accuracy_score(y_test, lr.predict(X_test_s))

    # XGBoost
    xgb = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    xgb.fit(X_train, y_train)
    xgb_auc = roc_auc_score(y_test, xgb.predict_proba(X_test)[:, 1])
    xgb_acc = accuracy_score(y_test, xgb.predict(X_test))

    logger.info("Matchup LR:  acc=%.3f auc=%.3f", lr_acc, lr_auc)
    logger.info("Matchup XGB: acc=%.3f auc=%.3f", xgb_acc, xgb_auc)

    if xgb_auc >= lr_auc:
        best_model, best_scaler, best_type = xgb, None, "xgboost"
        best_auc, best_acc = xgb_auc, xgb_acc
    else:
        best_model, best_scaler, best_type = lr, scaler, "logistic"
        best_auc, best_acc = lr_auc, lr_acc

    importances = (
        best_model.feature_importances_ if best_type == "xgboost"
        else abs(best_model.coef_[0])
    )
    top_factors = sorted(
        zip(available_cols, importances), key=lambda x: x[1], reverse=True
    )[:5]

    trained_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "model":          best_model,
        "scaler":         best_scaler,
        "feature_cols":   available_cols,
        "train_medians":  train_medians,
        "model_type":     best_type,
        "trained_at":     trained_at,
        "n_samples":      len(X),
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

    path = ML_MODELS_DIR / "matchup_predictor.joblib"
    joblib.dump(artifact, path)

    return {
        "status":      "trained",
        "model_type":  best_type,
        "accuracy":    round(best_acc, 4),
        "roc_auc":     round(best_auc, 4),
        "n_matches":   len(df),
        "n_train":     len(X_train),
        "n_test":      len(X_test),
        "top_factors": artifact["top_factors"],
        "lr_auc":      round(lr_auc, 4),
        "xgb_auc":     round(xgb_auc, 4),
    }


# ---------------------------------------------------------------------------
# Phase 3 — Role-Aware AI Layer
# ---------------------------------------------------------------------------

# Adjacent roles used for flex-pick detection in analyze_role_champion_fit.
# A champion that cannot natively play the declared role but can play an
# adjacent one is classified as a "flex" pick (score 0.5) rather than
# off-meta (score 0.1).
_ADJACENT_ROLES: dict[str, list[str]] = {
    "TOP":     ["JUNGLE", "MIDDLE"],
    "JUNGLE":  ["TOP", "MIDDLE"],
    "MIDDLE":  ["TOP", "JUNGLE", "UTILITY"],
    "BOTTOM":  ["MIDDLE"],
    "UTILITY": ["MIDDLE", "BOTTOM"],
}

# Composition archetype definitions — ordered by precedence.
# Each entry: (archetype_name, condition_fn(tag_counts, role_slots))
# tag_counts: {tag: count}  role_slots: list of {champion_meta, role} dicts
_COMP_TAG_ARCHETYPES: list[tuple[str, str]] = [
    # Label          Description
    ("poke",         "Long-range poke/siege — win through attrition"),
    ("engage-dive",  "Engage into backline — blow up the enemy team"),
    ("teamfight",    "Sustained teamfight damage and CC"),
    ("protect-carry","Peel and disengage around one damage threat"),
    ("skirmish-brawl","Small-fight specialists — punish isolated picks"),
    ("split-push",   "1-3-1 or 1-4 split pressure to force reactions"),
    ("balanced",     "Mixed archetype — flexible win conditions"),
]


def get_champion_role_stats(
    db: Session,
    champion_id: int,
    role: str,
) -> dict:
    """
    Aggregate participant_stats for a champion filtered by role.

    Joins participant_stats → players → derived_metrics to compute:
      win_rate, avg_kda, avg_cs_per_min, avg_gold_per_min,
      avg_damage_share, games_played.

    The role filter is case-insensitive and applied to
    participant_stats.role.

    Returns a dict with the above keys, or games_played=0 if no data.
    """
    sql = text("""
        SELECT
            COUNT(*)                        AS games_played,
            AVG(CASE WHEN ps.win THEN 1.0 ELSE 0.0 END)
                                            AS win_rate,
            AVG(dm.kda)                     AS avg_kda,
            AVG(dm.cs_per_min)              AS avg_cs_per_min,
            AVG(dm.gold_per_min)            AS avg_gold_per_min,
            AVG(dm.damage_share)            AS avg_damage_share
        FROM participant_stats ps
        JOIN players p
          ON p.id = ps.player_id
        JOIN derived_metrics dm
          ON dm.match_id = ps.match_id AND dm.puuid = p.puuid
        WHERE ps.champion_id = :champion_id
          AND UPPER(ps.role)  = UPPER(:role)
    """)
    row = db.execute(sql, {"champion_id": champion_id, "role": role}).mappings().first()

    if row is None or row["games_played"] == 0:
        return {
            "champion_id":    champion_id,
            "role":           role.upper(),
            "games_played":   0,
            "win_rate":       None,
            "avg_kda":        None,
            "avg_cs_per_min": None,
            "avg_gold_per_min": None,
            "avg_damage_share": None,
        }

    return {
        "champion_id":      champion_id,
        "role":             role.upper(),
        "games_played":     int(row["games_played"]),
        "win_rate":         round(float(row["win_rate"]), 4)        if row["win_rate"]        is not None else None,
        "avg_kda":          round(float(row["avg_kda"]), 3)         if row["avg_kda"]         is not None else None,
        "avg_cs_per_min":   round(float(row["avg_cs_per_min"]), 3)  if row["avg_cs_per_min"]  is not None else None,
        "avg_gold_per_min": round(float(row["avg_gold_per_min"]), 3) if row["avg_gold_per_min"] is not None else None,
        "avg_damage_share": round(float(row["avg_damage_share"]), 4) if row["avg_damage_share"] is not None else None,
    }


def analyze_role_champion_fit(
    champion_meta: dict,
    declared_role: str,
) -> dict:
    """
    Score how well a champion fits a declared role.

    Uses role_affinity from ChampionMeta (populated by ddragon.py) which
    maps DDragon tags → LoL roles via _TAG_ROLE_AFFINITY.

    Scoring:
      1.0  "native"   — declared_role is in champion_meta["role_affinity"]
      0.5  "flex"     — declared_role is adjacent to a native role
      0.1  "off-meta" — no recognised affinity

    Args:
        champion_meta: ChampionMeta dict from get_champion_full_map().
        declared_role: Role string, e.g. "TOP", "JUNGLE", "MIDDLE",
                       "BOTTOM", "UTILITY".

    Returns:
        {"fit_score": float, "fit_label": str, "role_affinity": list[str]}
    """
    role_up = declared_role.upper()
    affinity: list[str] = [r.upper() for r in (champion_meta.get("role_affinity") or [])]

    if role_up in affinity:
        return {"fit_score": 1.0, "fit_label": "native", "role_affinity": affinity}

    adjacent = _ADJACENT_ROLES.get(role_up, [])
    if any(adj in affinity for adj in adjacent):
        return {"fit_score": 0.5, "fit_label": "flex", "role_affinity": affinity}

    return {"fit_score": 0.1, "fit_label": "off-meta", "role_affinity": affinity}


def score_composition_archetype(player_slots: list[dict]) -> dict:
    """
    Determine the dominant playstyle archetype for a 5-player team.

    Args:
        player_slots: List of dicts, each with:
            champion_meta (ChampionMeta dict)
            role          (str, e.g. "TOP")

    Returns:
        {
          "archetype":    str,   # e.g. "engage-dive"
          "description":  str,
          "tag_counts":   dict,  # aggregated DDragon tags across the team
          "role_fit_avg": float, # mean fit score across all slots
        }

    Archetype decision rules (first match wins):
      poke          — 2+ Mages and no Tank/Fighter majority
      engage-dive   — 3+ Tanks or Fighters and a Support present
      teamfight     — Marksman + Mage + Support present (APC/double AP counts)
      protect-carry — 2+ Supports/Tanks with exactly 1 Marksman
      skirmish-brawl— 3+ Assassins
      split-push    — Fighter count dominant with a Mage or Assassin
      balanced      — fallback
    """
    tag_counts: dict[str, int] = {}
    fit_scores: list[float] = []

    for slot in player_slots:
        meta = slot.get("champion_meta") or {}
        role = str(slot.get("role") or "")
        tags: list[str] = meta.get("tags") or []
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        fit = analyze_role_champion_fit(meta, role) if role else {"fit_score": 0.1}
        fit_scores.append(fit["fit_score"])

    tank_fighter = tag_counts.get("Tank", 0) + tag_counts.get("Fighter", 0)
    mage_n    = tag_counts.get("Mage", 0)
    assassin_n = tag_counts.get("Assassin", 0)
    marksman_n = tag_counts.get("Marksman", 0)
    support_n  = tag_counts.get("Support", 0)

    if mage_n >= 2 and tank_fighter < 3:
        archetype, description = _COMP_TAG_ARCHETYPES[0]
    elif tank_fighter >= 3 and support_n >= 1:
        archetype, description = _COMP_TAG_ARCHETYPES[1]
    elif marksman_n >= 1 and mage_n >= 1 and support_n >= 1:
        archetype, description = _COMP_TAG_ARCHETYPES[2]
    elif support_n + tag_counts.get("Tank", 0) >= 2 and marksman_n == 1:
        archetype, description = _COMP_TAG_ARCHETYPES[3]
    elif assassin_n >= 3:
        archetype, description = _COMP_TAG_ARCHETYPES[4]
    elif tag_counts.get("Fighter", 0) >= 2 and (mage_n >= 1 or assassin_n >= 1):
        archetype, description = _COMP_TAG_ARCHETYPES[5]
    else:
        archetype, description = _COMP_TAG_ARCHETYPES[6]

    role_fit_avg = round(sum(fit_scores) / len(fit_scores), 3) if fit_scores else 0.0

    return {
        "archetype":    archetype,
        "description":  description,
        "tag_counts":   tag_counts,
        "role_fit_avg": role_fit_avg,
    }


def get_champion_matchup_stats(
    db: Session,
    champ_a_id: int,
    champ_b_id: int,
    role: Optional[str] = None,
) -> dict:
    """
    Return head-to-head statistics for champion A vs champion B.

    Method:
      Self-join on participant_stats to find every match where champion A
      and champion B appeared on opposite teams (team_id differs).  Joins
      derived_metrics for both participants to compute per-match KDA and
      kill differentials.

    Args:
        champ_a_id: Riot numeric champion id for side A.
        champ_b_id: Riot numeric champion id for side B.
        role:       Optional role filter applied to both sides (UPPER).

    Returns:
        {
          "champ_a_id": int,
          "champ_b_id": int,
          "role":        str | None,
          "sample_size": int,
          "win_rate_a":  float | None,   # fraction of matches A's team won
          "avg_kda_diff": float | None,  # avg(kda_a - kda_b)
          "avg_kill_diff": float | None, # avg(kills_a - kills_b)
        }
    """
    role_filter_a = "AND UPPER(a.role) = UPPER(:role)" if role else ""
    role_filter_b = "AND UPPER(b.role) = UPPER(:role)" if role else ""

    sql_str = f"""
        SELECT
            COUNT(*)                              AS sample_size,
            AVG(CASE WHEN a.win THEN 1.0 ELSE 0.0 END)
                                                  AS win_rate_a,
            AVG(dma.kda - dmb.kda)                AS avg_kda_diff,
            AVG(CAST(a.kills AS FLOAT) - CAST(b.kills AS FLOAT))
                                                  AS avg_kill_diff
        FROM participant_stats a
        JOIN participant_stats b
          ON  b.match_id   = a.match_id
          AND b.team_id   != a.team_id
          AND b.champion_id = :champ_b_id
          {role_filter_b}
        JOIN players pa ON pa.id = a.player_id
        JOIN players pb ON pb.id = b.player_id
        JOIN derived_metrics dma
          ON dma.match_id = a.match_id AND dma.puuid = pa.puuid
        JOIN derived_metrics dmb
          ON dmb.match_id = b.match_id AND dmb.puuid = pb.puuid
        WHERE a.champion_id = :champ_a_id
          {role_filter_a}
    """

    params: dict = {"champ_a_id": champ_a_id, "champ_b_id": champ_b_id}
    if role:
        params["role"] = role

    row = db.execute(text(sql_str), params).mappings().first()

    sample_size = int(row["sample_size"]) if row else 0

    if sample_size == 0:
        return {
            "champ_a_id":    champ_a_id,
            "champ_b_id":    champ_b_id,
            "role":          role.upper() if role else None,
            "sample_size":   0,
            "win_rate_a":    None,
            "avg_kda_diff":  None,
            "avg_kill_diff": None,
        }

    return {
        "champ_a_id":    champ_a_id,
        "champ_b_id":    champ_b_id,
        "role":          role.upper() if role else None,
        "sample_size":   sample_size,
        "win_rate_a":    round(float(row["win_rate_a"]), 4)   if row["win_rate_a"]   is not None else None,
        "avg_kda_diff":  round(float(row["avg_kda_diff"]), 3) if row["avg_kda_diff"] is not None else None,
        "avg_kill_diff": round(float(row["avg_kill_diff"]), 3) if row["avg_kill_diff"] is not None else None,
    }
