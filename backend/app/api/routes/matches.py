from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.team_objectives import TeamObjectives
from app.models.team_bans import TeamBans
from app.models.derived_metrics import DerivedMetrics
from app.models.player import Player
from app.models.draft_actions import DraftActions, ActionType

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/player/{puuid}")
def get_player_matches(puuid: str, limit: int = 20, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Match history for a player, ordered by most recent. Includes per-match stats."""
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    rows = (
        db.query(Match, ParticipantStats, DerivedMetrics)
        .join(ParticipantStats, ParticipantStats.match_id == Match.match_id)
        .outerjoin(
            DerivedMetrics,
            (DerivedMetrics.match_id == Match.match_id) & (DerivedMetrics.puuid == puuid),
        )
        .filter(ParticipantStats.player_id == player.id)
        .order_by(Match.game_creation.desc())
        .limit(limit)
        .all()
    )

    result = []
    for match, ps, dm in rows:
        result.append({
            "match_id": match.match_id,
            "game_creation": match.game_creation,
            "game_duration": match.game_duration,
            "queue_id": match.queue_id,
            "game_mode": match.game_mode,
            "patch_version": match.patch_version,
            "platform_id": match.platform_id,
            # Participant stats
            "champion": ps.champion,
            "champion_id": ps.champion_id,
            "champ_level": ps.champ_level,
            "role": ps.role,
            "kills": ps.kills,
            "deaths": ps.deaths,
            "assists": ps.assists,
            "cs": ps.cs,
            "gold_earned": ps.gold_earned,
            "gold_spent": ps.gold_spent,
            "total_damage": ps.total_damage,
            "vision_score": ps.vision_score,
            "wards_placed": ps.wards_placed,
            "penta_kills": ps.penta_kills,
            "first_blood_kill": ps.first_blood_kill,
            "items": [ps.item0, ps.item1, ps.item2, ps.item3, ps.item4, ps.item5, ps.item6],
            "win": ps.win,
            # Derived metrics
            "kda": dm.kda if dm else None,
            "cs_per_min": dm.cs_per_min if dm else None,
            "gold_per_min": dm.gold_per_min if dm else None,
            "kill_participation": dm.kill_participation if dm else None,
            "damage_share": dm.damage_share if dm else None,
            "vision_per_min": dm.vision_per_min if dm else None,
        })
    return result


@router.get("/{match_id}")
def get_match_detail(match_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Full match detail: metadata, both teams' objectives + bans,
    and all participant stats stored in the database.
    """
    match = db.query(Match).filter(Match.match_id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    objectives = (
        db.query(TeamObjectives)
        .filter(TeamObjectives.match_id == match_id)
        .all()
    )
    bans = db.query(TeamBans).filter(TeamBans.match_id == match_id).all()
    participants = (
        db.query(ParticipantStats, Player)
        .join(Player, Player.id == ParticipantStats.player_id)
        .filter(ParticipantStats.match_id == match_id)
        .all()
    )

    def _team_obj(t: TeamObjectives) -> dict:
        return {
            "team_id": t.team_id,
            "win": t.win_flag,
            "towers": t.towers, "tower_first": t.tower_first,
            "dragons": t.dragons, "dragon_first": t.dragon_first,
            "barons": t.barons, "baron_first": t.baron_first,
            "rift_herald_kills": t.rift_herald_kills, "rift_herald_first": t.rift_herald_first,
            "inhibitor_kills": t.inhibitor_kills, "inhibitor_first": t.inhibitor_first,
            "champion_kills": t.champion_kills, "champion_first": t.champion_first,
        }

    return {
        "match_id": match.match_id,
        "game_creation": match.game_creation,
        "game_duration": match.game_duration,
        "queue_id": match.queue_id,
        "game_mode": match.game_mode,
        "game_type": match.game_type,
        "patch_version": match.patch_version,
        "platform_id": match.platform_id,
        "end_of_game_result": match.end_of_game_result,
        "teams": [_team_obj(t) for t in objectives],
        "bans": [
            {"team_id": b.team_id, "champion_id": b.champion_id, "pick_turn": b.pick_turn}
            for b in sorted(bans, key=lambda x: (x.team_id, x.pick_turn))
        ],
        "participants": [
            {
                "puuid": player.puuid,
                "riot_id": player.riot_id,
                "tag_line": player.tag_line,
                "team_id": ps.team_id,
                "champion": ps.champion,
                "champion_id": ps.champion_id,
                "champ_level": ps.champ_level,
                "role": ps.role,
                "kills": ps.kills, "deaths": ps.deaths, "assists": ps.assists,
                "double_kills": ps.double_kills,
                "triple_kills": ps.triple_kills,
                "quadra_kills": ps.quadra_kills,
                "penta_kills": ps.penta_kills,
                "gold_earned": ps.gold_earned,
                "gold_spent": ps.gold_spent,
                "cs": ps.cs,
                "total_damage": ps.total_damage,
                "physical_damage_to_champions": ps.physical_damage_to_champions,
                "magic_damage_to_champions": ps.magic_damage_to_champions,
                "true_damage_to_champions": ps.true_damage_to_champions,
                "total_damage_taken": ps.total_damage_taken,
                "vision_score": ps.vision_score,
                "wards_placed": ps.wards_placed,
                "wards_killed": ps.wards_killed,
                "detector_wards_placed": ps.detector_wards_placed,
                "time_ccing_others": ps.time_ccing_others,
                "first_blood_kill": ps.first_blood_kill,
                "first_tower_kill": ps.first_tower_kill,
                "items": [ps.item0, ps.item1, ps.item2, ps.item3, ps.item4, ps.item5, ps.item6],
                "summoner1_id": ps.summoner1_id,
                "summoner2_id": ps.summoner2_id,
                "win": ps.win,
            }
            for ps, player in participants
        ],
    }


@router.get("/{match_id}/draft")
def get_match_draft(match_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Return the full draft (picks and bans for both teams) for a match.

    Bans are ordered by turn (1-5 per team, matching Riot pickTurn).
    Picks are ordered by turn (role-based: TOP=1, JUNGLE=2, MID=3, BOT=4, SUP=5).
    Returns 404 if this match has no draft data — re-ingest the match or run
    POST /backfill/draft-actions to populate existing matches.
    """
    if not db.query(Match).filter(Match.match_id == match_id).first():
        raise HTTPException(status_code=404, detail="Match not found")

    actions = (
        db.query(DraftActions)
        .filter(DraftActions.match_id == match_id)
        .order_by(DraftActions.team_id, DraftActions.phase, DraftActions.turn)
        .all()
    )

    if not actions:
        raise HTTPException(
            status_code=404,
            detail="No draft actions found for this match. Re-ingest or run POST /backfill/draft-actions.",
        )

    result: Dict[int, Dict] = {
        100: {"bans": [], "picks": []},
        200: {"bans": [], "picks": []},
    }

    for a in actions:
        team_bucket = result.get(a.team_id)
        if team_bucket is None:
            continue
        if a.action_type == ActionType.PICK:
            team_bucket["picks"].append({
                "champion_id": a.champion_id,
                "role": a.role,
                "turn": a.turn,
            })
        else:
            team_bucket["bans"].append({
                "champion_id": a.champion_id,
                "turn": a.turn,
            })

    return {
        "match_id": match_id,
        "draft": {str(team_id): data for team_id, data in result.items()},
    }

