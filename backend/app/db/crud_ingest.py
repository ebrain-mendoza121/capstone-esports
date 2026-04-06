from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import exists
import logging

from app.models.player import Player
from app.models.match import Match
from app.models.participant_stats import ParticipantStats
from app.models.team_objectives import TeamObjectives
from app.models.team_bans import TeamBans
from app.models.derived_metrics import DerivedMetrics
from app.models.match_timeline import MatchTimeline, TimelineParticipantFrame, TimelineEvent
from app.models.draft_actions import DraftActions, ActionType, DraftPhase
from app.models.participant_perks import ParticipantPerks
from app.services.derived_metrics_calculator import (
    compute_derived_metrics,
    extract_team_participants,
    normalize_game_duration,
)

logger = logging.getLogger(__name__)

# Maps Riot API teamPosition values to a deterministic per-team turn number.
# Used to populate draft_actions.turn for the PICK phase.
ROLE_TO_TURN: dict = {
    "TOP": 1,
    "JUNGLE": 2,
    "MIDDLE": 3,
    "BOTTOM": 4,
    "UTILITY": 5,
}


def insert_draft_actions(session: Session, match_id: str, info: dict) -> None:
    """Insert draft actions (bans and picks) for a match.

    Bans: sourced from teams[].bans[], turn = pickTurn (1-5 per team).
    Picks: sourced from participants[], turn = ROLE_TO_TURN mapping.
    If full role data is unavailable (e.g. ARAM), falls back to participantId ordering.
    Called from insert_match_bundle_for_player and the backfill endpoint.
    """
    all_participants = info.get("participants", [])

    # Group participants by team for the pick phase
    by_team: dict = {100: [], 200: []}
    for p in all_participants:
        tid = p.get("teamId")
        if tid in by_team:
            by_team[tid].append(p)

    # BAN phase — one row per non-empty ban slot per team
    for team in info.get("teams", []):
        team_id = team.get("teamId", 0)
        for ban in team.get("bans", []):
            champion_id = ban.get("championId")
            pick_turn = ban.get("pickTurn")
            if champion_id is None or champion_id == -1 or pick_turn is None:
                continue
            session.add(DraftActions(
                match_id=match_id,
                team_id=team_id,
                action_type=ActionType.BAN,
                phase=DraftPhase.BAN,
                champion_id=champion_id,
                role=None,
                turn=pick_turn,
                action_order=None,
            ))

    # PICK phase — one row per participant
    for team_id, players in by_team.items():
        if not players:
            continue

        # Use role-based turns only if all 5 canonical positions are filled
        positions = {(p.get("teamPosition") or "").upper().strip() for p in players}
        use_role_turns = positions == {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}

        if use_role_turns:
            for p in players:
                pos = p.get("teamPosition", "").upper().strip()
                session.add(DraftActions(
                    match_id=match_id,
                    team_id=team_id,
                    action_type=ActionType.PICK,
                    phase=DraftPhase.PICK,
                    champion_id=p.get("championId", 0),
                    role=pos,
                    turn=ROLE_TO_TURN[pos],
                    action_order=None,
                ))
        else:
            # Fallback: sort by participantId, assign sequential turns 1-5
            for idx, p in enumerate(
                sorted(players, key=lambda x: x.get("participantId", 0)),
                start=1,
            ):
                pos = (p.get("teamPosition") or "").upper().strip()
                session.add(DraftActions(
                    match_id=match_id,
                    team_id=team_id,
                    action_type=ActionType.PICK,
                    phase=DraftPhase.PICK,
                    champion_id=p.get("championId", 0),
                    role=pos if pos in ROLE_TO_TURN else None,
                    turn=idx,
                    action_order=None,
                ))
def insert_participant_perks(session: Session, match_id: str, player_id: int, participant: dict) -> None:
    """Insert rune/perk data for the tracked participant.

    Extracts primary style + 4 selections (keystone + 3 slot runes),
    secondary style + 2 selections, and all 3 stat shards from the
    participant.perks object in the Riot Match-V5 response.
    """
    perks_raw = participant.get("perks") or {}
    stat_perks = perks_raw.get("statPerks") or {}
    styles = perks_raw.get("styles") or []

    primary_style: int | None = None
    keystone: int | None = None
    primary_slot1: int | None = None
    primary_slot2: int | None = None
    primary_slot3: int | None = None
    sub_style: int | None = None
    sub_slot1: int | None = None
    sub_slot2: int | None = None

    for style in styles:
        description = (style.get("description") or "").lower()
        style_id = style.get("style")
        selections = style.get("selections") or []
        if description == "primarystyle":
            primary_style = style_id
            if len(selections) > 0:
                keystone = selections[0].get("perk")
            if len(selections) > 1:
                primary_slot1 = selections[1].get("perk")
            if len(selections) > 2:
                primary_slot2 = selections[2].get("perk")
            if len(selections) > 3:
                primary_slot3 = selections[3].get("perk")
        elif description == "substyle":
            sub_style = style_id
            if len(selections) > 0:
                sub_slot1 = selections[0].get("perk")
            if len(selections) > 1:
                sub_slot2 = selections[1].get("perk")

    stmt = (
        insert(ParticipantPerks)
        .values(
            match_id=match_id,
            player_id=player_id,
            primary_style=primary_style,
            keystone=keystone,
            primary_slot1=primary_slot1,
            primary_slot2=primary_slot2,
            primary_slot3=primary_slot3,
            sub_style=sub_style,
            sub_slot1=sub_slot1,
            sub_slot2=sub_slot2,
            stat_offense=stat_perks.get("offense"),
            stat_flex=stat_perks.get("flex"),
            stat_defense=stat_perks.get("defense"),
        )
        .on_conflict_do_nothing(index_elements=["match_id", "player_id"])
    )
    session.execute(stmt)


def upsert_player(session: Session, puuid: str, riot_id: str, tag_line: str, routing: str) -> Player:
    """Insert or update a player record. Returns the Player ORM object."""
    player = session.query(Player).filter(Player.puuid == puuid).one_or_none()
    if player:
        player.riot_id = riot_id
        player.tag_line = tag_line
        player.region = routing
        session.flush()
        return player

    player = Player(puuid=puuid, riot_id=riot_id, tag_line=tag_line, region=routing)
    session.add(player)
    session.flush()
    return player


def match_exists(session: Session, match_id: str) -> bool:
    return session.query(
        exists().where(Match.match_id == match_id)
    ).scalar()


def _upsert_player_stub(
    session: Session, puuid: str, game_name: str, tag_line: str, routing: str
) -> Player:
    """Get or create a Player row identified by PUUID.
    Does NOT overwrite an existing player's riot_id / tag_line / region —
    so a previously-tracked player's canonical data is always preserved.
    """
    player = session.query(Player).filter(Player.puuid == puuid).one_or_none()
    if player:
        return player
    player = Player(
        puuid=puuid,
        riot_id=game_name or puuid[:16],
        tag_line=tag_line or "",
        region=routing,
    )
    session.add(player)
    session.flush()
    return player


def insert_match_bundle_for_player(
    session: Session,
    match_json: dict,
    tracked_puuid: str,
    player_id: int,
    routing: str = "",
) -> None:
    """
    Insert a full match bundle:
    matches, participant_stats (all 10 participants), team_objectives,
    team_bans, derived_metrics.

    Populates all extended fields from the YAML schema including items,
    damage type breakdown, multi-kills, first objectives, etc.
    Non-tracked participants are automatically upserted as stub Player rows
    using the riotIdGameName / riotIdTagline values from the match JSON.
    """
    info = match_json["info"]
    metadata = match_json["metadata"]
    match_id = metadata["matchId"]

    game_duration_seconds = normalize_game_duration(info)

    m = Match(
        match_id=match_id,
        game_creation=info.get("gameCreation", 0),
        game_duration=game_duration_seconds,
        queue_id=info.get("queueId", 0),
        patch_version=info.get("gameVersion"),
        game_mode=info.get("gameMode"),
        game_type=info.get("gameType"),
        platform_id=info.get("platformId"),
        game_start_timestamp=info.get("gameStartTimestamp"),
        game_end_timestamp=info.get("gameEndTimestamp"),
        end_of_game_result=info.get("endOfGameResult"),
    )
    session.add(m)
    session.flush()

    # Find the tracked participant — used later for derived metrics and perks.
    all_participants = info.get("participants", [])
    participant = next(
        (p for p in all_participants if p.get("puuid") == tracked_puuid), None
    )
    if participant is None:
        raise RuntimeError(f"Tracked participant not found in match {match_id}")

    team_id = participant.get("teamId", 0)

    # Insert participant_stats for ALL 10 participants.
    # Non-tracked players are auto-created as stub Player rows so that
    # match detail endpoints can return a complete scoreboard.
    for p in all_participants:
        p_puuid = p.get("puuid") or ""
        if p_puuid == tracked_puuid:
            p_player_id = player_id
        else:
            stub = _upsert_player_stub(
                session,
                puuid=p_puuid,
                game_name=p.get("riotIdGameName") or "",
                tag_line=p.get("riotIdTagline") or "",
                routing=routing,
            )
            p_player_id = stub.id

        p_total_minions = p.get("totalMinionsKilled") or 0
        p_neutral_minions = p.get("neutralMinionsKilled") or 0
        p_cs = int(p_total_minions + p_neutral_minions)

        session.add(ParticipantStats(
            match_id=match_id,
            player_id=p_player_id,
            team_id=p.get("teamId", 0),
            # Champion identity
            champion=p.get("championName"),
            champion_id=p.get("championId"),
            champ_level=p.get("champLevel"),
            role=(
                p.get("teamPosition")
                or p.get("individualPosition")
                or p.get("role")
            ),
            # Core KDA
            kills=p.get("kills", 0),
            deaths=p.get("deaths", 0),
            assists=p.get("assists", 0),
            double_kills=p.get("doubleKills"),
            triple_kills=p.get("tripleKills"),
            quadra_kills=p.get("quadraKills"),
            penta_kills=p.get("pentaKills"),
            # Economy
            gold_earned=p.get("goldEarned", 0),
            gold_spent=p.get("goldSpent"),
            # CS
            cs=p_cs,
            total_minions_killed=p_total_minions,
            neutral_minions_killed=p_neutral_minions,
            # Damage
            total_damage=p.get("totalDamageDealtToChampions", 0),
            physical_damage_to_champions=p.get("physicalDamageDealtToChampions"),
            magic_damage_to_champions=p.get("magicDamageDealtToChampions"),
            true_damage_to_champions=p.get("trueDamageDealtToChampions"),
            total_damage_taken=p.get("totalDamageTaken"),
            # Vision
            vision_score=p.get("visionScore", 0),
            wards_placed=p.get("wardsPlaced"),
            wards_killed=p.get("wardsKilled"),
            detector_wards_placed=p.get("detectorWardsPlaced"),
            # CC
            time_ccing_others=p.get("timeCCingOthers"),
            # First objectives
            first_blood_kill=p.get("firstBloodKill"),
            first_blood_assist=p.get("firstBloodAssist"),
            first_tower_kill=p.get("firstTowerKill"),
            first_tower_assist=p.get("firstTowerAssist"),
            # Items
            item0=p.get("item0"),
            item1=p.get("item1"),
            item2=p.get("item2"),
            item3=p.get("item3"),
            item4=p.get("item4"),
            item5=p.get("item5"),
            item6=p.get("item6"),
            # Summoner spells
            summoner1_id=p.get("summoner1Id"),
            summoner2_id=p.get("summoner2Id"),
            win=p.get("win"),
        ))
        insert_participant_perks(session, match_id, p_player_id, p)

    # Team objectives + team bans (2 teams)
    for t in info.get("teams", []):
        t_id = t.get("teamId", 0)
        obj = t.get("objectives", {})

        def _obj(key: str) -> dict:
            return obj.get(key) or {}

        to = TeamObjectives(
            match_id=match_id,
            team_id=t_id,
            win_flag=bool(t.get("win", False)),
            towers=_obj("tower").get("kills", 0),
            tower_first=_obj("tower").get("first"),
            dragons=_obj("dragon").get("kills", 0),
            dragon_first=_obj("dragon").get("first"),
            barons=_obj("baron").get("kills", 0),
            baron_first=_obj("baron").get("first"),
            rift_herald_kills=_obj("riftHerald").get("kills"),
            rift_herald_first=_obj("riftHerald").get("first"),
            inhibitor_kills=_obj("inhibitor").get("kills"),
            inhibitor_first=_obj("inhibitor").get("first"),
            champion_kills=_obj("champion").get("kills"),
            champion_first=_obj("champion").get("first"),
        )
        session.add(to)

        for ban in t.get("bans", []):
            champion_id = ban.get("championId")
            pick_turn = ban.get("pickTurn")
            if champion_id and champion_id != -1:
                session.add(TeamBans(
                    match_id=match_id,
                    team_id=t_id,
                    champion_id=champion_id,
                    pick_turn=pick_turn,
                ))

    # Derived metrics (upsert to handle re-ingestion)
    team_participants = extract_team_participants(all_participants, team_id)
    metrics = compute_derived_metrics(participant, team_participants, game_duration_seconds)

    stmt = insert(DerivedMetrics).values(
        match_id=match_id,
        puuid=tracked_puuid,
        **metrics,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_derived_metrics_match_puuid",
        set_=metrics,
    )
    session.execute(stmt)

    # Flush participant_stats, team_objectives, team_bans, and derived_metrics first.
    # Then attempt draft_actions inside a savepoint: if it fails, only the draft rows
    # are rolled back and the rest of the bundle remains intact.
    session.flush()
    try:
        with session.begin_nested():
            insert_draft_actions(session, match_id, info)
    except Exception as draft_err:
        # Log at ERROR so failures surface clearly in server output.
        # The savepoint ensures the rest of the match bundle is already committed.
        logger.error(
            "insert_draft_actions FAILED for %s — draft rows NOT saved. "
            "Cause: %s. "
            "Verify the draft_actions table exists (run `alembic upgrade head` or "
            "`npx prisma db push`) and that the DraftActions model uses "
            "native_enum=False on both SQLEnum columns.",
            match_id,
            draft_err,
            exc_info=True,
        )






def insert_timeline(session: Session, match_id: str, timeline_json: dict) -> None:
    """
    Store timeline data: raw JSON + parsed participant frames.
    Called optionally after insert_match_bundle_for_player.
    Idempotent: silently returns if a MatchTimeline row already exists for match_id.
    """
    if session.query(MatchTimeline.match_id).filter_by(match_id=match_id).first():
        logger.debug("insert_timeline: skipping %s — already stored", match_id)
        return

    info = timeline_json.get("info", {})

    tl = MatchTimeline(
        match_id=match_id,
        frame_interval=info.get("frameInterval"),
        end_of_game_result=info.get("endOfGameResult"),
    )
    session.add(tl)
    session.flush()

    for frame in info.get("frames", []):
        frame_ts = frame.get("timestamp", 0)
        participant_frames = frame.get("participantFrames", {})

        for pid_str, pf in participant_frames.items():
            pos = pf.get("position") or {}
            session.add(TimelineParticipantFrame(
                match_id=match_id,
                frame_timestamp=frame_ts,
                participant_id=int(pid_str),
                position_x=pos.get("x"),
                position_y=pos.get("y"),
                current_gold=pf.get("currentGold"),
                total_gold=pf.get("totalGold"),
                gold_per_second=pf.get("goldPerSecond"),
                xp=pf.get("xp"),
                level=pf.get("level"),
                minions_killed=pf.get("minionsKilled"),
                jungle_minions_killed=pf.get("jungleMinionsKilled"),
            ))

        # Only store the 3 event types used by the early-game model,
        # and only before 15 minutes. All other events are discarded
        # to keep storage usage manageable.
        _USEFUL_EVENTS = {"CHAMPION_KILL", "BUILDING_KILL", "ELITE_MONSTER_KILL"}
        for event in frame.get("events", []):
            evt_type = event.get("type")
            evt_ts = event.get("timestamp", 0)
            if evt_type not in _USEFUL_EVENTS or evt_ts >= 900000:
                continue
            session.add(TimelineEvent(
                match_id=match_id,
                timestamp=evt_ts,
                real_timestamp=event.get("realTimestamp"),
                event_type=evt_type,
                raw_event_json=event,
            ))

    session.flush()

