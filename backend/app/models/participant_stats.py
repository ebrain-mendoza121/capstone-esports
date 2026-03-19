from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey, Boolean

from app.db.session import Base


class ParticipantStats(Base):
    __tablename__ = "participant_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    match_id: Mapped[str] = mapped_column(String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id", ondelete="CASCADE"), index=True)

    team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Champion identity
    champion: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    champion_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    champ_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Core KDA
    kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    double_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    triple_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quadra_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    penta_kills: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Economy
    gold_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # CS (computed sum stored for backwards compat)
    cs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_minions_killed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    neutral_minions_killed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Damage
    total_damage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # to champions
    physical_damage_to_champions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    magic_damage_to_champions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    true_damage_to_champions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_damage_taken: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Vision
    vision_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wards_placed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wards_killed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detector_wards_placed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # CC
    time_ccing_others: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # First blood / first tower
    first_blood_kill: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    first_blood_assist: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    first_tower_kill: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    first_tower_assist: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Items (build path)
    item0: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item3: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item4: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item5: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item6: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # trinket

    # Summoner spells
    summoner1_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summoner2_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    win: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    match = relationship("Match", back_populates="participant_stats")
    player = relationship("Player", back_populates="participant_stats")
