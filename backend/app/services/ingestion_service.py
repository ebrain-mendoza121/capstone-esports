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
    """Ingest a player and their full match history (all 6 tables).
    If fetch_timeline=True, also fetches and stores per-minute frame data.
    """

    platform_enum = Platform(platform)
    routing = PLATFORM_TO_ROUTING[platform_enum]

    client = RiotClient()

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

    logger.info(f"Fetching match IDs for {game_name}#{tag_line} - routing={routing}, queue={queue}, count={count}")
    match_ids = await client.get_match_ids(puuid, routing=routing, count=count, queue=queue)
    logger.info(f"Found {len(match_ids)} matches for queue {queue}")

    inserted = 0
    skipped = 0
    failed: List[str] = []

    try:
        for match_id in match_ids:
            if match_exists(session, match_id):
                skipped += 1
                continue

            try:
                match_json = await client.get_match(match_id, routing)
                insert_match_bundle_for_player(
                    session=session,
                    match_json=match_json,
                    tracked_puuid=puuid,
                    player_id=player.id,
                    routing=routing,
                )
                if fetch_timeline:
                    try:
                        timeline_json = await client.get_match_timeline(match_id, routing)
                        insert_timeline(session=session, match_id=match_id, timeline_json=timeline_json)
                    except Exception as te:
                        logger.warning(f"Timeline fetch failed for {match_id}: {te}")
                inserted += 1
            except Exception as e:
                logger.error(f"Failed to ingest match {match_id}: {e}")
                session.rollback()
                failed.append(match_id)

        session.commit()

    except Exception:
        session.rollback()
        raise

    return puuid, platform, routing, inserted, skipped, failed

