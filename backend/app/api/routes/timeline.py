from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.match_timeline import MatchTimeline, TimelineParticipantFrame
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

    return {
        "match_id": match_id,
        "frame_interval_ms": tl.frame_interval,
        "end_of_game_result": tl.end_of_game_result,
        "participant_frame_rows": frame_count,
    }


@router.get("/{match_id}/frames")
def get_timeline_frames(
    match_id: str,
    participant_id: Optional[int] = None,
    limit: int = 500,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns parsed per-minute frames for a match.
    Filter by participant_id (1–10) to get a single player's journey.
    Ordered by frame_timestamp ASC.
    Data includes position (x/y), gold, XP, level, CS per frame — 
    the foundation for heatmaps and early-game AI features.
    """
    tl = db.query(MatchTimeline).filter(MatchTimeline.match_id == match_id).first()
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
