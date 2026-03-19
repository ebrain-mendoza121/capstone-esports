from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.metrics_service import get_player_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/player/{puuid}")
def player_metrics(puuid: str, db: Session = Depends(get_db)):
    result = get_player_metrics(db, puuid)
    if result is None:
        raise HTTPException(status_code=404, detail="No matches found for this player")
    return result
