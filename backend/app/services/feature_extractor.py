"""
feature_extractor.py
====================
Data-layer service bridging raw DB tables and ML models.

All public functions:
- Accept ``db: Session`` (synchronous SQLAlchemy — see app/db/session.py)
- Use ``text()`` for raw SQL — never ORM select for multi-table aggregates
- Return ``pd.DataFrame`` or ``dict``
- Apply median imputation for numeric NULLs before returning
- Filter ``queue_id = 420`` (ranked solo/duo) unless noted otherwise
- Never raise on empty results — return empty DataFrame or empty dict

Key schema note
---------------
``participant_stats`` has ``player_id`` (FK → ``players.id``) but NO ``puuid``
column.  Any query requiring a player's puuid must bridge through the
``players`` table::

    JOIN players p ON p.id = ps.player_id
    -- then reference p.puuid

Connection map
--------------
``ai_service.py`` imports all public functions + constants from this module.
Route handlers (``api/routes/ai.py``) never import this file directly.
``feature_extractor.py`` requires no startup wiring — it is called on demand.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — imported by ai_service.py
# ---------------------------------------------------------------------------

CLUSTERING_FEATURES: list[str] = [
    "avg_kda",
    "avg_cs_per_min",
    "avg_gold_per_min",
    "avg_kill_participation",
    "avg_damage_share",
    "avg_vision_per_min",
    "avg_kills",
    "avg_deaths",
    "avg_assists",
    "avg_wards_placed",
    "avg_vision_score",
    "first_blood_rate",
    "physical_dmg_pct",
    "magic_dmg_pct",
]

ROLLING_FEATURES: list[str] = [
    "win_rate_20",
    "avg_kda_20",
    "avg_cs_per_min_20",
    "avg_gold_per_min_20",
    "avg_kill_part_20",
    "win_streak",
    # --- added: volatility & momentum ---
    "death_rate_20",       # avg deaths/game rolling window — high value = tilting/diving
    "vision_per_min_20",  # rolling vision density — proxy for warding habit consistency
    "kda_std_10",         # KDA standard deviation over last 10 — measures consistency
    "cs_trend_10",        # slope of cs/min over last 10 — positive = improving farm
]

TIMELINE_FEATURES: list[str] = [
    "gold_diff_10",
    "xp_diff_10",
    "level_diff_10",
    "cs_diff_10",
    "gold_diff_15",
    "xp_diff_15",
    "first_blood_team",
    "first_tower_team",
    "first_dragon_team",
]

ROLE_ENCODING: dict[str, int] = {
    "TOP": 0,
    "JUNGLE": 1,
    "MIDDLE": 2,
    "BOTTOM": 3,
    "UTILITY": 4,
    "NONE": -1,
}

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _linear_trend(values: list[float]) -> float:
    """Return the slope of a least-squares line fit through ``values``.

    Values are ordered oldest-first.  A positive slope means the metric is
    *improving* over time; negative means declining.

    Returns ``0.0`` if fewer than 2 data points are provided.
    """
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = float(np.mean(values))
    num = float(np.sum((x - x_mean) * (np.array(values) - y_mean)))
    den = float(np.sum((x - x_mean) ** 2))
    return num / den if den != 0.0 else 0.0


def _impute_medians(df: pd.DataFrame) -> pd.DataFrame:
    """In-place median imputation for all numeric columns.  Returns df."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        median_val = df[col].median()
        df[col] = df[col].fillna(median_val)
    return df


def _compute_streak(results: list[bool]) -> int:
    """Compute consecutive win/loss streak.

    Args:
        results: Boolean list ordered most-recent-first.

    Returns:
        Positive integer = consecutive wins.
        Negative integer = consecutive losses.
        0 if the list is empty.
    """
    if not results:
        return 0
    streak = 1 if results[0] else -1
    for i in range(1, len(results)):
        if results[i] == results[0]:
            streak += 1 if results[0] else -1
        else:
            break
    return streak


def _add_win_streak_column(df: pd.DataFrame) -> pd.DataFrame:
    """Compute win_streak for every row in a multi-player DataFrame.

    For each row at position i within a player's game history, the streak is
    derived from that player's *prior* games only (wins[:i] reversed to
    most-recent-first), matching the strict-prior semantics of
    ``get_rolling_features()``.

    The DataFrame must contain ``puuid``, ``game_creation``, and ``win``
    columns.  The operation is O(N·G) where N = total rows and G = average
    games per player — acceptable for training workloads.

    Returns:
        A copy of ``df`` sorted by (puuid, game_creation) with a new
        ``win_streak`` column appended.
    """
    streaks: list[int] = []
    for _puuid, group in df.groupby("puuid"):
        group = group.sort_values("game_creation")
        wins = group["win"].tolist()
        for i in range(len(wins)):
            prior = wins[:i]          # strictly prior games — same as shift(1)
            streaks.append(_compute_streak(list(reversed(prior))))
    df = df.sort_values(["puuid", "game_creation"]).copy()
    df["win_streak"] = streaks
    return df


def _encode_patch(patch_version: Optional[str]) -> float:
    """Convert patch version string to a sortable float.

    Examples::

        "14.8.1"  → 14.08
        "14.10.1" → 14.10

    Returns ``0.0`` on any parse failure.
    """
    if not patch_version:
        return 0.0
    try:
        parts = patch_version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return float(f"{major}.{minor:02d}")
    except (ValueError, IndexError):
        return 0.0


def _killer_team_from_event(raw_event: dict) -> int:
    """Extract killer team from a raw Riot timeline event JSON dict.

    Priority:
      1. ``raw_event["killerTeamId"]`` when present.
      2. Derive from ``raw_event["killerId"]``: participant IDs 1–5 → team 100,
         IDs 6–10 → team 200.

    Returns:
        ``1`` for team 100, ``-1`` for team 200, ``0`` if unknown.
    """
    killer_team_id = raw_event.get("killerTeamId")
    if killer_team_id == 100:
        return 1
    if killer_team_id == 200:
        return -1

    killer_id = raw_event.get("killerId")
    if killer_id is not None:
        try:
            kid = int(killer_id)
            if 1 <= kid <= 5:
                return 1
            if 6 <= kid <= 10:
                return -1
        except (ValueError, TypeError):
            pass
    return 0


def _has_derived_metrics(db: Session, puuid: str) -> bool:
    """Return True if the player has at least one derived_metrics row."""
    result = db.execute(
        text("SELECT 1 FROM derived_metrics WHERE puuid = :puuid LIMIT 1"),
        {"puuid": puuid},
    ).scalar()
    return result is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_clustering_features(db: Session) -> pd.DataFrame:
    """Return one row per player with 14 aggregate features for KMeans clustering.

    Only players with ≥ 5 ranked (queue_id = 420) games are included.

    Join note: ``participant_stats`` has ``player_id`` (FK → ``players.id``)
    but no ``puuid`` column.  The query bridges through ``players`` so that
    ``derived_metrics`` (keyed on ``puuid``) can be joined correctly.

    Returns:
        DataFrame with columns: ``puuid``, ``riot_id``, ``games_played``,
        and all 14 ``CLUSTERING_FEATURES``.  Empty DataFrame if no data.
    """
    sql = text("""
        SELECT
            p.puuid,
            p.riot_id,
            COUNT(ps.match_id)                                              AS games_played,

            -- Derived-metrics averages
            AVG(dm.kda)                                                     AS avg_kda,
            AVG(dm.cs_per_min)                                              AS avg_cs_per_min,
            AVG(dm.gold_per_min)                                            AS avg_gold_per_min,
            AVG(dm.kill_participation)                                      AS avg_kill_participation,
            AVG(dm.damage_share)                                            AS avg_damage_share,
            AVG(dm.vision_per_min)                                          AS avg_vision_per_min,

            -- Raw participant-stats averages
            AVG(ps.kills)                                                   AS avg_kills,
            AVG(ps.deaths)                                                  AS avg_deaths,
            AVG(ps.assists)                                                 AS avg_assists,
            AVG(ps.wards_placed)                                            AS avg_wards_placed,
            AVG(ps.vision_score)                                            AS avg_vision_score,
            AVG((ps.first_blood_kill)::int)                                 AS first_blood_rate,

            -- Damage composition ratios (NULLIF guard via CASE)
            AVG(
                CASE WHEN ps.total_damage > 0
                THEN ps.physical_damage_to_champions::float / ps.total_damage
                ELSE NULL END
            )                                                               AS physical_dmg_pct,
            AVG(
                CASE WHEN ps.total_damage > 0
                THEN ps.magic_damage_to_champions::float / ps.total_damage
                ELSE NULL END
            )                                                               AS magic_dmg_pct

        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN matches m          ON m.match_id = ps.match_id
        JOIN derived_metrics dm ON dm.match_id = ps.match_id
                               AND dm.puuid = p.puuid
        WHERE m.queue_id = 420
          AND EXISTS (
              SELECT 1 FROM derived_metrics dm2
              WHERE dm2.puuid = p.puuid
          )
        GROUP BY p.puuid, p.riot_id
        HAVING COUNT(ps.match_id) >= 5
        ORDER BY games_played DESC
    """)

    rows = db.execute(sql).mappings().all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Median imputation only over the 14 clustering feature columns
    for col in CLUSTERING_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    return df


def get_rolling_features(
    db: Session,
    puuid: str,
    before_ts: int,
    window: int = 20,
) -> dict:
    """Return rolling window stats for one player strictly before ``before_ts``.

    Leakage guard: ``m.game_creation < :before_ts`` (strict less-than).
    The target match is never part of the window.

    Returns:
        Dict with keys defined in ``ROLLING_FEATURES`` plus
        ``games_in_window`` and ``has_full_window``.
        Empty dict if the player has fewer than 5 prior ranked games.
    """
    # ------------------------------------------------------------------
    # Step 1 — Rolling aggregates using ROW_NUMBER window to cap at `window`
    # ------------------------------------------------------------------
    agg_sql = text("""
        WITH ranked AS (
            SELECT
                p.puuid,
                ps.match_id,
                ps.win,
                ps.champion_id,
                ps.deaths,
                dm.kda,
                dm.cs_per_min,
                dm.gold_per_min,
                dm.kill_participation,
                dm.vision_per_min,
                m.game_creation,
                ROW_NUMBER() OVER (
                    PARTITION BY p.puuid
                    ORDER BY m.game_creation DESC
                ) AS rn
            FROM participant_stats ps
            JOIN players p          ON p.id = ps.player_id
            JOIN matches m          ON m.match_id = ps.match_id
            JOIN derived_metrics dm ON dm.match_id = ps.match_id
                                   AND dm.puuid = p.puuid
            WHERE p.puuid     = :puuid
              AND m.game_creation < :before_ts
              AND m.queue_id  = 420
        )
        SELECT
            AVG((win)::int)         AS win_rate_20,
            AVG(kda)                AS avg_kda_20,
            AVG(cs_per_min)         AS avg_cs_per_min_20,
            AVG(gold_per_min)       AS avg_gold_per_min_20,
            AVG(kill_participation) AS avg_kill_part_20,
            AVG(deaths)             AS death_rate_20,
            AVG(vision_per_min)     AS vision_per_min_20,
            COUNT(*)                AS games_in_window
        FROM ranked
        WHERE rn <= :window
    """)

    agg_row = db.execute(
        agg_sql, {"puuid": puuid, "before_ts": before_ts, "window": window}
    ).mappings().first()

    games_count = int(agg_row["games_in_window"]) if agg_row and agg_row["games_in_window"] else 0

    if games_count < 5:
        return {}

    # ------------------------------------------------------------------
    # Step 2 — Streak: fetch last `window` results ordered most-recent-first
    # ------------------------------------------------------------------
    streak_sql = text("""
        SELECT ps.win, m.game_creation
        FROM participant_stats ps
        JOIN players p ON p.id = ps.player_id
        JOIN matches m ON m.match_id = ps.match_id
        WHERE p.puuid         = :puuid
          AND m.game_creation < :before_ts
          AND m.queue_id      = 420
        ORDER BY m.game_creation DESC
        LIMIT :window
    """)

    # ------------------------------------------------------------------
    # Step 2 — Streak + KDA std + CS trend (last 10, oldest-first for slope)
    # Fetch kda and cs_per_min alongside win so we can compute volatility/
    # trend in one pass without an extra query.
    # ------------------------------------------------------------------
    streak_sql = text("""
        SELECT ps.win, dm.kda, dm.cs_per_min, m.game_creation
        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN matches m          ON m.match_id = ps.match_id
        JOIN derived_metrics dm ON dm.match_id = ps.match_id
                               AND dm.puuid = p.puuid
        WHERE p.puuid         = :puuid
          AND m.game_creation < :before_ts
          AND m.queue_id      = 420
        ORDER BY m.game_creation DESC
        LIMIT :window
    """)

    streak_rows = db.execute(
        streak_sql, {"puuid": puuid, "before_ts": before_ts, "window": window}
    ).fetchall()

    win_results = [bool(r[0]) for r in streak_rows]
    streak = _compute_streak(win_results)

    # KDA std and CS trend over last 10 games (or fewer if < 10 available)
    # streak_rows is most-recent-first; reverse to oldest-first for trend
    recent_10 = streak_rows[:10]
    kda_vals  = [float(r[1]) for r in recent_10 if r[1] is not None]
    cs_vals   = [float(r[2]) for r in recent_10 if r[2] is not None]
    # Reverse so index 0 = oldest (correct direction for slope)
    kda_vals_asc = list(reversed(kda_vals))
    cs_vals_asc  = list(reversed(cs_vals))

    kda_std_10 = float(np.std(kda_vals)) if len(kda_vals) >= 2 else 0.0
    cs_trend_10 = _linear_trend(cs_vals_asc)

    return {
        "puuid": puuid,
        "win_rate_20":       float(agg_row["win_rate_20"] or 0.0),
        "avg_kda_20":        float(agg_row["avg_kda_20"] or 0.0),
        "avg_cs_per_min_20": float(agg_row["avg_cs_per_min_20"] or 0.0),
        "avg_gold_per_min_20": float(agg_row["avg_gold_per_min_20"] or 0.0),
        "avg_kill_part_20":  float(agg_row["avg_kill_part_20"] or 0.0),
        "death_rate_20":     float(agg_row["death_rate_20"] or 0.0),
        "vision_per_min_20": float(agg_row["vision_per_min_20"] or 0.0),
        "kda_std_10":        round(kda_std_10, 4),
        "cs_trend_10":       round(cs_trend_10, 6),
        "win_streak":        streak,
        "games_in_window":   games_count,
        "has_full_window":   games_count >= window,
    }


def get_champion_stats(db: Session, puuid: str) -> pd.DataFrame:
    """Return per-champion aggregates for one player (champion recommendation).

    Only champions with ≥ 3 ranked games are included.

    Returns:
        DataFrame with one row per (champion, role) pair.
        Empty DataFrame (not None) if no data found.
    """
    sql = text("""
        SELECT
            p.puuid,
            ps.champion,
            ps.champion_id,
            ps.role,
            COUNT(*)                        AS games_played,
            AVG((ps.win)::int)              AS win_rate,
            SUM((ps.win)::int)              AS total_wins,
            AVG(dm.kda)                     AS avg_kda,
            AVG(dm.cs_per_min)              AS avg_cs_per_min,
            AVG(dm.gold_per_min)            AS avg_gold_per_min,
            AVG(dm.kill_participation)      AS avg_kill_participation,
            AVG(dm.damage_share)            AS avg_damage_share,
            MAX(m.game_creation)            AS last_played_ts
        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN matches m          ON m.match_id = ps.match_id
        JOIN derived_metrics dm ON dm.match_id = ps.match_id
                               AND dm.puuid = p.puuid
        WHERE p.puuid    = :puuid
          AND m.queue_id = 420
          AND EXISTS (
              SELECT 1 FROM derived_metrics dm2
              WHERE dm2.puuid = p.puuid
          )
        GROUP BY p.puuid, ps.champion, ps.champion_id, ps.role
        HAVING COUNT(*) >= 3
        ORDER BY games_played DESC
    """)

    rows = db.execute(sql, {"puuid": puuid}).mappings().all()
    if not rows:
        return pd.DataFrame()

    return _impute_medians(pd.DataFrame(rows))


def get_win_prediction_features(db: Session, match_id: str) -> pd.DataFrame:
    """Return one feature row per participant in a match for win-prediction training.

    Assembles per-player rolling window stats and team-level aggregate
    features.  Label column is ``win`` (bool from ``participant_stats``).

    Steps:
      1. Fetch match metadata (game_creation, queue_id, patch_version).
      2. Fetch all 10 participants (puuid, team_id, champion_id, role, win).
      3. Call ``get_rolling_features()`` for each participant using
         ``game_creation`` as the ``before_ts`` leakage guard.
      4. Compute team-level aggregate columns (100 vs 200).
      5. Encode patch_version and role as numeric features.

    Returns:
        DataFrame with one row per participant (≤ 10 rows).
        Empty DataFrame if the match is not found or has no participants.
    """
    # ------------------------------------------------------------------
    # Step 1 — Match metadata
    # ------------------------------------------------------------------
    meta_sql = text("""
        SELECT game_creation, queue_id, patch_version
        FROM matches
        WHERE match_id = :match_id
    """)
    meta = db.execute(meta_sql, {"match_id": match_id}).mappings().first()
    if not meta:
        return pd.DataFrame()

    game_creation: int = meta["game_creation"]
    patch_float: float = _encode_patch(meta["patch_version"])

    # ------------------------------------------------------------------
    # Step 2 — Participants
    # ------------------------------------------------------------------
    parts_sql = text("""
        SELECT p.puuid, ps.team_id, ps.champion_id, ps.role, ps.win
        FROM participant_stats ps
        JOIN players p ON p.id = ps.player_id
        WHERE ps.match_id = :match_id
    """)
    participants = db.execute(parts_sql, {"match_id": match_id}).mappings().all()
    if not participants:
        return pd.DataFrame()

    # Filter to ingested players only (those who have derived_metrics rows)
    participants = [
        p for p in participants
        if _has_derived_metrics(db, p["puuid"])
    ]
    if not participants:
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Step 3 — Per-participant rolling features
    # ------------------------------------------------------------------
    rows: list[dict] = []
    for part in participants:
        rolling = get_rolling_features(db, part["puuid"], game_creation)
        row: dict = {
            "match_id": match_id,
            "puuid": part["puuid"],
            "team_id": part["team_id"],
            "champion_id": part["champion_id"],
            "role": part["role"],
            "role_encoded": ROLE_ENCODING.get(
                str(part["role"]).upper() if part["role"] else "NONE", -1
            ),
            "win": int(part["win"]) if part["win"] is not None else None,
            "patch_version_float": patch_float,
            "queue_id": meta["queue_id"],
            # Rolling features — NaN when player has insufficient history
            "win_rate_20":        rolling.get("win_rate_20", np.nan),
            "avg_kda_20":         rolling.get("avg_kda_20", np.nan),
            "avg_cs_per_min_20":  rolling.get("avg_cs_per_min_20", np.nan),
            "avg_gold_per_min_20": rolling.get("avg_gold_per_min_20", np.nan),
            "avg_kill_part_20":   rolling.get("avg_kill_part_20", np.nan),
            "death_rate_20":      rolling.get("death_rate_20", np.nan),
            "vision_per_min_20":  rolling.get("vision_per_min_20", np.nan),
            "kda_std_10":         rolling.get("kda_std_10", np.nan),
            "cs_trend_10":        rolling.get("cs_trend_10", np.nan),
            "win_streak":         rolling.get("win_streak", 0),
            "games_in_window":    rolling.get("games_in_window", 0),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # ------------------------------------------------------------------
    # Step 4 — Team-level aggregate columns
    # ------------------------------------------------------------------
    team_avgs: dict[int, dict] = {}
    for team_id in (100, 200):
        mask = df["team_id"] == team_id
        team_avgs[team_id] = {
            "avg_win_rate": df.loc[mask, "win_rate_20"].mean(),
            "avg_kda": df.loc[mask, "avg_kda_20"].mean(),
            "avg_cs_min": df.loc[mask, "avg_cs_per_min_20"].mean(),
            "avg_gold_per_min": df.loc[mask, "avg_gold_per_min_20"].mean(),
        }

    for team_id in (100, 200):
        mask = df["team_id"] == team_id
        avgs = team_avgs[team_id]
        df.loc[mask, "team_avg_win_rate_20"] = avgs["avg_win_rate"]
        df.loc[mask, "team_avg_kda_20"] = avgs["avg_kda"]
        df.loc[mask, "team_avg_cs_min_20"] = avgs["avg_cs_min"]
        df.loc[mask, "team_avg_gold_per_min_20"] = avgs["avg_gold_per_min"]

    # Per-row gold diff prior (team100 perspective — same value on all rows)
    t100_gold = team_avgs[100]["avg_gold_per_min"]
    t200_gold = team_avgs[200]["avg_gold_per_min"]
    df["team_gold_diff_prior"] = (
        (t100_gold if pd.notna(t100_gold) else 0.0)
        - (t200_gold if pd.notna(t200_gold) else 0.0)
    )

    return _impute_medians(df)


def get_timeline_features(
    db: Session,
    match_ids: list[str],
) -> pd.DataFrame:
    """Return team differential features at T=10 min and T=15 min per match.

    Columns: all ``TIMELINE_FEATURES`` + ``team100_won`` (label from
    ``team_objectives``).

    Frame windows:
        T=10 min: frame_timestamp BETWEEN 590_000 AND 610_000 (ms)
        T=15 min: frame_timestamp BETWEEN 890_000 AND 910_000 (ms)

    Event encoding (first-objective columns):
        ``1`` = team 100 achieved the objective first
        ``-1`` = team 200 achieved the objective first
        ``0`` = not observed before 15-min mark

    Building-kill note: in the Riot API timeline, a BUILDING_KILL event's
    ``teamId`` identifies the team that *owned* the destroyed structure.
    The team that *scored* the first tower is therefore the opponent.

    Args:
        match_ids: List of match_id strings to process in bulk.

    Returns:
        One row per match.  Empty DataFrame if no frame data is found.
    """
    if not match_ids:
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Frame differentials (team 100 minus team 200)
    # ------------------------------------------------------------------
    frames_sql = text("""
        WITH frames_10 AS (
            SELECT
                match_id,
                participant_id,
                total_gold,
                xp,
                level,
                COALESCE(minions_killed, 0) + COALESCE(jungle_minions_killed, 0) AS cs,
                CASE WHEN participant_id <= 5 THEN 100 ELSE 200 END              AS team_id
            FROM timeline_participant_frames
            WHERE match_id = ANY(:match_ids)
              AND frame_timestamp BETWEEN 590000 AND 610000
        ),
        frames_15 AS (
            SELECT
                match_id,
                participant_id,
                total_gold,
                xp,
                COALESCE(minions_killed, 0) + COALESCE(jungle_minions_killed, 0) AS cs,
                CASE WHEN participant_id <= 5 THEN 100 ELSE 200 END              AS team_id
            FROM timeline_participant_frames
            WHERE match_id = ANY(:match_ids)
              AND frame_timestamp BETWEEN 890000 AND 910000
        ),
        team_10 AS (
            SELECT
                match_id,
                team_id,
                SUM(total_gold) AS gold,
                SUM(xp)         AS xp,
                AVG(level)      AS avg_level,
                SUM(cs)         AS cs
            FROM frames_10
            GROUP BY match_id, team_id
        ),
        team_15 AS (
            SELECT
                match_id,
                team_id,
                SUM(total_gold) AS gold,
                SUM(xp)         AS xp
            FROM frames_15
            GROUP BY match_id, team_id
        ),
        diffs AS (
            SELECT
                t1.match_id,
                t1.gold      - t2.gold      AS gold_diff_10,
                t1.xp        - t2.xp        AS xp_diff_10,
                t1.avg_level - t2.avg_level  AS level_diff_10,
                t1.cs        - t2.cs        AS cs_diff_10,
                f15a.gold    - f15b.gold    AS gold_diff_15,
                f15a.xp      - f15b.xp      AS xp_diff_15
            FROM team_10 t1
            JOIN  team_10 t2   ON t1.match_id = t2.match_id
                              AND t1.team_id = 100 AND t2.team_id = 200
            LEFT JOIN team_15 f15a ON t1.match_id = f15a.match_id AND f15a.team_id = 100
            LEFT JOIN team_15 f15b ON t1.match_id = f15b.match_id AND f15b.team_id = 200
        )
        SELECT * FROM diffs
    """)

    diff_rows = db.execute(frames_sql, {"match_ids": match_ids}).mappings().all()

    # ------------------------------------------------------------------
    # First-objective events (kills / buildings / monsters before 15 min)
    # DB column name is "type" (Python attribute on model is "event_type")
    # ------------------------------------------------------------------
    events_sql = text("""
        SELECT
            match_id,
            type,
            timestamp,
            raw_event_json
        FROM timeline_events
        WHERE match_id = ANY(:match_ids)
          AND type IN ('CHAMPION_KILL', 'BUILDING_KILL', 'ELITE_MONSTER_KILL')
          AND timestamp < 900000
        ORDER BY match_id, timestamp ASC
    """)

    event_rows = db.execute(events_sql, {"match_ids": match_ids}).mappings().all()

    # Determine first-objective team per match
    first_obj: dict[str, dict] = {}
    for row in event_rows:
        mid = row["match_id"]
        if mid not in first_obj:
            first_obj[mid] = {
                "first_blood_team": 0,
                "first_tower_team": 0,
                "first_dragon_team": 0,
            }
        obj = first_obj[mid]
        evt_type: str = row["type"] or ""
        raw: dict = row["raw_event_json"] if isinstance(row["raw_event_json"], dict) else {}

        if evt_type == "CHAMPION_KILL" and obj["first_blood_team"] == 0:
            obj["first_blood_team"] = _killer_team_from_event(raw)

        elif evt_type == "BUILDING_KILL" and obj["first_tower_team"] == 0:
            # teamId on BUILDING_KILL = owning team (the one that LOST the tower)
            # → destroying team is the opponent
            building_owner = raw.get("teamId")
            if building_owner == 100:
                obj["first_tower_team"] = -1    # team 200 destroyed team 100's tower
            elif building_owner == 200:
                obj["first_tower_team"] = 1     # team 100 destroyed team 200's tower

        elif evt_type == "ELITE_MONSTER_KILL" and obj["first_dragon_team"] == 0:
            if raw.get("monsterType") == "DRAGON":
                obj["first_dragon_team"] = _killer_team_from_event(raw)

    # ------------------------------------------------------------------
    # Win labels (team_objectives.win_flag for team 100)
    # ------------------------------------------------------------------
    labels_sql = text("""
        SELECT match_id, win_flag
        FROM team_objectives
        WHERE match_id = ANY(:match_ids)
          AND team_id = 100
    """)
    label_rows = db.execute(labels_sql, {"match_ids": match_ids}).mappings().all()
    labels: dict[str, int] = {r["match_id"]: int(r["win_flag"]) for r in label_rows}

    # ------------------------------------------------------------------
    # Assemble final DataFrame
    # ------------------------------------------------------------------
    if not diff_rows:
        return pd.DataFrame()

    records: list[dict] = []
    _empty_obj = {"first_blood_team": 0, "first_tower_team": 0, "first_dragon_team": 0}
    for dr in diff_rows:
        mid = dr["match_id"]
        record = dict(dr)
        record.update(first_obj.get(mid, _empty_obj))
        record["team100_won"] = labels.get(mid, np.nan)
        records.append(record)

    return _impute_medians(pd.DataFrame(records))


def get_all_rolling_features_bulk(db: Session) -> pd.DataFrame:
    """Return rolling window features for every (puuid, match_id) pair in bulk.

    This is the fast training-time equivalent of calling
    ``get_rolling_features()`` individually for every participant in every
    match.  A single SQL round-trip fetches raw per-game rows; all rolling
    computations are done in pandas using groupby + shift so that no game
    ever sees its own data as a feature (leakage guard).

    Leakage guard:
        ``shift(1)`` inside every ``transform`` ensures that the feature for
        row i is computed from rows 0 … i-1 only — identical semantics to
        the ``game_creation < :before_ts`` filter in ``get_rolling_features()``.

    Team-level features:
        After per-player rolling windows are computed, team aggregates
        (``team_avg_*`` and ``team_gold_diff_prior``) are computed by grouping
        on ``(match_id, team_id)`` — matching the logic in
        ``get_win_prediction_features()``.

    Returns:
        DataFrame with one row per (puuid, match_id) that has ≥ 5 prior
        ranked games.  Columns:

        From SQL:   puuid, match_id, win, role, champion_id, team_id,
                    game_creation, patch_version, kda, cs_per_min,
                    gold_per_min, kill_participation, deaths, vision_per_min

        Rolling:    win_rate_20, avg_kda_20, avg_cs_per_min_20,
                    avg_gold_per_min_20, avg_kill_part_20, death_rate_20,
                    vision_per_min_20, kda_std_10, cs_trend_10,
                    games_in_window, win_streak

        Encoded:    patch_version_float, role_encoded

        Team:       team_avg_win_rate_20, team_avg_kda_20,
                    team_avg_cs_min_20, team_gold_diff_prior

        Imputation is NOT applied here — callers are responsible.

    Raises nothing on empty results — returns an empty DataFrame.
    """
    # ------------------------------------------------------------------
    # Step 1 — Single bulk SQL fetch (no self-join)
    # ------------------------------------------------------------------
    sql = text("""
        SELECT
            p.puuid,
            ps.match_id,
            ps.win,
            ps.role,
            ps.champion_id,
            ps.team_id,
            ps.deaths,
            m.game_creation,
            m.patch_version,
            dm.kda,
            dm.cs_per_min,
            dm.gold_per_min,
            dm.kill_participation,
            dm.vision_per_min
        FROM participant_stats ps
        JOIN players p          ON p.id = ps.player_id
        JOIN matches m          ON m.match_id = ps.match_id
        JOIN derived_metrics dm ON dm.match_id = ps.match_id
                               AND dm.puuid = p.puuid
        WHERE m.queue_id = 420
        ORDER BY p.puuid, m.game_creation ASC
    """)

    rows = db.execute(sql).mappings().all()
    if not rows:
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Step 2 — Load into DataFrame, sort by (puuid, game_creation)
    # ------------------------------------------------------------------
    df = pd.DataFrame(rows)
    df["win"] = df["win"].astype(float)
    df = df.sort_values(["puuid", "game_creation"]).reset_index(drop=True)

    grouped = df.groupby("puuid")

    # ------------------------------------------------------------------
    # Step 3 — Per-player rolling features via groupby + shift(1)
    #          shift(1) is the leakage guard — same as before_ts filter.
    # ------------------------------------------------------------------
    df["win_rate_20"] = grouped["win"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    df["avg_kda_20"] = grouped["kda"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    df["avg_cs_per_min_20"] = grouped["cs_per_min"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    df["avg_gold_per_min_20"] = grouped["gold_per_min"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    df["avg_kill_part_20"] = grouped["kill_participation"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    df["death_rate_20"] = grouped["deaths"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    df["vision_per_min_20"] = grouped["vision_per_min"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).mean()
    )
    # Rolling std over last 10 — pandas handles NaN from shift internally
    df["kda_std_10"] = grouped["kda"].transform(
        lambda x: x.shift(1).rolling(10, min_periods=2).std()
    ).fillna(0.0)
    # Linear CS trend over last 10 — filter NaN edge (from shift) before passing
    df["cs_trend_10"] = grouped["cs_per_min"].transform(
        lambda x: x.shift(1).rolling(10, min_periods=2).apply(
            lambda w: _linear_trend([float(v) for v in w if not np.isnan(v)]),
            raw=True,
        )
    ).fillna(0.0)
    df["games_in_window"] = grouped["win"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=1).count()
    )

    # ------------------------------------------------------------------
    # Step 4 — Win streak (strictly prior games, most-recent-first)
    # ------------------------------------------------------------------
    df = _add_win_streak_column(df)

    # ------------------------------------------------------------------
    # Step 5 — Drop rows with insufficient prior history
    # ------------------------------------------------------------------
    df = df[df["games_in_window"] >= 5].reset_index(drop=True)

    # ------------------------------------------------------------------
    # Step 6 — Encode patch_version and role
    # ------------------------------------------------------------------
    df["patch_version_float"] = df["patch_version"].apply(_encode_patch)
    df["role_encoded"] = (
        df["role"].map(ROLE_ENCODING).fillna(-1).astype(int)
    )

    # ------------------------------------------------------------------
    # Step 6b — Team-level aggregate features (mirrors get_win_prediction_features)
    # ------------------------------------------------------------------
    if "team_id" in df.columns and not df.empty:
        team_aggs = (
            df.groupby(["match_id", "team_id"])
            .agg(
                team_avg_win_rate_20=("win_rate_20", "mean"),
                team_avg_kda_20=("avg_kda_20", "mean"),
                team_avg_cs_min_20=("avg_cs_per_min_20", "mean"),
                _team_avg_gold=("avg_gold_per_min_20", "mean"),
            )
            .reset_index()
        )
        df = df.merge(
            team_aggs[["match_id", "team_id",
                       "team_avg_win_rate_20", "team_avg_kda_20", "team_avg_cs_min_20",
                       "_team_avg_gold"]],
            on=["match_id", "team_id"],
            how="left",
        )

        # Gold diff: team 100 avg_gold_per_min − team 200 avg_gold_per_min
        t100 = (
            team_aggs[team_aggs["team_id"] == 100][["match_id", "_team_avg_gold"]]
            .rename(columns={"_team_avg_gold": "_gold_100"})
        )
        t200 = (
            team_aggs[team_aggs["team_id"] == 200][["match_id", "_team_avg_gold"]]
            .rename(columns={"_team_avg_gold": "_gold_200"})
        )
        gold_diff = t100.merge(t200, on="match_id", how="outer")
        gold_diff["team_gold_diff_prior"] = (
            gold_diff["_gold_100"].fillna(0.0) - gold_diff["_gold_200"].fillna(0.0)
        )
        df = df.merge(
            gold_diff[["match_id", "team_gold_diff_prior"]],
            on="match_id",
            how="left",
        )
        # Drop internal helper column
        df = df.drop(columns=["_team_avg_gold"], errors="ignore")

    return df

