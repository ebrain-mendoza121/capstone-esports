"""
teams.py — Team composition analysis + matchup prediction routes.

POST /teams/build          → analyze a 5-player team (stats + gaps)
POST /teams/matchup        → team vs team prediction with per-role breakdown
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.riot_live_service import get_team_stats, get_live_player_stats
from app.services.ai_service import analyze_team_composition, role_matchup_breakdown, _load_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PlayerInput(BaseModel):
    game_name: str = Field(..., description="Riot ID game name, e.g. 'Faker'")
    tag_line:  str = Field("NA1", description="Riot ID tag, e.g. 'NA1'")
    role:      Optional[str] = Field(None, description="Expected role if known (TOP/JUNGLE/etc)")


class TeamBuildRequest(BaseModel):
    players:  List[PlayerInput] = Field(..., min_length=1, max_length=5)
    platform: str = Field("NA", description="Platform (NA, EUW, KR, …)")


class MatchupRequest(BaseModel):
    blue_team: List[PlayerInput] = Field(..., min_length=1, max_length=5)
    red_team:  List[PlayerInput] = Field(..., min_length=1, max_length=5)
    platform:  str = Field("NA")


# ---------------------------------------------------------------------------
# Composition analysis helpers
# ---------------------------------------------------------------------------

_ROLE_ORDER = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

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

    # Attach declared role if provided
    for i, pstat in enumerate(player_stats):
        declared = body.players[i].role
        if declared:
            pstat["declared_role"] = declared.upper()

    team_agg    = _aggregate_team(player_stats)
    gaps        = _team_gaps(player_stats)
    strengths   = _team_strengths(player_stats)
    ai_analysis = analyze_team_composition(db, player_stats)

    # Per-player summary with confidence label
    players_out = []
    for p in player_stats:
        games = int(p.get("games_in_window", 0))
        confidence = (
            "high"   if games >= 15 else
            "medium" if games >= 5  else
            "low"
        )
        players_out.append({
            "summoner_name":         p.get("summoner_name"),
            "puuid":                 p.get("puuid"),
            "source":                p.get("source", "unknown"),
            "primary_role":          p.get("primary_role"),
            "declared_role":         p.get("declared_role"),
            "games_in_window":       games,
            "confidence":            confidence,
            "win_rate_20":           p.get("win_rate_20"),
            "avg_kda_20":            p.get("avg_kda_20"),
            "avg_cs_per_min_20":     p.get("avg_cs_per_min_20"),
            "avg_gold_per_min_20":   p.get("avg_gold_per_min_20"),
            "avg_kill_part_20":      p.get("avg_kill_part_20"),
            "avg_vision_per_min_20": p.get("avg_vision_per_min_20"),
            "error":                 p.get("error"),
        })

    return {
        "platform":        body.platform,
        "players":         players_out,
        "team_stats":      team_agg,
        "strengths":       strengths,
        "gaps":            gaps,
        "team_dna":        ai_analysis["team_dna"],
        "threat_scores":   ai_analysis["threat_scores"],
        "predicted_carry": ai_analysis["predicted_carry"],
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
            ("t100_avg_gold_per_min_20",blue_stats, "avg_gold_per_min_20",350.0),
            ("t100_vision_per_min_20",  blue_stats, "vision_per_min_20",  1.0),
            ("t100_avg_kill_part_20",   blue_stats, "avg_kill_part_20",   0.5),
            ("t200_win_rate_20",        red_stats,  "win_rate_20",        0.5),
            ("t200_avg_kda_20",         red_stats,  "avg_kda_20",         2.5),
            ("t200_avg_cs_per_min_20",  red_stats,  "avg_cs_per_min_20",  7.0),
            ("t200_avg_gold_per_min_20",red_stats,  "avg_gold_per_min_20",350.0),
            ("t200_vision_per_min_20",  red_stats,  "vision_per_min_20",  1.0),
            ("t200_avg_kill_part_20",   red_stats,  "avg_kill_part_20",   0.5),
        ]
        for feat, stats, key, default in STAT_MAP:
            row[feat] = _agg(stats, key, default)

        # Differentials
        row["win_rate_diff"]  = row["t100_win_rate_20"]        - row["t200_win_rate_20"]
        row["kda_diff"]       = row["t100_avg_kda_20"]         - row["t200_avg_kda_20"]
        row["cs_diff"]        = row["t100_avg_cs_per_min_20"]  - row["t200_avg_cs_per_min_20"]
        row["gold_diff"]      = row["t100_avg_gold_per_min_20"]- row["t200_avg_gold_per_min_20"]
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

    # --- Per-role matchup breakdown ---
    def _player_row(pstat: dict, declared_role: Optional[str]) -> dict:
        games = int(pstat.get("games_in_window", 0))
        return {
            "summoner_name":  pstat.get("summoner_name"),
            "source":         pstat.get("source", "unknown"),
            "role":           declared_role or pstat.get("primary_role"),
            "games":          games,
            "confidence":     "high" if games >= 15 else "medium" if games >= 5 else "low",
            "win_rate_20":    pstat.get("win_rate_20"),
            "avg_kda_20":     pstat.get("avg_kda_20"),
            "avg_cs_per_min": pstat.get("avg_cs_per_min_20"),
        }

    blue_players_out = [
        _player_row(s, body.blue_team[i].role)
        for i, s in enumerate(blue_stats)
    ]
    red_players_out = [
        _player_row(s, body.red_team[i].role)
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

    # --- Role matchup breakdown ---
    role_matchups = role_matchup_breakdown(blue_stats, red_stats)

    # --- Edge count summary ---
    blue_edges = sum(1 for m in role_matchups if m["overall_edge"] == "blue")
    red_edges  = sum(1 for m in role_matchups if m["overall_edge"] == "red")
    even_lanes = sum(1 for m in role_matchups if m["overall_edge"] == "even")

    return {
        "platform":             body.platform,
        "blue_win_probability": blue_win_prob,
        "red_win_probability":  red_win_prob,
        "prediction_method":    win_prob_source,
        "role_matchups":        role_matchups,
        "lane_edges": {
            "blue_lanes_winning": blue_edges,
            "red_lanes_winning":  red_edges,
            "even_lanes":         even_lanes,
        },
        "blue_team": {
            "players":         blue_players_out,
            "team_stats":      blue_agg,
            "gaps":            blue_gaps,
            "team_dna":        blue_ai["team_dna"],
            "threat_scores":   blue_ai["threat_scores"],
            "predicted_carry": blue_ai["predicted_carry"],
        },
        "red_team": {
            "players":         red_players_out,
            "team_stats":      red_agg,
            "gaps":            red_gaps,
            "team_dna":        red_ai["team_dna"],
            "threat_scores":   red_ai["threat_scores"],
            "predicted_carry": red_ai["predicted_carry"],
        },
        "key_advantages": advantages,
    }
