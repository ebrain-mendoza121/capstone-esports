import { FALLBACK_LOL_CHAMPIONS } from "@/lib/lolData";
import { getApiBaseUrl } from "@/lib/apiBaseUrl";

export type PlayerRoleCode = "TOP" | "JUNGLE" | "MID" | "BOT" | "SUPPORT";
export type PlatformCode = "NA" | "EUW" | "EUNE" | "KR" | "BR" | "LAN" | "LAS" | "JP" | "OCE" | "TR" | "RU";

export interface PlayerInsightInput {
  gameName: string;
  tagLine: string;
  role: PlayerRoleCode;
  champion?: string;
}

export interface PlayerInsightInputForm {
  gameName: string;
  tagLine: string;
  role: PlayerRoleCode | "";
  champion: string;
}

export interface TeamInsightsRequest {
  platform: PlatformCode;
  players: PlayerInsightInput[];
}

export interface MatchupInsightsRequest {
  teamAPlatform: PlatformCode;
  teamBPlatform: PlatformCode;
  teamAPlayers: PlayerInsightInput[];
  teamBPlayers: PlayerInsightInput[];
}

// ── Rich response types matching the backend ─────────────────────────────────

export interface ChampionMeta {
  id: number;
  name: string;
  title: string;
  tags: string[];
  image_url: string;
  role_affinity: string[];
}

export interface TeamPlayerResult {
  summoner_name: string | null;
  puuid: string | null;
  source: string;
  primary_role: string | null;
  declared_role: string | null;
  champion_meta: ChampionMeta | null;
  role_champion_fit: "native" | "flex" | "off-meta" | "unknown";
  games_in_window: number;
  confidence: "high" | "medium" | "low";
  win_rate_20: number | null;
  avg_kda_20: number | null;
  avg_cs_per_min_20: number | null;
  avg_gold_per_min_20: number | null;
  avg_kill_part_20: number | null;
  avg_vision_per_min_20: number | null;
  error: string | null;
}

export interface TeamAggStats {
  win_rate_20: number | null;
  avg_kda_20: number | null;
  avg_cs_per_min_20: number | null;
  avg_gold_per_min_20: number | null;
  avg_kill_part_20: number | null;
  avg_vision_per_min_20: number | null;
  players_with_data: number;
}

export interface ThreatScore {
  summoner_name: string;
  threat_score: number;
  win_rate_20: number | null;
  avg_kda_20: number | null;
}

export interface PredictedCarry {
  summoner_name: string;
  carry_score: number;
  win_rate_20: number | null;
  avg_kda_20: number | null;
  avg_cs_per_min_20: number | null;
}

export interface TeamDna {
  label: string;
  emoji: string;
  tagline: string;
  breakdown: Record<string, number>;
  players_classified: number;
}

export interface TeamBuildResponse {
  platform: string;
  composition_focus: string | null;
  players: TeamPlayerResult[];
  team_stats: TeamAggStats;
  strengths: string[];
  gaps: string[];
  composition_archetype: string;
  synergy_flags: string[];
  team_dna: TeamDna | null;
  threat_scores: ThreatScore[];
  predicted_carry: PredictedCarry | null;
}

export interface EdgeStats {
  metric: string;
  winner: "blue" | "red" | "even";
  blue: number;
  red: number;
  delta: number;
  pct_diff?: number;
}

export interface RoleMatchup {
  role: string;
  blue_player: string | null;
  red_player: string | null;
  overall_edge: "blue" | "red" | "even";
  edge_label: string;
  win_rate: EdgeStats;
  kda: EdgeStats;
  cs_per_min: EdgeStats;
}

export interface TeamMatchupResponse {
  platform: string;
  blue_win_probability: number;
  red_win_probability: number;
  prediction_method: string;
  role_matchups: RoleMatchup[];
  lane_edges: {
    blue_lanes_winning: number;
    red_lanes_winning: number;
    even_lanes: number;
  };
  blue_team: {
    players: TeamPlayerResult[];
    team_stats: TeamAggStats;
    gaps: string[];
    composition_archetype: string;
    synergy_flags: string[];
    team_dna: TeamDna | null;
    threat_scores: ThreatScore[];
    predicted_carry: PredictedCarry | null;
  };
  red_team: {
    players: TeamPlayerResult[];
    team_stats: TeamAggStats;
    gaps: string[];
    composition_archetype: string;
    synergy_flags: string[];
    team_dna: TeamDna | null;
    threat_scores: ThreatScore[];
    predicted_carry: PredictedCarry | null;
  };
  key_advantages: {
    blue: string[];
    red: string[];
  };
}

// ── Legacy shape kept for InsightResponsePanel (still used as fallback) ──────
export interface InsightResponse {
  headline: string;
  summary: string;
  bullets: string[];
  generatedAt: string;
}

const API_BASE_URL = getApiBaseUrl();

export async function postJson<TResponse, TPayload>(path: string, payload: TPayload): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }

  return (await response.json()) as TResponse;
}

// ── Champion list (GET /champions returns flat array) ────────────────────────

interface ChampionEntry {
  name?: string;
  id?: number;
}

export async function listChampionOptions(): Promise<string[]> {
  const fallback = [...FALLBACK_LOL_CHAMPIONS];

  if (!API_BASE_URL) return fallback;

  try {
    const response = await fetch(`${API_BASE_URL}/champions`);
    if (!response.ok) return fallback;

    const payload = await response.json();

    // Backend returns { champions: [...] } or a flat array — handle both
    const raw: ChampionEntry[] = Array.isArray(payload)
      ? payload
      : (payload.champions ?? []);

    const names = raw
      .map((c) => c.name?.trim())
      .filter((n): n is string => Boolean(n));

    return names.length > 0
      ? Array.from(new Set(names)).sort((a, b) => a.localeCompare(b))
      : fallback;
  } catch {
    return fallback;
  }
}

// ── Team build ────────────────────────────────────────────────────────────────

export async function requestTeamInsights(
  payload: TeamInsightsRequest,
): Promise<TeamBuildResponse> {
  return postJson<TeamBuildResponse, object>("/teams/build", {
    platform: payload.platform,
    players: payload.players.map((p) => ({
      game_name: p.gameName,
      tag_line:  p.tagLine,
      role:      p.role,
      ...(p.champion ? { champion: p.champion } : {}),
    })),
  });
}

// ── Team matchup ──────────────────────────────────────────────────────────────

export async function requestMatchupInsights(
  payload: MatchupInsightsRequest,
): Promise<TeamMatchupResponse> {
  return postJson<TeamMatchupResponse, object>("/teams/matchup", {
    platform:  payload.teamAPlatform,
    blue_team: payload.teamAPlayers.map((p) => ({
      game_name: p.gameName,
      tag_line:  p.tagLine,
      role:      p.role,
      ...(p.champion ? { champion: p.champion } : {}),
    })),
    red_team: payload.teamBPlayers.map((p) => ({
      game_name: p.gameName,
      tag_line:  p.tagLine,
      role:      p.role,
      ...(p.champion ? { champion: p.champion } : {}),
    })),
  });
}
