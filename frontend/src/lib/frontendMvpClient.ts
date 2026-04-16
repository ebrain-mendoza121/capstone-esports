import { getApiBaseUrl } from "@/lib/apiBaseUrl";

const _API = getApiBaseUrl();

export type QueueCode = 420 | 440;
export type RoleCode = "TOP" | "JUNGLE" | "MID" | "BOT" | "SUPPORT";

export interface PlayerSummary {
  puuid: string;
  riot_id: string;
  tag_line: string;
  region: string;
  match_count: number;
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
  kill_participation: number;
  damage_share: number;
}

export interface RolePerformanceEntry {
  role: string;
  games_played: number;
  win_rate: number;
  avg_kda: number;
  avg_cs_per_min: number;
  avg_kill_part: number;
  avg_vision: number;
  vs_peers: {
    global_win_rate: number;
    global_avg_kda: number;
    global_avg_cs: number;
    win_rate_vs_peers: string;
    cs_vs_peers: string;
    kda_delta: number;
    cs_delta: number;
    wr_delta: number;
  };
}

export interface PlayerRolePerformance {
  puuid: string;
  primary_role: string | null;
  roles: RolePerformanceEntry[];
}

export interface PlaystyleResult {
  puuid: string;
  cluster_id: number;
  playstyle_label: string;
  meets_min_sample: boolean;
  games_played: number;
  feature_snapshot: Record<string, number>;
  model_trained_at: string | null;
}

export interface ChampionRecommendation {
  champion_id: number;
  champion_name: string;
  role: string | null;
  score: number;
  games_played: number;
  win_rate: number;
  smoothed_win_rate: number;
  playstyle_match: boolean;
}

export interface TrendGamePoint {
  match_id: string;
  game_creation: number;
  champion: string | null;
  role: string | null;
  win: boolean;
  kda: number | null;
  cs_per_min: number | null;
  gold_per_min: number | null;
  kill_participation: number | null;
  vision_per_min: number | null;
  kills: number | null;
  deaths: number | null;
  assists: number | null;
}

export interface PlayerTrends {
  puuid: string;
  summoner_name: string;
  games_in_window: number;
  has_full_window: boolean;
  message?: string;
  rolling: {
    win_rate_20: number;
    avg_kda_20: number;
    avg_cs_per_min_20: number;
    avg_gold_per_min_20: number;
    avg_kill_part_20: number;
    death_rate_20: number;
    vision_per_min_20: number;
    kda_std_10: number;
    cs_trend_10: number;
    win_streak: number;
  } | null;
  series: TrendGamePoint[];
}

export interface ChampionStat {
  champion_id: number;
  champion_name: string;
  games_played: number;
  win_rate: number | null;
  avg_kda: number | null;
  avg_cs_per_min: number | null;
  avg_gold_per_min: number | null;
  avg_kills: number | null;
  avg_deaths: number | null;
  avg_assists: number | null;
}

export interface PlayerChampionStats {
  puuid: string;
  min_games: number;
  champions_found: number;
  champions: ChampionStat[];
}

export interface ObjectiveControl {
  avg_towers_when_winning: number;
  avg_towers_when_losing: number;
  avg_dragons_when_winning: number;
  avg_dragons_when_losing: number;
  avg_barons_when_winning: number;
  avg_barons_when_losing: number;
  dragon_soul_rate: number;
  total_matches_analyzed: number;
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
  team_id: 100 | 200;
  game_duration: number;
  patch_version: string;
  kda: number | null;
  cs_per_min: number | null;
  queue_id: QueueCode;
  // derived metrics — null when backfill hasn't run yet
  total_damage: number | null;
  kill_participation: number | null;
  damage_share: number | null;
  gold_per_min: number | null;
  vision_per_min: number | null;
  wards_placed: number | null;
  penta_kills: number | null;
  first_blood_kill: boolean | null;
}

export interface WinPrediction {
  puuid: string;
  match_id: string;
  model_trained: boolean;
  win_probability: number | null;
  confidence: string;
  prior_games: number;
}

export interface KdaPrediction {
  puuid: string;
  match_id: string;
  model_trained: boolean;
  expected_kda: number | null;
  confidence: string;
}

export interface CsPrediction {
  puuid: string;
  match_id: string;
  model_trained: boolean;
  expected_cs_per_min: number | null;
  confidence: string;
}

export interface EarlyGamePrediction {
  match_id: string;
  model_trained: boolean;
  team_100_win_probability: number | null;
  team_200_win_probability: number | null;
  confidence: string;
  error?: string;
}

export interface ModelStatusEntry {
  trained: boolean;
  trained_at: string | null;
  version: string | null;
  metrics: Record<string, number | string>;
}

export interface ModelsStatus {
  [modelName: string]: ModelStatusEntry;
}

export interface ThreatWeights {
  win_rate_weight: number;
  kda_weight: number;
  source: "model" | "default" | string;
  model_auc: number | null;
  feature_breakdown: Record<string, number> | null;
  interpretation: string;
}

export interface WinPredictionBacktestSummary {
  total: number;
  correct: number;
  accuracy: number | null;
  mean_predicted_prob: number | null;
  actual_win_rate: number | null;
  brier_score: number | null;
}

export interface WinPredictionCalibrationBucket {
  bucket: string;
  predicted_range: [number, number];
  n_matches: number;
  actual_win_rate: number | null;
}

export interface WinPredictionBacktest {
  model_trained: boolean;
  reason?: string;
  summary?: WinPredictionBacktestSummary;
  calibration_buckets?: WinPredictionCalibrationBucket[];
  match_results?: Array<{
    match_id: string;
    puuid: string;
    predicted_prob: number;
    actual_win: number;
    correct: boolean;
    confidence: string;
  }>;
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
  tag_line: string;
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
  game_creation: number;
  platform_id: string;
  teams: TeamStats[];
  participants: MatchParticipant[];
  has_timeline: boolean;
}

export interface DraftData {
  team100_bans: number[];
  team200_bans: number[];
  team100_picks: number[];
  team200_picks: number[];
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
  [runeId: string]: string;
}

export interface TimelineAvailability {
  match_id: string;
  participant_frame_rows: number;
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

export interface TimelineFrameRaw {
  frame_timestamp: number;
  participant_id: number;
  total_gold: number;
}

export type TimelineEventType =
  | "CHAMPION_KILL"
  | "BUILDING_KILL"
  | "ELITE_MONSTER_KILL"
  | "ITEM_PURCHASED";

export interface TimelineEvent {
  event_id: string;
  timestamp: number;
  type: TimelineEventType;
  detail: {
    killerId: number;
  };
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
  listPlayers(minMatches?: number): Promise<PlayerSummary[]>;
  ingestPlayer(payload: IngestPlayerInput): Promise<PlayerSummary>;

  // Page 2
  getPlayer(puuid: string): Promise<PlayerDetail>;
  getPlayerMetrics(puuid: string): Promise<PlayerMetrics>;
  getPlayerRunes(puuid: string, limit: number): Promise<RuneEntry[]>;
  getPlayerRolePerformance(puuid: string): Promise<PlayerRolePerformance>;
  getPlayerPlaystyle(puuid: string): Promise<PlaystyleResult | null>;
  getChampionRecommendations(puuid: string, topN?: number): Promise<ChampionRecommendation[]>;
  getPlayerTrends(puuid: string, window?: number): Promise<PlayerTrends>;
  getPlayerChampionStats(puuid: string, minGames?: number): Promise<PlayerChampionStats>;
  getObjectiveControl(puuid: string): Promise<ObjectiveControl>;

  // Page 3
  getMatchesByPlayer(puuid: string, limit: number): Promise<MatchHistoryEntry[]>;
  getWinPrediction(puuid: string, matchId: string): Promise<WinPrediction>;
  getKdaPrediction(puuid: string, matchId: string): Promise<KdaPrediction>;
  getCsPrediction(puuid: string, matchId: string): Promise<CsPrediction>;

  // Page 4
  getMatch(matchId: string): Promise<MatchDetail>;
  getMatchDraft(matchId: string): Promise<DraftData>;
  getEarlyGamePrediction(matchId: string): Promise<EarlyGamePrediction>;
  getModelsStatus(): Promise<ModelsStatus>;
  getThreatWeights(): Promise<ThreatWeights>;
  getWinPredictionBacktest(nMatches?: number): Promise<WinPredictionBacktest>;

  // Page 5
  getPlayerBanAnalytics(puuid: string, limit: number): Promise<PlayerBanAnalytics>;
  getGlobalMostBanned(limit: number): Promise<GlobalBanEntry[]>;
  getChampionBanRate(championId: number): Promise<ChampionBanRate>;
  getAllBanRates(): Promise<{ total_matches: number; rates: Record<number, ChampionBanRate> }>;

  // Page 6
  getRunesMap(): Promise<RuneMapEntry[]>;//TODO
  getPlayerRuneHistory(puuid: string, limit: number): Promise<RuneEntry[]>;//TODO

  // Page 7
  getTimelineAvailability(matchId: string): Promise<TimelineAvailability>;//TODO
  getTimelineFramesByPuuid(matchId: string, puuid: string): Promise<TimelineFrame[]>;//TODO
  getTimelineFramesAll(matchId: string, limit?: number): Promise<TimelineFrameRaw[]>;
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
  const res = await fetch(`${_API}/players/`);
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

async function resolvePlayer(puuid: string){
  const res = await fetch(`${_API}/players/${puuid}`);
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
    match_count: player.match_count ?? 0,
    created_at: player.created_at
  };
}

const frontendMvpClient: FrontendMvpClient = {
  async listPlayers(minMatches = 10) {
    const url = `${_API}/players/?min_matches=${minMatches}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error("Failed to fetch player list from Riot API");
    }
    const players = await res.json();
    return players as PlayerSummary[];
  },

  async ingestPlayer(payload) {
    const res = await fetch(`${_API}/ingest/player`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gameName: payload.gameName,
        tagLine: payload.tagLine,
        platform: payload.platform,
        count: payload.matchCount,
        queue: payload.queue,
      }),
    });

    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail ?? ""; } catch { /* ignore */ }
      if (res.status === 404) throw new MockApiError(404, detail || "Player not found on Riot servers");
      if (res.status === 503) throw new MockApiError(503, detail || "Riot API rate limit hit — try again in 30 seconds");
      if (res.status === 502) throw new MockApiError(502, detail || "Riot API error — check API key");
      throw new Error(detail || "Unexpected ingest error");
    }

    const data = await res.json() as {
      puuid: string;
      platform: string;
      routing: string;
      inserted: number;
      skipped: number;
      failed: string[];
    };

    return {
      puuid: data.puuid,
      riot_id: payload.gameName,
      tag_line: payload.tagLine,
      region: payload.platform,
      match_count: data.inserted,
    };
  },

  async getPlayer(puuid) {
    const player = await resolvePlayer(puuid);
    return {
      ...player
    };
  },

  async getPlayerMetrics(puuid) {
    const res = await fetch(`${_API}/metrics/player/${puuid}`);
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
      kill_participation: metrics.kill_participation ?? 0,
      damage_share: metrics.damage_share ?? 0,
    };
  },

  async getPlayerRunes(puuid, limit) {
    const res = await fetch(`${_API}/analytics/player/${puuid}/runes?limit=${limit}`);
    if (!res.ok) {      throw new Error("Failed to fetch player rune history from Riot API");
    }
    const runes = await res.json();

    return [...runes.runes];
  },

  async getPlayerRolePerformance(puuid) {
    const res = await fetch(`${_API}/analytics/player/${puuid}/role-performance`);
    if (!res.ok) throw new Error("Failed to fetch role performance");
    return res.json() as Promise<PlayerRolePerformance>;
  },

  async getPlayerPlaystyle(puuid) {
    const res = await fetch(`${_API}/ai/playstyle/${puuid}`);
    // 503 = model not trained yet — return null instead of throwing
    if (res.status === 503) return null;
    if (!res.ok) throw new Error("Failed to fetch playstyle");
    return res.json() as Promise<PlaystyleResult>;
  },

  async getChampionRecommendations(puuid, topN = 10) {
    const res = await fetch(`${_API}/ai/champions/${puuid}?top_n=${topN}`);
    if (!res.ok) throw new Error("Failed to fetch champion recommendations");
    return res.json() as Promise<ChampionRecommendation[]>;
  },

  async getMatchesByPlayer(puuid, limit) {
    const res = await fetch(`${_API}/matches/player/${puuid}?limit=${limit}`);
    if (!res.ok) {
      throw new Error("Failed to fetch player match history from Riot API");
    }
    const matches = await res.json();

    return [...matches];
  },

  async getWinPrediction(puuid, matchId) {
    const res = await fetch(`${_API}/ai/predict/${puuid}/${matchId}`);
    if (!res.ok) throw new Error("Failed to fetch win prediction");
    return res.json() as Promise<WinPrediction>;
  },

  async getKdaPrediction(puuid, matchId) {
    const res = await fetch(`${_API}/ai/predict/kda/${puuid}/${matchId}`);
    if (!res.ok) throw new Error("Failed to fetch KDA prediction");
    return res.json() as Promise<KdaPrediction>;
  },

  async getCsPrediction(puuid, matchId) {
    const res = await fetch(`${_API}/ai/predict/cs/${puuid}/${matchId}`);
    if (!res.ok) throw new Error("Failed to fetch CS prediction");
    return res.json() as Promise<CsPrediction>;
  },

  async getMatch(matchId) {
    const res = await fetch(`${_API}/matches/${matchId}`);
    if (!res.ok) {
      throw new Error("Failed to fetch match details from Riot API");
    }
    const match = await res.json();
    return match;
  },

  async getMatchDraft(matchId) {
    const res = await fetch(`${_API}/matches/${matchId}/draft`);
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

  async getEarlyGamePrediction(matchId) {
    const res = await fetch(`${_API}/ai/early-game/${matchId}`);
    if (!res.ok) throw new Error("Failed to fetch early game prediction");
    return res.json() as Promise<EarlyGamePrediction>;
  },

  async getModelsStatus() {
    const res = await fetch(`${_API}/ai/models/status`);
    if (!res.ok) throw new Error("Failed to fetch models status");
    return res.json() as Promise<ModelsStatus>;
  },

  async getThreatWeights() {
    const res = await fetch(`${_API}/ai/threat-weights`);
    if (!res.ok) throw new Error("Failed to fetch threat weights");
    return res.json() as Promise<ThreatWeights>;
  },

  async getWinPredictionBacktest(nMatches = 50) {
    const res = await fetch(`${_API}/ai/backtest/win-prediction?n_matches=${nMatches}`);
    if (!res.ok) throw new Error("Failed to fetch win-prediction backtest");
    return res.json() as Promise<WinPredictionBacktest>;
  },

  async getPlayerBanAnalytics(puuid, limit) {
    const res = await fetch(`${_API}/analytics/player/${puuid}/bans?limit=${limit}`);
    if (!res.ok) {
      throw new Error("Failed to fetch player ban analytics from Riot API");
    }
    const banAnalytics = await res.json();
    const aggregateBans = (
      bans: Array<{ champion_id: number; champion_name: string }>
    ): BanEntry[] => {
      const byChampion = new Map<number, BanEntry>();

      bans.forEach((ban) => {
        const existing = byChampion.get(ban.champion_id);

        if (existing) {
          existing.count += 1;
        } else {
          byChampion.set(ban.champion_id, {
            champion_id: ban.champion_id,
            champion_name: ban.champion_name,
            count: 1,
          });
        }
      });

      return Array.from(byChampion.values()).sort((a, b) => b.count - a.count);
    };

    return {
      matches_analyzed: banAnalytics.matches_analyzed,
      banned_against: aggregateBans(banAnalytics.bans_against ?? []),
      banned_by_team: aggregateBans(banAnalytics.bans_by_team ?? []),
    };
  },

  async getGlobalMostBanned(limit) {
    const res = await fetch(`${_API}/analytics/bans/most-banned?limit=${limit}`);
    if (!res.ok) {
      throw new Error("Failed to fetch global ban data from Riot API");
    }
    const globalBans = await res.json();
    return [...globalBans];
  },

  async getChampionBanRate(championId) {
    const res = await fetch(`${_API}/analytics/champion/${championId}/ban-rate`);
    if (!res.ok) {
      throw new Error("Failed to fetch champion ban rate from Riot API");
    }
    const banRate = await res.json();
    return banRate;
  },

  async getAllBanRates() {
    const res = await fetch(`${_API}/analytics/bans/all-rates`);
    if (!res.ok) {
      throw new Error("Failed to fetch ban rates");
    }
    return res.json();
  },

  async getRunesMap() {
    const res = await fetch(`${_API}/analytics/runes/map`);
    if (!res.ok) {
      throw new Error("Failed to fetch runes map from Riot API");
    }
    const runesMap = await res.json();
    return runesMap;
  },

  async getPlayerRuneHistory(puuid, limit) {
    const res = await fetch(`${_API}/analytics/player/${puuid}/runes?limit=${limit}`);
    if (!res.ok) {
      throw new Error("Failed to fetch player rune history from Riot API");
    }
    const runes = await res.json();
    return [...runes.runes];
  },

  async getTimelineAvailability(matchId) {
    const res = await fetch(`${_API}/timeline/${matchId}`);
    if (!res.ok) {
      if (res.status === 404) {
        throw new MockApiError(
          404,
          "Timeline data not available for this match. Re-ingest with fetch_timeline=true."
        );
      }
      throw new Error("Failed to fetch timeline availability from Riot API");
    }
    const timelineMeta = await res.json();
    const matchDetails = await this.getMatch(matchId); // Ensure match details are loaded to get participant puuids
    const participant_puuids = matchDetails.participants.map((p) => p.puuid);
    return {...timelineMeta, participant_puuids};  
  },

  async getTimelineFramesByPuuid(matchId, puuid) {
    const res = await fetch(`${_API}/timeline/${matchId}/frames/by-puuid/${puuid}`);
    if (!res.ok) {
      throw new Error("Failed to fetch timeline frames from Riot API");
    }
    const frames = await res.json();
    return frames;
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

async getPlayerTrends(puuid, window = 20) {
    const res = await fetch(
      `${_API}/analytics/player/${puuid}/trends?window=${window}`
    );
    if (!res.ok) {
      throw new Error(`Failed to fetch trends (${res.status})`);
    }
    return (await res.json()) as PlayerTrends;
  },

  async getPlayerChampionStats(puuid, minGames = 1) {
    const res = await fetch(
      `${_API}/analytics/player/${puuid}/champion-stats?min_games=${minGames}`
    );
    if (!res.ok) throw new Error(`Failed to fetch champion stats (${res.status})`);
    return res.json() as Promise<PlayerChampionStats>;
  },

  async getObjectiveControl(puuid) {
    const res = await fetch(
      `${_API}/analytics/player/${puuid}/objective-control`
    );
    if (!res.ok) throw new Error(`Failed to fetch objective control (${res.status})`);
    return res.json() as Promise<ObjectiveControl>;
  },

  async getTimelineFramesAll(matchId, limit = 1000) {
    const res = await fetch(
      `${_API}/timeline/${matchId}/frames?limit=${limit}`
    );
    if (!res.ok) throw new Error(`Failed to fetch timeline frames (${res.status})`);
    return res.json() as Promise<TimelineFrameRaw[]>;
  },

  async getTimelineEvents(matchId, limit, cursor) {
  const url =
    `${_API}/timeline/${matchId}/events?limit=${limit}` +
    (cursor ? `&cursor=${cursor}` : "");

  const res = await fetch(url);

  if (!res.ok) {
    throw new Error("Failed to fetch timeline events from Riot API");
  }

  const data = await res.json();

  return {
    events: (data.events ?? []).map(
      (event: {
        event_id: number;
        timestamp: number;
        type: string;
        detail: unknown;
      }) => ({
        event_id: String(event.event_id),
        timestamp: event.timestamp,
        type: event.type,
        detail: event.detail,
      })
    ),
    next_cursor: data.next_cursor ?? null,
  };
}
};

export { frontendMvpClient };
