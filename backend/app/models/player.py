from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, func

from app.db.session import Base


class Player(Base):
    """
    Player model representing a League of Legends player.
    
    Attributes:
        id: Primary key
        riot_id: Riot ID game name (e.g., "Doublelift")
        tag_line: Riot ID tag line (e.g., "NA1")
        puuid: Riot's universal unique player identifier
        region: Regional routing value (americas, europe, asia, sea)
        created_at: Timestamp of first ingestion
    """
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    riot_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="Riot ID game name")
    tag_line: Mapped[str] = mapped_column(String(16), nullable=False, comment="Riot ID tag line")
    puuid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False, comment="Universal player ID")
    region: Mapped[str] = mapped_column(String(16), nullable=False, comment="Regional routing: americas, europe, asia, sea")

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participant_stats = relationship("ParticipantStats", back_populates="player")
    derived_metrics = relationship("DerivedMetrics", back_populates="player", cascade="all, delete-orphan")