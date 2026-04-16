"""
AI/ML routes
============
All endpoints use kebab-case path segments (FastAPI converts them to
snake_case in OpenAPI docs automatically).

Endpoint map:
  POST /ai/train/playstyle           → train KMeans playstyle model
  POST /ai/train/win-prediction      → train win-prediction classifier
    POST /ai/train/all                 → train all models sequentially
  POST /ai/train/kda-regression      → train KDA regression model
  POST /ai/train/cs-regression       → train CS/min regression model
  POST /ai/train/early-game          → train early-game predictor
  GET  /ai/models/status             → status for all models
  GET  /ai/playstyle/{puuid}         → playstyle cluster for one player
  GET  /ai/predict/{puuid}/{match_id}→ win-probability for one player/match
  GET  /ai/predict/kda/{puuid}/{match_id} → expected KDA for one player/match
  GET  /ai/predict/cs/{puuid}/{match_id}  → expected CS/min for one player/match
  GET  /ai/champions/{puuid}         → champion recommendations
  GET  /ai/backtest/win-prediction   → calibration backtest for win-prediction model
  GET  /ai/early-game/{match_id}     → early-game win probability for a match

Artifact keys (internal joblib file stem) are stable identifiers that
MUST NOT bleed into URLs.  The ``_ARTIFACT_ROUTE_SLUG`` mapping in
``ai_service.py`` is the single source of truth for key ↔ slug mapping.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.ai_service import (
    InsufficientDataError,
    ModelNotTrainedError,
    get_champion_recommendations,
    get_model_status,
    get_player_playstyle,
    get_threat_weights,
    predict_cs,
    predict_earlygame,
    predict_kda,
    predict_win,
    run_win_prediction_backtest,
    train_cs_regressor,
    train_champion_clusters,
    train_earlygame_model,
    train_kda_regressor,
    train_matchup_predictor,
    train_playstyle_model,
    train_win_predictor,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Training endpoints
# All routes are synchronous and block until training completes.
# The /ai/train/* prefix receives a 600 s timeout (same as /backfill) so
# these never hit the default 60 s middleware cutoff.
# ---------------------------------------------------------------------------


@router.post("/train/playstyle", summary="Train playstyle clustering model")
def train_playstyle(db: Session = Depends(get_db)) -> dict:
    """
    Train the KMeans playstyle clustering model on all ingested players.
    Returns training metrics and centroid snapshots when complete.
    Raises 422 when the database has fewer than 20 players with 10+ ranked matches.
    """
    try:
        return train_playstyle_model(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/train/win-prediction", summary="Train win-prediction classifier")
def train_win_prediction(db: Session = Depends(get_db)) -> dict:
    """
    Train the win-prediction model (Logistic Regression vs XGBoost).
    The better model by ROC-AUC is saved to ``win_predictor.joblib``.
    Raises 422 when fewer than 100 labeled training rows exist.
    """
    try:
        return train_win_predictor(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/train/matchup-prediction", summary="Train match-level win-prediction model")
def train_matchup_prediction(db: Session = Depends(get_db)) -> dict:
    """
    Train the matchup-level win-prediction model (team-vs-team differentials).
    Requires at least 50 unique ranked matches. Saved to ``matchup_predictor.joblib``.
    """
    try:
        return train_matchup_predictor(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/train/kda-regression", summary="Train KDA regression model")
def train_kda_regression(db: Session = Depends(get_db)) -> dict:
    """
    Train the KDA regression model (Ridge vs XGBRegressor).
    The better model by R² is saved to ``kda_regressor.joblib``.
    Raises 422 when fewer than 100 labeled training rows exist.
    """
    try:
        return train_kda_regressor(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/train/cs-regression", summary="Train CS/min regression model")
def train_cs_regression(db: Session = Depends(get_db)) -> dict:
    """
    Train the CS/min regression model (Ridge vs XGBRegressor).
    The better model by R² is saved to ``cs_regressor.joblib``.
    Raises 422 when fewer than 100 labeled training rows exist.
    """
    try:
        return train_cs_regressor(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/train/early-game", summary="Train early-game win-prediction model")
def train_early_game(db: Session = Depends(get_db)) -> dict:
    """
    Train the early-game predictor (Logistic Regression) on T=10 and T=15 minute
    timeline differentials. Requires matches ingested with ``fetch_timeline=true``.
    Raises 422 when fewer than 50 matches with timeline frame data exist.
    """
    try:
        return train_earlygame_model(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error training early-game model")
        raise HTTPException(status_code=503, detail=f"Early-game model training failed: {exc}") from exc


@router.post("/train/all", summary="Train all models sequentially")
def train_all_models(db: Session = Depends(get_db)) -> dict:
    """
    Train all model artifacts sequentially in one blocking call.
    Returns a per-model summary of results, skips, and failures.
    Individual InsufficientDataError failures are recorded but do not abort the run.
    """
    import time as _time

    trainers = [
        ("playstyle_kmeans",    train_playstyle_model),
        ("win_predictor",       train_win_predictor),
        ("matchup_predictor",   train_matchup_predictor),
        ("kda_regressor",       train_kda_regressor),
        ("cs_regressor",        train_cs_regressor),
        ("earlygame_predictor", train_earlygame_model),
        ("champion_clusters",   train_champion_clusters),
    ]
    total = len(trainers)
    summary: dict[str, dict] = {}
    run_start = _time.time()

    for step, (model_name, trainer) in enumerate(trainers, start=1):
        logger.info("[%d/%d] Starting: %s", step, total, model_name)
        t0 = _time.time()
        try:
            result = trainer(db)
            elapsed = round(_time.time() - t0, 1)
            logger.info("[%d/%d] ✓ Completed: %s (%.1fs)", step, total, model_name, elapsed)
            summary[model_name] = {
                "step":    step,
                "status":  "trained",
                "elapsed_s": elapsed,
                "result":  result,
            }
        except InsufficientDataError as exc:
            elapsed = round(_time.time() - t0, 1)
            logger.warning("[%d/%d] ⚠ Skipped: %s — %s", step, total, model_name, exc)
            summary[model_name] = {
                "step":    step,
                "status":  "skipped",
                "elapsed_s": elapsed,
                "reason":  str(exc),
            }
        except Exception as exc:
            elapsed = round(_time.time() - t0, 1)
            db.rollback()  # clear aborted transaction so subsequent trainers can run
            logger.exception("[%d/%d] ✗ Failed: %s (%.1fs)", step, total, model_name, elapsed)
            summary[model_name] = {
                "step":    step,
                "status":  "failed",
                "elapsed_s": elapsed,
                "error":   str(exc),
            }

    total_elapsed = round(_time.time() - run_start, 1)
    trained  = sum(1 for v in summary.values() if v["status"] == "trained")
    skipped  = sum(1 for v in summary.values() if v["status"] == "skipped")
    failed   = sum(1 for v in summary.values() if v["status"] == "failed")

    logger.info(
        "train/all complete in %.1fs — %d trained, %d skipped, %d failed",
        total_elapsed, trained, skipped, failed,
    )
    return {
        "total_elapsed_s": total_elapsed,
        "trained":  trained,
        "skipped":  skipped,
        "failed":   failed,
        "summary":  summary,
    }


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/models/status", summary="Model training status")
def models_status() -> dict:
    """
    Return training status, version metadata, and metrics for all models.
    Does not require a database session.
    """
    return get_model_status()


@router.get("/opponent-coverage", summary="Frequent untracked opponents to ingest next")
def opponent_coverage(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    """
    Find the most frequently occurring opponents across all tracked players'
    match histories who are NOT yet fully ingested (stub players only).

    Ingesting these players will directly populate the opponent differential
    features (win_rate_diff, kda_diff, cs_diff) used by the win-prediction
    model, improving AUC.

    Returns:
        tracked_players   - how many fully tracked players exist
        stub_players      - how many stub-only opponents exist
        top_opponents     - list of {puuid, riot_id, tag_line, appearances}
                           sorted by appearance count descending
        coverage_pct      - % of opponent slots that are fully tracked
    """
    from sqlalchemy import text as _text

    sql = _text("""
        WITH tracked AS (
            -- Players who have at least one derived_metrics row = fully ingested
            SELECT DISTINCT p.id, p.puuid
            FROM players p
            JOIN derived_metrics dm ON dm.puuid = p.puuid
        ),
        stub AS (
            -- Players with NO derived_metrics = stub only
            SELECT p.id, p.puuid, p.riot_id, p.tag_line
            FROM players p
            WHERE NOT EXISTS (
                SELECT 1 FROM derived_metrics dm WHERE dm.puuid = p.puuid
            )
        ),
        opponent_appearances AS (
            -- Count how many times each stub player appears in tracked players' matches
            SELECT
                ps.player_id,
                COUNT(*) AS appearances
            FROM participant_stats ps
            -- The match must contain at least one tracked player on the other team
            WHERE EXISTS (
                SELECT 1
                FROM participant_stats ps2
                JOIN tracked t ON t.id = ps2.player_id
                WHERE ps2.match_id = ps.match_id
                  AND ps2.team_id != ps.team_id
            )
            AND ps.player_id IN (SELECT id FROM stub)
            GROUP BY ps.player_id
        )
        SELECT
            s.puuid,
            s.riot_id,
            s.tag_line,
            oa.appearances
        FROM opponent_appearances oa
        JOIN stub s ON s.id = oa.player_id
        ORDER BY oa.appearances DESC
        LIMIT :limit
    """)

    rows = db.execute(sql, {"limit": limit}).mappings().all()

    # Summary counts
    tracked_count = db.execute(_text("""
        SELECT COUNT(DISTINCT p.id) FROM players p
        JOIN derived_metrics dm ON dm.puuid = p.puuid
    """)).scalar() or 0

    stub_count = db.execute(_text("""
        SELECT COUNT(*) FROM players p
        WHERE NOT EXISTS (
            SELECT 1 FROM derived_metrics dm WHERE dm.puuid = p.puuid
        )
    """)).scalar() or 0

    total_opponent_slots = db.execute(_text("""
        SELECT COUNT(*) FROM participant_stats ps
        WHERE EXISTS (
            SELECT 1 FROM players p
            JOIN derived_metrics dm ON dm.puuid = p.puuid
            WHERE p.id = ps.player_id
        )
    """)).scalar() or 1

    tracked_opponent_slots = db.execute(_text("""
        SELECT COUNT(*) FROM participant_stats ps
        JOIN players p ON p.id = ps.player_id
        JOIN derived_metrics dm ON dm.puuid = p.puuid
    """)).scalar() or 0

    coverage_pct = round(100.0 * tracked_opponent_slots / max(total_opponent_slots, 1), 1)

    return {
        "tracked_players":   tracked_count,
        "stub_players":      stub_count,
        "coverage_pct":      coverage_pct,
        "interpretation":    (
            f"{coverage_pct}% of opponent match slots belong to fully tracked players. "
            f"Ingest the top opponents below to increase differential feature coverage."
        ),
        "top_opponents": [
            {
                "puuid":       r["puuid"],
                "riot_id":     r["riot_id"],
                "tag_line":    r["tag_line"],
                "appearances": r["appearances"],
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Inference endpoints
# ---------------------------------------------------------------------------


@router.get("/threat-weights", summary="Current threat score weights")
def threat_weights(db: Session = Depends(get_db)) -> dict:
    """
    Return the weights currently used by the threat score formula.

    When the win-prediction model has been trained and its AUC >= 0.60,
    the weights are derived from that model's feature importances.
    Otherwise the hand-tuned defaults (win_rate: 4.0, kda: 4.0) are used.

    Response fields:
    - win_rate_weight   — multiplier for normalised win rate (max 4.0 by default)
    - kda_weight        — multiplier for normalised KDA      (max 4.0 by default)
    - source            — "model" if backed by ML, "default" if hand-tuned
    - model_auc         — AUC of the underlying model (null if default)
    - feature_breakdown — full per-feature importance map (null if default)
    - interpretation    — human-readable explanation of the current weights
    """
    w = get_threat_weights(db)

    if w["source"] == "model":
        interpretation = (
            f"Weights derived from the trained win-prediction model "
            f"(AUC {w['model_auc']:.3f}). "
            f"Win rate contributes {w['win_rate_weight']:.2f} pts, "
            f"KDA contributes {w['kda_weight']:.2f} pts out of 8 available "
            f"(plus up to 2 pts confidence bonus)."
        )
    else:
        interpretation = (
            "Using hand-tuned defaults (win_rate: 4.0, kda: 4.0). "
            "Train the win-prediction model (POST /ai/train/win-prediction) "
            "and ensure it reaches AUC >= 0.60 to unlock model-backed weights."
        )

    return {**w, "interpretation": interpretation}


@router.get("/playstyle/{puuid}", summary="Player playstyle cluster")
def player_playstyle(puuid: str, db: Session = Depends(get_db)) -> dict:
    """
    Return the playstyle cluster for a single player.

    Returns ``cluster_id: -1`` with ``playstyle_label: "insufficient_data"``
    when the player has fewer than 10 ranked games — never 404.

    Raises 503 when the model has not been trained yet.
    """
    try:
        return get_player_playstyle(db, puuid)
    except ModelNotTrainedError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
            headers={"Retry-After": "0"},
        ) from exc


@router.get(
    "/predict/{puuid}/{match_id}",
    summary="Win-probability for a player in a match",
)
def predict_win_probability(
    puuid: str,
    match_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Return win-probability for ``puuid`` in ``match_id`` using that player's
    rolling match history up to (but not including) the match start.

    Always returns a dict — ``model_trained: false`` when the win-prediction
    model has not been trained yet; ``confidence: "low"`` or
    ``win_probability: null`` when the player has insufficient prior history.
    """
    return predict_win(db, puuid, match_id)


@router.get("/champions/{puuid}", summary="Champion recommendations")
def champion_recommendations(
    puuid: str,
    top_n: int = Query(default=10, ge=1, le=20),
    role: Optional[str] = Query(default=None, description="Filter by role e.g. MIDDLE, BOTTOM"),
    db: Session = Depends(get_db),
) -> list:
    """
    Return ranked champion recommendations for a player using Bayesian-smoothed
    win rate, KDA, CS efficiency, and experience weighting.

    Returns an empty list when the player has no ranked game history.
    """
    return get_champion_recommendations(db, puuid, top_n=top_n, role_filter=role)


# ---------------------------------------------------------------------------
# Regression inference endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/predict/kda/{puuid}/{match_id}",
    summary="Expected KDA for a player in a match",
)
def predict_kda_endpoint(
    puuid: str,
    match_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the expected KDA for ``puuid`` in ``match_id`` using that player's
    rolling match history up to (but not including) the match start.

    Always returns a dict — ``model_trained: false`` when the KDA regression
    model has not been trained yet; ``expected_kda: null`` when the player
    has insufficient prior history.
    """
    return predict_kda(db, puuid, match_id)


@router.get(
    "/predict/cs/{puuid}/{match_id}",
    summary="Expected CS/min for a player in a match",
)
def predict_cs_endpoint(
    puuid: str,
    match_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the expected CS per minute for ``puuid`` in ``match_id`` using that
    player's rolling match history up to (but not including) the match start.

    Always returns a dict — ``model_trained: false`` when the CS regression
    model has not been trained yet; ``expected_cs_per_min: null`` when the
    player has insufficient prior history.
    """
    return predict_cs(db, puuid, match_id)


# ---------------------------------------------------------------------------
# Backtest endpoint
# ---------------------------------------------------------------------------


@router.get("/backtest/win-prediction", summary="Calibration backtest for win-prediction model")
def backtest_win_prediction(
    n_matches: int = Query(default=50, ge=1, le=500, description="Number of recent matches to evaluate"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Run the trained win-prediction model against the most recent ``n_matches``
    ranked matches and compare predictions to actual outcomes.

    Only medium- and high-confidence predictions are included (players with
    fewer than 5 prior games are skipped, as the model itself flags them as
    unreliable).

    Returns a calibration table (predicted probability vs actual win rate per
    10 %-wide bucket), per-match prediction detail, and aggregate metrics
    including Brier score (lower is better; random baseline = 0.25).

    Returns ``model_trained: false`` if the win-prediction model has not been
    trained yet.
    """
    return run_win_prediction_backtest(db, n_matches=n_matches)


# ---------------------------------------------------------------------------
# Early-game inference endpoint
# ---------------------------------------------------------------------------


@router.get("/early-game/{match_id}", summary="Early-game win probability for a match")
def early_game_prediction(
    match_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the probability that team 100 wins based on T=10 and T=15 minute
    timeline differentials (gold/XP/level/CS diffs and first-objective flags).

    Always returns a dict — ``model_trained: false`` when the early-game model
    has not been trained yet; ``error: "no_timeline_data"`` when the match was
    not ingested with ``fetch_timeline=true``.
    """
    return predict_earlygame(db, match_id)


# ---------------------------------------------------------------------------
# Opponent feature enrichment — fills opp_avg_* columns for training data
# ---------------------------------------------------------------------------


@router.post(
    "/enrich/opponent-features",
    summary="Analyse opponent-feature coverage for training data",
)
def enrich_opponent_features(
    limit: int = Query(500, description="Max matches to analyse"),
    db: Session = Depends(get_db),
) -> dict:
    """
    **Fast DB-only** opponent coverage analysis — no Riot API calls, completes
    in milliseconds.

    Explains how many training matches already have opponent rolling stats
    available (because the opponents were also tracked and have derived_metrics)
    vs matches where opponent features will fall back to neutral league-wide
    averages (win_rate=0.5, kda=2.5, cs_min=7.0).

    The win-predictor model is already trained with these neutral fallbacks for
    stub opponents, so this endpoint is purely diagnostic.  Run it after
    ingesting new players to see how coverage improves.

    To truly improve opponent features beyond neutral defaults:
      1. Ingest the opponent players directly via ``POST /ingest/player``
      2. Retrain: ``POST /ai/train/win-prediction``
    """
    from sqlalchemy import text as _text

    try:
        # ---------------------------------------------------------------
        # For each recent match, count how many of the 10 participants
        # have at least 5 games of derived_metrics history in the DB.
        # Those are the players who contribute real (non-fallback) rolling
        # stats to the opponent feature columns.
        # ---------------------------------------------------------------
        sql = _text("""
            WITH match_participants AS (
                SELECT
                    ps.match_id,
                    ps.team_id,
                    ps.player_id,
                    p.puuid
                FROM participant_stats ps
                JOIN players p ON p.id = ps.player_id
                WHERE ps.team_id IN (100, 200)
            ),
            player_history AS (
                SELECT puuid, COUNT(*) AS game_count
                FROM derived_metrics
                GROUP BY puuid
            ),
            match_team_coverage AS (
                SELECT
                    mp.match_id,
                    mp.team_id,
                    COUNT(*) AS team_size,
                    COUNT(CASE WHEN COALESCE(ph.game_count, 0) >= 5 THEN 1 END) AS players_with_history
                FROM match_participants mp
                LEFT JOIN player_history ph ON ph.puuid = mp.puuid
                GROUP BY mp.match_id, mp.team_id
            )
            SELECT
                match_id,
                team_id,
                team_size,
                players_with_history,
                CASE WHEN players_with_history > 0 THEN true ELSE false END AS has_any_opp_data
            FROM match_team_coverage
            ORDER BY match_id DESC
            LIMIT :limit
        """)
        rows = db.execute(sql, {"limit": limit}).mappings().all()
    except Exception as exc:
        logger.exception("Enrichment coverage query failed")
        raise HTTPException(status_code=500, detail=f"DB query failed: {exc}") from exc

    if not rows:
        return {
            "status": "no_data",
            "message": "No participant_stats rows found. Ingest some matches first.",
            "matches_analysed": 0,
        }

    total_teams = len(rows)
    teams_with_any_data = sum(1 for r in rows if r["has_any_opp_data"])
    teams_fully_covered = sum(
        1 for r in rows if r["players_with_history"] >= 3  # ≥3 of 5 have history
    )
    total_players = sum(r["team_size"] for r in rows)
    players_with_history = sum(r["players_with_history"] for r in rows)

    coverage_pct = round(players_with_history / total_players * 100, 1) if total_players else 0.0

    return {
        "status": "complete",
        "matches_analysed":   total_teams // 2,   # two teams per match
        "teams_analysed":     total_teams,
        "teams_with_any_opp_history":   teams_with_any_data,
        "teams_with_good_opp_history":  teams_fully_covered,
        "total_opponent_player_slots":  total_players,
        "slots_with_history":           players_with_history,
        "coverage_pct":                 coverage_pct,
        "explanation": (
            f"{coverage_pct}% of opponent player-slots have real rolling stats in the DB. "
            f"The remaining {100 - coverage_pct:.1f}% fall back to neutral league averages "
            f"(win_rate=0.50, kda=2.50, cs_min=7.00) during win-predictor training."
        ),
        "next_step": (
            "To improve coverage: POST /ingest/player for each opponent, "
            "then POST /ai/train/win-prediction."
        ),
    }


# ---------------------------------------------------------------------------
# Champion cluster training endpoint
# ---------------------------------------------------------------------------


@router.post("/train/champion-clusters", summary="Train champion archetype clustering model")
def train_champion_clusters_endpoint(db: Session = Depends(get_db)) -> dict:
    """
    Cluster all champions in tracked matches by their aggregate stat profiles
    (KDA, CS/min, gold/min, damage share, vision, kill participation).

    Produces 4 archetypes: farm_carry, skirmisher, utility, versatile.
    Used to match player playstyle → champion recommendations.

    Requires at least 8 distinct champions with 3+ games each.
    Run after ingesting a representative set of matches.
    """
    try:
        return train_champion_clusters(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error training champion clusters model")
        raise HTTPException(status_code=503, detail=f"Champion-clusters model training failed: {exc}") from exc
