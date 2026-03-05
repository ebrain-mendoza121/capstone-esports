from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, BigInteger, DateTime, func

from app.db.session import Base


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    game_creation: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)  # epoch ms
    game_duration: Mapped[int] = mapped_column(Integer, nullable=False)  # seconds
    queue_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    patch_version: Mapped[str] = mapped_column(String(32), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participant_stats = relationship("ParticipantStats", back_populates="match")
    team_objectives = relationship("TeamObjectives", back_populates="match")
    team_bans = relationship("TeamBans", back_populates="match", cascade="all, delete-orphan")
    derived_metrics = relationship("DerivedMetrics", back_populates="match", cascade="all, delete-orphan")