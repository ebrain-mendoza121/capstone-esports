from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Dict, Any

from app.db.session import get_db
from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.team_bans import TeamBans

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/player/{puuid}/bans")
def get_player_bans(
    puuid: str,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ban analytics for a player's recent matches.
    Returns bans by the player's team and bans against it (enemy team),
    plus top-10 most banned champions in each category.
    """
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    player_matches = (
        db.query(ParticipantStats.match_id, ParticipantStats.team_id)
        .filter(ParticipantStats.player_id == player.id)
        .join(Match, Match.match_id == ParticipantStats.match_id)
        .order_by(Match.game_creation.desc())
        .limit(limit)
        .all()
    )

    if not player_matches:
        return {
            "puuid": puuid,
            "matches_analyzed": 0,
            "bans_against": [],
            "bans_by_team": [],
            "most_banned_against": [],
            "most_banned_by_team": [],
            "total_bans_against": 0,
            "total_bans_by_team": 0,
        }

    match_ids = [m.match_id for m in player_matches]
    match_teams = {m.match_id: m.team_id for m in player_matches}

    all_bans = (
        db.query(TeamBans).filter(TeamBans.match_id.in_(match_ids)).all()
    )

    bans_against = []
    bans_by_team = []

    for ban in all_bans:
        player_team = match_teams.get(ban.match_id)
        entry = {
            "match_id": ban.match_id,
            "champion_id": ban.champion_id,
            "pick_turn": ban.pick_turn,
        }
        if ban.team_id == player_team:
            bans_by_team.append(entry)
        else:
            bans_against.append(entry)

    def top_champs(ban_list: list, n: int = 10) -> list:
        counts: Dict[int, int] = {}
        for b in ban_list:
            counts[b["champion_id"]] = counts.get(b["champion_id"], 0) + 1
        return [
            {"champion_id": cid, "ban_count": cnt}
            for cid, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ][:n]

    return {
        "puuid": puuid,
        "matches_analyzed": len(player_matches),
        "bans_against": bans_against,
        "bans_by_team": bans_by_team,
        "most_banned_against": top_champs(bans_against),
        "most_banned_by_team": top_champs(bans_by_team),
        "total_bans_against": len(bans_against),
        "total_bans_by_team": len(bans_by_team),
    }


@router.get("/champion/{champion_id}/ban-rate")
def get_champion_ban_rate(
    champion_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Ban rate for a specific champion across all stored matches."""
    total_matches = db.query(func.count(Match.match_id)).scalar()

    if total_matches == 0:
        return {
            "champion_id": champion_id,
            "total_matches": 0,
            "times_banned": 0,
            "ban_rate": 0.0,
        }

    times_banned = (
        db.query(func.count(TeamBans.id))
        .filter(TeamBans.champion_id == champion_id)
        .scalar()
    )

    ban_rate = (times_banned / total_matches) * 100 if total_matches > 0 else 0.0

    return {
        "champion_id": champion_id,
        "total_matches": total_matches,
        "times_banned": times_banned,
        "ban_rate": round(ban_rate, 2),
    }


@router.get("/bans/most-banned")
def get_most_banned_champions(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Most banned champions across all stored matches."""
    most_banned = (
        db.query(TeamBans.champion_id, func.count(TeamBans.id).label("ban_count"))
        .group_by(TeamBans.champion_id)
        .order_by(desc("ban_count"))
        .limit(limit)
        .all()
    )

    return [
        {"champion_id": champ_id, "ban_count": count}
        for champ_id, count in most_banned
    ]
