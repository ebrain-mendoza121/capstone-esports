import logging
from typing import Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.cache import TTLCache
from app.db.session import get_db
from app.models.player import Player
from app.models.participant_stats import ParticipantStats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process TTL cache for the player list.
# GET /players/ runs a full GROUP BY across participant_stats on every call —
# expensive under load.  Cache the result for 5 minutes; data is only stale
# while a new match is being ingested, which is acceptable for analytics.
# ---------------------------------------------------------------------------
_players_list_cache: TTLCache = TTLCache()


# ---------------------------------------------------------------------------
# Module-level compute + warm function (callable from startup warmer)
# ---------------------------------------------------------------------------

def _compute_player_list_sql(db: Session) -> List:
    """Run the full GROUP BY player list query and return serialisable dicts."""
    match_count_subq = (
        db.query(
            ParticipantStats.player_id,
            func.count(ParticipantStats.match_id).label("match_count"),
        )
        .group_by(ParticipantStats.player_id)
        .subquery()
    )
    results = (
        db.query(Player, func.coalesce(match_count_subq.c.match_count, 0).label("match_count"))
        .outerjoin(match_count_subq, match_count_subq.c.player_id == Player.id)
        .order_by(func.coalesce(match_count_subq.c.match_count, 0).desc())
        .all()
    )
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
            logger.warning("Skipping player id=%s: %s", player.id, exc)
    return output


def warm_players_cache(db: Session) -> None:
    """Pre-populate the player list cache at startup."""
    try:
        _players_list_cache.get_or_compute(lambda: _compute_player_list_sql(db))
        logger.info("warm_players_cache: player list ready")
    except Exception as exc:
        logger.warning("warm_players_cache: failed — %s", exc)


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


@router.get("/count", response_model=dict)
def count_players(db: Session = Depends(get_db)):
    """
    Return the total number of players in the database in a single COUNT query.

    Prefer this over ``GET /players/`` when you only need the player count —
    it avoids loading and serialising every row.
    """
    from sqlalchemy import text as sa_text
    total = db.execute(sa_text("SELECT COUNT(*) FROM players")).scalar() or 0
    return {"count": int(total)}


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
    # Only cache the default (min_matches=0, limit=None) call — what the
    # frontend always sends.  Parametrised calls bypass the cache.
    if min_matches == 0 and limit is None:
        return _players_list_cache.get_or_compute(lambda: _compute_player_list_sql(db))

    # Parametrised call — run query directly (no cache)
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

    output: List[PlayerResponse] = []
    for player, mc in query.all():
        try:
            output.append(PlayerResponse(
                id=player.id, riot_id=player.riot_id, tag_line=player.tag_line,
                puuid=player.puuid, region=player.region, created_at=player.created_at,
                match_count=int(mc),
            ))
        except Exception as exc:
            logger.warning("Skipping player id=%s: %s", player.id, exc)
    return output


@router.get("/{puuid}", response_model=PlayerResponse)
def get_player(puuid: str, db: Session = Depends(get_db)):
    """Get a specific player by PUUID."""
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player
