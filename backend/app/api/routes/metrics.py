import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError as SAOperationalError, TimeoutError as SATimeoutError
from sqlalchemy.orm import Session

from app.core.cache import TTLCacheDict
from app.db.session import get_db
from app.services.metrics_service import get_player_metrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["metrics"])

# Per-puuid metrics cache.  get_player_metrics() aggregates the full
# derived_metrics table — expensive under concurrent load with no caching.
# TTLCacheDict gives each puuid its own stampede-safe 5-minute slot.
_metrics_cache: TTLCacheDict = TTLCacheDict()


@router.get("/player/{puuid}")
def player_metrics(puuid: str, db: Session = Depends(get_db)):
    try:
        result = _metrics_cache.get_or_compute(
            puuid,
            lambda: get_player_metrics(db, puuid),
        )
    except (SAOperationalError, SATimeoutError):
        # Let the app-level handlers in main.py convert these to 503 responses.
        # Catching them here and re-raising as HTTPException(500) would hide the
        # "DB busy" signal that monitoring tools and Locust rely on.
        raise
    except Exception as exc:
        logger.error("Error computing metrics for puuid=%s: %s", puuid, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute metrics: {type(exc).__name__}",
        )
    if result is None:
        raise HTTPException(status_code=404, detail="No matches found for this player")
    return result
