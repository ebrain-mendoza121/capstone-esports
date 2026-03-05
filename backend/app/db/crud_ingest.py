from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
import logging

from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.team_objectives import TeamObjectives
from app.models.team_bans import TeamBans
from app.models.derived_metrics import DerivedMetrics
from app.services.derived_metrics_calculator import (
    compute_derived_metrics, 
    extract_team_participants,
    normalize_game_duration
)

# Set up logger
logger = logging.getLogger(__name__)


def upsert_player(session: Session, puuid: str, riot_id: str, tag_line: str, routing: str) -> Player:
    """
    Insert or update a player record.
    
    Args:
        session: Database session
        puuid: Player's unique identifier
        riot_id: Riot ID game name
        tag_line: Riot ID tag line
        routing: Regional routing value (americas, europe, asia, sea)
        
    Returns:
        Player object
        
    Note:
        Region field stores the routing value (not the platform).
        Updates all fields on every call to keep data fresh.
    """
    player = session.query(Player).filter(Player.puuid == puuid).one_or_none()
    if player:
        # Keep info fresh - update every time (simple approach)
        player.riot_id = riot_id
        player.tag_line = tag_line
        player.region = routing  # Store routing value
        session.flush()
        return player

    player = Player(puuid=puuid, riot_id=riot_id, tag_line=tag_line, region=routing)
    session.add(player)
    session.flush()
    return player


def match_exists(session: Session, match_id: str) -> bool:
    return session.query(Match).filter(Match.match_id == match_id).first() is not None


def insert_match_bundle_for_player(session: Session, match_json: dict, tracked_puuid: str, player_id: int) -> None:
    info = match_json["info"]
    match_id = match_json["metadata"]["matchId"]
    
    # Normalize game duration (handles patch 11.20 change)
    game_duration_seconds = normalize_game_duration(info)

    # Insert match
    m = Match(
        match_id=match_id,
        game_creation=info.get("gameCreation", 0),
        game_duration=game_duration_seconds,  # Store normalized seconds
        queue_id=info.get("queueId", 0),
        patch_version=info.get("gameVersion"),
    )
    session.add(m)
    session.flush()

    # Find tracked participant
    participant = None
    all_participants = info.get("participants", [])
    for p in all_participants:
        if p.get("puuid") == tracked_puuid:
            participant = p
            break
    if participant is None:
        raise RuntimeError(f"Tracked participant not found in match {match_id}")

    team_id = participant.get("teamId", 0)
    cs = int((participant.get("totalMinionsKilled") or 0) + (participant.get("neutralMinionsKilled") or 0))

    ps = ParticipantStats(
        match_id=match_id,
        player_id=player_id,
        team_id=team_id,
        champion=participant.get("championName"),
        role=participant.get("teamPosition") or participant.get("individualPosition") or participant.get("role"),
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

    # Team objectives (2 teams)
    teams = info.get("teams", [])
    logger.info(f"Processing {len(teams)} teams for match {match_id}, queueId: {info.get('queueId')}")
    
    for t in teams:
        team_id = t.get("teamId", 0)
        obj = t.get("objectives", {})
        to = TeamObjectives(
            match_id=match_id,
            team_id=team_id,
            towers=(obj.get("tower", {}) or {}).get("kills", 0),
            dragons=(obj.get("dragon", {}) or {}).get("kills", 0),
            barons=(obj.get("baron", {}) or {}).get("kills", 0),
            win_flag=bool(t.get("win", False)),
        )
        session.add(to)
        
        # Team bans (draft phase)
        bans = t.get("bans", [])
        logger.info(f"Team {team_id} has {len(bans)} bans: {bans}")
        
        ban_count = 0
        for ban in bans:
            champion_id = ban.get("championId")
            pick_turn = ban.get("pickTurn")
            
            # championId -1 means no ban (e.g., in blind pick or ARAM)
            if champion_id and champion_id != -1:
                tb = TeamBans(
                    match_id=match_id,
                    team_id=team_id,
                    champion_id=champion_id,
                    pick_turn=pick_turn,
                )
                session.add(tb)
                ban_count += 1
        
        logger.info(f"Inserted {ban_count} bans for team {team_id}")

    # Compute and insert derived metrics using normalized duration
    team_participants = extract_team_participants(all_participants, team_id)
    metrics = compute_derived_metrics(participant, team_participants, game_duration_seconds)
    
    # Upsert derived metrics (in case of re-ingestion)
    stmt = insert(DerivedMetrics).values(
        match_id=match_id,
        puuid=tracked_puuid,
        **metrics
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_derived_metrics_match_puuid",
        set_=metrics
    )
    session.execute(stmt)
    session.flush()