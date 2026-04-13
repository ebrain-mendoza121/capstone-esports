import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.models.player import Player
from app.models.participant_stats import ParticipantStats

logger = logging.getLogger(__name__)


class PlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    riot_id: str
    tag_line: str
    puuid: str
    region: str
    # Nullable — rows inserted before the column migration may lack a timestamp.
    created_at: Optional[datetime] = None
    match_count: int = 0

    # Coerce None/empty to empty string so legacy rows with NULL string fields
    # don't raise a ValidationError and crash the entire list response.
    @field_validator("riot_id", "tag_line", "region", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return v if v else ""


router = APIRouter(prefix="/players", tags=["players"])


@router.get("/", response_model=List[PlayerResponse])
def list_players(
    min_matches: int = 0,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get players in the database, ordered by match count descending.

    Query params:
    - min_matches: filter out ghost participants with fewer than N matches (default 0 = all)
    - limit: cap the number of results returned (default None = all)

    Ghost participants are opponents ingested alongside tracked players.
    Use min_matches=5 or min_matches=10 to return only properly tracked players.
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

    query = query.order_by(func.coalesce(match_count_subq.c.match_count, 0).desc())

    if limit is not None and limit > 0:
        query = query.limit(limit)

    results = query.all()

    output = []
    for player, mc in results:
        try:
            output.append(PlayerResponse(
                id=player.id,
                riot_id=player.riot_id,
                tag_line=player.tag_line,
                puuid=player.puuid,
                region=player.region,
                created_at=player.created_at,
                match_count=int(mc),
            ))
        except Exception as exc:
            # Skip individual malformed rows rather than failing the entire list.
            logger.warning("Skipping player id=%s due to serialization error: %s", player.id, exc)

    return output


@router.get("/{puuid}", response_model=PlayerResponse)
def get_player(puuid: str, db: Session = Depends(get_db)):
    """Get a specific player by PUUID."""
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player
