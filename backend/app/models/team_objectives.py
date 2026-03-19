from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, ForeignKey

from app.db.session import Base


class TeamObjectives(Base):
    __tablename__ = "team_objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    match_id: Mapped[str] = mapped_column(String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    win_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Towers
    towers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tower_first: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Dragons
    dragons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dragon_first: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Barons
    barons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baron_first: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Rift Heralds
    rift_herald_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rift_herald_first: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Inhibitors
    inhibitor_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inhibitor_first: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Champion (first blood team level)
    champion_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    champion_first: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    match = relationship("Match", back_populates="team_objectives")
