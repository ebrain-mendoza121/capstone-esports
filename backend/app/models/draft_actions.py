from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    Index,
    Enum as SQLEnum,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ActionType(str, enum.Enum):
    PICK = "PICK"
    BAN = "BAN"


class DraftPhase(str, enum.Enum):
    PICK = "PICK"
    BAN = "BAN"


class DraftActions(Base):
    __tablename__ = "draft_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    match_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("matches.match_id", ondelete="CASCADE"),
        nullable=False,
        comment="Match identifier",
    )

    team_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Team ID (100 or 200)",
    )

    action_type: Mapped[ActionType] = mapped_column(
        SQLEnum(ActionType, name="action_type_enum", create_type=False, native_enum=False),
        nullable=False,
        comment="Action type (PICK or BAN)",
    )

    phase: Mapped[DraftPhase] = mapped_column(
        SQLEnum(DraftPhase, name="draft_phase_enum", create_type=False, native_enum=False),
        nullable=False,
        comment="Draft phase (PICK or BAN). Typically mirrors action_type.",
    )

    champion_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Champion ID involved in the action",
    )

    role: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="Role/position for picks (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY); NULL for bans",
    )

    turn: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Order inside the phase per team. BAN: 1-5 per team. PICK: deterministic 1-5 per team (MVP).",
    )

    action_order: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Optional global draft order if available; otherwise NULL",
    )

    match = relationship("Match", back_populates="draft_actions")

    __table_args__ = (
        CheckConstraint("team_id IN (100, 200)", name="ck_draft_actions_team_id"),
        UniqueConstraint("match_id", "phase", "team_id", "turn", name="uq_draft_actions_match_phase_team_turn"),
        Index("ix_draft_actions_match_id", "match_id"),
        Index("ix_draft_actions_champion_id", "champion_id"),
        Index("ix_draft_actions_match_team", "match_id", "team_id"),
        Index("ix_draft_actions_action_type", "action_type"),
        Index("ix_draft_actions_role", "role"),
        Index("ix_draft_actions_match_phase", "match_id", "phase"),
        Index("ix_draft_actions_match_team_phase", "match_id", "team_id", "phase"),
        Index("ix_draft_actions_match_phase_turn", "match_id", "phase", "turn"),
        Index("ix_draft_actions_match_order", "match_id", "action_order"),
    )
