from typing import Tuple, List
from sqlalchemy.orm import Session
import logging

from app.schemas.ingest import PLATFORM_TO_ROUTING, Platform
from app.db.crud_ingest import upsert_player, match_exists, insert_match_bundle_for_player
from app.services.riot_client import RiotClient

# Set up logger
logger = logging.getLogger(__name__)

# Queue IDs for ranked games
RANKED_SOLO_QUEUE = 420  # Ranked Solo/Duo
RANKED_FLEX_QUEUE = 440  # Ranked Flex


async def ingest_player(
    session: Session,
    game_name: str,
    tag_line: str,
    platform: str,
    count: int = 20,
    queue: int = RANKED_SOLO_QUEUE,  # Default to ranked solo/duo
) -> Tuple[str, str, str, int, int, List[str]]:
    """
    Ingest a player and their match history.
    
    Args:
        session: Database session
        game_name: Riot ID game name
        tag_line: Riot ID tag line
        platform: Platform region (NA, EUW, KR, etc.)
        count: Number of matches to fetch
        queue: Queue ID filter (default: 420 for Ranked Solo/Duo)
        
    Returns:
        Tuple of (puuid, platform, routing, inserted, skipped, failed_matches)
    """
    # Convert platform to routing
    platform_enum = Platform(platform)
    routing = PLATFORM_TO_ROUTING[platform_enum]
    
    # Create client (no longer needs routing in constructor)
    client = RiotClient()

    # Get PUUID with routing
    puuid = await client.get_puuid(game_name, tag_line, routing)

    player = upsert_player(
        session=session,
        puuid=puuid,
        riot_id=game_name,
        tag_line=tag_line,
        routing=routing,  # Store routing value in players.region
    )

    # Get match IDs with routing and queue filter
    logger.info(f"Fetching match IDs for {game_name}#{tag_line} - routing={routing}, queue={queue}, count={count}")
    match_ids = await client.get_match_ids(
        puuid, 
        routing=routing, 
        count=count,
        queue=queue  # Filter for specific queue (ranked by default)
    )
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
                # Get match details with routing
                match_json = await client.get_match(match_id, routing)
                insert_match_bundle_for_player(
                    session=session,
                    match_json=match_json,
                    tracked_puuid=puuid,
                    player_id=player.id,
                )
                inserted += 1
            except Exception as e:
                # keep going, but don't poison the whole transaction
                logger.error(f"Failed to ingest match {match_id}: {e}")
                session.rollback()
                failed.append(match_id)

        # one commit for everything that succeeded
        session.commit()

    except Exception:
        session.rollback()
        raise

    return puuid, platform, routing, inserted, skipped, failed