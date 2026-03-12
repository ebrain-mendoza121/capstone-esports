from typing import Tuple, List
from sqlalchemy.orm import Session
import logging

from app.schemas.ingest import PLATFORM_TO_ROUTING, Platform
from app.services.riot_client import RiotClient
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.team_objectives import TeamObjectives

logger = logging.getLogger(__name__)

RANKED_SOLO_QUEUE = 420


def normalize_game_duration(match_info: dict) -> int:
    """Normalize game duration to seconds."""
    game_duration = match_info.get("gameDuration", 0)
    game_end_timestamp = match_info.get("gameEndTimestamp")
    
    if game_end_timestamp is not None:
        return int(game_duration)
    
    return int(game_duration / 1000)


async def ingest_player(
    session: Session,
    game_name: str,
    tag_line: str,
    platform: str,
    count: int = 20,
    queue: int = RANKED_SOLO_QUEUE,
) -> Tuple[str, str, str, int, int, List[str]]:
    """Ingest a player and their match history (simplified - only players, matches, participant_stats, team_objectives)."""
    
    platform_enum = Platform(platform)
    routing = PLATFORM_TO_ROUTING[platform_enum]
    
    client = RiotClient()

    # Get PUUID
    puuid = await client.get_puuid(game_name, tag_line, routing)

    # Upsert player
    player = session.query(Player).filter(Player.puuid == puuid).one_or_none()
    if player:
        player.riot_id = game_name
        player.tag_line = tag_line
        player.region = routing
    else:
        player = Player(puuid=puuid, riot_id=game_name, tag_line=tag_line, region=routing)
        session.add(player)
    
    # Commit player first so it's available for all matches
    session.commit()
    session.refresh(player)

    # Get match IDs
    logger.info(f"Fetching match IDs for {game_name}#{tag_line} - routing={routing}, queue={queue}, count={count}")
    match_ids = await client.get_match_ids(puuid, routing=routing, count=count, queue=queue)
    logger.info(f"Found {len(match_ids)} matches for queue {queue}")

    inserted = 0
    skipped = 0
    failed: List[str] = []

    for match_id in match_ids:
        # Check if match exists
        if session.query(Match).filter(Match.match_id == match_id).first():
            skipped += 1
            continue

        try:
            # Get match details
            match_json = await client.get_match(match_id, routing)
            info = match_json["info"]
            
            # Normalize game duration
            game_duration_seconds = normalize_game_duration(info)

            # Insert match
            match = Match(
                match_id=match_id,
                game_creation=info.get("gameCreation", 0),
                game_duration=game_duration_seconds,
                queue_id=info.get("queueId", 0),
                patch_version=info.get("gameVersion"),
            )
            session.add(match)
            session.flush()

            # Find tracked participant
            all_participants = info.get("participants", [])
            participant = None
            for p in all_participants:
                if p.get("puuid") == puuid:
                    participant = p
                    break
            
            if not participant:
                logger.warning(f"Tracked participant not found in match {match_id}")
                session.rollback()
                failed.append(match_id)
                continue

            team_id = participant.get("teamId", 0)
            cs = int((participant.get("totalMinionsKilled") or 0) + (participant.get("neutralMinionsKilled") or 0))

            # Insert participant stats
            ps = ParticipantStats(
                match_id=match_id,
                player_id=player.id,
                team_id=team_id,
                champion=participant.get("championName"),
                role=participant.get("teamPosition") or participant.get("individualPosition"),
                kills=participant.get("kills", 0),
                deaths=participant.get("deaths", 0),
                assists=participant.get("assists", 0),
                gold_earned=participant.get("goldEarned", 0),
                total_damage=participant.get("totalDamageDealtToChampions", 0),
                cs=cs,
                vision_score=participant.get("visionScore", 0),
                win=participant.get("win"),
            )
            session.add(ps)

            # Insert team objectives
            teams = info.get("teams", [])
            for t in teams:
                team_id_obj = t.get("teamId", 0)
                obj = t.get("objectives", {})
                to = TeamObjectives(
                    match_id=match_id,
                    team_id=team_id_obj,
                    towers=(obj.get("tower", {}) or {}).get("kills", 0),
                    dragons=(obj.get("dragon", {}) or {}).get("kills", 0),
                    barons=(obj.get("baron", {}) or {}).get("kills", 0),
                    win_flag=bool(t.get("win", False)),
                )
                session.add(to)

            # Commit this match
            session.commit()
            inserted += 1
            
        except Exception as e:
            logger.error(f"Failed to ingest match {match_id}: {e}")
            session.rollback()
            failed.append(match_id)

    return puuid, platform, routing, inserted, skipped, failed
