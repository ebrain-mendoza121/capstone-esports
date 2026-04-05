"""
Pure functions for computing derived metrics from match data.
These functions are stateless and easy to unit test.
"""
from typing import Dict, List, Any, Optional


def normalize_game_duration(match_info: Dict[str, Any]) -> int:
    """
    Normalize game duration to seconds, handling Riot API's patch 11.20 change.

    Riot API Behavior:
    - Patch 11.20+ (with gameEndTimestamp): gameDuration is in SECONDS
    - Pre-patch 11.20 (no gameEndTimestamp): gameDuration is in MILLISECONDS
    """
    game_duration = match_info.get("gameDuration", 0)
    game_end_timestamp = match_info.get("gameEndTimestamp")

    if game_end_timestamp is not None:
        return int(game_duration)

    return int(game_duration / 1000)


def compute_derived_metrics(
    participant: Dict[str, Any],
    team_participants: List[Dict[str, Any]],
    game_duration_seconds: int,
) -> Dict[str, Optional[float]]:
    """
    Compute derived metrics for a single participant in a match.

    Edge cases:
    - deaths = 0: KDA = (kills + assists) / 1
    - game_duration = 0: per-minute metrics = 0.0
    - team_kills = 0: kill_participation = 0.0
    - team_damage = 0: damage_share = 0.0
    """
    kills = participant.get("kills", 0)
    deaths = participant.get("deaths", 0)
    assists = participant.get("assists", 0)
    gold_earned = participant.get("goldEarned", 0)
    total_damage = participant.get("totalDamageDealtToChampions", 0)
    vision_score = participant.get("visionScore", 0)

    total_minions = participant.get("totalMinionsKilled", 0)
    neutral_minions = participant.get("neutralMinionsKilled", 0)
    cs = total_minions + neutral_minions

    game_minutes = game_duration_seconds / 60.0 if game_duration_seconds > 0 else 0.0

    kda = (kills + assists) / max(deaths, 1)

    cs_per_min = cs / game_minutes if game_minutes > 0 else 0.0
    gold_per_min = gold_earned / game_minutes if game_minutes > 0 else 0.0
    vision_per_min = vision_score / game_minutes if game_minutes > 0 else 0.0

    team_kills = sum(p.get("kills", 0) for p in team_participants)
    team_damage = sum(p.get("totalDamageDealtToChampions", 0) for p in team_participants)

    kill_participation = (kills + assists) / team_kills if team_kills > 0 else 0.0
    damage_share = total_damage / team_damage if team_damage > 0 else 0.0

    # Role: prefer teamPosition (most accurate), fall back to individualPosition / role
    role = (
        participant.get("teamPosition")
        or participant.get("individualPosition")
        or participant.get("role")
        or None
    )
    # Normalise to uppercase; discard non-canonical values (e.g. "Invalid", "")
    _VALID_ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
    if role:
        role = role.upper().strip()
        if role not in _VALID_ROLES:
            role = None

    return {
        "role": role,
        "kda": round(kda, 2),
        "cs_per_min": round(cs_per_min, 2),
        "gold_per_min": round(gold_per_min, 2),
        "kill_participation": round(kill_participation, 4),
        "damage_share": round(damage_share, 4),
        "vision_per_min": round(vision_per_min, 2),
    }


def extract_team_participants(
    all_participants: List[Dict[str, Any]],
    team_id: int,
) -> List[Dict[str, Any]]:
    """Filter participants by team ID."""
    return [p for p in all_participants if p.get("teamId") == team_id]
