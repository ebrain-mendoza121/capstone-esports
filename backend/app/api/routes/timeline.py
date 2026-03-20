from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.match_timeline import MatchTimeline, TimelineParticipantFrame, TimelineEvent
from app.models.player import Player

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("/{match_id}")
def get_timeline_summary(match_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns timeline metadata and frame count for a match.
    Use this to check if timeline data is available before fetching frames.
    """
    tl = db.query(MatchTimeline).filter(MatchTimeline.match_id == match_id).first()
    if not tl:
        raise HTTPException(status_code=404, detail="Timeline not found for this match. Re-ingest with fetch_timeline=true.")

    frame_count = (
        db.query(TimelineParticipantFrame)
        .filter(TimelineParticipantFrame.match_id == match_id)
        .count()
    )

    event_count = (
        db.query(TimelineEvent)
        .filter(TimelineEvent.match_id == match_id)
        .count()
    )

    return {
        "match_id": match_id,
        "frame_interval_ms": tl.frame_interval,
        "end_of_game_result": tl.end_of_game_result,
        "participant_frame_rows": frame_count,
        "event_rows": event_count,
    }


@router.get("/{match_id}/frames")
def get_timeline_frames(
    match_id: str,
    participant_id: Optional[int] = None,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns parsed per-minute frames for a match.

    Filter by participant_id (1–10) to get a single player's journey.
    Ordered by frame_timestamp ASC, then participant_id ASC.

    Pagination (offset-based — dataset is bounded at ~400 rows per match):
      limit  — max rows to return (default 500, capped at 1000)
      offset — number of rows to skip (default 0)

    Example:
      GET /timeline/NA1_12345/frames?limit=200&offset=0
      GET /timeline/NA1_12345/frames?participant_id=3&limit=50&offset=0
    """
    limit = min(limit, 1000)

    tl = db.query(MatchTimeline.match_id).filter(MatchTimeline.match_id == match_id).first()
    if not tl:
        raise HTTPException(status_code=404, detail="Timeline not found for this match.")

    q = db.query(TimelineParticipantFrame).filter(
        TimelineParticipantFrame.match_id == match_id
    )
    if participant_id is not None:
        q = q.filter(TimelineParticipantFrame.participant_id == participant_id)

    frames = (
        q.order_by(
            TimelineParticipantFrame.frame_timestamp,
            TimelineParticipantFrame.participant_id,
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "frame_timestamp": f.frame_timestamp,
            "participant_id": f.participant_id,
            "position_x": f.position_x,
            "position_y": f.position_y,
            "current_gold": f.current_gold,
            "total_gold": f.total_gold,
            "gold_per_second": f.gold_per_second,
            "xp": f.xp,
            "level": f.level,
            "minions_killed": f.minions_killed,
            "jungle_minions_killed": f.jungle_minions_killed,
        }
        for f in frames
    ]


@router.get("/{match_id}/frames/by-puuid/{puuid}")
def get_timeline_frames_for_player(
    match_id: str,
    puuid: str,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns all timeline frames for a specific player (by PUUID) in a match.
    The participant_id is resolved from the raw timeline JSON stored in match_timelines.
    """
    tl = db.query(MatchTimeline).filter(MatchTimeline.match_id == match_id).first()
    if not tl:
        raise HTTPException(status_code=404, detail="Timeline not found for this match.")

    # Look up participant_id from the raw timeline JSON
    participant_id = None
    if tl.raw_timeline_json:
        participants = tl.raw_timeline_json.get("participants", [])
        for p in participants:
            if p.get("puuid") == puuid:
                participant_id = p.get("participantId")
                break

    if participant_id is None:
        raise HTTPException(status_code=404, detail="Player not found in this match's timeline.")

    frames = (
        db.query(TimelineParticipantFrame)
        .filter(
            TimelineParticipantFrame.match_id == match_id,
            TimelineParticipantFrame.participant_id == participant_id,
        )
        .order_by(TimelineParticipantFrame.frame_timestamp)
        .all()
    )

    return [
        {
            "frame_timestamp": f.frame_timestamp,
            "participant_id": f.participant_id,
            "position_x": f.position_x,
            "position_y": f.position_y,
            "current_gold": f.current_gold,
            "total_gold": f.total_gold,
            "gold_per_second": f.gold_per_second,
            "xp": f.xp,
            "level": f.level,
            "minions_killed": f.minions_killed,
            "jungle_minions_killed": f.jungle_minions_killed,
        }
        for f in frames
    ]


@router.get("/{match_id}/events")
def get_timeline_events(
    match_id: str,
    event_type: Optional[str] = None,
    limit: int = 100,
    after_event_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns structured timeline events for a match with cursor-based pagination.

    Cursor pagination via after_event_id:
      - First page: omit after_event_id (or pass 0)
      - Next pages: pass the next_cursor value from the previous response
      - End of results: next_cursor is null

    Cursor uses the event_id primary key index — O(1) at any page depth regardless
    of total event count. Safe for matches with 2000+ events.

    Parameters:
      limit         — max events per page (default 100, capped at 500)
      after_event_id — cursor: return events with event_id > this value
      event_type    — optional filter (e.g. CHAMPION_KILL, BUILDING_KILL,
                       ELITE_MONSTER_KILL, ITEM_PURCHASED, LEVEL_UP, WARD_PLACED)

    Response:
      events      — list of event objects
      count       — number of events in this page
      next_cursor — pass as after_event_id on the next request; null if no more pages

    Example:
      GET /timeline/NA1_12345/events?limit=100
      GET /timeline/NA1_12345/events?limit=100&after_event_id=843
      GET /timeline/NA1_12345/events?event_type=CHAMPION_KILL&limit=500
    """
    limit = min(limit, 500)

    tl = db.query(MatchTimeline.match_id).filter(MatchTimeline.match_id == match_id).first()
    if not tl:
        raise HTTPException(
            status_code=404,
            detail="Timeline not found for this match. Re-ingest with fetch_timeline=true.",
        )

    q = db.query(TimelineEvent).filter(TimelineEvent.match_id == match_id)

    if event_type is not None:
        q = q.filter(TimelineEvent.event_type == event_type.upper())

    if after_event_id is not None:
        q = q.filter(TimelineEvent.event_id > after_event_id)

    # Fetch one extra row to determine whether a next page exists without a COUNT query.
    events = q.order_by(TimelineEvent.event_id).limit(limit + 1).all()

    has_more = len(events) > limit
    page = events[:limit]
    next_cursor = page[-1].event_id if has_more and page else None

    return {
        "events": [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "real_timestamp": e.real_timestamp,
                "type": e.event_type,
                "detail": e.raw_event_json,
            }
            for e in page
        ],
        "count": len(page),
        "next_cursor": next_cursor,
    }
