from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint, Index

from app.db.session import Base


class ParticipantPerks(Base):
    __tablename__ = "participant_perks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )

    # Primary rune path
    primary_style: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    keystone: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    primary_slot1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    primary_slot2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    primary_slot3: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Secondary rune path
    sub_style: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sub_slot1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sub_slot2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Stat shards
    stat_offense: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stat_flex: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stat_defense: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    match = relationship("Match", back_populates="participant_perks")
    player = relationship("Player", back_populates="participant_perks")

    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_participant_perks_match_player"),
        Index("ix_participant_perks_match_id", "match_id"),
        Index("ix_participant_perks_player_id", "player_id"),
        Index("ix_participant_perks_keystone", "keystone"),
        Index("ix_participant_perks_primary_style", "primary_style"),
    )
