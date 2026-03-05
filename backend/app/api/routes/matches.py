from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.player import Player

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/player/{puuid}")
def get_player_matches(puuid: str, limit: int = 20, db: Session = Depends(get_db)):
    return (
        db.query(Match)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .filter(Player.puuid == puuid)
        .order_by(Match.game_creation.desc())
        .limit(limit)
        .all()
    )