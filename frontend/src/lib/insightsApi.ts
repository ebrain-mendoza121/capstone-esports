import { FALLBACK_LOL_CHAMPIONS } from "@/lib/lolData";

export type PlayerRoleCode = "TOP" | "JUNGLE" | "MID" | "BOT" | "SUPPORT";
export type PlatformCode = "NA1" | "EUW1" | "KR" | "LA1";

export interface PlayerInsightInput {
  gameName: string;
  tagLine: string;
  role: PlayerRoleCode;
  champion: string;
}

export interface PlayerInsightInputForm {
  gameName: string;
  tagLine: string;
  role: PlayerRoleCode | "";
  champion: string;
}

export interface TeamInsightsRequest {
  platform: PlatformCode;
  // Expected length: 5 players.
  players: PlayerInsightInput[];
}

export interface MatchupInsightsRequest {
  teamAPlatform: PlatformCode;
  teamBPlatform: PlatformCode;
  // Expected length: 5 players each.
  teamAPlayers: PlayerInsightInput[];
  teamBPlayers: PlayerInsightInput[];
}

export interface InsightResponse {
  headline: string;
  summary: string;
  bullets: string[];
  generatedAt: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function summarizePlayers(players: PlayerInsightInput[]): string {
  return players
    .map(
      (player) =>
        `${player.gameName.trim()}#${player.tagLine.trim()} (${player.role}, ${player.champion.trim()})`,
    )
    .join(", ");
}

interface ChampionsListResponse {
  champions?: Array<{ name?: string }>;
}

export async function listChampionOptions(): Promise<string[]> {
  const fallback = [...FALLBACK_LOL_CHAMPIONS];

  if (!API_BASE_URL) {
    return fallback;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/champions`, {
      method: "GET",
    });

    if (!response.ok) {
      return fallback;
    }

    const payload = (await response.json()) as ChampionsListResponse;
    const championNames = (payload.champions ?? [])
      .map((entry) => entry.name?.trim())
      .filter((name): name is string => Boolean(name));

    if (championNames.length === 0) {
      return fallback;
    }

    return Array.from(new Set(championNames)).sort((a, b) => a.localeCompare(b));
  } catch {
    return fallback;
  }
}

export async function requestTeamInsights(payload: TeamInsightsRequest): Promise<InsightResponse> {
  // Backend-ready placeholder:
  // return postJson<InsightResponse, TeamInsightsRequest>("/insights/team", payload);

  await delay(780);
  const roster = summarizePlayers(payload.players);

  return {
    headline: "Team Synergy Snapshot",
    summary: `Mock analysis for ${roster} on ${payload.platform}. This placeholder estimates macro coordination, engage timing, and lane-to-objective transitions.`,
    bullets: [
      "Projected strongest phase: mid-game objective setups around dragon and Herald.",
      "Monitor jungle-support pathing sync to prevent tempo drops in minute 8-14 windows.",
      "Add one high-priority draft adaptation recommendation once real model output is connected.",
    ],
    generatedAt: new Date().toISOString(),
  };
}

export async function requestMatchupInsights(payload: MatchupInsightsRequest): Promise<InsightResponse> {
  // Backend-ready placeholder:
  // return postJson<InsightResponse, MatchupInsightsRequest>("/insights/matchup", payload);

  await delay(920);
  const teamA = summarizePlayers(payload.teamAPlayers);
  const teamB = summarizePlayers(payload.teamBPlayers);

  return {
    headline: "Matchup Comparison Snapshot",
    summary: `Mock comparison for Team A (${teamA}) on ${payload.teamAPlatform} versus Team B (${teamB}) on ${payload.teamBPlatform}. This placeholder represents where lane pressure and objective control could diverge.`,
    bullets: [
      "Projected first-swing factor: jungle-priority conversion into first dragon setup.",
      "Highest volatility lane should be tracked for roam windows and vision denial.",
      "Future model output will include win-condition confidence, draft counters, and macro call timing.",
    ],
    generatedAt: new Date().toISOString(),
  };
}
