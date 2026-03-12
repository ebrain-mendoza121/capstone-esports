from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.session import get_db
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.player import Player


class MatchResponse(BaseModel):
    match_id: str
    game_creation: int
    game_duration: int
    queue_id: int
    patch_version: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/player/{puuid}", response_model=List[MatchResponse])
def get_player_matches(puuid: str, limit: int = 20, db: Session = Depends(get_db)):
    """
    Get matches for a specific player.
    
    Args:
        puuid: Player's PUUID
        limit: Maximum number of matches to return (default: 20)
        
    Returns:
        List of matches ordered by most recent first
    """
    # Check if player exists
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    matches = (
        db.query(Match)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .filter(Player.puuid == puuid)
        .order_by(Match.game_creation.desc())
        .limit(limit)
        .all()
    )
    
    return matches
