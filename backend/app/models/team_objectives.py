from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey

from app.db.session import Base


class TeamObjectives(Base):
    __tablename__ = "team_objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    match_id: Mapped[str] = mapped_column(String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    towers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dragons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    barons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    win_flag: Mapped[bool] = mapped_column(nullable=False, default=False)

    match = relationship("Match", back_populates="team_objectives")