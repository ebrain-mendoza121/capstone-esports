from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text
from typing import Optional

from app.db.session import get_db
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.derived_metrics import DerivedMetrics
from app.models.team_bans import TeamBans
from app.models.draft_actions import DraftActions
from app.models.participant_perks import ParticipantPerks
from app.services.riot_client import RiotClient
from app.services.derived_metrics_calculator import (
    compute_derived_metrics,
    extract_team_participants,
    normalize_game_duration,
)
from app.models.match_timeline import MatchTimeline
from app.db.crud_ingest import (
    insert_draft_actions,
    insert_participant_perks,
    insert_timeline,
)

router = APIRouter(prefix="/backfill", tags=["backfill"])


@router.post("/derived")
def backfill_derived_metrics(
    puuid: Optional[str] = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """
    Backfill derived metrics for matches that are missing them.
    Pass `puuid` to limit to a single player; omit to run globally.

    Computes entirely from data already stored in participant_stats and
    matches — no Riot API calls are made, so there is no rate-limit risk.

    Performance: uses two bulk SELECTs + one bulk INSERT … ON CONFLICT DO UPDATE
    regardless of how many rows are processed (no N+1 queries).
    """
    # ------------------------------------------------------------------
    # Step 1 — find (match_id, game_duration, player_id, puuid) combos
    #           that are missing a derived_metrics row.
    # ------------------------------------------------------------------
    query = (
        db.query(Match.match_id, Match.game_duration, ParticipantStats.player_id, Player.puuid)
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

    limit = min(limit, 5000)
    missing_records = query.limit(limit).all()

    if not missing_records:
        return {
            "status": "success",
            "message": "No missing derived metrics found",
            "processed": 0,
            "failed": 0,
            "failed_matches": [],
        }

    # ------------------------------------------------------------------
    # Step 2 — bulk-load ALL participant_stats for every affected match
    #           in a single IN query, then group by match_id in Python.
    # ------------------------------------------------------------------
    unique_match_ids = list({r.match_id for r in missing_records})
    all_ps_rows = (
        db.query(ParticipantStats)
        .filter(ParticipantStats.match_id.in_(unique_match_ids))
        .all()
    )

    from collections import defaultdict
    ps_by_match: dict = defaultdict(list)
    for ps in all_ps_rows:
        ps_by_match[ps.match_id].append(ps)

    def _ps_to_dict(ps: ParticipantStats) -> dict:
        return {
            "kills":                       ps.kills or 0,
            "deaths":                      ps.deaths or 0,
            "assists":                     ps.assists or 0,
            "goldEarned":                  ps.gold_earned or 0,
            "totalDamageDealtToChampions": ps.total_damage or 0,
            "visionScore":                 ps.vision_score or 0,
            "totalMinionsKilled":          ps.total_minions_killed or 0,
            "neutralMinionsKilled":        ps.neutral_minions_killed or 0,
            "teamId":                      ps.team_id or 0,
            "teamPosition":                ps.role,
        }

    # ------------------------------------------------------------------
    # Step 3 — compute metrics in Python (pure CPU, no DB round-trips).
    # ------------------------------------------------------------------
    rows_to_insert: list[dict] = []
    failed = 0
    failed_matches: list[str] = []

    for match_id, game_duration_seconds, player_id, player_puuid in missing_records:
        try:
            all_ps = ps_by_match.get(match_id, [])
            target = next((p for p in all_ps if p.player_id == player_id), None)
            if not target:
                failed += 1
                failed_matches.append(f"{match_id}: player_id {player_id} not found")
                continue

            participant_dict = _ps_to_dict(target)
            team_id = target.team_id or 0
            team_dicts = [_ps_to_dict(p) for p in all_ps if (p.team_id or 0) == team_id]

            metrics = compute_derived_metrics(
                participant_dict,
                team_dicts,
                game_duration_seconds or 0,
            )
            rows_to_insert.append({"match_id": match_id, "puuid": player_puuid, **metrics})

        except Exception as exc:
            failed += 1
            failed_matches.append(f"{match_id}: {exc}")

    # ------------------------------------------------------------------
    # Step 4 — bulk INSERT … ON CONFLICT DO UPDATE.
    #
    # Two problems to avoid:
    #  a) psycopg3 executemany pipelines rows individually → cumulative
    #     wall-time trips PostgreSQL's statement_timeout.
    #  b) A single 5000-row VALUES list can also be slow on large indexes.
    #
    # Fix: disable statement_timeout for this session (SET LOCAL only
    # affects the current transaction), then insert in chunks of 500
    # using the Core Table (not the ORM class) so SQLAlchemy emits one
    # true multi-row INSERT … VALUES (…),(…),… per chunk — not executemany.
    # ------------------------------------------------------------------
    processed = 0
    if rows_to_insert:
        metrics_keys = [k for k in rows_to_insert[0] if k not in ("match_id", "puuid")]
        _table = DerivedMetrics.__table__

        # Lift the PG statement timeout for this transaction only.
        db.execute(text("SET LOCAL statement_timeout = 0"))

        chunk_size = 500
        for i in range(0, len(rows_to_insert), chunk_size):
            chunk = rows_to_insert[i : i + chunk_size]
            stmt = insert(_table).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_derived_metrics_match_puuid",
                set_={k: stmt.excluded[k] for k in metrics_keys},
            )
            db.execute(stmt)

        db.commit()
        processed = len(rows_to_insert)

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


@router.post("/participant-perks")
async def backfill_participant_perks(
    puuid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Backfill participant_perks for matches that have participant_stats but no perks row.
    Re-fetches match JSON from Riot API for each missing record.
    Omit `puuid` to run globally.
    """
    has_perks_subq = (
        db.query(ParticipantPerks.match_id, ParticipantPerks.player_id)
        .subquery()
    )

    missing_q = (
        db.query(
            ParticipantStats.match_id,
            ParticipantStats.player_id,
            Player.puuid,
            Player.region,
        )
        .join(Player, Player.id == ParticipantStats.player_id)
        .outerjoin(
            has_perks_subq,
            (has_perks_subq.c.match_id == ParticipantStats.match_id)
            & (has_perks_subq.c.player_id == ParticipantStats.player_id),
        )
        .filter(has_perks_subq.c.match_id == None)  # noqa: E711
        .order_by(ParticipantStats.match_id)
    )

    if puuid:
        missing_q = missing_q.filter(Player.puuid == puuid)

    records = missing_q.all()

    if not records:
        return {
            "status": "success",
            "message": "No matches missing participant perks",
            "processed": 0,
            "failed": 0,
            "failed_matches": [],
        }

    client = RiotClient()
    processed = 0
    failed = 0
    failed_matches = []

    for match_id, player_id, player_puuid, routing in records:
        try:
            match_json = await client.get_match(match_id, routing)
            info = match_json["info"]
            all_participants = info.get("participants", [])
            participant = next(
                (p for p in all_participants if p.get("puuid") == player_puuid), None
            )
            if not participant:
                failed += 1
                failed_matches.append(match_id)
                continue
            insert_participant_perks(db, match_id, player_id, participant)
            processed += 1
        except Exception:
            failed += 1
            failed_matches.append(match_id)

    db.commit()

    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Backfilled participant perks for {processed} records",
        "processed": processed,
        "failed": failed,
        "failed_matches": failed_matches[:10],
    }


@router.get("/participant-perks/status")
def participant_perks_status(db: Session = Depends(get_db)):
    """Coverage report for participant_perks."""
    total = db.query(ParticipantStats).count()
    with_perks = db.query(ParticipantPerks).count()
    missing = total - with_perks
    coverage = (with_perks / total * 100) if total > 0 else 0.0
    return {
        "total_participant_stats": total,
        "with_perks": with_perks,
        "missing_perks": missing,
        "coverage_percentage": round(coverage, 2),
    }


@router.post("/timeline")
async def backfill_timeline(
    puuid: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Backfill timeline data (match_timelines, timeline_participant_frames, timeline_events)
    for matches that were ingested without fetch_timeline=True.

    - Queries matches that have no row in match_timelines.
    - Optionally scope to a single player by passing `puuid`.
    - `limit` controls how many matches are processed per call (default 20, max 100).
    - Skips matches that already have timeline data (insert_timeline is idempotent).
    - Continues on per-match failures; reports them in failed_matches.
    """
    limit = min(limit, 100)

    # Sub-query: match_ids that already have timeline data
    has_timeline_subq = db.query(MatchTimeline.match_id).subquery()

    # Find matches without timeline, with one routing region to re-fetch
    missing_q = (
        db.query(Match.match_id, Player.region)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .filter(Match.match_id.notin_(db.query(has_timeline_subq.c.match_id)))
        .order_by(Match.game_creation.desc())
        .distinct(Match.match_id)
    )

    if puuid:
        missing_q = missing_q.filter(Player.puuid == puuid)

    records = missing_q.limit(limit).all()

    if not records:
        return {
            "status": "success",
            "message": "No matches missing timeline data",
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "failed_matches": [],
        }

    client = RiotClient()
    processed = 0
    skipped = 0
    failed = 0
    failed_matches = []

    for match_id, routing in records:
        try:
            timeline_json = await client.get_match_timeline(match_id, routing)
            insert_timeline(db, match_id, timeline_json)
            db.commit()
            processed += 1
        except Exception as exc:
            db.rollback()
            failed += 1
            failed_matches.append(f"{match_id}: {exc}")

    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Backfilled timeline for {processed} matches",
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "failed_matches": failed_matches[:10],
    }


@router.get("/timeline/status")
def timeline_backfill_status(puuid: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Coverage report for match_timelines.
    Shows how many ingested matches have timeline data.
    Optionally scope to a single player by passing `puuid`.
    """
    total_q = db.query(Match.match_id)
    if puuid:
        total_q = (
            total_q
            .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
            .join(Player, Player.id == ParticipantStats.player_id)
            .filter(Player.puuid == puuid)
        )
    total_matches = total_q.distinct().count()

    with_timeline_q = db.query(MatchTimeline.match_id)
    if puuid:
        with_timeline_q = (
            with_timeline_q
            .join(Match, Match.match_id == MatchTimeline.match_id)
            .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
            .join(Player, Player.id == ParticipantStats.player_id)
            .filter(Player.puuid == puuid)
        )
    with_timeline = with_timeline_q.distinct().count()

    missing = total_matches - with_timeline
    coverage = (with_timeline / total_matches * 100) if total_matches > 0 else 0.0

    return {
        "total_matches": total_matches,
        "with_timeline": with_timeline,
        "missing_timeline": missing,
        "coverage_percentage": round(coverage, 2),
    }
