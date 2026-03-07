from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_db
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.derived_metrics import DerivedMetrics
from app.models.draft_actions import DraftActions, ActionType, DraftPhase
from app.services.riot_client import RiotClient
from app.services.derived_metrics_calculator import (
    compute_derived_metrics,
    extract_team_participants,
    normalize_game_duration,
)

router = APIRouter(prefix="/backfill", tags=["backfill"])

# Keep it local here to avoid circular imports; or import from your ingest module.
ROLE_TURN = {
    "TOP": 1,
    "JUNGLE": 2,
    "MIDDLE": 3,
    "BOTTOM": 4,
    "UTILITY": 5,
}


@router.post("/derived")
async def backfill_derived_metrics(
    puuid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Backfill derived metrics for matches that don't have them yet.
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
        }

    client = RiotClient()
    processed = 0
    failed = 0
    failed_matches: list[dict] = []

    for match_id, _player_id, player_puuid, player_routing in missing_records:
        try:
            match_json = await client.get_match(match_id, player_routing)
            info = match_json["info"]

            game_duration_seconds = normalize_game_duration(info)
            all_participants = info.get("participants", [])

            participant = next((p for p in all_participants if p.get("puuid") == player_puuid), None)
            if not participant:
                failed += 1
                failed_matches.append({"match_id": match_id, "error": "Tracked participant not found"})
                continue

            team_id = participant.get("teamId", 0)
            team_participants = extract_team_participants(all_participants, team_id)
            metrics = compute_derived_metrics(participant, team_participants, game_duration_seconds)

            stmt = insert(DerivedMetrics).values(match_id=match_id, puuid=player_puuid, **metrics)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_derived_metrics_match_puuid",
                set_=metrics,
            )
            db.execute(stmt)
            processed += 1

        except Exception as e:
            failed += 1
            failed_matches.append({"match_id": match_id, "error": str(e)})
            continue

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
    Check how many matches are missing derived metrics.
    """
    total_query = db.query(ParticipantStats).join(Player, Player.id == ParticipantStats.player_id)
    if puuid:
        total_query = total_query.filter(Player.puuid == puuid)
    total_matches = total_query.count()

    with_metrics_query = db.query(DerivedMetrics)
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
        "meets_95_percent_goal": coverage >= 95.0,
    }


@router.post("/draft-actions")
async def backfill_draft_actions(
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Backfill draft_actions for matches that don't have them yet.

    Key fixes vs your version:
      - Only backfills draft-capable queues (420/440) by default.
      - Guards against missing pickTurn for bans.
      - Inserts PICK rows even when role/teamPosition is missing using unique fallback turns.
      - Only counts a match "processed" if it inserted at least 1 row.
    """
    # Only target queues where draft data is expected (ranked solo/flex).
    draft_queues = [420, 440]

    # Find matches missing draft_actions, with at least one player's routing for API calls.
    query = (
        db.query(Match.match_id, Player.region)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .outerjoin(DraftActions, DraftActions.match_id == Match.match_id)
        .filter(DraftActions.id == None)  # noqa: E711
        .filter(Match.queue_id.in_(draft_queues))
        .distinct(Match.match_id)
    )

    if limit:
        query = query.limit(limit)

    missing_matches = query.all()
    if not missing_matches:
        return {
            "status": "success",
            "message": "No matches missing draft_actions found (for queues 420/440)",
            "processed": 0,
            "failed": 0,
        }

    client = RiotClient()
    processed = 0
    failed = 0
    failed_matches: list[dict] = []

    for match_id, routing in missing_matches:
        try:
            match_json = await client.get_match(match_id, routing)
            info = match_json.get("info", {})

            # Delete any existing draft_actions for this match (re-runs safe).
            db.query(DraftActions).filter(DraftActions.match_id == match_id).delete()

            teams = info.get("teams", []) or []
            participants = info.get("participants", []) or []

            ban_count = 0
            pick_count = 0

            # -------- BANS ----------
            for team in teams:
                team_id = team.get("teamId")
                for ban in (team.get("bans", []) or []):
                    champion_id = ban.get("championId")
                    pick_turn = ban.get("pickTurn")

                    # -1 means no ban; pick_turn can be None in some modes
                    if champion_id in (None, -1):
                        continue
                    if not pick_turn:
                        continue
                    if team_id not in (100, 200):
                        continue

                    db.add(
                        DraftActions(
                            match_id=match_id,
                            team_id=int(team_id),
                            action_type=ActionType.BAN,
                            phase=DraftPhase.BAN,
                            champion_id=int(champion_id),
                            role=None,
                            turn=int(pick_turn),
                            action_order=None,
                        )
                    )
                    ban_count += 1

            # -------- PICKS ----------
            # We must avoid violating:
            # UniqueConstraint(match_id, phase, team_id, turn)
            used_turns = {100: set(), 200: set()}
            missing_role_turn = {100: 90, 200: 90}  # unique fallback turns per team

            for p in participants:
                team_id = p.get("teamId")
                champion_id = p.get("championId")
                if team_id not in (100, 200) or not champion_id:
                    continue

                # Prefer teamPosition; fallback to individualPosition
                team_position = p.get("teamPosition") or p.get("individualPosition") or ""

                # Deterministic role turn if possible, else fallback unique.
                turn = ROLE_TURN.get(team_position)
                if turn is None or turn in used_turns[team_id]:
                    turn = missing_role_turn[team_id]
                    missing_role_turn[team_id] += 1

                used_turns[team_id].add(turn)

                db.add(
                    DraftActions(
                        match_id=match_id,
                        team_id=int(team_id),
                        action_type=ActionType.PICK,
                        phase=DraftPhase.PICK,
                        champion_id=int(champion_id),
                        role=team_position if team_position else None,
                        turn=int(turn),
                        action_order=None,
                    )
                )
                pick_count += 1

            # Only count as processed if something was inserted.
            if (ban_count + pick_count) == 0:
                failed += 1
                failed_matches.append(
                    {
                        "match_id": match_id,
                        "error": "No draft data inserted (likely non-draft match JSON or missing fields)",
                        "queue_id": info.get("queueId"),
                    }
                )
                db.rollback()
                continue

            db.flush()
            processed += 1

        except Exception as e:
            failed += 1
            failed_matches.append({"match_id": match_id, "error": str(e)})
            db.rollback()
            continue

    db.commit()

    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Backfilled draft_actions for {processed} matches (queues 420/440)",
        "processed": processed,
        "failed": failed,
        "failed_matches": failed_matches[:10],
    }


@router.get("/draft-actions/status")
def draft_actions_status(db: Session = Depends(get_db)):
    """
    Check how many matches are missing draft_actions.
    """
    total_matches = db.query(Match).count()

    matches_with_draft = db.query(DraftActions.match_id).distinct().count()

    missing = total_matches - matches_with_draft
    coverage = (matches_with_draft / total_matches * 100) if total_matches > 0 else 0

    total_actions = db.query(DraftActions).count()
    total_picks = db.query(DraftActions).filter(DraftActions.action_type == ActionType.PICK).count()
    total_bans = db.query(DraftActions).filter(DraftActions.action_type == ActionType.BAN).count()

    return {
        "total_matches": total_matches,
        "matches_with_draft_actions": matches_with_draft,
        "matches_missing_draft_actions": missing,
        "coverage_percentage": round(coverage, 2),
        "total_draft_actions": total_actions,
        "total_picks": total_picks,
        "total_bans": total_bans,
        "avg_actions_per_match": round(total_actions / matches_with_draft, 2) if matches_with_draft > 0 else 0,
    }