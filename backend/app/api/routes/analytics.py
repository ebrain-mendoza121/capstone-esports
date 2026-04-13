import logging
import time
from typing import Dict, List, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text

from app.db.session import get_db
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.team_bans import TeamBans
from app.models.participant_perks import ParticipantPerks
from app.services.ddragon import get_champion_map, get_rune_map
from app.services.feature_extractor import get_rolling_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/player/{puuid}/bans")
async def get_player_bans(
    puuid: str,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ban analytics for a player's recent matches.
    Returns bans by the player's team and bans against it (enemy team),
    plus top-10 most banned champions in each category.
    """
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    player_matches = (
        db.query(ParticipantStats.match_id, ParticipantStats.team_id)
        .filter(ParticipantStats.player_id == player.id)
        .join(Match, Match.match_id == ParticipantStats.match_id)
        .order_by(Match.game_creation.desc())
        .limit(limit)
        .all()
    )

    if not player_matches:
        return {
            "puuid": puuid,
            "matches_analyzed": 0,
            "bans_against": [],
            "bans_by_team": [],
            "most_banned_against": [],
            "most_banned_by_team": [],
            "total_bans_against": 0,
            "total_bans_by_team": 0,
        }

    match_ids = [m.match_id for m in player_matches]
    match_teams = {m.match_id: m.team_id for m in player_matches}

    all_bans = (
        db.query(TeamBans).filter(TeamBans.match_id.in_(match_ids)).all()
    )

    champion_map = await get_champion_map()
    bans_against = []
    bans_by_team = []

    for ban in all_bans:
        player_team = match_teams.get(ban.match_id)
        entry = {
            "match_id": ban.match_id,
            "champion_id": ban.champion_id,
            "champion_name": champion_map.get(ban.champion_id),
            "pick_turn": ban.pick_turn,
        }
        if ban.team_id == player_team:
            bans_by_team.append(entry)
        else:
            bans_against.append(entry)

    def top_champs(ban_list: list, n: int = 10) -> list:
        counts: Dict[int, int] = {}
        for b in ban_list:
            counts[b["champion_id"]] = counts.get(b["champion_id"], 0) + 1
        return [
            {
                "champion_id": cid,
                "champion_name": champion_map.get(cid),
                "ban_count": cnt,
            }
            for cid, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ][:n]

    return {
        "puuid": puuid,
        "matches_analyzed": len(player_matches),
        "bans_against": bans_against,
        "bans_by_team": bans_by_team,
        "most_banned_against": top_champs(bans_against),
        "most_banned_by_team": top_champs(bans_by_team),
        "total_bans_against": len(bans_against),
        "total_bans_by_team": len(bans_by_team),
    }


@router.get("/champion/{champion_id}/ban-rate")
async def get_champion_ban_rate(
    champion_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Ban rate for a specific champion across all stored matches."""
    champion_map = await get_champion_map()
    total_matches = db.query(func.count(Match.match_id)).scalar()

    if total_matches == 0:
        return {
            "champion_id": champion_id,
            "champion_name": champion_map.get(champion_id),
            "total_matches": 0,
            "times_banned": 0,
            "ban_rate": 0.0,
        }

    times_banned = (
        db.query(func.count(TeamBans.id))
        .filter(TeamBans.champion_id == champion_id)
        .scalar()
    )

    ban_rate = (times_banned / total_matches) * 100 if total_matches > 0 else 0.0

    return {
        "champion_id": champion_id,
        "champion_name": champion_map.get(champion_id),
        "total_matches": total_matches,
        "times_banned": times_banned,
        "ban_rate": round(ban_rate, 2),
    }


@router.get("/bans/most-banned")
async def get_most_banned_champions(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Most banned champions across all stored matches."""
    champion_map = await get_champion_map()
    most_banned = (
        db.query(TeamBans.champion_id, func.count(TeamBans.id).label("ban_count"))
        .group_by(TeamBans.champion_id)
        .order_by(desc("ban_count"))
        .limit(limit)
        .all()
    )

    return [
        {
            "champion_id": champ_id,
            "champion_name": champion_map.get(champ_id),
            "ban_count": count,
        }
        for champ_id, count in most_banned
    ]


@router.get("/runes/map")
async def get_rune_name_map() -> Dict[int, str]:
    """
    Returns the full Data Dragon rune name map: {rune_id: rune_name}.
    Covers both path IDs (e.g. 8000 → "Precision") and individual perk IDs
    (e.g. 8005 → "Press the Attack").  Cached after the first request.
    """
    return await get_rune_map()


@router.get("/player/{puuid}/runes")
async def get_player_runes(
    puuid: str,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Rune summary for a player's recent matches.
    Returns each match's keystone, primary path, and secondary path — all
    resolved to human-readable names via Data Dragon.
    """
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    rows = (
        db.query(ParticipantPerks, Match.game_creation, ParticipantStats.champion)
        .join(Match, Match.match_id == ParticipantPerks.match_id)
        .join(
            ParticipantStats,
            (ParticipantStats.match_id == ParticipantPerks.match_id)
            & (ParticipantStats.player_id == ParticipantPerks.player_id),
        )
        .filter(ParticipantPerks.player_id == player.id)
        .order_by(Match.game_creation.desc())
        .limit(limit)
        .all()
    )

    if not rows:
        return {"puuid": puuid, "matches_analyzed": 0, "runes": []}

    rune_map = await get_rune_map()

    return {
        "puuid": puuid,
        "matches_analyzed": len(rows),
        "runes": [
            {
                "match_id": pk.match_id,
                "champion": champion,
                "primary_style_id": pk.primary_style,
                "primary_style_name": rune_map.get(pk.primary_style) if pk.primary_style else None,
                "keystone_id": pk.keystone,
                "keystone_name": rune_map.get(pk.keystone) if pk.keystone else None,
                "primary_slot1_id": pk.primary_slot1,
                "primary_slot1_name": rune_map.get(pk.primary_slot1) if pk.primary_slot1 else None,
                "primary_slot2_id": pk.primary_slot2,
                "primary_slot2_name": rune_map.get(pk.primary_slot2) if pk.primary_slot2 else None,
                "primary_slot3_id": pk.primary_slot3,
                "primary_slot3_name": rune_map.get(pk.primary_slot3) if pk.primary_slot3 else None,
                "sub_style_id": pk.sub_style,
                "sub_style_name": rune_map.get(pk.sub_style) if pk.sub_style else None,
                "sub_slot1_id": pk.sub_slot1,
                "sub_slot1_name": rune_map.get(pk.sub_slot1) if pk.sub_slot1 else None,
                "sub_slot2_id": pk.sub_slot2,
                "sub_slot2_name": rune_map.get(pk.sub_slot2) if pk.sub_slot2 else None,
            }
            for pk, _game_creation, champion in rows
        ],
    }


# ---------------------------------------------------------------------------
# Role Performance — how this player ranks vs peers in the same role
# ---------------------------------------------------------------------------

@router.get("/player/{puuid}/role-performance")
async def get_role_performance(
    puuid: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Compare this player's per-role stats against all tracked players
    who play the same role.  Returns percentile ranks for win rate,
    KDA, and CS/min so the frontend can show "Top 20% KDA for BOTTOM".
    """
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Step 1: this player's stats broken down by role
    # dm.kda is precomputed in derived_metrics — kills/deaths/assists live in participant_stats
    player_role_sql = text("""
        SELECT
            ps.role,
            COUNT(*)                                      AS games,
            ROUND(AVG(ps.win::int)::numeric, 4)           AS win_rate,
            ROUND(AVG(dm.kda)::numeric, 3)                AS avg_kda,
            ROUND(AVG(dm.cs_per_min)::numeric, 3)         AS avg_cs_per_min,
            ROUND(AVG(dm.kill_participation)::numeric, 3) AS avg_kill_part,
            ROUND(AVG(dm.vision_per_min)::numeric, 3)     AS avg_vision
        FROM participant_stats ps
        JOIN players p ON p.id = ps.player_id
        JOIN derived_metrics dm
          ON dm.match_id = ps.match_id AND dm.puuid = p.puuid
        WHERE p.puuid = :puuid
          AND ps.role IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
        GROUP BY ps.role
        ORDER BY games DESC
    """)
    player_rows = db.execute(player_role_sql, {"puuid": puuid}).mappings().all()

    if not player_rows:
        return {
            "puuid": puuid,
            "message": "No role data found. Ingest matches first.",
            "roles": [],
        }

    # Step 2: global stats per role across ALL tracked players (peer baseline)
    global_role_sql = text("""
        SELECT
            ps.role,
            COUNT(*)                                      AS total_games,
            ROUND(AVG(ps.win::int)::numeric, 4)           AS global_win_rate,
            ROUND(AVG(dm.kda)::numeric, 3)                AS global_avg_kda,
            ROUND(AVG(dm.cs_per_min)::numeric, 3)         AS global_avg_cs,
            PERCENTILE_CONT(0.25) WITHIN GROUP
                (ORDER BY ps.win::int)                    AS wr_p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP
                (ORDER BY ps.win::int)                    AS wr_p50,
            PERCENTILE_CONT(0.75) WITHIN GROUP
                (ORDER BY ps.win::int)                    AS wr_p75,
            PERCENTILE_CONT(0.25) WITHIN GROUP
                (ORDER BY dm.cs_per_min)                  AS cs_p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP
                (ORDER BY dm.cs_per_min)                  AS cs_p50,
            PERCENTILE_CONT(0.75) WITHIN GROUP
                (ORDER BY dm.cs_per_min)                  AS cs_p75
        FROM participant_stats ps
        JOIN players p ON p.id = ps.player_id
        JOIN derived_metrics dm
          ON dm.match_id = ps.match_id AND dm.puuid = p.puuid
        WHERE ps.role IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
        GROUP BY ps.role
    """)
    global_rows = {
        row["role"]: dict(row)
        for row in db.execute(global_role_sql).mappings().all()
    }

    def _percentile_label(value: float, p25: float, p50: float, p75: float) -> str:
        if value >= p75:
            return "top 25%"
        if value >= p50:
            return "top 50%"
        if value >= p25:
            return "bottom 50%"
        return "bottom 25%"

    roles_out = []
    primary_role = None
    most_games = 0

    for row in player_rows:
        role = row["role"]
        g = global_rows.get(role, {})
        games = int(row["games"])

        wr   = float(row["win_rate"]      or 0)
        kda  = float(row["avg_kda"]       or 0)
        cs   = float(row["avg_cs_per_min"] or 0)
        kp   = float(row["avg_kill_part"] or 0)
        vis  = float(row["avg_vision"]    or 0)

        g_wr = float(g.get("global_win_rate",  0.5) or 0.5)
        g_kda = float(g.get("global_avg_kda",  2.5) or 2.5)
        g_cs  = float(g.get("global_avg_cs",   6.0) or 6.0)

        wr_label = _percentile_label(
            wr,
            float(g.get("wr_p25", 0.4) or 0.4),
            float(g.get("wr_p50", 0.5) or 0.5),
            float(g.get("wr_p75", 0.6) or 0.6),
        )
        cs_label = _percentile_label(
            cs,
            float(g.get("cs_p25", 5.0) or 5.0),
            float(g.get("cs_p50", 7.0) or 7.0),
            float(g.get("cs_p75", 8.5) or 8.5),
        )

        roles_out.append({
            "role":             role,
            "games_played":     games,
            "win_rate":         round(wr, 4),
            "avg_kda":          round(kda, 3),
            "avg_cs_per_min":   round(cs, 3),
            "avg_kill_part":    round(kp, 3),
            "avg_vision":       round(vis, 3),
            "vs_peers": {
                "global_win_rate":  round(g_wr, 4),
                "global_avg_kda":   round(g_kda, 3),
                "global_avg_cs":    round(g_cs, 3),
                "win_rate_vs_peers":  wr_label,
                "cs_vs_peers":        cs_label,
                "kda_delta":          round(kda - g_kda, 3),
                "cs_delta":           round(cs - g_cs, 3),
                "wr_delta":           round(wr - g_wr, 4),
            },
        })

        if games > most_games:
            most_games = games
            primary_role = role

    return {
        "puuid":        puuid,
        "primary_role": primary_role,
        "roles":        roles_out,
    }


# ---------------------------------------------------------------------------
# Performance Trends — rolling window stats + per-game series for charting
# ---------------------------------------------------------------------------

@router.get("/player/{puuid}/trends")
def get_player_trends(
    puuid: str,
    window: int = 20,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return rolling performance stats and a per-game time series for one player.

    Rolling aggregates (``window`` most recent ranked games) come from
    ``feature_extractor.get_rolling_features()`` — the same feature vector
    used by every ML model, ensuring front-end numbers are consistent with
    what the models see.

    Also returns a game-by-game series (KDA, CS/min, win/loss, champion)
    so the frontend can render a trend sparkline or line chart.

    Query params:
        window (int, default 20): rolling window size (also controls series length)
    """
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Use "now" as the cutoff so we get the player's current rolling state
    before_ts = int(time.time() * 1000)  # milliseconds, consistent with game_creation

    rolling = get_rolling_features(db, puuid, before_ts=before_ts, window=window)

    if not rolling:
        return {
            "puuid":         puuid,
            "summoner_name": player.riot_id,
            "games_in_window": 0,
            "has_full_window": False,
            "rolling": None,
            "series":  [],
            "message": f"Fewer than 5 ranked games found. Ingest more matches to see trends.",
        }

    # Per-game series for charting (same window, chronological order)
    series_sql = text("""
        SELECT
            m.match_id,
            m.game_creation,
            ps.champion,
            ps.role,
            ps.win,
            dm.kda,
            dm.cs_per_min,
            dm.gold_per_min,
            dm.kill_participation,
            dm.vision_per_min,
            ps.kills,
            ps.deaths,
            ps.assists
        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN matches m          ON m.match_id = ps.match_id
        JOIN derived_metrics dm ON dm.match_id = ps.match_id
                               AND dm.puuid = p.puuid
        WHERE p.puuid      = :puuid
          AND m.queue_id   = 420
        ORDER BY m.game_creation DESC
        LIMIT :window
    """)

    series_rows = db.execute(
        series_sql, {"puuid": puuid, "window": window}
    ).mappings().all()

    # Return oldest-first so chart renders left→right as time progresses
    series = [
        {
            "match_id":        r["match_id"],
            "game_creation":   r["game_creation"],
            "champion":        r["champion"],
            "role":            r["role"],
            "win":             bool(r["win"]),
            "kda":             round(float(r["kda"]), 2) if r["kda"] is not None else None,
            "cs_per_min":      round(float(r["cs_per_min"]), 2) if r["cs_per_min"] is not None else None,
            "gold_per_min":    round(float(r["gold_per_min"]), 1) if r["gold_per_min"] is not None else None,
            "kill_participation": round(float(r["kill_participation"]), 3) if r["kill_participation"] is not None else None,
            "vision_per_min":  round(float(r["vision_per_min"]), 3) if r["vision_per_min"] is not None else None,
            "kills":           r["kills"],
            "deaths":          r["deaths"],
            "assists":         r["assists"],
        }
        for r in reversed(series_rows)  # oldest first
    ]

    return {
        "puuid":           puuid,
        "summoner_name":   player.riot_id,
        "games_in_window": rolling.get("games_in_window", 0),
        "has_full_window": rolling.get("has_full_window", False),
        "rolling": {
            "win_rate_20":         rolling.get("win_rate_20"),
            "avg_kda_20":          rolling.get("avg_kda_20"),
            "avg_cs_per_min_20":   rolling.get("avg_cs_per_min_20"),
            "avg_gold_per_min_20": rolling.get("avg_gold_per_min_20"),
            "avg_kill_part_20":    rolling.get("avg_kill_part_20"),
            "death_rate_20":       rolling.get("death_rate_20"),
            "vision_per_min_20":   rolling.get("vision_per_min_20"),
            "kda_std_10":          rolling.get("kda_std_10"),
            "cs_trend_10":         rolling.get("cs_trend_10"),
            "win_streak":          rolling.get("win_streak"),
        },
        "series": series,
    }
