from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime

from app.db.session import get_db
from app.models.player import Player
from app.models.participant_stats import ParticipantStats


class PlayerResponse(BaseModel):
    id: int
    riot_id: str
    tag_line: str
    puuid: str
    region: str
    created_at: datetime
    match_count: int = 0

    class Config:
        from_attributes = True


router = APIRouter(prefix="/players", tags=["players"])


@router.get("/", response_model=List[PlayerResponse])
def list_players(
    min_matches: int = 0,
    db: Session = Depends(get_db),
):
    """
    Get all players in the database.
    Pass `min_matches` to filter out ghost participants with too few matches.
    Each result includes a `match_count` field.
    """
    match_count_subq = (
        db.query(
            ParticipantStats.player_id,
            func.count(ParticipantStats.match_id).label("match_count"),
        )
        .group_by(ParticipantStats.player_id)
        .subquery()
    )

    query = (
        db.query(Player, func.coalesce(match_count_subq.c.match_count, 0).label("match_count"))
        .outerjoin(match_count_subq, match_count_subq.c.player_id == Player.id)
    )

    if min_matches > 0:
        query = query.filter(func.coalesce(match_count_subq.c.match_count, 0) >= min_matches)

    results = query.order_by(func.coalesce(match_count_subq.c.match_count, 0).desc()).all()

    output = []
    for player, mc in results:
        output.append(PlayerResponse(
            id=player.id,
            riot_id=player.riot_id,
            tag_line=player.tag_line,
            puuid=player.puuid,
            region=player.region,
            created_at=player.created_at,
            match_count=mc,
        ))
    return output


@router.get("/{puuid}", response_model=PlayerResponse)
def get_player(puuid: str, db: Session = Depends(get_db)):
    """Get a specific player by PUUID."""
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player
