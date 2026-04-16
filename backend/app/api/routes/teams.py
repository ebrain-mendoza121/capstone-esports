"""
teams.py — Team composition analysis + matchup prediction routes.

POST /teams/build          → analyze a 5-player team (stats + gaps)
POST /teams/matchup        → team vs team prediction with per-role breakdown
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.champion_matchups import ChampionMatchup
from app.services.ddragon import get_champion_full_map
from app.services.riot_live_service import get_team_stats, get_live_player_stats
from app.services.ai_service import (
    analyze_team_composition,
    role_matchup_breakdown,
    _load_model,
    get_player_playstyle,
    get_champion_recommendations,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PlayerInput(BaseModel):
    game_name:    str           = Field(...,  description="Riot ID game name, e.g. 'Faker'")
    tag_line:     str           = Field("NA1", description="Riot ID tag, e.g. 'NA1'")
    role:         Optional[str] = Field(None, description="Expected lane role (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY)")
    champion_id:  Optional[int] = Field(None, description="DDragon numeric champion id (preferred)")
    champion:     Optional[str] = Field(None, description="Champion display name — fallback if champion_id is unknown")


class TeamBuildRequest(BaseModel):
    players:           List[PlayerInput] = Field(..., min_length=1, max_length=5)
    platform:          str               = Field("NA", description="Platform (NA, EUW, KR, …)")
    composition_focus: Optional[str]    = Field(
        None,
        description="Desired comp style hint: teamfight / poke / dive / split / skirmish"
    )


class MatchupRequest(BaseModel):
    blue_team: List[PlayerInput] = Field(..., min_length=1, max_length=5)
    red_team:  List[PlayerInput] = Field(..., min_length=1, max_length=5)
    platform:  str = Field("NA")


# ---------------------------------------------------------------------------
# Composition analysis helpers
# ---------------------------------------------------------------------------

_ROLE_ORDER = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

# Maps playstyle archetype → roles where the player naturally excels
_PLAYSTYLE_ROLE_AFFINITY: dict[str, list[str]] = {
    "carry":           ["BOTTOM", "MIDDLE"],
    "skirmisher":      ["JUNGLE", "TOP"],
    "support_utility": ["UTILITY", "SUPPORT"],
    "farm_efficiency": ["BOTTOM", "MIDDLE", "TOP"],
}

# Human-readable role suggestion per archetype
_PLAYSTYLE_ROLE_HINT: dict[str, str] = {
    "carry":           "BOTTOM or MIDDLE (damage carry)",
    "skirmisher":      "JUNGLE or TOP (skirmish/engage)",
    "support_utility": "SUPPORT or UTILITY (peel/engage)",
    "farm_efficiency": "BOTTOM, MIDDLE, or TOP (farm-heavy lane)",
}

# Maps playstyle archetype → damage/engage profile
_PLAYSTYLE_PROFILE: dict[str, dict] = {
    "carry":           {"damage": "high",   "engage": "low",    "farm": "high"},
    "skirmisher":      {"damage": "medium", "engage": "medium", "farm": "medium"},
    "support_utility": {"damage": "low",    "engage": "high",   "farm": "low"},
    "farm_efficiency": {"damage": "medium", "engage": "low",    "farm": "high"},
}

def _team_gaps(player_stats: list[dict]) -> list[str]:
    """
    Identify composition gaps based on team's aggregate win rate,
    KDA, CS, and primary roles.  Returns a list of human-readable warnings.
    """
    gaps = []
    roles_present = {
        str(p.get("primary_role") or "").upper()
        for p in player_stats
        if p.get("primary_role")
    }

    # Role coverage
    missing_roles = [r for r in _ROLE_ORDER if r not in roles_present]
    if missing_roles:
        gaps.append(f"Missing roles: {', '.join(missing_roles)}")

    # Low CS average → potential farm deficit
    cs_vals = [p["avg_cs_per_min_20"] for p in player_stats if p.get("avg_cs_per_min_20")]
    if cs_vals:
        avg_cs = sum(cs_vals) / len(cs_vals)
        if avg_cs < 5.5:
            gaps.append("Below-average CS/min across team — resource deficit risk")

    # Low win rate
    wr_vals = [p["win_rate_20"] for p in player_stats if p.get("win_rate_20")]
    if wr_vals:
        avg_wr = sum(wr_vals) / len(wr_vals)
        if avg_wr < 0.45:
            gaps.append("Team average win rate below 45% — consider role adjustments")

    # All carries, no utility/engage
    carry_count = sum(
        1 for p in player_stats
        if str(p.get("primary_role") or "").upper() in ("BOTTOM", "MIDDLE")
    )
    utility_count = sum(
        1 for p in player_stats
        if str(p.get("primary_role") or "").upper() in ("UTILITY", "SUPPORT")
    )
    if carry_count >= 3 and utility_count == 0:
        gaps.append("Heavy carry composition with no utility/engage — vulnerable to dive")

    return gaps


def _team_strengths(player_stats: list[dict]) -> list[str]:
    """Identify positive signals in the team composition."""
    strengths = []

    wr_vals = [p["win_rate_20"] for p in player_stats if p.get("win_rate_20")]
    kda_vals = [p["avg_kda_20"] for p in player_stats if p.get("avg_kda_20")]
    cs_vals  = [p["avg_cs_per_min_20"] for p in player_stats if p.get("avg_cs_per_min_20")]

    if wr_vals and sum(wr_vals) / len(wr_vals) >= 0.55:
        strengths.append("High team win rate — consistent performers")
    if kda_vals and sum(kda_vals) / len(kda_vals) >= 3.5:
        strengths.append("Strong average KDA — team dies infrequently")
    if cs_vals and sum(cs_vals) / len(cs_vals) >= 7.5:
        strengths.append("Excellent farm efficiency — high resource generation")

    roles_present = {
        str(p.get("primary_role") or "").upper()
        for p in player_stats if p.get("primary_role")
    }
    if len(roles_present) == 5:
        strengths.append("Full role coverage — balanced composition")

    return strengths


def _playstyle_warnings(player_playstyles: list[dict]) -> list[str]:
    """
    Generate team-level playstyle composition warnings.

    player_playstyles: list of dicts, each with 'playstyle_label' and 'summoner_name'.
    Returns a list of human-readable warning strings.
    """
    warnings: list[str] = []
    from collections import Counter
    label_counts: Counter = Counter(
        p["playstyle_label"] for p in player_playstyles
        if p.get("playstyle_label") and p["playstyle_label"] not in ("unknown", "insufficient_data")
    )

    # Too many of one archetype
    for label, count in label_counts.items():
        if count >= 3:
            names = [
                p.get("summoner_name", "?")
                for p in player_playstyles
                if p.get("playstyle_label") == label
            ]
            hint = _PLAYSTYLE_ROLE_HINT.get(label, label)
            warnings.append(
                f"{count} players classified as '{label}' ({', '.join(names)}) — "
                f"all naturally suited to {hint}. Consider redistributing roles."
            )
        elif count == 2 and label == "carry":
            names = [
                p.get("summoner_name", "?")
                for p in player_playstyles
                if p.get("playstyle_label") == label
            ]
            warnings.append(
                f"2 carry-archetype players ({', '.join(names)}) — "
                f"confirm only one takes BOTTOM/MID to avoid resource contention."
            )

    # No utility/engage archetype
    if label_counts.get("support_utility", 0) == 0 and sum(label_counts.values()) >= 3:
        warnings.append(
            "No support-utility archetype on the team — vision, peel, and engage may be lacking."
        )

    return warnings


# Normalize short role codes (frontend) → canonical affinity role names (backend)
_ROLE_NORMALIZE: dict[str, str] = {
    "MID":     "MIDDLE",
    "MIDDLE":  "MIDDLE",
    "BOT":     "BOTTOM",
    "BOTTOM":  "BOTTOM",
    "TOP":     "TOP",
    "JUNGLE":  "JUNGLE",
    "SUPPORT": "SUPPORT",
    "UTILITY": "UTILITY",
}


def _fetch_player_playstyles(db, player_stats: list[dict]) -> list[dict]:
    """
    Fetch playstyle for every player who has a puuid tracked in the DB.
    Returns a parallel list of playstyle dicts (safe — never raises).
    """
    results = []
    for p in player_stats:
        puuid = p.get("puuid")
        if not puuid:
            results.append({"playstyle_label": None, "playstyle_recommended_roles": [], "role_mismatch": False})
            continue
        try:
            ps = get_player_playstyle(db, puuid)
            label = ps.get("playstyle_label")
            recommended = _PLAYSTYLE_ROLE_AFFINITY.get(label or "", [])
            raw_role = str(p.get("declared_role") or p.get("primary_role") or "").upper()
            declared = _ROLE_NORMALIZE.get(raw_role, raw_role)
            mismatch = bool(declared and recommended and declared not in recommended)
            results.append({
                "playstyle_label":             label,
                "playstyle_recommended_roles": recommended,
                "role_mismatch":               mismatch,
                "summoner_name":               p.get("summoner_name"),
            })
        except Exception:
            results.append({"playstyle_label": None, "playstyle_recommended_roles": [], "role_mismatch": False})
    return results


def _fetch_champion_recs(
    db,
    player_stats: list[dict],
    player_slots: list[dict],
    top_n: int = 3,
) -> list[list[dict]]:
    """
    Fetch top-N champion recommendations for each player.

    Only fetches when a player has a puuid tracked in the DB AND no champion
    was provided by the caller (champion_meta is None).  Players who already
    picked a champion get an empty list — no recommendation needed.

    Returns a parallel list of recommendation lists (safe — never raises).
    """
    results = []
    for i, p in enumerate(player_stats):
        puuid = p.get("puuid")
        already_has_champion = player_slots[i].get("champion_meta") is not None
        if not puuid or already_has_champion:
            results.append([])
            continue
        try:
            # Pass the player's declared/primary role as a filter hint so
            # recommendations stay relevant to their lane.
            raw_role = str(p.get("declared_role") or p.get("primary_role") or "").upper()
            canonical = _ROLE_NORMALIZE.get(raw_role, raw_role)
            recs = get_champion_recommendations(db, puuid, top_n=top_n, role_filter=canonical or None)
            # Trim to safe subset of keys for the API response
            results.append([
                {
                    "champion_id":       r.get("champion_id"),
                    "champion_name":     r.get("champion_name"),
                    "role":              r.get("role"),
                    "score":             r.get("score"),
                    "games_played":      r.get("games_played"),
                    "win_rate":          r.get("win_rate"),
                    "smoothed_win_rate": r.get("smoothed_win_rate"),
                    "playstyle_match":   r.get("playstyle_match"),
                }
                for r in recs
            ])
        except Exception:
            results.append([])
    return results


def _aggregate_team(player_stats: list[dict]) -> dict:
    """Compute team-level averages from individual player stats."""
    numeric_keys = [
        "win_rate_20", "avg_kda_20", "avg_cs_per_min_20",
        "avg_gold_per_min_20", "avg_kill_part_20", "avg_vision_per_min_20",
    ]
    agg: dict[str, Any] = {}
    for key in numeric_keys:
        vals = [p[key] for p in player_stats if p.get(key) is not None]
        agg[key] = round(sum(vals) / len(vals), 4) if vals else None
    agg["players_with_data"] = sum(
        1 for p in player_stats if p.get("games_in_window", 0) >= 5
    )
    return agg


# ---------------------------------------------------------------------------
# Champion + composition helpers
# ---------------------------------------------------------------------------

# Adjacent roles used to classify "flex" picks.
# A champion is flex if its role_affinity doesn't include the declared role
# but does include a role commonly played adjacent to it on the map.
_FLEX_ADJACENCY: Dict[str, set] = {
    "TOP":     {"JUNGLE"},
    "JUNGLE":  {"TOP", "MIDDLE"},
    "MIDDLE":  {"JUNGLE", "UTILITY"},
    "BOTTOM":  set(),
    "UTILITY": {"MIDDLE"},
}


def _role_champion_fit(champion_meta: Optional[Dict], declared_role: Optional[str]) -> str:
    """
    Classify how well a champion fits a declared lane role.

    Returns:
        "native"   — champion's role_affinity includes the declared role
        "flex"     — affinity covers an adjacent role (common flex pick)
        "off-meta" — no affinity match at all (unconventional pick)
        "unknown"  — no champion or role data provided
    """
    if not champion_meta or not declared_role:
        return "unknown"
    role = declared_role.upper()
    affinity: List[str] = champion_meta.get("role_affinity", [])
    if role in affinity:
        return "native"
    if any(a in affinity for a in _FLEX_ADJACENCY.get(role, set())):
        return "flex"
    return "off-meta"


# Ordered rules: first match wins.
# Each entry is (archetype_label, predicate(tag_counter)).
_ARCHETYPE_RULES: List[tuple] = [
    ("skirmish-brawl", lambda t: t.get("Assassin", 0) >= 2),
    ("poke-siege",     lambda t: t.get("Mage", 0) >= 3),
    ("engage-dive",    lambda t: (t.get("Tank", 0) + t.get("Fighter", 0)) >= 3 and t.get("Tank", 0) >= 1),
    ("split-push",     lambda t: t.get("Fighter", 0) >= 3),
    ("teamfight",      lambda t: t.get("Tank", 0) >= 1 and t.get("Marksman", 0) >= 1 and t.get("Mage", 0) >= 1),
]


def _composition_archetype(player_slots: List[Dict]) -> str:
    """
    Derive the team composition archetype from champion tag frequencies.

    player_slots: list of dicts, each with an optional "champion_meta" key.

    Returns one of: skirmish-brawl, poke-siege, engage-dive, split-push,
                    teamfight, balanced, unknown.
    """
    tag_counts: Counter = Counter()
    for slot in player_slots:
        meta = slot.get("champion_meta")
        if meta:
            tag_counts.update(meta.get("tags", []))

    if not tag_counts:
        return "unknown"

    for name, test_fn in _ARCHETYPE_RULES:
        if test_fn(tag_counts):
            return name
    return "balanced"


def _synergy_flags(player_slots: List[Dict]) -> List[str]:
    """
    Identify notable synergies and composition gaps for a team.

    player_slots: list of dicts, each with optional "champion_meta" and
                  "role_champion_fit" keys.

    Returns a list of human-readable strings — positive synergies first,
    then risk/gap warnings.
    """
    flags: List[str] = []
    tag_counts: Counter = Counter()
    off_meta_count = 0

    for slot in player_slots:
        meta = slot.get("champion_meta")
        if meta:
            tag_counts.update(meta.get("tags", []))
        if slot.get("role_champion_fit") == "off-meta":
            off_meta_count += 1

    if not tag_counts:
        return flags

    # ── Positive synergies ──────────────────────────────────────────────────
    if tag_counts.get("Tank", 0) + tag_counts.get("Fighter", 0) >= 3:
        flags.append("Strong frontline — multiple tanks/fighters enable deep dives and zone control")

    if tag_counts.get("Mage", 0) >= 2:
        flags.append("Multiple mages — sustained AoE poke and teamfight damage")

    if tag_counts.get("Assassin", 0) >= 2:
        flags.append("Dual assassin burst — high pick potential, but requires leads to function")

    if tag_counts.get("Support", 0) >= 1 and tag_counts.get("Tank", 0) >= 1:
        flags.append("Engage + peel coverage — can both initiate and protect carries")

    # ── Gaps / risks ────────────────────────────────────────────────────────
    if tag_counts.get("Marksman", 0) == 0:
        flags.append("No marksman — sustained physical DPS source missing, consider ADC alternative")

    if tag_counts.get("Mage", 0) == 0 and tag_counts.get("Assassin", 0) == 0:
        flags.append("No magic damage — enemy can itemise pure armor and nullify team damage")

    if tag_counts.get("Support", 0) == 0:
        flags.append("No dedicated support — vision control and carry peel may be lacking")

    if tag_counts.get("Tank", 0) == 0 and tag_counts.get("Fighter", 0) == 0:
        flags.append("No frontline — team is vulnerable to engage and hard to siege objectives")

    # ── Pick quality ─────────────────────────────────────────────────────────
    if off_meta_count == 1:
        flags.append("1 off-meta pick — unconventional selection may create surprise value or expose a weak lane")
    elif off_meta_count >= 2:
        flags.append(
            f"{off_meta_count} off-meta picks — high-variance composition, requires strong individual performance"
        )

    return flags


async def _resolve_champion_slots(
    player_inputs: List[PlayerInput],
    player_stats:  List[Dict],
) -> List[Dict]:
    """
    Resolve champion metadata and role fit for each player slot.

    Loads DDragon full map only when at least one PlayerInput has champion data.
    Returns a list parallel to player_inputs, each dict containing:
        champion_meta     — full metadata or None
        role              — resolved role string or None
        role_champion_fit — "native" | "flex" | "off-meta" | "unknown"
    """
    has_champion_data = any(p.champion_id or p.champion for p in player_inputs)
    champ_full_map: Dict[int, Any] = {}
    if has_champion_data:
        champ_full_map = await get_champion_full_map()

    slots: List[Dict] = []
    for i, p_input in enumerate(player_inputs):
        p_stat = player_stats[i] if i < len(player_stats) else {}

        # Resolve champion meta — id takes priority, name is fallback
        champ_meta: Optional[Dict] = None
        if p_input.champion_id and p_input.champion_id in champ_full_map:
            raw = champ_full_map[p_input.champion_id]
            champ_meta = {
                "id":           raw["id"],
                "name":         raw["name"],
                "title":        raw["title"],
                "tags":         raw["tags"],
                "image_url":    raw["image_url"],
                "role_affinity":raw["role_affinity"],
            }
        elif p_input.champion and champ_full_map:
            # Name lookup — case-insensitive
            name_lower = p_input.champion.strip().lower()
            for raw in champ_full_map.values():
                if raw["name"].lower() == name_lower:
                    champ_meta = {
                        "id":           raw["id"],
                        "name":         raw["name"],
                        "title":        raw["title"],
                        "tags":         raw["tags"],
                        "image_url":    raw["image_url"],
                        "role_affinity":raw["role_affinity"],
                    }
                    break

        # Resolve role: declared > primary from stats
        resolved_role = (
            p_input.role.upper() if p_input.role
            else str(p_stat.get("primary_role") or "").upper() or None
        )

        slots.append({
            "champion_meta":     champ_meta,
            "role":              resolved_role,
            "role_champion_fit": _role_champion_fit(champ_meta, resolved_role),
        })

    return slots


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/build")
async def build_team(
    body: TeamBuildRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Analyze a team of up to 5 players.

    For each player:
      - If tracked in DB → use stored rolling stats (fast)
      - Otherwise → live fetch from Riot API

    Returns per-player stats, team aggregates, composition gaps,
    and composition strengths.
    """
    player_inputs = [
        {"game_name": p.game_name, "tag_line": p.tag_line}
        for p in body.players
    ]

    player_stats = await get_team_stats(player_inputs, platform=body.platform, db=db)

    # Attach declared role if provided (needed by _team_gaps and AI analysis)
    for i, pstat in enumerate(player_stats):
        declared = body.players[i].role
        if declared:
            pstat["declared_role"] = declared.upper()

    # Resolve champion metadata + role fit for every slot
    player_slots = await _resolve_champion_slots(body.players, player_stats)

    team_agg    = _aggregate_team(player_stats)
    gaps        = _team_gaps(player_stats)
    strengths   = _team_strengths(player_stats)
    ai_analysis = analyze_team_composition(db, player_stats)

    composition_archetype = _composition_archetype(player_slots)
    synergy_flags         = _synergy_flags(player_slots)

    # Playstyle per player (silently skipped when model not trained)
    player_playstyle_data = _fetch_player_playstyles(db, player_stats)
    playstyle_warnings    = _playstyle_warnings(player_playstyle_data)

    # Champion recommendations for players who didn't select a champion
    player_champ_recs = _fetch_champion_recs(db, player_stats, player_slots)

    # Per-player summary with confidence label + champion + playstyle enrichment
    players_out = []
    for i, p in enumerate(player_stats):
        games = int(p.get("games_in_window", 0))
        confidence = (
            "high"   if games >= 15 else
            "medium" if games >= 5  else
            "low"
        )
        slot = player_slots[i]
        ps   = player_playstyle_data[i]
        players_out.append({
            "summoner_name":               p.get("summoner_name"),
            "puuid":                       p.get("puuid"),
            "source":                      p.get("source", "unknown"),
            "primary_role":                p.get("primary_role"),
            "declared_role":               p.get("declared_role"),
            # Champion selection (null when not provided by caller)
            "champion_meta":               slot["champion_meta"],
            "role_champion_fit":           slot["role_champion_fit"],
            "games_in_window":             games,
            "confidence":                  confidence,
            "win_rate_20":                 p.get("win_rate_20"),
            "avg_kda_20":                  p.get("avg_kda_20"),
            "avg_cs_per_min_20":           p.get("avg_cs_per_min_20"),
            "avg_gold_per_min_20":         p.get("avg_gold_per_min_20"),
            "avg_kill_part_20":            p.get("avg_kill_part_20"),
            "avg_vision_per_min_20":       p.get("avg_vision_per_min_20"),
            "error":                       p.get("error"),
            # Playstyle enrichment
            "playstyle_label":             ps.get("playstyle_label"),
            "playstyle_recommended_roles": ps.get("playstyle_recommended_roles", []),
            "role_mismatch":               ps.get("role_mismatch", False),
            # Champion recommendations (populated when no champion was provided)
            "recommended_champions":       player_champ_recs[i],
        })

    return {
        "platform":             body.platform,
        "composition_focus":    body.composition_focus,
        "players":              players_out,
        "team_stats":           team_agg,
        "strengths":            strengths,
        "gaps":                 gaps,
        "playstyle_warnings":   playstyle_warnings,
        # Composition analysis (populated when champion data is provided)
        "composition_archetype": composition_archetype,
        "synergy_flags":         synergy_flags,
        # AI analysis
        "team_dna":              ai_analysis["team_dna"],
        "threat_scores":         ai_analysis["threat_scores"],
        "predicted_carry":       ai_analysis["predicted_carry"],
    }


@router.post("/matchup")
async def predict_matchup(
    body: MatchupRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Predict win probability for a blue vs red team matchup.

    Fetches stats for all 10 players (DB-first, live fallback), computes
    team-level averages, runs a stat comparison, and returns win probability
    alongside per-role matchup breakdown.
    """
    blue_inputs = [{"game_name": p.game_name, "tag_line": p.tag_line} for p in body.blue_team]
    red_inputs  = [{"game_name": p.game_name, "tag_line": p.tag_line} for p in body.red_team]

    # Fetch both teams concurrently
    import asyncio as _asyncio
    blue_stats, red_stats = await _asyncio.gather(
        get_team_stats(blue_inputs, platform=body.platform, db=db),
        get_team_stats(red_inputs,  platform=body.platform, db=db),
    )

    # Attach declared roles so role_matchup_breakdown can pair by role
    for i, p in enumerate(body.blue_team):
        if p.role:
            blue_stats[i]["declared_role"] = p.role.upper()
    for i, p in enumerate(body.red_team):
        if p.role:
            red_stats[i]["declared_role"] = p.role.upper()

    # Resolve champion metadata + role fit for both teams (single DDragon cache hit)
    blue_slots, red_slots = await _asyncio.gather(
        _resolve_champion_slots(body.blue_team, blue_stats),
        _resolve_champion_slots(body.red_team,  red_stats),
    )

    blue_agg = _aggregate_team(blue_stats)
    red_agg  = _aggregate_team(red_stats)

    # --- Win probability: ML model preferred, rule-based fallback ---
    def _safe(val, default=0.5):
        return val if val is not None else default

    blue_win_prob = 0.5
    win_prob_source = "rule_based"

    try:
        artifact = _load_model("matchup_predictor")
        model      = artifact["model"]
        scaler     = artifact.get("scaler")
        feat_cols  = artifact["feature_cols"]
        medians    = artifact.get("train_medians", {})

        import numpy as _np
        import pandas as _pd

        def _agg(stats, key, default):
            vals = [_safe(s.get(key), default) for s in stats]
            return float(_np.mean(vals)) if vals else default

        row = {}
        STAT_MAP = [
            ("t100_win_rate_20",        blue_stats, "win_rate_20",        0.5),
            ("t100_avg_kda_20",         blue_stats, "avg_kda_20",         2.5),
            ("t100_avg_cs_per_min_20",  blue_stats, "avg_cs_per_min_20",  7.0),
            ("t100_avg_gold_per_min_20", blue_stats, "avg_gold_per_min_20", 350.0),
            ("t100_vision_per_min_20",  blue_stats, "vision_per_min_20",  1.0),
            ("t100_avg_kill_part_20",   blue_stats, "avg_kill_part_20",   0.5),
            ("t200_win_rate_20",        red_stats,  "win_rate_20",        0.5),
            ("t200_avg_kda_20",         red_stats,  "avg_kda_20",         2.5),
            ("t200_avg_cs_per_min_20",  red_stats,  "avg_cs_per_min_20",  7.0),
            ("t200_avg_gold_per_min_20", red_stats,  "avg_gold_per_min_20", 350.0),
            ("t200_vision_per_min_20",  red_stats,  "vision_per_min_20",  1.0),
            ("t200_avg_kill_part_20",   red_stats,  "avg_kill_part_20",   0.5),
        ]
        for feat, stats, key, default in STAT_MAP:
            row[feat] = _agg(stats, key, default)

        # Differentials
        row["win_rate_diff"]  = row["t100_win_rate_20"]        - row["t200_win_rate_20"]
        row["kda_diff"]       = row["t100_avg_kda_20"]         - row["t200_avg_kda_20"]
        row["cs_diff"]        = row["t100_avg_cs_per_min_20"]  - row["t200_avg_cs_per_min_20"]
        row["gold_diff"]      = row["t100_avg_gold_per_min_20"] - row["t200_avg_gold_per_min_20"]
        row["vision_diff"]    = row["t100_vision_per_min_20"]  - row["t200_vision_per_min_20"]
        row["kill_part_diff"] = row["t100_avg_kill_part_20"]   - row["t200_avg_kill_part_20"]
        row["t100_tracked"]   = float(len(blue_stats))
        row["t200_tracked"]   = float(len(red_stats))
        row["patch_version_float"] = 0.0

        X_row = _pd.DataFrame([row])
        X_input = _np.array([[
            X_row[c].values[0] if c in X_row.columns else medians.get(c, 0.0)
            for c in feat_cols
        ]])

        if scaler is not None:
            X_input = scaler.transform(X_input)

        blue_win_prob = round(float(model.predict_proba(X_input)[0][1]), 4)
        win_prob_source = "matchup_model"

    except Exception:
        # Model not trained yet — fall back to rule-based weighted formula
        metrics = [
            ("win_rate_20",         0.40, 0.5),
            ("avg_kda_20",          0.25, 2.5),
            ("avg_cs_per_min_20",   0.20, 7.0),
            ("avg_gold_per_min_20", 0.15, 350.0),
        ]
        blue_score = 0.0
        red_score  = 0.0
        for key, weight, neutral in metrics:
            b = _safe(blue_agg.get(key), neutral)
            r = _safe(red_agg.get(key),  neutral)
            total = b + r
            if total > 0:
                blue_score += weight * (b / total)
                red_score  += weight * (r / total)
            else:
                blue_score += weight * 0.5
                red_score  += weight * 0.5
        total_score = blue_score + red_score
        blue_win_prob = round(blue_score / total_score, 4) if total_score > 0 else 0.5

    red_win_prob = round(1.0 - blue_win_prob, 4)

    # --- Playstyle + champion recs for both teams ---
    blue_playstyle_data = _fetch_player_playstyles(db, blue_stats)
    red_playstyle_data  = _fetch_player_playstyles(db, red_stats)
    blue_champ_recs     = _fetch_champion_recs(db, blue_stats, blue_slots)
    red_champ_recs      = _fetch_champion_recs(db, red_stats,  red_slots)

    # --- Per-role matchup breakdown ---
    def _player_row(pstat: dict, declared_role: Optional[str], slot: dict, ps: dict, champ_recs: list) -> dict:
        games = int(pstat.get("games_in_window", 0))
        return {
            "summoner_name":               pstat.get("summoner_name"),
            "puuid":                       pstat.get("puuid"),
            "source":                      pstat.get("source", "unknown"),
            "primary_role":                pstat.get("primary_role"),
            "declared_role":               declared_role,
            "champion_meta":               slot["champion_meta"],
            "role_champion_fit":           slot["role_champion_fit"],
            "games_in_window":             games,
            "confidence":                  "high" if games >= 15 else "medium" if games >= 5 else "low",
            "win_rate_20":                 pstat.get("win_rate_20"),
            "avg_kda_20":                  pstat.get("avg_kda_20"),
            "avg_cs_per_min_20":           pstat.get("avg_cs_per_min_20"),
            "avg_gold_per_min_20":         pstat.get("avg_gold_per_min_20"),
            "avg_kill_part_20":            pstat.get("avg_kill_part_20"),
            "avg_vision_per_min_20":       pstat.get("avg_vision_per_min_20"),
            "error":                       pstat.get("error"),
            "playstyle_label":             ps.get("playstyle_label"),
            "playstyle_recommended_roles": ps.get("playstyle_recommended_roles", []),
            "role_mismatch":               ps.get("role_mismatch", False),
            "recommended_champions":       champ_recs,
        }

    blue_players_out = [
        _player_row(s, body.blue_team[i].role, blue_slots[i], blue_playstyle_data[i], blue_champ_recs[i])
        for i, s in enumerate(blue_stats)
    ]
    red_players_out = [
        _player_row(s, body.red_team[i].role, red_slots[i], red_playstyle_data[i], red_champ_recs[i])
        for i, s in enumerate(red_stats)
    ]

    # --- Key advantages per side ---
    advantages: dict[str, list[str]] = {"blue": [], "red": []}
    for key, label in [
        ("win_rate_20",       "Higher historical win rate"),
        ("avg_kda_20",        "Better average KDA"),
        ("avg_cs_per_min_20", "Better CS/min"),
    ]:
        b = _safe(blue_agg.get(key))
        r = _safe(red_agg.get(key))
        if b > r * 1.05:
            advantages["blue"].append(label)
        elif r > b * 1.05:
            advantages["red"].append(label)

    # --- Composition health ---
    blue_gaps = _team_gaps(blue_stats)
    red_gaps  = _team_gaps(red_stats)

    # --- AI analysis for both teams ---
    blue_ai = analyze_team_composition(db, blue_stats)
    red_ai  = analyze_team_composition(db, red_stats)

    # --- Composition archetype + synergy for both teams ---
    blue_archetype = _composition_archetype(blue_slots)
    red_archetype  = _composition_archetype(red_slots)
    blue_synergy   = _synergy_flags(blue_slots)
    red_synergy    = _synergy_flags(red_slots)

    # --- Role matchup breakdown ---
    role_matchups = role_matchup_breakdown(blue_stats, red_stats)

    # --- Edge count summary ---
    blue_edges = sum(1 for m in role_matchups if m["overall_edge"] == "blue")
    red_edges  = sum(1 for m in role_matchups if m["overall_edge"] == "red")
    even_lanes = sum(1 for m in role_matchups if m["overall_edge"] == "even")

    # --- Champion matchup warnings from researched CSV data ---
    # Cross-reference each lane's champion pair against the champion_matchups table.
    # Surfaces unfavorable (win_rate < 0.45) and favorable (win_rate > 0.55) flags.
    champion_matchup_flags: List[Dict[str, Any]] = []
    try:
        _UNFAV_THRESHOLD = 0.45
        _FAV_THRESHOLD   = 0.55

        for blue_slot, red_slot in zip(blue_slots, red_slots):
            b_champ_id = (blue_slot.get("champion_meta") or {}).get("id")
            r_champ_id = (red_slot.get("champion_meta") or {}).get("id")
            b_role = blue_slot.get("declared_role") or blue_slot.get("primary_role")
            if not b_champ_id or not r_champ_id:
                continue

            # Check both directions; prefer the stored direction
            row: Optional[ChampionMatchup] = db.query(ChampionMatchup).filter(
                ChampionMatchup.champion_a_id == b_champ_id,
                ChampionMatchup.champion_b_id == r_champ_id,
            ).first()
            inverted = False
            if row is None:
                row = db.query(ChampionMatchup).filter(
                    ChampionMatchup.champion_a_id == r_champ_id,
                    ChampionMatchup.champion_b_id == b_champ_id,
                ).first()
                inverted = row is not None

            if row is None:
                continue

            blue_wr = row.win_rate_a_vs_b if not inverted else 1.0 - row.win_rate_a_vs_b

            if blue_wr < _UNFAV_THRESHOLD:
                flag_type = "unfavorable_for_blue"
                msg = (
                    f"{blue_slot['champion_meta']['name']} vs "
                    f"{red_slot['champion_meta']['name']}"
                    f"{' in ' + b_role if b_role else ''}: "
                    f"Blue wins {round(blue_wr * 100, 1)}% — unfavorable matchup "
                    f"({row.confidence} confidence, {row.games_played} games)"
                )
            elif blue_wr > _FAV_THRESHOLD:
                flag_type = "favorable_for_blue"
                msg = (
                    f"{blue_slot['champion_meta']['name']} vs "
                    f"{red_slot['champion_meta']['name']}"
                    f"{' in ' + b_role if b_role else ''}: "
                    f"Blue wins {round(blue_wr * 100, 1)}% — favorable matchup "
                    f"({row.confidence} confidence, {row.games_played} games)"
                )
            else:
                continue  # even matchup, no flag needed

            champion_matchup_flags.append({
                "type":                flag_type,
                "blue_champion_id":    b_champ_id,
                "blue_champion_name":  (blue_slot.get("champion_meta") or {}).get("name"),
                "red_champion_id":     r_champ_id,
                "red_champion_name":   (red_slot.get("champion_meta") or {}).get("name"),
                "role":                b_role,
                "blue_win_rate":       round(blue_wr, 4),
                "confidence":          row.confidence,
                "games_played":        row.games_played,
                "source":              row.source,
                "message":             msg,
            })
    except Exception as _e:
        logger.warning("Champion matchup flag lookup failed: %s", _e)

    return {
        "platform":               body.platform,
        "blue_win_probability":   blue_win_prob,
        "red_win_probability":    red_win_prob,
        "prediction_method":      win_prob_source,
        "role_matchups":          role_matchups,
        "champion_matchup_flags": champion_matchup_flags,   # NEW — from researched CSV data
        "lane_edges": {
            "blue_lanes_winning": blue_edges,
            "red_lanes_winning":  red_edges,
            "even_lanes":         even_lanes,
        },
        "blue_team": {
            "players":               blue_players_out,
            "team_stats":            blue_agg,
            "gaps":                  blue_gaps,
            "composition_archetype": blue_archetype,
            "synergy_flags":         blue_synergy,
            "team_dna":              blue_ai["team_dna"],
            "threat_scores":         blue_ai["threat_scores"],
            "predicted_carry":       blue_ai["predicted_carry"],
        },
        "red_team": {
            "players":               red_players_out,
            "team_stats":            red_agg,
            "gaps":                  red_gaps,
            "composition_archetype": red_archetype,
            "synergy_flags":         red_synergy,
            "team_dna":              red_ai["team_dna"],
            "threat_scores":         red_ai["threat_scores"],
            "predicted_carry":       red_ai["predicted_carry"],
        },
        "key_advantages": advantages,
    }
