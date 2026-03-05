from sqlalchemy import String, Float, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
class DerivedMetrics(Base):
    __tablename__ = "derived_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    match_id: Mapped[str] = mapped_column(
        String, ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    puuid: Mapped[str] = mapped_column(
        String, ForeignKey("players.puuid", ondelete="CASCADE"), nullable=False
    )

    # Examples (align to what you compute)
    kda: Mapped[float | None] = mapped_column(Float, nullable=True)
    cs_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    gold_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    kill_participation: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1 or 0-100, choose one
    damage_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    vision_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Optional relationships (recommended)
    match = relationship("Match", back_populates="derived_metrics")
    player = relationship("Player", back_populates="derived_metrics")

    __table_args__ = (
        UniqueConstraint("match_id", "puuid", name="uq_derived_metrics_match_puuid"),
        Index("ix_derived_metrics_puuid", "puuid"),
        Index("ix_derived_metrics_match_id", "match_id"),
    )