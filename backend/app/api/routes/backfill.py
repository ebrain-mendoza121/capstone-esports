from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from typing import Optional

from app.db.session import get_db
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.derived_metrics import DerivedMetrics
from app.models.team_bans import TeamBans
from app.models.draft_actions import DraftActions
from app.services.riot_client import RiotClient
from app.services.derived_metrics_calculator import (
    compute_derived_metrics,
    extract_team_participants,
    normalize_game_duration,
)
from app.db.crud_ingest import insert_draft_actions

router = APIRouter(prefix="/backfill", tags=["backfill"])


@router.post("/derived")
async def backfill_derived_metrics(
    puuid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Backfill derived metrics for matches that are missing them.
    Pass `puuid` to limit to a single player; omit to run globally.
    """
    query = (
        db.query(Match.match_id, ParticipantStats.player_id, Player.puuid, Player.region)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .outerjoin(
            DerivedMetrics,
            (DerivedMetrics.match_id == Match.match_id)
            & (DerivedMetrics.puuid == Player.puuid),
        )
        .filter(DerivedMetrics.id == None)  # noqa: E711
    )

    if puuid:
        query = query.filter(Player.puuid == puuid)

    missing_records = query.all()

    if not missing_records:
        return {
            "status": "success",
            "message": "No missing derived metrics found",
            "processed": 0,
            "failed": 0,
            "failed_matches": [],
        }

    client = RiotClient()
    processed = 0
    failed = 0
    failed_matches = []

    for match_id, player_id, player_puuid, player_routing in missing_records:
        try:
            match_json = await client.get_match(match_id, player_routing)
            info = match_json["info"]
            game_duration_seconds = normalize_game_duration(info)
            all_participants = info.get("participants", [])

            participant = next(
                (p for p in all_participants if p.get("puuid") == player_puuid), None
            )
            if not participant:
                failed += 1
                failed_matches.append(match_id)
                continue

            team_id = participant.get("teamId", 0)
            team_participants = extract_team_participants(all_participants, team_id)
            metrics = compute_derived_metrics(participant, team_participants, game_duration_seconds)

            stmt = insert(DerivedMetrics).values(
                match_id=match_id,
                puuid=player_puuid,
                **metrics,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_derived_metrics_match_puuid",
                set_=metrics,
            )
            db.execute(stmt)
            processed += 1

        except Exception:
            failed += 1
            failed_matches.append(match_id)

    db.commit()

    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Backfilled {processed} derived metrics records",
        "processed": processed,
        "failed": failed,
        "failed_matches": failed_matches[:10],
    }


@router.get("/status")
def backfill_status(puuid: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Check derived metrics coverage.
    Pass `puuid` to scope to a specific player.
    """
    total_query = (
        db.query(ParticipantStats).join(Player, Player.id == ParticipantStats.player_id)
    )
    if puuid:
        total_query = total_query.filter(Player.puuid == puuid)
    total_matches = total_query.count()

    with_metrics_query = db.query(DerivedMetrics)
    if puuid:
        with_metrics_query = with_metrics_query.filter(DerivedMetrics.puuid == puuid)
    with_metrics = with_metrics_query.count()

    missing = total_matches - with_metrics
    coverage = (with_metrics / total_matches * 100) if total_matches > 0 else 0.0

    return {
        "total_matches": total_matches,
        "with_derived_metrics": with_metrics,
        "missing_derived_metrics": missing,
        "coverage_percentage": round(coverage, 2),
        "meets_95_percent_goal": coverage >= 95.0,
    }


@router.post("/draft-actions")
async def backfill_draft_actions(
    puuid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Backfill draft_actions for drafted matches (those with team_bans) that have
    no draft_actions rows yet. Omit `puuid` to run globally across all players.
    """
    # Find match_ids that have team_bans (i.e. drafted games) but no draft_actions yet,
    # along with one player's routing region to re-fetch the match JSON.
    has_actions_subq = db.query(DraftActions.match_id).distinct().subquery()

    missing_q = (
        db.query(Match.match_id, Player.region)
        .join(TeamBans, TeamBans.match_id == Match.match_id)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .filter(Match.match_id.notin_(db.query(has_actions_subq.c.match_id)))
        .order_by(Match.match_id)
        .distinct(Match.match_id)
    )

    if puuid:
        missing_q = missing_q.filter(Player.puuid == puuid)

    records = missing_q.all()

    if not records:
        return {
            "status": "success",
            "message": "No matches missing draft actions",
            "processed": 0,
            "failed": 0,
            "failed_matches": [],
        }

    client = RiotClient()
    processed = 0
    failed = 0
    failed_matches = []

    for match_id, routing in records:
        try:
            match_json = await client.get_match(match_id, routing)
            info = match_json["info"]
            insert_draft_actions(db, match_id, info)
            processed += 1
        except Exception:
            failed += 1
            failed_matches.append(match_id)

    db.commit()

    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Backfilled draft actions for {processed} matches",
        "processed": processed,
        "failed": failed,
        "failed_matches": failed_matches[:10],
    }


@router.get("/draft-actions/status")
def draft_actions_status(db: Session = Depends(get_db)):
    """
    Coverage report for draft_actions.
    Shows how many drafted matches (those with team_bans) have draft_actions populated.
    """
    total_drafted = (
        db.query(Match.match_id)
        .join(TeamBans, TeamBans.match_id == Match.match_id)
        .distinct()
        .count()
    )

    with_actions = (
        db.query(DraftActions.match_id)
        .distinct()
        .count()
    )

    missing = total_drafted - with_actions
    coverage = (with_actions / total_drafted * 100) if total_drafted > 0 else 0.0

    return {
        "total_drafted_matches": total_drafted,
        "with_draft_actions": with_actions,
        "missing_draft_actions": missing,
        "coverage_percentage": round(coverage, 2),
    }
