"""
AI/ML routes
============
All endpoints use kebab-case path segments (FastAPI converts them to
snake_case in OpenAPI docs automatically).

Endpoint map:
  POST /ai/train/playstyle           → train KMeans playstyle model
  POST /ai/train/win-prediction      → train win-prediction classifier
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
    predict_cs,
    predict_earlygame,
    predict_kda,
    predict_win,
    run_win_prediction_backtest,
    train_cs_regressor,
    train_earlygame_model,
    train_kda_regressor,
    train_playstyle_model,
    train_win_predictor,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Training endpoints
# ---------------------------------------------------------------------------


@router.post("/train/playstyle", summary="Train playstyle clustering model")
def train_playstyle(db: Session = Depends(get_db)) -> dict:
    """
    Train the KMeans playstyle clustering model on all ingested players.

    Returns training metrics and centroid snapshots.  After training,
    review ``CLUSTER_LABELS`` in ``ai_service.py`` and update label
    names to match the centroid characteristics before exposing
    ``GET /ai/playstyle/{puuid}`` to end users.

    Raises 422 when the database has fewer than 20 players with 10+
    ranked matches.
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


@router.post("/train/kda-regression", summary="Train KDA regression model")
def train_kda_regression(db: Session = Depends(get_db)) -> dict:
    """
    Train the KDA regression model (Ridge vs XGBRegressor).
    The better model by R² is saved to ``kda_regressor.joblib``.

    Features are rolling prior-game stats only; current-game outcomes
    (kills, deaths, assists) are never included to prevent target leakage.

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

    Identical pipeline to KDA regression with a separate scaler,
    separate artifact, and separate output files.

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
    timeline differentials.  The model predicts team 100's win probability from
    gold/XP/level/CS diffs and first-objective flags.

    Requires matches to have been ingested with ``fetch_timeline=true``.

    Raises 422 when fewer than 50 matches with timeline frame data exist.
    """
    try:
        return train_earlygame_model(db)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


# ---------------------------------------------------------------------------
# Inference endpoints
# ---------------------------------------------------------------------------


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
