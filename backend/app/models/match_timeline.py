from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base


class MatchTimeline(Base):
    """
    Stores Match-V5 timeline header metadata.
    One row per match. Frame and event data stored in child tables.
    """
    __tablename__ = "match_timelines"

    match_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    frame_interval: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # ms between frames
    end_of_game_result: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    match = relationship("Match", back_populates="timeline")
    participant_frames = relationship(
        "TimelineParticipantFrame",
        back_populates="timeline",
        cascade="all, delete-orphan",
    )
    events = relationship(
        "TimelineEvent",
        back_populates="timeline",
        cascade="all, delete-orphan",
    )


class TimelineParticipantFrame(Base):
    """
    Per-frame positional and resource snapshot for each participant.
    Enables heatmaps, gold-diff charts, and early-game features for AI.
    One row per (match, frame_timestamp, participant_id).
    """
    __tablename__ = "timeline_participant_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("match_timelines.match_id", ondelete="CASCADE"), nullable=False
    )
    frame_timestamp: Mapped[int] = mapped_column(Integer, nullable=False)  # ms since game start
    participant_id: Mapped[int] = mapped_column(Integer, nullable=False)   # 1–10

    # Map position
    position_x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Economy snapshot
    current_gold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_gold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gold_per_second: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Progression
    xp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # CS
    minions_killed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jungle_minions_killed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    timeline = relationship("MatchTimeline", back_populates="participant_frames")

    __table_args__ = (
        Index("ix_tpf_match_ts", "match_id", "frame_timestamp"),
        Index("ix_tpf_match_participant", "match_id", "participant_id"),
    )


class TimelineEvent(Base):
    """
    One row per event emitted in a timeline frame (kills, objectives, items, etc.).
    Stores minimal structured fields for querying plus the full raw event JSON
    for forward compatibility and AI feature extraction.
    """
    __tablename__ = "timeline_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("match_timelines.match_id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)       # ms since game start
    real_timestamp: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # epoch ms
    event_type: Mapped[Optional[str]] = mapped_column(
        "type", String(64), nullable=True
    )
    raw_event_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    timeline = relationship("MatchTimeline", back_populates="events")

    __table_args__ = (
        Index("ix_timeline_events_match_ts", "match_id", "timestamp"),
        Index("ix_timeline_events_match_type", "match_id", "type"),
    )
