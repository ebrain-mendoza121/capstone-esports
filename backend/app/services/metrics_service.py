from sqlalchemy.orm import Session

from app.models.participant_stats import ParticipantStats
from app.models.match import Match
from app.models.player import Player


def get_player_metrics(session: Session, puuid: str):
    """Aggregate performance stats for a player across all stored matches."""
    stats = (
        session.query(ParticipantStats, Match)
        .join(Match, Match.match_id == ParticipantStats.match_id)
        .join(Player, Player.id == ParticipantStats.player_id)
        .filter(Player.puuid == puuid)
        .all()
    )

    if not stats:
        return None

    total_kills = total_deaths = total_assists = 0
    total_cs = total_gold = total_vision = 0
    total_minutes = 0.0
    total_wins = 0

    for ps, match in stats:
        minutes = match.game_duration / 60.0 if match.game_duration else 0.0
        total_kills += ps.kills
        total_deaths += ps.deaths
        total_assists += ps.assists
        total_cs += ps.cs
        total_gold += ps.gold_earned
        total_vision += ps.vision_score
        total_minutes += minutes
        total_wins += 1 if ps.win else 0

    matches_played = len(stats)
    kda = (
        (total_kills + total_assists) / total_deaths
        if total_deaths > 0
        else float(total_kills + total_assists)
    )

    return {
        "matches": matches_played,
        "win_rate": round(total_wins / matches_played, 4),
        "kda": round(kda, 2),
        "cs_per_min": round(total_cs / total_minutes, 2) if total_minutes else 0.0,
        "gold_per_min": round(total_gold / total_minutes, 2) if total_minutes else 0.0,
        "vision_per_min": round(total_vision / total_minutes, 2) if total_minutes else 0.0,
    }
