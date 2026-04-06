import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_player_metrics(session: Session, puuid: str):
    """Aggregate performance stats for a player across all stored matches.

    Queries the pre-computed ``derived_metrics`` table for all per-match KPIs
    (KDA, CS/min, gold/min, kill participation, damage share, vision/min) and
    joins ``participant_stats`` for win/loss data.  Falls back to raw
    participant-stats aggregation if no derived-metrics rows exist yet for this
    player (e.g. before a backfill has been run).
    """
    # ---- Primary path: use pre-computed derived_metrics ----
    row = session.execute(
        text("""
            SELECT
                COUNT(*)                                            AS matches,
                ROUND(AVG(ps.win::int)::numeric, 4)                AS win_rate,
                ROUND(AVG(dm.kda)::numeric, 2)                     AS kda,
                ROUND(AVG(dm.cs_per_min)::numeric, 2)              AS cs_per_min,
                ROUND(AVG(dm.gold_per_min)::numeric, 2)            AS gold_per_min,
                ROUND(AVG(dm.vision_per_min)::numeric, 2)          AS vision_per_min,
                ROUND(AVG(dm.kill_participation)::numeric, 4)      AS kill_participation,
                ROUND(AVG(dm.damage_share)::numeric, 4)            AS damage_share
            FROM derived_metrics dm
            JOIN players p        ON p.puuid = dm.puuid
            JOIN participant_stats ps
                ON ps.match_id = dm.match_id AND ps.player_id = p.id
            WHERE dm.puuid = :puuid
        """),
        {"puuid": puuid},
    ).mappings().first()

    if row and row["matches"]:
        return {
            "matches":            int(row["matches"]),
            "win_rate":           float(row["win_rate"]           or 0),
            "kda":                float(row["kda"]                or 0),
            "cs_per_min":         float(row["cs_per_min"]         or 0),
            "gold_per_min":       float(row["gold_per_min"]       or 0),
            "vision_per_min":     float(row["vision_per_min"]     or 0),
            "kill_participation": float(row["kill_participation"] or 0),
            "damage_share":       float(row["damage_share"]       or 0),
        }

    # ---- Fallback path: aggregate from raw participant_stats ----
    # Used when derived_metrics rows are absent (e.g. legacy data before backfill).
    logger.warning(
        "No derived_metrics rows found for puuid=%s — falling back to raw aggregation. "
        "Run POST /backfill/derived to populate pre-computed metrics.",
        puuid,
    )
    from app.models.participant_stats import ParticipantStats
    from app.models.match import Match
    from app.models.player import Player

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
        total_kills    += ps.kills
        total_deaths   += ps.deaths
        total_assists  += ps.assists
        total_cs       += ps.cs
        total_gold     += ps.gold_earned
        total_vision   += ps.vision_score
        total_minutes  += minutes
        total_wins     += 1 if ps.win else 0

    matches_played = len(stats)
    kda = (
        (total_kills + total_assists) / total_deaths
        if total_deaths > 0
        else float(total_kills + total_assists)
    )

    return {
        "matches":            matches_played,
        "win_rate":           round(total_wins / matches_played, 4),
        "kda":                round(kda, 2),
        "cs_per_min":         round(total_cs / total_minutes, 2) if total_minutes else 0.0,
        "gold_per_min":       round(total_gold / total_minutes, 2) if total_minutes else 0.0,
        "vision_per_min":     round(total_vision / total_minutes, 2) if total_minutes else 0.0,
        "kill_participation": 0.0,  # not available from raw stats alone
        "damage_share":       0.0,  # not available from raw stats alone
    }
