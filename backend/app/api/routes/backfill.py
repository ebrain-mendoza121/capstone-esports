from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from typing import Optional

from app.db.session import get_db
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.derived_metrics import DerivedMetrics
from app.services.riot_client import RiotClient
from app.services.derived_metrics_calculator import (
    compute_derived_metrics, 
    extract_team_participants,
    normalize_game_duration
)

router = APIRouter(prefix="/backfill", tags=["backfill"])


@router.post("/derived")
async def backfill_derived_metrics(
    puuid: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Backfill derived metrics for matches that don't have them yet.
    
    Args:
        puuid: Optional - if provided, only backfill for this player
               If omitted, backfill for all players
    
    Returns:
        Summary of backfill operation
    """
    
    # Build query for matches missing derived metrics
    # Include player.region (routing) for API calls
    query = (
        db.query(Match.match_id, ParticipantStats.player_id, Player.puuid, Player.region)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .outerjoin(
            DerivedMetrics,
            (DerivedMetrics.match_id == Match.match_id) & 
            (DerivedMetrics.puuid == Player.puuid)
        )
        .filter(DerivedMetrics.id == None)  # Missing derived metrics
    )
    
    if puuid:
        query = query.filter(Player.puuid == puuid)
    
    missing_records = query.all()
    
    if not missing_records:
        return {
            "status": "success",
            "message": "No missing derived metrics found",
            "processed": 0,
            "failed": 0
        }
    
    # Fetch match details and compute metrics
    client = RiotClient()  # No routing in constructor
    processed = 0
    failed = 0
    failed_matches = []
    
    for match_id, player_id, player_puuid, player_routing in missing_records:
        try:
            # Fetch full match data from Riot API with player's routing
            match_json = await client.get_match(match_id, player_routing)
            info = match_json["info"]
            
            # Normalize game duration (handles patch 11.20 change)
            game_duration_seconds = normalize_game_duration(info)
            all_participants = info.get("participants", [])
            
            # Find the participant
            participant = None
            for p in all_participants:
                if p.get("puuid") == player_puuid:
                    participant = p
                    break
            
            if not participant:
                failed += 1
                failed_matches.append(match_id)
                continue
            
            team_id = participant.get("teamId", 0)
            team_participants = extract_team_participants(all_participants, team_id)
            metrics = compute_derived_metrics(participant, team_participants, game_duration_seconds)
            
            # Upsert derived metrics
            stmt = insert(DerivedMetrics).values(
                match_id=match_id,
                puuid=player_puuid,
                **metrics
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_derived_metrics_match_puuid",
                set_=metrics
            )
            db.execute(stmt)
            processed += 1
            
        except Exception as e:
            failed += 1
            failed_matches.append(match_id)
            continue
    
    # Commit all successful inserts
    db.commit()
    
    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Backfilled {processed} derived metrics records",
        "processed": processed,
        "failed": failed,
        "failed_matches": failed_matches[:10] if failed_matches else []  # Return first 10 failures
    }


@router.get("/status")
def backfill_status(puuid: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Check how many matches are missing derived metrics.
    
    Args:
        puuid: Optional - if provided, check only for this player
    
    Returns:
        Count of matches with and without derived metrics
    """
    
    # Total matches for player(s)
    total_query = (
        db.query(ParticipantStats)
        .join(Player, Player.id == ParticipantStats.player_id)
    )
    
    if puuid:
        total_query = total_query.filter(Player.puuid == puuid)
    
    total_matches = total_query.count()
    
    # Matches with derived metrics
    with_metrics_query = (
        db.query(DerivedMetrics)
    )
    
    if puuid:
        with_metrics_query = with_metrics_query.filter(DerivedMetrics.puuid == puuid)
    
    with_metrics = with_metrics_query.count()
    
    missing = total_matches - with_metrics
    coverage = (with_metrics / total_matches * 100) if total_matches > 0 else 0
    
    return {
        "total_matches": total_matches,
        "with_derived_metrics": with_metrics,
        "missing_derived_metrics": missing,
        "coverage_percentage": round(coverage, 2),
        "meets_95_percent_goal": coverage >= 95.0
    }
