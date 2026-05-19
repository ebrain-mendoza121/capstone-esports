"""
opponent_backfill.py — Background worker that promotes stub opponents to
fully-ingested players.

When a player is ingested, every participant in their matches is stored as a
stub `Player` row (riot_id + tag_line from the match payload, but no
derived_metrics / no match history of their own). This module exposes a
single in-process asyncio worker that pops stub puuids off a queue and runs
the full ingestion pipeline on them, one at a time.

Rate limiting:
    The Riot client already holds a global Semaphore(3) and handles 429
    backoff, so this worker does NOT add its own throttling. Running it
    sequentially is enough — the bottleneck is Riot, not the worker.

Cascade safety:
    The worker calls ``ingest_player`` but does NOT re-enqueue opponents
    discovered during its own runs (would otherwise crawl the entire KR
    server). Only opponents discovered from foreground ingests are queued.

State:
    Everything is in-memory. Restarting the backend clears the queue and
    history. This is intentional — the queue can be rebuilt at any time
    by re-triggering ingests, and persisting it would require a DB table
    that the project doesn't need.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.derived_metrics import DerivedMetrics
from app.models.participant_stats import ParticipantStats
from app.models.player import Player
from app.services.ingestion_service import ingest_player
from app.services.riot_client import RiotApiError, RiotClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job + worker state
# ---------------------------------------------------------------------------

@dataclass
class OpponentJob:
    puuid:    str
    platform: str          # NA, EUW, KR, ...
    count:    int = 10     # smaller default than foreground ingest
    queue_id: int = 420
    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


_queue:    "asyncio.Queue[OpponentJob]" = asyncio.Queue()
_inflight: set[str]                     = set()
_history:  deque[dict]                  = deque(maxlen=100)
_worker_task: Optional[asyncio.Task]    = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_worker() -> None:
    """Spawn the background worker if it is not already running."""
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_run_worker(), name="opponent-backfill")
    logger.info("Opponent backfill worker started.")


async def stop_worker() -> None:
    """Cancel the worker — used during shutdown."""
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except (asyncio.CancelledError, Exception):
        pass
    _worker_task = None


def get_status() -> dict:
    """Return a snapshot of queue depth and recent job history."""
    return {
        "queue_size":   _queue.qsize(),
        "inflight":     len(_inflight),
        "worker_alive": _worker_task is not None and not _worker_task.done(),
        "recent":       list(_history),
    }


def enqueue_opponents_for_puuid(
    db: Session,
    tracked_puuid: str,
    platform: str,
    count: int = 10,
) -> int:
    """
    Look up every opponent of ``tracked_puuid`` who is still a stub (no
    derived_metrics rows of their own) and queue them for background ingest.

    Returns the number of jobs enqueued (excluding duplicates and already-
    ingested opponents). Does NOT make Riot API calls — pure DB read.
    """
    # Sub-query: every match the tracked player appears in.
    tracked_matches_q = (
        select(ParticipantStats.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .where(Player.puuid == tracked_puuid)
    )

    # Sub-query: puuids that already have derived_metrics rows (fully ingested).
    ingested_puuids_q = select(DerivedMetrics.puuid).distinct()

    # Pull every other participant in those matches who is NOT already ingested.
    stub_puuids: list[str] = [
        row[0]
        for row in db.execute(
            select(Player.puuid)
            .join(ParticipantStats, ParticipantStats.player_id == Player.id)
            .where(ParticipantStats.match_id.in_(tracked_matches_q))
            .where(Player.puuid != tracked_puuid)
            .where(Player.puuid.notin_(ingested_puuids_q))
            .distinct()
        ).all()
    ]

    return enqueue_puuids(db, stub_puuids, platform, count=count)


def enqueue_puuids(
    db: Session,
    puuids: list[str],
    platform: str,
    count: int = 10,
) -> int:
    """
    Queue an arbitrary list of puuids for background ingest.

    Skips puuids that already have ``derived_metrics`` rows (fully ingested)
    and puuids that are already in flight. Returns the number of new jobs
    enqueued.
    """
    if not puuids:
        return 0

    already_ingested: set[str] = {
        row[0]
        for row in db.execute(
            select(DerivedMetrics.puuid)
            .where(DerivedMetrics.puuid.in_(puuids))
            .distinct()
        ).all()
    }

    enqueued = 0
    for puuid in puuids:
        if not puuid or puuid in already_ingested or puuid in _inflight:
            continue
        _inflight.add(puuid)
        _queue.put_nowait(OpponentJob(puuid=puuid, platform=platform, count=count))
        enqueued += 1

    if enqueued:
        logger.info("Enqueued %d background ingest jobs.", enqueued)
    return enqueued


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

async def _run_worker() -> None:
    """Single consumer — pops jobs and runs ingest_player one at a time."""
    while True:
        job: OpponentJob = await _queue.get()
        try:
            await _process_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — never let the worker die
            logger.exception("Opponent backfill crashed for %s…: %s", job.puuid[:8], exc)
            _history.appendleft({
                "puuid":    job.puuid,
                "platform": job.platform,
                "status":   "error",
                "error":    str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            _inflight.discard(job.puuid)
            _queue.task_done()


async def _process_job(job: OpponentJob) -> None:
    """
    Resolve Riot ID (from DB stub or Riot API), then run the standard
    ingestion pipeline. ``fetch_timeline=False`` to keep API quota modest —
    we only need this opponent's rolling stats, not their frame data.
    """
    db: Session = SessionLocal()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        stub = db.query(Player).filter(Player.puuid == job.puuid).one_or_none()
        game_name = (stub.riot_id   if stub else "").strip()
        tag_line  = (stub.tag_line  if stub else "").strip()

        # If the match payload didn't carry a Riot ID (older patches sometimes
        # left it blank), resolve via the by-puuid account endpoint.
        if not game_name or not tag_line:
            routing = (stub.region if stub else "americas")
            async with RiotClient() as client:
                acct = await client.get_account_by_puuid(job.puuid, routing)
            game_name = acct.get("gameName") or game_name
            tag_line  = acct.get("tagLine")  or tag_line

        if not game_name or not tag_line:
            raise RiotApiError(
                f"Could not resolve Riot ID for puuid {job.puuid[:8]}…"
            )

        puuid, _platform, _routing, inserted, skipped, failed = await ingest_player(
            session=db,
            game_name=game_name,
            tag_line=tag_line,
            platform=job.platform,
            count=job.count,
            queue=job.queue_id,
            fetch_timeline=False,
        )

        _history.appendleft({
            "puuid":       puuid,
            "riot_id":     f"{game_name}#{tag_line}",
            "platform":    job.platform,
            "status":      "success" if not failed else "partial",
            "inserted":    inserted,
            "skipped":     skipped,
            "failed":      len(failed),
            "started_at":  started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        db.close()
