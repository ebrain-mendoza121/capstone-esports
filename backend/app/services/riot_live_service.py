"""
riot_live_service.py
--------------------
Fetch rolling stats for ANY summoner on demand — whether or not they are
tracked in the local database.  Used by:

  - POST /teams/build          : compute stats for all 5 team members
  - POST /ai/predict/matchup   : compute opponent stats live
  - POST /ai/enrich/opponent-features : backfill training data

Design:
  * For TRACKED players  → prefer DB (fast, deep).
  * For UNTRACKED players → Riot API live fetch (slower, shallower).
  * Results are NOT persisted — caller caches if needed.
  * Rate-limit-safe: each call fetches at most `match_count` matches
    (default 20) and respects the RiotClient retry/back-off logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.schemas.ingest import PLATFORM_TO_ROUTING, Platform
from app.services.riot_client import RiotApiError, RiotClient

logger = logging.getLogger(__name__)

# Ranked solo queue ID — only analyse competitive games
RANKED_SOLO_QUEUE = 420

# Minimum games required before we trust the rolling averages
MIN_GAMES_THRESHOLD = 5

# Feature keys returned by get_live_player_stats — mirrors feature_extractor
LIVE_FEATURE_KEYS = [
    "win_rate_20",
    "avg_kda_20",
    "avg_cs_per_min_20",
    "avg_gold_per_min_20",
    "avg_kill_part_20",
    "avg_vision_per_min_20",
    "games_in_window",
    "source",          # "db" | "live" | "insufficient_data"
    "puuid",
    "summoner_name",
    "primary_role",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _platform_to_routing(platform: str) -> str:
    """Convert a platform string (e.g. 'NA', 'EUW') to Riot routing value."""
    try:
        p = Platform(platform.upper())
        return PLATFORM_TO_ROUTING[p]
    except (ValueError, KeyError):
        return "americas"  # safe default


def _compute_rolling_stats(participant_rows: list[dict]) -> dict:
    """
    Given a list of participant dicts (one per match, sorted newest first),
    compute rolling averages over up to 20 games.

    Each dict must have: win, kills, deaths, assists, cs, gold_earned,
    kill_participation (optional), vision_score (optional),
    game_duration_seconds.
    """
    rows = participant_rows[:20]  # cap at 20
    n = len(rows)
    if n == 0:
        return {"games_in_window": 0, "source": "insufficient_data"}

    wins = 0
    kda_sum = 0.0
    cs_sum = 0.0
    gold_sum = 0.0
    kp_sum = 0.0
    vision_sum = 0.0
    primary_role_counts: dict[str, int] = {}

    for r in rows:
        wins += 1 if r.get("win") else 0

        k = float(r.get("kills", 0) or 0)
        d = float(r.get("deaths", 0) or 0)
        a = float(r.get("assists", 0) or 0)
        kda_sum += (k + a) / d if d > 0 else (k + a)

        dur_min = max(float(r.get("game_duration_seconds", 1800) or 1800) / 60, 1.0)
        cs_sum   += float(r.get("cs", 0) or 0) / dur_min
        gold_sum += float(r.get("gold_earned", 0) or 0) / dur_min

        # kill participation: if not provided, rough estimate = (k+a) / max(team_kills,1)
        kp = r.get("kill_participation")
        if kp is not None:
            kp_sum += float(kp)

        vision_sum += float(r.get("vision_score", 0) or 0) / dur_min

        role = str(r.get("role") or r.get("teamPosition") or "").upper()
        if role:
            primary_role_counts[role] = primary_role_counts.get(role, 0) + 1

    primary_role = max(primary_role_counts, key=primary_role_counts.get) if primary_role_counts else None

    return {
        "games_in_window":     n,
        "win_rate_20":         round(wins / n, 4),
        "avg_kda_20":          round(kda_sum / n, 3),
        "avg_cs_per_min_20":   round(cs_sum / n, 3),
        "avg_gold_per_min_20": round(gold_sum / n, 3),
        "avg_kill_part_20":    round(kp_sum / n, 3) if kp_sum > 0 else None,
        "avg_vision_per_min_20": round(vision_sum / n, 3),
        "primary_role":        primary_role,
        "source":              "live",
    }


# ---------------------------------------------------------------------------
# DB fast path — for tracked players
# ---------------------------------------------------------------------------

def _get_stats_from_db(db: Session, puuid: str) -> Optional[dict]:
    """
    Pull rolling stats directly from the DB for a tracked player.
    Returns None if the player is not found or has too few games.
    """
    sql = text("""
        SELECT
            p.puuid,
            p.riot_id                                     AS summoner_name,
            COUNT(*)                                      AS games_in_window,
            ROUND(AVG(ps.win::int)::numeric, 4)           AS win_rate_20,
            ROUND(AVG(dm.kda)::numeric, 3)                AS avg_kda_20,
            ROUND(AVG(dm.cs_per_min)::numeric, 3)         AS avg_cs_per_min_20,
            ROUND(AVG(dm.gold_per_min)::numeric, 3)       AS avg_gold_per_min_20,
            ROUND(AVG(dm.kill_participation)::numeric, 3) AS avg_kill_part_20,
            ROUND(AVG(dm.vision_per_min)::numeric, 3)     AS avg_vision_per_min_20,
            MODE() WITHIN GROUP (ORDER BY ps.role)        AS primary_role
        FROM players p
        JOIN participant_stats ps ON ps.player_id = p.id
        JOIN derived_metrics   dm ON dm.match_id = ps.match_id
                                  AND dm.puuid = p.puuid
        WHERE p.puuid = :puuid
        GROUP BY p.puuid, p.riot_id
    """)
    row = db.execute(sql, {"puuid": puuid}).mappings().first()
    if not row:
        return None
    games = int(row["games_in_window"] or 0)
    if games < MIN_GAMES_THRESHOLD:
        return None
    return {
        "puuid":               puuid,
        "summoner_name":       row["summoner_name"],
        "games_in_window":     games,
        "win_rate_20":         float(row["win_rate_20"]         or 0),
        "avg_kda_20":          float(row["avg_kda_20"]          or 0),
        "avg_cs_per_min_20":   float(row["avg_cs_per_min_20"]   or 0),
        "avg_gold_per_min_20": float(row["avg_gold_per_min_20"] or 0),
        "avg_kill_part_20":    float(row["avg_kill_part_20"]    or 0),
        "avg_vision_per_min_20": float(row["avg_vision_per_min_20"] or 0),
        "primary_role":        row["primary_role"],
        "source":              "db",
    }


# ---------------------------------------------------------------------------
# Live Riot API path — for untracked players
# ---------------------------------------------------------------------------

async def _get_stats_from_riot(
    game_name: str,
    tag_line: str,
    platform: str = "NA",
    match_count: int = 20,
) -> dict:
    """
    Fetch recent ranked match stats from Riot API for any summoner.
    Returns a feature dict compatible with LIVE_FEATURE_KEYS.
    """
    client = RiotClient()
    routing = _platform_to_routing(platform)

    try:
        puuid = await client.get_puuid(game_name, tag_line, routing)
    except RiotApiError as e:
        logger.warning("PUUID lookup failed for %s#%s: %s", game_name, tag_line, e)
        return {
            "puuid":           None,
            "summoner_name":   f"{game_name}#{tag_line}",
            "games_in_window": 0,
            "source":          "error",
            "error":           str(e),
        }

    try:
        match_ids = await client.get_match_ids(
            puuid,
            routing=routing,
            count=match_count,
            queue=RANKED_SOLO_QUEUE,
        )
    except RiotApiError as e:
        logger.warning("Match ID fetch failed for %s: %s", puuid[:8], e)
        match_ids = []

    if not match_ids:
        return {
            "puuid":           puuid,
            "summoner_name":   f"{game_name}#{tag_line}",
            "games_in_window": 0,
            "source":          "insufficient_data",
            "error":           "No ranked matches found.",
        }

    # Fetch match details concurrently (batched to avoid rate limit)
    participant_rows: list[dict] = []
    batch_size = 5

    for i in range(0, len(match_ids), batch_size):
        batch = match_ids[i : i + batch_size]
        tasks = [client.get_match(mid, routing) for mid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for match_data in results:
            if isinstance(match_data, Exception):
                continue
            try:
                info = match_data.get("info", {})
                game_dur = float(info.get("gameDuration", 1800) or 1800)
                for p in info.get("participants", []):
                    if p.get("puuid") == puuid:
                        participant_rows.append({
                            "win":                   p.get("win", False),
                            "kills":                 p.get("kills", 0),
                            "deaths":                p.get("deaths", 0),
                            "assists":               p.get("assists", 0),
                            "cs":                    p.get("totalMinionsKilled", 0)
                                                     + p.get("neutralMinionsKilled", 0),
                            "gold_earned":           p.get("goldEarned", 0),
                            "vision_score":          p.get("visionScore", 0),
                            "game_duration_seconds": game_dur,
                            "role":                  p.get("teamPosition") or p.get("role"),
                        })
                        break
            except Exception as parse_err:
                logger.debug("Match parse error: %s", parse_err)

        # Brief pause between batches to respect rate limits
        if i + batch_size < len(match_ids):
            await asyncio.sleep(0.5)

    stats = _compute_rolling_stats(participant_rows)
    stats["puuid"] = puuid
    stats["summoner_name"] = f"{game_name}#{tag_line}"
    return stats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_live_player_stats(
    game_name: str,
    tag_line: str,
    platform: str = "NA",
    db: Optional[Session] = None,
    match_count: int = 20,
) -> dict:
    """
    Return rolling stats for any summoner.

    Strategy:
      1. If db is provided, check if player is tracked → use DB (fast path).
      2. If not tracked (or no db), fetch from Riot API live.

    Args:
        game_name:   Riot ID game name (e.g. "Faker")
        tag_line:    Riot ID tag (e.g. "KR1")
        platform:    Platform string (e.g. "NA", "EUW", "KR")
        db:          SQLAlchemy session (optional — enables DB fast path)
        match_count: Max recent ranked matches to fetch from Riot API

    Returns:
        dict with LIVE_FEATURE_KEYS entries.
    """
    # DB fast path
    if db is not None:
        try:
            # Resolve PUUID to check if tracked — first hit Riot if needed
            # (We look up by riot_id in the players table directly)
            from sqlalchemy import text as _text
            puuid_row = db.execute(
                _text("SELECT puuid FROM players WHERE riot_id = :rid LIMIT 1"),
                {"rid": game_name},
            ).mappings().first()

            if puuid_row:
                db_stats = _get_stats_from_db(db, puuid_row["puuid"])
                if db_stats:
                    logger.debug("DB fast path for %s", game_name)
                    return db_stats
        except Exception as e:
            logger.warning("DB fast path failed for %s — falling back to live API: %s", game_name, e)

    # Live Riot API path
    logger.info("Live fetch for %s#%s on %s", game_name, tag_line, platform)
    return await _get_stats_from_riot(game_name, tag_line, platform, match_count)


async def get_team_stats(
    players: list[dict],
    platform: str = "NA",
    db: Optional[Session] = None,
) -> list[dict]:
    """
    Fetch stats for an entire team concurrently.

    Args:
        players: list of {"game_name": str, "tag_line": str}
        platform: shared platform for all players
        db: optional SQLAlchemy session for DB fast path

    Returns:
        list of stat dicts (one per player, same order as input)
    """
    tasks = [
        get_live_player_stats(
            p["game_name"],
            p.get("tag_line", "NA1"),
            platform=platform,
            db=db,
        )
        for p in players
    ]
    return list(await asyncio.gather(*tasks))
