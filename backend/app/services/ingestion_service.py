import asyncio
from typing import Tuple, List
from sqlalchemy.orm import Session
import logging

from app.schemas.ingest import PLATFORM_TO_ROUTING, Platform
from app.services.riot_client import RiotClient
from app.db.crud_ingest import (
    upsert_player,
    match_exists,
    insert_match_bundle_for_player,
    insert_timeline,
)

logger = logging.getLogger(__name__)

RANKED_SOLO_QUEUE = 420


async def ingest_player(
    session: Session,
    game_name: str,
    tag_line: str,
    platform: str,
    count: int = 20,
    queue: int = RANKED_SOLO_QUEUE,
    fetch_timeline: bool = False,
) -> Tuple[str, str, str, int, int, List[str]]:
    """
    Ingest a player and their match history (all 6 DB tables).

    Match-detail calls are fetched concurrently in batches of 5 to cut
    wall-clock time from ~60s to ~10-15s for a 20-match ingest.
    A single shared httpx client is used throughout - no per-request
    TCP handshake overhead.

    Returns: (puuid, platform, routing, inserted, skipped, failed_ids)
    """
    platform_enum = Platform(platform)
    routing = PLATFORM_TO_ROUTING[platform_enum]

    tag = f"{game_name}#{tag_line}"

    # One client for the full ingest - connection pool shared across calls
    async with RiotClient() as client:

        print(f"[ingest] {tag} - resolving PUUID ...", flush=True)
        puuid = await client.get_puuid(game_name, tag_line, routing)

        player = upsert_player(
            session=session,
            puuid=puuid,
            riot_id=game_name,
            tag_line=tag_line,
            routing=routing,
        )
        session.commit()
        session.refresh(player)

        print(f"[ingest] {tag} - fetching match list ...", flush=True)
        all_match_ids = await client.get_match_ids(
            puuid, routing=routing, count=count, queue=queue
        )
        print(f"[ingest] {tag} - found {len(all_match_ids)} match IDs", flush=True)

        # Split into already-stored (skip) vs new (fetch concurrently)
        new_ids: List[str] = []
        skipped = 0
        for mid in all_match_ids:
            if match_exists(session, mid):
                skipped += 1
            else:
                new_ids.append(mid)

        total_new = len(new_ids)
        print(
            f"[ingest] {tag} - {total_new} new / {skipped} already in DB",
            flush=True,
        )

        inserted = 0
        failed: List[str] = []

        if not new_ids:
            print(f"[ingest] {tag} - nothing to fetch, done.", flush=True)
            return puuid, platform, routing, inserted, skipped, failed

        # Fetch all new match JSONs concurrently
        print(f"[ingest] {tag} - fetching {total_new} matches ...", flush=True)
        match_jsons = await client.get_matches_concurrent(new_ids, routing)

        # Insert sequentially (DB writes are fast; API was the bottleneck)
        for idx, match_id in enumerate(new_ids, 1):
            result = match_jsons.get(match_id)
            if isinstance(result, Exception):
                print(
                    f"[ingest] {tag} - [{idx}/{total_new}] FETCH ERROR {match_id}: {result}",
                    flush=True,
                )
                logger.error("Failed to fetch match %s: %s", match_id, result)
                failed.append(match_id)
                continue

            try:
                insert_match_bundle_for_player(
                    session=session,
                    match_json=result,
                    tracked_puuid=puuid,
                    player_id=player.id,
                    routing=routing,
                )

                if fetch_timeline:
                    try:
                        timeline_json = await client.get_match_timeline(
                            match_id, routing
                        )
                        insert_timeline(
                            session=session,
                            match_id=match_id,
                            timeline_json=timeline_json,
                        )
                    except Exception as te:
                        logger.warning(
                            "Timeline fetch failed for %s: %s", match_id, te
                        )

                inserted += 1
                print(
                    f"[ingest] {tag} - [{idx}/{total_new}] saved {match_id}",
                    flush=True,
                )

            except Exception as exc:
                print(
                    f"[ingest] {tag} - [{idx}/{total_new}] SKIP {match_id}: {exc}",
                    flush=True,
                )
                logger.warning("Failed to insert match %s: %s", match_id, exc)
                session.rollback()
                failed.append(match_id)

        try:
            session.commit()
        except Exception as exc:
            logger.error("Final commit failed: %s", exc)
            session.rollback()
            raise

        print(
            f"[ingest] {tag} - DONE. inserted={inserted} skipped={skipped} failed={len(failed)}",
            flush=True,
        )

    return puuid, platform, routing, inserted, skipped, failed
