export type QueueCode = 420 | 440;
export type RoleCode = "TOP" | "JUNGLE" | "MID" | "BOT" | "SUPPORT";

export interface PlayerSummary {
  puuid: string;
  riot_id: string;
  tag_line: string;
  region: string;
}

export interface IngestPlayerInput {
  gameName: string;
  tagLine: string;
  platform: string;
  matchCount: number;
  queue: QueueCode;
}

export interface PlayerDetail extends PlayerSummary {
  created_at: string;
}

export interface PlayerMetrics {
  matches_played: number;
  win_rate: number;
  avg_kda: number;
  avg_cs_per_min: number;
  avg_gold_per_min: number;
  avg_vision_per_min: number;
}

export interface RuneEntry {
  match_id: string;
  champion: string;
  keystone_name: string;
  primary_style_name: string;
  primary_slot1_name: string;
  primary_slot2_name: string;
  primary_slot3_name: string;
  sub_style_name: string;
  sub_slot1_name: string;
  sub_slot2_name: string;
}

export interface MatchHistoryEntry {
  match_id: string;
  champion: string;
  champion_id: number;
  role: RoleCode;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  gold_earned: number;
  vision_score: number;
  items: number[];
  win: boolean;
  game_duration: number;
  patch_version: string;
  kda: number;
  cs_per_min: number;
  queue_id: QueueCode;
}

export interface TeamStats {
  team_id: 100 | 200;
  towers: number;
  dragons: number;
  barons: number;
  inhibitor_kills: number;
  rift_herald_kills: number;
  win: boolean;
}

export interface MatchParticipant {
  puuid: string;
  riot_id: string;
  champion: string;
  role: RoleCode;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  gold_earned: number;
  total_damage: number;
  vision_score: number;
  items: number[];
  perks: {
    keystone: string;
  };
  team_id: 100 | 200;
  win: boolean;
}

export interface MatchDetail {
  match_id: string;
  queue_id: QueueCode;
  patch_version: string;
  game_duration: number;
  date: string;
  teams: TeamStats[];
  participants: MatchParticipant[];
  has_timeline: boolean;
}

export interface DraftData {
  team100_bans: string[];
  team200_bans: string[];
  team100_picks: string[];
  team200_picks: string[];
}

export interface BanEntry {
  champion_id: number;
  champion_name: string;
  count: number;
}

export interface PlayerBanAnalytics {
  matches_analyzed: number;
  banned_against: BanEntry[];
  banned_by_team: BanEntry[];
}

export interface GlobalBanEntry {
  champion_id: number;
  champion_name: string;
  ban_count: number;
}

export interface ChampionBanRate {
  champion_name: string;
  ban_rate: number;
  times_banned: number;
  total_matches: number;
}

export interface RuneMapEntry {
  rune_id: number;
  rune_name: string;
}

export interface TimelineAvailability {
  match_id: string;
  frame_rows: number;
  event_rows: number;
  frame_interval_ms: number;
  participant_puuids: string[];
}

export interface TimelineFrame {
  frame_timestamp: number;
  current_gold: number;
  total_gold: number;
  xp: number;
  level: number;
  minions_killed: number;
  jungle_minions_killed: number;
  position_x: number;
  position_y: number;
}

export type TimelineEventType =
  | "CHAMPION_KILL"
  | "BUILDING_KILL"
  | "ELITE_MONSTER_KILL"
  | "ITEM_PURCHASED";

export interface TimelineEvent {
  id: string;
  timestamp: number;
  type: TimelineEventType;
  detail: string;
}

export interface TimelineEventsResponse {
  events: TimelineEvent[];
  next_cursor: string | null;
}

export class MockApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface FrontendMvpClient {
  // Page 1
  listPlayers(): Promise<PlayerSummary[]>;
  ingestPlayer(payload: IngestPlayerInput): Promise<PlayerSummary>;

  // Page 2
  getPlayer(puuid: string): Promise<PlayerDetail>;
  getPlayerMetrics(puuid: string): Promise<PlayerMetrics>;
  getPlayerRunes(puuid: string, limit: number): Promise<RuneEntry[]>;

  // Page 3
  getMatchesByPlayer(puuid: string, limit: number): Promise<MatchHistoryEntry[]>;

  // Page 4
  getMatch(matchId: string): Promise<MatchDetail>;
  getMatchDraft(matchId: string): Promise<DraftData>;

  // Page 5
  getPlayerBanAnalytics(puuid: string, limit: number): Promise<PlayerBanAnalytics>;//TODO
  getGlobalMostBanned(limit: number): Promise<GlobalBanEntry[]>;//TODO
  getChampionBanRate(championId: number): Promise<ChampionBanRate>;//TODO

  // Page 6
  getRunesMap(): Promise<RuneMapEntry[]>;//TODO
  getPlayerRuneHistory(puuid: string, limit: number): Promise<RuneEntry[]>;//TODO

  // Page 7
  getTimelineAvailability(matchId: string): Promise<TimelineAvailability>;//TODO
  getTimelineFramesByPuuid(matchId: string, puuid: string): Promise<TimelineFrame[]>;//TODO
  getTimelineEvents(matchId: string, limit: number, cursor?: string): Promise<TimelineEventsResponse>;//TODO
}

const CHAMPIONS = [
  "Aatrox",
  "Ahri",
  "Azir",
  "Jinx",
  "Kai'Sa",
  "Lee Sin",
  "Lulu",
  "Nautilus",
  "Orianna",
  "Ornn",
  "Rakan",
  "Sejuani",
  "Thresh",
  "Vi",
  "Yone",
  "Zeri",
];

const REGIONS = ["NA1", "EUW1", "KR", "LA1"];
const ROLES: RoleCode[] = ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"];
const QUEUES: QueueCode[] = [420, 440];
const PATCHES = ["14.6", "14.7", "14.8", "14.9", "14.10"];

const KEYSTONES = ["Conqueror", "First Strike", "Fleet Footwork", "Summon Aery", "Aftershock"];
const PRIMARY_STYLES = ["Precision", "Domination", "Sorcery", "Resolve", "Inspiration"];
const SUB_STYLES = ["Inspiration", "Precision", "Sorcery", "Resolve", "Domination"];

const SLOT_NAMES = {
  primary: ["Triumph", "Legend: Alacrity", "Coup de Grace", "Manaflow Band", "Transcendence", "Scorch"],
  sub: ["Biscuit Delivery", "Cosmic Insight", "Bone Plating", "Second Wind", "Sudden Impact", "Ultimate Hunter"],
};

const TIMELINE_EVENT_TYPES: TimelineEventType[] = [
  "CHAMPION_KILL",
  "BUILDING_KILL",
  "ELITE_MONSTER_KILL",
  "ITEM_PURCHASED",
];

function hash(input: string): number {
  let result = 0;
  for (let index = 0; index < input.length; index += 1) {
    result = (result << 5) - result + input.charCodeAt(index);
    result |= 0;
  }
  return Math.abs(result) + 1;
}

function createRng(seedKey: string): () => number {
  let seed = hash(seedKey) % 2147483647;
  if (seed <= 0) {
    seed += 2147483646;
  }

  return () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

function randomInt(rng: () => number, min: number, max: number): number {
  return Math.floor(rng() * (max - min + 1)) + min;
}

function randomFloat(rng: () => number, min: number, max: number, decimals = 2): number {
  const value = min + rng() * (max - min);
  return Number(value.toFixed(decimals));
}

function pick<T>(rng: () => number, list: T[]): T {
  return list[randomInt(rng, 0, list.length - 1)];
}

function formatDateFromOffset(daysBack: number): string {
  const now = new Date();
  now.setDate(now.getDate() - daysBack);
  return now.toISOString();
}

function makePuuid(seedText: string): string {
  return `puuid_${hash(seedText).toString(36).slice(0, 10)}`;
}

async function getPuuidFromRiotId(riotId: string, tagLine: string){
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/players/`);
  if (!res.ok) {
    throw new Error("Failed to fetch player list from Riot API");
  }

  const players = await res.json();
  let puuid = null;
  players.forEach((player: PlayerSummary) => {
    if (player.riot_id === riotId && player.tag_line === tagLine) {
      puuid = player.puuid;
    }
  });
  
  return puuid;
}

function makeRiotId(seed: string): string {
  return `player${hash(seed).toString().slice(0, 4)}`;
}

function makeRuneEntry(seed: string, index: number): RuneEntry {
  const rng = createRng(`${seed}:rune:${index}`);

  return {
    match_id: `EUW1_${hash(`${seed}:${index}`)}`,
    champion: pick(rng, CHAMPIONS),
    keystone_name: pick(rng, KEYSTONES),
    primary_style_name: pick(rng, PRIMARY_STYLES),
    primary_slot1_name: pick(rng, SLOT_NAMES.primary),
    primary_slot2_name: pick(rng, SLOT_NAMES.primary),
    primary_slot3_name: pick(rng, SLOT_NAMES.primary),
    sub_style_name: pick(rng, SUB_STYLES),
    sub_slot1_name: pick(rng, SLOT_NAMES.sub),
    sub_slot2_name: pick(rng, SLOT_NAMES.sub),
  };
}

async function resolvePlayer(puuid: string){
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/players/${puuid}/`);
    if (!res.ok) {
      if (res.status === 404) {
        throw new MockApiError(
          404,
          "Player not found on Riot servers"
        );
      }
      if (res.status === 503) {
        throw new MockApiError(
          503,
          "Riot API rate limit hit — try again in 30 seconds"
        );
      }
      if (res.status === 502) {
        throw new MockApiError(
          502,
          "Riot API error — check API key"
        );
      }
      throw new Error("Unexpected API error");
    }
  const player = await res.json();
  return {
    puuid,
    riot_id: player.riot_id,
    tag_line: player.tag_line,
    region: player.region,
    created_at: player.created_at
  };
}

function makeMatchParticipants(matchId: string): MatchParticipant[] {
  const rng = createRng(`${matchId}:participants`);

  return Array.from({ length: 10 }, (_, index) => {
    const teamId: 100 | 200 = index < 5 ? 100 : 200;
    const role = ROLES[index % ROLES.length];
    const participantPuuid = makePuuid(`${matchId}:${index}`);

    return {
      puuid: participantPuuid,
      riot_id: makeRiotId(participantPuuid),
      champion: pick(rng, CHAMPIONS),
      role,
      kills: randomInt(rng, 0, 16),
      deaths: randomInt(rng, 0, 12),
      assists: randomInt(rng, 1, 24),
      cs: randomInt(rng, 90, 360),
      gold_earned: randomInt(rng, 7000, 20000),
      total_damage: randomInt(rng, 8000, 58000),
      vision_score: randomInt(rng, 8, 88),
      items: Array.from({ length: 7 }, () => randomInt(rng, 1001, 7000)),
      perks:{keystone: pick(rng, KEYSTONES)},
      team_id: teamId,
      win: teamId === 100,
    };
  });
}

const runesMapStatic: RuneMapEntry[] = [
  { rune_id: 8005, rune_name: "Press the Attack" },
  { rune_id: 8010, rune_name: "Conqueror" },
  { rune_id: 8229, rune_name: "Arcane Comet" },
  { rune_id: 8128, rune_name: "Dark Harvest" },
  { rune_id: 8465, rune_name: "Guardian" },
  { rune_id: 8369, rune_name: "First Strike" },
];

const frontendMvpClient: FrontendMvpClient = {
  async listPlayers() {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/players/`);
    if (!res.ok) {
      throw new Error("Failed to fetch player list from Riot API");
    }
    const players = await res.json();
    return players.slice(0, 20); // Return only the first 20 for listing
  },

  async ingestPlayer(payload) {
    if (payload.gameName.toLowerCase() === "404") {
      throw new MockApiError(404, "Player not found on Riot servers");
    }

    if (payload.gameName.toLowerCase() === "503") {
      throw new MockApiError(503, "Riot API rate limit hit — try again in 30 seconds");
    }

    if (payload.gameName.toLowerCase() === "502") {
      throw new MockApiError(502, "Riot API error — check API key");
    }

    const puuid = await getPuuidFromRiotId(payload.gameName, payload.tagLine) || "";

    const player: PlayerSummary = {
      puuid,
      riot_id: payload.gameName,
      tag_line: payload.tagLine,
      region: payload.platform,
    };

    return player;
  },

  async getPlayer(puuid) {
    const player = await resolvePlayer(puuid);
    return {
      ...player
    };
  },

  async getPlayerMetrics(puuid) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/metrics/player/${puuid}/`);
    if (!res.ok) {
      throw new Error("Failed to fetch player metrics from Riot API");
    }
    const metrics = await res.json();

    return {
      matches_played: metrics.matches,
      win_rate: metrics.win_rate,
      avg_kda: metrics.kda,
      avg_cs_per_min: metrics.cs_per_min,
      avg_gold_per_min: metrics.gold_per_min,
      avg_vision_per_min: metrics.vision_per_min,
    };
  },

  async getPlayerRunes(puuid, limit) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/analytics/player/${puuid}/runes/?limit=${limit}`);
    if (!res.ok) {      throw new Error("Failed to fetch player rune history from Riot API");
    }
    const runes = await res.json();

    return [...runes.runes];
  },

  async getMatchesByPlayer(puuid, limit) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/matches/player/${puuid}/?limit=${limit}`);
    if (!res.ok) {
      throw new Error("Failed to fetch player match history from Riot API");
    }
    const matches = await res.json();

    return [...matches];
  },

  async getMatch(matchId) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/matches/${matchId}/`);
    if (!res.ok) {
      throw new Error("Failed to fetch match details from Riot API");
    }
    const match = await res.json();
    return match;
  },

  async getMatchDraft(matchId) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/matches/${matchId}/draft/`);
    if (!res.ok) {
      throw new Error("Failed to fetch match draft data from Riot API");
    }
    const draft = await res.json();
    return {
    team100_bans: (draft.draft["100"].bans).map(
      (ban: { champion_id: number }) => ban.champion_id
    ),
    team200_bans: (draft.draft["200"].bans).map(
      (ban: { champion_id: number }) => ban.champion_id
    ),
    team100_picks: (draft.draft["100"].picks).map(
      (pick: { champion_id: number }) => pick.champion_id
    ),
    team200_picks: (draft.draft["200"].picks).map(
      (pick: { champion_id: number }) => pick.champion_id
    ),
  }
  },

  async getPlayerBanAnalytics(puuid, limit) {
    const rng = createRng(`${puuid}:bans:${limit}`);

    const makeEntry = (): BanEntry => ({
      champion_id: randomInt(rng, 1, 300),
      champion_name: pick(rng, CHAMPIONS),
      count: randomInt(rng, 4, 60),
    });

    return {
      matches_analyzed: limit,
      banned_against: Array.from({ length: 10 }, makeEntry),
      banned_by_team: Array.from({ length: 10 }, makeEntry),
    };
  },

  async getGlobalMostBanned(limit) {
    const rng = createRng(`global-bans:${limit}`);
    return Array.from({ length: limit }, () => ({
      champion_id: randomInt(rng, 1, 300),
      champion_name: pick(rng, CHAMPIONS),
      ban_count: randomInt(rng, 120, 940),
    }));
  },

  async getChampionBanRate(championId) {
    const rng = createRng(`champion-rate:${championId}`);
    const totalMatches = randomInt(rng, 600, 5000);
    const timesBanned = randomInt(rng, 50, Math.floor(totalMatches * 0.45));

    return {
      champion_name: CHAMPIONS[championId % CHAMPIONS.length],
      ban_rate: Number(((timesBanned / totalMatches) * 100).toFixed(2)),
      times_banned: timesBanned,
      total_matches: totalMatches,
    };
  },

  async getRunesMap() {
    return runesMapStatic;
  },

  async getPlayerRuneHistory(puuid, limit) {
    return Array.from({ length: limit }, (_, index) => makeRuneEntry(`${puuid}:history`, index));
  },

  async getTimelineAvailability(matchId) {
    if (hash(matchId) % 5 === 0) {
      throw new MockApiError(
        404,
        "Timeline data not available for this match. Re-ingest with fetch_timeline=true.",
      );
    }

    const participants = makeMatchParticipants(matchId).map((entry) => entry.puuid);

    return {
      match_id: matchId,
      frame_rows: randomInt(createRng(`${matchId}:timeline-frames`), 24, 42),
      event_rows: randomInt(createRng(`${matchId}:timeline-events`), 90, 180),
      frame_interval_ms: 60000,
      participant_puuids: participants,
    };
  },

  async getTimelineFramesByPuuid(matchId, puuid) {
    const rng = createRng(`${matchId}:${puuid}:frames`);
    let totalGold = randomInt(rng, 500, 900);

    return Array.from({ length: 30 }, (_, index) => {
      const goldGain = randomInt(rng, 220, 760);
      totalGold += goldGain;

      return {
        frame_timestamp: index * 60000,
        current_gold: randomInt(rng, 200, 1800),
        total_gold: totalGold,
        xp: randomInt(rng, 200, 22000),
        level: randomInt(rng, 1, 18),
        minions_killed: randomInt(rng, 0, 250),
        jungle_minions_killed: randomInt(rng, 0, 120),
        position_x: randomInt(rng, 0, 15000),
        position_y: randomInt(rng, 0, 15000),
      };
    });
  },

  async getTimelineEvents(matchId, limit, cursor) {
    const rng = createRng(`${matchId}:events`);
    const totalEvents = 180;
    const start = cursor ? Number(cursor) : 0;
    const end = Math.min(start + limit, totalEvents);

    const events = Array.from({ length: end - start }, (_, localIndex) => {
      const index = start + localIndex;
      const eventType = pick(rng, TIMELINE_EVENT_TYPES);

      return {
        id: `${matchId}-${index}`,
        timestamp: index * 15000,
        type: eventType,
        detail: `${eventType} event payload ${randomInt(rng, 1000, 9999)}`,
      };
    });

    return {
      events,
      next_cursor: end >= totalEvents ? null : String(end),
    };
  },
};

export { frontendMvpClient };
