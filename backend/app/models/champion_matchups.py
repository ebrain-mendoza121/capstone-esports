"""
champion_matchups.py — Manually-researched champion vs. champion win-rate data.

Rows are sourced from external sites (Lolalytics, op.gg, u.gg) and imported
via POST /matchups/import/csv.  The endpoint GET /champions/matchup/{a}/{b}
checks this table first (higher sample sizes) before falling back to the
participant_stats self-join derived from ingested matches.

Uniqueness constraint: (champion_a_id, champion_b_id, role) — one row per
directed pair per role.  The reverse direction is NOT stored; callers that
need champ_b vs champ_a must invert (1 - win_rate_a_vs_b).
"""

from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChampionMatchup(Base):
    """
    One directed champion-vs-champion matchup stat row.

    win_rate_a_vs_b is Champion A's win rate when facing Champion B in the
    specified role, as a fraction (0.0 – 1.0).  A value of 0.53 means
    Champion A wins 53 % of those games.

    confidence is computed at insert time from games_played:
        high   → games_played >= 30
        medium → games_played >= 10
        low    → games_played <  10
    Bayesian smoothing is applied to low/medium rows at query time.
    """

    __tablename__ = "champion_matchups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Riot numeric champion keys (from DDragon)
    champion_a_id: Mapped[int] = mapped_column(Integer, nullable=False)
    champion_b_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Human-readable names stored for fast display (denormalised on purpose)
    champion_a_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    champion_b_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Lane / role where the matchup was measured
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    # Core stat — fraction, not percent
    win_rate_a_vs_b: Mapped[float] = mapped_column(Float, nullable=False)

    # Research metadata
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patch: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # lolalytics | opgg | ugg
    notes: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Computed confidence tier, set on write
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="low")

    __table_args__ = (
        # One directed row per champion pair × role
        UniqueConstraint(
            "champion_a_id", "champion_b_id", "role",
            name="uq_champion_matchup_pair_role",
        ),
        # win_rate must be a valid fraction
        CheckConstraint(
            "win_rate_a_vs_b >= 0.0 AND win_rate_a_vs_b <= 1.0",
            name="ck_champion_matchup_win_rate_range",
        ),
        # Lookup by champion A (most common query pattern)
        Index("ix_champion_matchups_a_role", "champion_a_id", "role"),
        # Lookup by champion B (counter-to queries)
        Index("ix_champion_matchups_b_role", "champion_b_id", "role"),
    )
