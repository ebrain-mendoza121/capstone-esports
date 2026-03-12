from sqlalchemy import String, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TeamBans(Base):
    """
    Team bans model representing champion bans in draft phase.
    
    Attributes:
        id: Primary key
        match_id: Foreign key to matches table
        team_id: Team identifier (100 or 200)
        champion_id: Banned champion ID
        pick_turn: Order in which ban occurred (1-5 per team)
    """
    __tablename__ = "team_bans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(64), 
        ForeignKey("matches.match_id", ondelete="CASCADE"), 
        nullable=False,
        comment="Match identifier"
    )
    team_id: Mapped[int] = mapped_column(
        Integer, 
        nullable=False,
        comment="Team ID (100 or 200)"
    )
    champion_id: Mapped[int] = mapped_column(
        Integer, 
        nullable=False,
        comment="Banned champion ID"
    )
    pick_turn: Mapped[int] = mapped_column(
        Integer, 
        nullable=False,
        comment="Ban order (1-5 per team)"
    )

    # Relationship
    match = relationship("Match", back_populates="team_bans")

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_team_bans_match_id", "match_id"),
        Index("ix_team_bans_champion_id", "champion_id"),
        Index("ix_team_bans_match_team", "match_id", "team_id"),
    )
