"""
champions.py — Champion data + analytics routes.

Standalone module.  All DDragon data is served from the in-process cache
loaded at startup — zero Riot API calls per request.
DB-backed stats (win rate, KDA, etc.) query participant_stats directly.

Endpoints
---------
GET /champions                              → list all (filterable by role/tag/search)
GET /champions/by-role/{role}               → shortcut — champions with role affinity
GET /champions/matchup/{champ_a}/{champ_b}  → head-to-head stats from participant_stats
GET /champions/{champion_id}                → single champion + live DB stats
                                              (MUST be registered last — path param
                                               would shadow the routes above otherwise)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.champion_matchups import ChampionMatchup
from app.services.ddragon import get_champion_full_map
from app.services.champion_role_tiers import (
    convert_ddragon_roles_to_display,
    get_champion_role_tiers,
    normalize_role,
    visible_roles_from_tiers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/champions", tags=["champions"])

# Valid roles for champions browse endpoints (display-oriented)
_VALID_CHAMPION_ROLES = {"TOP", "JUNGLE", "MID", "BOTTOM", "SUPPORT"}

# Valid roles for matchup endpoints (participant_stats-oriented)
_VALID_MATCHUP_ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _full_map() -> Dict[int, Any]:
    """Return DDragon full champion map; raises 503 if cache is empty."""
    m = await get_champion_full_map()
    if not m:
        raise HTTPException(
            status_code=503,
            detail="Champion data is not yet available. DDragon cache may still be loading.",
        )
    return m


def _champion_db_stats(db: Session, champion_id: int) -> Dict[str, Any]:
    """
    Query participant_stats for aggregate performance of a specific champion.
    Returns empty-safe dict — all values are None if no data exists yet.
    """
    sql = text("""
        SELECT
            COUNT(*)                                                    AS games_played,
            ROUND(AVG(CASE WHEN ps.win THEN 1.0 ELSE 0.0 END)::numeric, 4)
                                                                        AS win_rate,
            ROUND(AVG(
                CASE WHEN ps.deaths > 0
                     THEN (ps.kills + ps.assists)::float / ps.deaths
                     ELSE (ps.kills + ps.assists)::float
                END
            )::numeric, 4)                                              AS avg_kda,
            ROUND(AVG(
                ps.cs::float / NULLIF(m.game_duration / 60.0, 0)
            )::numeric, 2)                                              AS avg_cs_per_min,
            ROUND(AVG(
                ps.gold_earned::float / NULLIF(m.game_duration / 60.0, 0)
            )::numeric, 2)                                              AS avg_gold_per_min,
            ROUND(AVG(ps.kills)::numeric, 2)                            AS avg_kills,
            ROUND(AVG(ps.deaths)::numeric, 2)                           AS avg_deaths,
            ROUND(AVG(ps.assists)::numeric, 2)                          AS avg_assists
        FROM participant_stats ps
        JOIN matches m ON m.match_id = ps.match_id
        WHERE ps.champion_id = :cid
          AND m.queue_id     = 420
    """)
    row = db.execute(sql, {"cid": champion_id}).mappings().first()
    if not row or not row["games_played"]:
        return {
            "games_played":    0,
            "win_rate":        None,
            "avg_kda":         None,
            "avg_cs_per_min":  None,
            "avg_gold_per_min":None,
            "avg_kills":       None,
            "avg_deaths":      None,
            "avg_assists":     None,
        }
    return dict(row)


# ---------------------------------------------------------------------------
# GET /champions
# ---------------------------------------------------------------------------

@router.get("")
async def list_champions(
    role:   Optional[str] = Query(None, description="Filter by LoL role: TOP/JUNGLE/MID/BOTTOM/SUPPORT"),
    tag:    Optional[str] = Query(None, description="Filter by DDragon tag: Fighter/Mage/Marksman/Support/Tank/Assassin/Specialist"),
    search: Optional[str] = Query(None, description="Case-insensitive name search"),
) -> Dict[str, Any]:
    """
    Return all champions from DDragon, optionally filtered.

    Query params:
    - role   → only champions whose role_affinity includes this role
    - tag    → only champions with this DDragon tag
    - search → substring match on champion name (case-insensitive)

    Each entry includes: id, key, name, title, tags, image_url, role_affinity.
    Sorted alphabetically by name.
    """
    champ_map = await _full_map()

    # Normalise filters
    role_filter   = normalize_role(role) if role else None
    tag_filter    = tag.capitalize() if tag  else None
    search_filter = search.lower() if search else None

    if role_filter and role_filter not in _VALID_CHAMPION_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{role}'. Valid roles: {', '.join(sorted(_VALID_CHAMPION_ROLES))}",
        )

    results: List[Dict[str, Any]] = []
    for meta in champ_map.values():
        role_tiers = get_champion_role_tiers(meta["id"], meta["name"])
        role_affinity = visible_roles_from_tiers(role_tiers)
        if not role_affinity:
            role_affinity = convert_ddragon_roles_to_display(meta["role_affinity"])

        # Role filter
        if role_filter and role_filter not in role_affinity:
            continue
        # Tag filter
        if tag_filter and tag_filter not in meta["tags"]:
            continue
        # Search filter
        if search_filter and search_filter not in meta["name"].lower():
            continue

        results.append({
            "id":           meta["id"],
            "key":          meta["key"],
            "name":         meta["name"],
            "title":        meta["title"],
            "tags":         meta["tags"],
            "image_url":    meta["image_url"],
            "role_affinity":role_affinity,
            "role_tiers":   role_tiers,
        })

    results.sort(key=lambda c: c["name"])

    return {
        "count":   len(results),
        "filters": {
            "role":   role_filter,
            "tag":    tag_filter,
            "search": search_filter,
        },
        "champions": results,
    }


# ---------------------------------------------------------------------------
# GET /champions/by-role/{role}
# Must be registered BEFORE /champions/{champion_id}
# ---------------------------------------------------------------------------

@router.get("/by-role/{role}")
async def champions_by_role(role: str) -> Dict[str, Any]:
    """
    Convenience endpoint — return all champions whose role_affinity
    includes the given LoL role.

    Example: GET /champions/by-role/MID
    Returns Mages and Assassins (and Specialists with mid affinity).
    """
    role_upper = normalize_role(role)
    if role_upper not in _VALID_CHAMPION_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{role}'. Valid roles: {', '.join(sorted(_VALID_CHAMPION_ROLES))}",
        )

    champ_map = await _full_map()

    results = []
    for meta in champ_map.values():
        role_tiers = get_champion_role_tiers(meta["id"], meta["name"])
        role_affinity = visible_roles_from_tiers(role_tiers)
        if not role_affinity:
            role_affinity = convert_ddragon_roles_to_display(meta["role_affinity"])
        if role_upper not in role_affinity:
            continue
        results.append({
            "id":           meta["id"],
            "key":          meta["key"],
            "name":         meta["name"],
            "title":        meta["title"],
            "tags":         meta["tags"],
            "image_url":    meta["image_url"],
            "role_affinity":role_affinity,
            "role_tiers":   role_tiers,
        })
    results.sort(key=lambda c: c["name"])

    return {
        "role":      role_upper,
        "count":     len(results),
        "champions": results,
    }


# ---------------------------------------------------------------------------
# GET /champions/matchup/{champ_a_id}/{champ_b_id}
# Must be registered BEFORE /champions/{champion_id}
# ---------------------------------------------------------------------------

@router.get("/matchup/{champ_a_id}/{champ_b_id}")
async def champion_matchup(
    champ_a_id: int,
    champ_b_id: int,
    role:       Optional[str] = Query(None, description="Scope matchup to a specific lane role"),
    db:         Session       = Depends(get_db),
) -> Dict[str, Any]:
    """
    Head-to-head matchup statistics for two champions.

    Data source priority (highest first):
      1. champion_matchups table — manually-researched rows from Lolalytics/op.gg/u.gg
         uploaded via POST /matchups/import/csv.  These typically have 500–5000 games
         and are far more statistically reliable.
      2. participant_stats self-join — derived from locally-ingested matches.
         Only used when no researched row exists for this pair + role.

    If the researched table has the pair in one direction (A vs B) but the request
    asks for B vs A, the win rate is inverted automatically (1 - win_rate_a_vs_b).

    Optional ?role=MIDDLE scopes the query to a specific lane.
    """
    champ_map = await _full_map()

    # Validate both champion IDs
    meta_a = champ_map.get(champ_a_id)
    meta_b = champ_map.get(champ_b_id)
    if not meta_a:
        raise HTTPException(status_code=404, detail=f"Champion id {champ_a_id} not found in DDragon data.")
    if not meta_b:
        raise HTTPException(status_code=404, detail=f"Champion id {champ_b_id} not found in DDragon data.")

    role_filter = role.upper() if role else None
    if role_filter and role_filter not in _VALID_MATCHUP_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{role}'. Valid roles: {', '.join(sorted(_VALID_MATCHUP_ROLES))}",
        )

    # ------------------------------------------------------------------
    # 1. Check champion_matchups table first (manually-researched data)
    #    Wrapped in try/except so the endpoint degrades gracefully if the
    #    migration hasn't been run yet (table doesn't exist in Supabase).
    # ------------------------------------------------------------------
    def _cm_query(a_id: int, b_id: int):
        q = db.query(ChampionMatchup).filter(
            ChampionMatchup.champion_a_id == a_id,
            ChampionMatchup.champion_b_id == b_id,
        )
        if role_filter:
            q = q.filter(ChampionMatchup.role == role_filter)
        return q.first()

    researched: Optional[ChampionMatchup] = None
    inverted = False
    try:
        researched = _cm_query(champ_a_id, champ_b_id)
        if researched is None:
            # Check if stored in the other direction
            researched = _cm_query(champ_b_id, champ_a_id)
            inverted = researched is not None
    except Exception as _e:
        # Table doesn't exist yet — fall through to participant_stats path
        logger.debug("champion_matchups lookup skipped (%s), falling back to ingested data", _e)
        db.rollback()  # clear the failed transaction so the session stays usable

    if researched is not None:
        # Bayesian smoothing (applied at query time, not stored)
        raw_wr = researched.win_rate_a_vs_b if not inverted else 1.0 - researched.win_rate_a_vs_b
        weight = 20  # prior weight — small samples pulled toward 0.5
        smoothed = (raw_wr * researched.games_played + 0.5 * weight) / (researched.games_played + weight)

        return {
            "champ_a": {"id": meta_a["id"], "name": meta_a["name"], "image_url": meta_a["image_url"]},
            "champ_b": {"id": meta_b["id"], "name": meta_b["name"], "image_url": meta_b["image_url"]},
            "role_scope":               role_filter,
            "data_source":              "researched",   # explicitly flags which source was used
            "games_played":             researched.games_played,
            "confidence":               researched.confidence,
            "champ_a_win_rate":         round(raw_wr, 4),
            "champ_a_win_rate_smoothed": round(smoothed, 4),
            "champ_b_win_rate":         round(1.0 - raw_wr, 4),
            "avg_kda_diff":             None,   # not available from external research data
            "avg_kill_diff":            None,
            "avg_gold_diff_per_min":    None,
            "patch":                    researched.patch,
            "source":                   researched.source,
            "note": (
                f"Data sourced from {researched.source or 'external research'} "
                f"(patch {researched.patch or 'unknown'}). "
                + (f"Bayesian smoothing applied — only {researched.games_played} games."
                   if researched.confidence == "low" else "")
            ),
        }

    # ------------------------------------------------------------------
    # 2. Fall back to participant_stats self-join (locally ingested data)
    # ------------------------------------------------------------------
    role_clause = "AND a.role = :role AND b.role = :role" if role_filter else ""

    sql = text(f"""
        SELECT
            COUNT(*)                                                          AS games_played,
            ROUND(AVG(CASE WHEN a.win THEN 1.0 ELSE 0.0 END)::numeric, 4)   AS champ_a_win_rate,
            ROUND(AVG(
                (CASE WHEN a.deaths > 0
                      THEN (a.kills + a.assists)::float / a.deaths
                      ELSE (a.kills + a.assists)::float END)
                -
                (CASE WHEN b.deaths > 0
                      THEN (b.kills + b.assists)::float / b.deaths
                      ELSE (b.kills + b.assists)::float END)
            )::numeric, 4)                                                    AS avg_kda_diff,
            ROUND(AVG(a.kills - b.kills)::numeric, 2)                        AS avg_kill_diff,
            ROUND(AVG(
                a.gold_earned::float / NULLIF(m.game_duration / 60.0, 0)
                - b.gold_earned::float / NULLIF(m.game_duration / 60.0, 0)
            )::numeric, 2)                                                    AS avg_gold_diff_per_min
        FROM participant_stats a
        JOIN participant_stats b
            ON  a.match_id = b.match_id
            AND a.team_id != b.team_id
        JOIN matches m ON m.match_id = a.match_id
        WHERE a.champion_id = :champ_a_id
          AND b.champion_id = :champ_b_id
          AND m.queue_id    = 420
          {role_clause}
    """)

    params: Dict[str, Any] = {"champ_a_id": champ_a_id, "champ_b_id": champ_b_id}
    if role_filter:
        params["role"] = role_filter

    row = db.execute(sql, params).mappings().first()
    games = int(row["games_played"]) if row else 0
    confidence = "high" if games >= 30 else "medium" if games >= 10 else "low"

    return {
        "champ_a": {"id": meta_a["id"], "name": meta_a["name"], "image_url": meta_a["image_url"]},
        "champ_b": {"id": meta_b["id"], "name": meta_b["name"], "image_url": meta_b["image_url"]},
        "role_scope":            role_filter,
        "data_source":           "ingested",   # derived from locally-ingested matches
        "games_played":          games,
        "confidence":            confidence,
        "champ_a_win_rate":      float(row["champ_a_win_rate"]) if games else None,
        "champ_a_win_rate_smoothed": None,
        "champ_b_win_rate":      round(1.0 - float(row["champ_a_win_rate"]), 4) if games else None,
        "avg_kda_diff":          float(row["avg_kda_diff"])          if games else None,
        "avg_kill_diff":         float(row["avg_kill_diff"])         if games else None,
        "avg_gold_diff_per_min": float(row["avg_gold_diff_per_min"]) if games else None,
        "patch":                 None,
        "source":                None,
        "note": (
            "No researched matchup data found — showing stats derived from locally-ingested matches. "
            "Upload a CSV via POST /matchups/import/csv for higher-quality data."
            if games == 0 else
            f"Derived from {games} ingested ranked games. "
            + ("Low sample size — results may not be reliable. " if games < 10 else "")
            + "Upload researched data via POST /matchups/import/csv for higher accuracy."
        ),
    }


# ---------------------------------------------------------------------------
# GET /champions/{champion_id}
# MUST be registered last — path param would shadow /by-role and /matchup
# ---------------------------------------------------------------------------

@router.get("/{champion_id}")
async def get_champion(
    champion_id: int,
    db:          Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Full champion detail — DDragon metadata + live performance stats from DB.

    DDragon fields: id, name, title, tags, blurb, image_url, role_affinity, base stats.
    DB fields: games_played, win_rate, avg_kda, avg_cs_per_min, avg_gold_per_min
               (ranked solo/duo only — queue_id 420).
               All DB fields are null if the champion has no data yet.
    """
    champ_map = await _full_map()
    meta = champ_map.get(champion_id)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Champion id {champion_id} not found. Use GET /champions to browse all IDs.",
        )

    db_stats = _champion_db_stats(db, champion_id)
    role_tiers = get_champion_role_tiers(meta["id"], meta["name"])
    role_affinity = visible_roles_from_tiers(role_tiers)
    if not role_affinity:
        role_affinity = convert_ddragon_roles_to_display(meta["role_affinity"])

    return {
        # DDragon metadata
        "id":           meta["id"],
        "key":          meta["key"],
        "name":         meta["name"],
        "title":        meta["title"],
        "blurb":        meta["blurb"],
        "tags":         meta["tags"],
        "image_url":    meta["image_url"],
        "role_affinity":role_affinity,
        "role_tiers":   role_tiers,
        "base_stats":   meta["stats"],
        # Tracked performance data (null if no matches ingested for this champion)
        "tracked_stats": db_stats,
    }
