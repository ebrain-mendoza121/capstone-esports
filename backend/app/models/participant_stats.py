from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, BigInteger, ForeignKey, Float

from app.db.session import Base


class ParticipantStats(Base):
    __tablename__ = "participant_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    match_id: Mapped[str] = mapped_column(String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id", ondelete="CASCADE"), index=True)

    team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    champion: Mapped[str] = mapped_column(String(64), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=True)

    kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    gold_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_damage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vision_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # optional raw field if you want it later
    win: Mapped[bool] = mapped_column(nullable=True)

    match = relationship("Match", back_populates="participant_stats")
    player = relationship("Player", back_populates="participant_stats")
