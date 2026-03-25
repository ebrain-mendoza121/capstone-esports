"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import styles from "./page.module.css";

type GameSlug = "league-of-legends" | "valorant";
type MatchWindow = 5 | 10 | 20;
type MatchResult = "Win" | "Loss";
type ResultFilter = "All" | MatchResult;
type SortDirection = "asc" | "desc";
type SortKey = "matchId" | "character" | "kda" | "secondaryStat" | "result";

interface MetricDefinition {
  key: string;
  label: string;
  min: number;
  max: number;
  decimals: number;
  unit: string;
}

interface MetricCard {
  label: string;
  value: number;
  decimals: number;
  unit: string;
  trend: number;
}

interface RoleAxis {
  label: string;
  value: number;
}

interface CharacterAnalytics {
  name: string;
  winRate: number;
  pickRate: number;
  performance: number;
}

interface MatchRow {
  matchId: string;
  character: string;
  kda: number;
  secondaryStat: number;
  result: MatchResult;
}

interface DashboardData {
  metrics: MetricCard[];
  trendSeries: number[];
  rollingSeries: number[];
  comparisonSeries: number[];
  roleRadar: RoleAxis[];
  characterAnalytics: CharacterAnalytics[];
  matchHistory: MatchRow[];
  insights: string[];
}

interface GameConfig {
  label: string;
  roles: string[];
  metricDefinitions: MetricDefinition[];
  secondaryStatLabel: string;
  secondaryStatUnit: string;
  characterLabel: string;
  characters: string[];
  radarAxes: string[];
  trendColor: string;
}

const GAME_CONFIG: Record<GameSlug, GameConfig> = {
  "league-of-legends": {
    label: "League of Legends",
    roles: ["All", "Top", "Jungle", "Mid", "ADC", "Support"],
    metricDefinitions: [
      { key: "kda", label: "KDA", min: 1.4, max: 6.2, decimals: 2, unit: "" },
      { key: "csMin", label: "CS / Min", min: 5.2, max: 9.8, decimals: 1, unit: "" },
      { key: "goldMin", label: "Gold / Min", min: 280, max: 620, decimals: 0, unit: "" },
      { key: "winRate", label: "Win Rate", min: 42, max: 78, decimals: 1, unit: "%" },
      {
        key: "killParticipation",
        label: "Kill Participation",
        min: 44,
        max: 80,
        decimals: 1,
        unit: "%",
      },
      { key: "damageShare", label: "Damage Share", min: 15, max: 39, decimals: 1, unit: "%" },
      {
        key: "visionMin",
        label: "Vision / Min",
        min: 0.8,
        max: 2.3,
        decimals: 2,
        unit: "",
      },
    ],
    secondaryStatLabel: "CS / Min",
    secondaryStatUnit: "",
    characterLabel: "Champion",
    characters: ["Jinx", "Azir", "Ahri", "Lee Sin", "Ornn", "Kai'Sa", "Thresh", "Yone"],
    radarAxes: [
      "Damage Contribution",
      "Gold Generation",
      "CS Efficiency",
      "Vision Control",
      "Survivability",
    ],
    trendColor: "#118ab2",
  },
  valorant: {
    label: "Valorant",
    roles: ["All", "Duelist", "Initiator", "Controller", "Sentinel"],
    metricDefinitions: [
      { key: "kda", label: "KDA", min: 0.9, max: 1.8, decimals: 2, unit: "" },
      { key: "acs", label: "ACS", min: 145, max: 315, decimals: 0, unit: "" },
      { key: "headshot", label: "Headshot Rate", min: 12, max: 38, decimals: 1, unit: "%" },
      { key: "winRate", label: "Win Rate", min: 40, max: 74, decimals: 1, unit: "%" },
      { key: "kast", label: "KAST", min: 58, max: 82, decimals: 1, unit: "%" },
      { key: "firstBlood", label: "First Blood", min: 7, max: 22, decimals: 1, unit: "%" },
      { key: "econ", label: "Econ Rating", min: 90, max: 140, decimals: 0, unit: "" },
    ],
    secondaryStatLabel: "ACS",
    secondaryStatUnit: "",
    characterLabel: "Agent",
    characters: ["Jett", "Raze", "Sova", "Omen", "Cypher", "Reyna", "Skye", "Fade"],
    radarAxes: ["Entry Impact", "Utility Value", "Econ Control", "Survivability", "Team Play"],
    trendColor: "#ef476f",
  },
};

function isGameSlug(value: string): value is GameSlug {
  return value === "league-of-legends" || value === "valorant";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function hashString(value: string): number {
  let hash = 0;

  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index);
    hash |= 0;
  }

  return Math.abs(hash) + 1;
}

function createRng(seed: number): () => number {
  let state = seed % 2147483647;
  if (state <= 0) {
    state += 2147483646;
  }

  return () => {
    state = (state * 16807) % 2147483647;
    return (state - 1) / 2147483646;
  };
}

function randomInRange(rng: () => number, min: number, max: number): number {
  return min + rng() * (max - min);
}

function movingAverage(values: number[], window: number): number[] {
  const result: number[] = [];

  for (let index = 0; index < values.length; index += 1) {
    const start = Math.max(0, index - window + 1);
    const slice = values.slice(start, index + 1);
    const average = slice.reduce((sum, value) => sum + value, 0) / slice.length;
    result.push(average);
  }

  return result;
}

function buildInsights(
  config: GameConfig,
  metrics: MetricCard[],
  comparisonSeries: number[],
  roleFilter: string,
): string[] {
  const winRate = metrics.find((metric) => metric.label === "Win Rate");
  const kdaMetric = metrics.find((metric) => metric.label === "KDA");
  const averageSwing =
    comparisonSeries.reduce((sum, value) => sum + Math.abs(value), 0) / comparisonSeries.length;

  const insights: string[] = [
    `Automated analysis: ${config.label} profile is strongest when tempo stays controlled in mid-game rounds.`,
  ];

  if (winRate && winRate.value < 50) {
    insights.push(
      "Performance drop detection: late game conversion is below target. Prioritize safer objective or site-retake decisions.",
    );
  } else {
    insights.push(
      "Performance drop detection: consistency is stable with no major collapse pattern in recent matches.",
    );
  }

  if (kdaMetric && kdaMetric.value < 1.5) {
    insights.push(
      `AI coaching insight: focus on reducing early deaths while playing ${
        roleFilter === "All" ? "your main role" : roleFilter.toLowerCase()
      }.`,
    );
  } else {
    insights.push("AI coaching insight: high-value fights are being selected well; keep the same pacing.");
  }

  insights.push(
    `${config.characterLabel} suggestion: rotate toward top-performing picks with positive win-rate and high pick confidence.`,
  );

  if (averageSwing > 11) {
    insights.push(
      "Macro recommendation: match-to-match volatility is high; tighten pre-match strategy and role execution.",
    );
  } else {
    insights.push(
      "Macro recommendation: trend variance is low; continue current prep and champion/agent pool usage.",
    );
  }

  return insights.slice(0, 5);
}

function generateDashboardData(
  riotId: string,
  game: GameSlug,
  matchWindow: MatchWindow,
  roleFilter: string,
): DashboardData {
  const config = GAME_CONFIG[game];
  const rng = createRng(hashString(`${riotId}:${game}:${roleFilter}:${matchWindow}`));

  const metrics = config.metricDefinitions.map((definition) => ({
    label: definition.label,
    value: randomInRange(rng, definition.min, definition.max),
    decimals: definition.decimals,
    unit: definition.unit,
    trend: randomInRange(rng, -7.5, 9.5),
  }));

  const trendSeries = Array.from({ length: matchWindow }, (_, index) => {
    const base = 50 + index * randomInRange(rng, 0.5, 1.4);
    const variance = randomInRange(rng, -8, 10);
    return clamp(base + variance, 30, 95);
  });

  const rollingSeries = movingAverage(trendSeries, 3);

  const comparisonSeries = Array.from({ length: matchWindow }, () => randomInRange(rng, -20, 20));

  const roleRadar = config.radarAxes.map((axis) => ({
    label: axis,
    value: randomInRange(rng, 38, 96),
  }));

  const characterAnalytics = config.characters.slice(0, 6).map((character) => ({
    name: character,
    winRate: randomInRange(rng, 40, 75),
    pickRate: randomInRange(rng, 8, 34),
    performance: randomInRange(rng, 50, 97),
  }));

  const matchHistory = Array.from({ length: matchWindow }, (_, index) => {
    const matchId = `M-${String(hashString(`${riotId}-${index}`)).slice(0, 6)}`;

    return {
      matchId,
      character: config.characters[Math.floor(rng() * config.characters.length)],
      kda: randomInRange(rng, game === "valorant" ? 0.8 : 1.2, game === "valorant" ? 2.0 : 6.3),
      secondaryStat: randomInRange(
        rng,
        game === "valorant" ? 130 : 4.2,
        game === "valorant" ? 335 : 10,
      ),
      result: (rng() > 0.46 ? "Win" : "Loss") as MatchResult,
    };
  });

  return {
    metrics,
    trendSeries,
    rollingSeries,
    comparisonSeries,
    roleRadar,
    characterAnalytics,
    matchHistory,
    insights: buildInsights(config, metrics, comparisonSeries, roleFilter),
  };
}

function formatMetric(metric: MetricCard): string {
  return `${metric.value.toFixed(metric.decimals)}${metric.unit}`;
}

function sortRows(rows: MatchRow[], sortKey: SortKey, sortDirection: SortDirection): MatchRow[] {
  const direction = sortDirection === "asc" ? 1 : -1;

  return [...rows].sort((a, b) => {
    const leftValue = a[sortKey];
    const rightValue = b[sortKey];

    if (typeof leftValue === "number" && typeof rightValue === "number") {
      return (leftValue - rightValue) * direction;
    }

    return String(leftValue).localeCompare(String(rightValue)) * direction;
  });
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const width = 620;
  const height = 220;
  const padding = 24;
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);
  const range = Math.max(maxValue - minValue, 1);

  const toX = (index: number): number =>
    padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);

  const toY = (value: number): number =>
    height - padding - ((value - minValue) / range) * (height - padding * 2);

  const polyline = values.map((value, index) => `${toX(index)},${toY(value)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={styles.chartSvg} role="img" aria-label="Trend chart">
      <defs>
        <linearGradient id="line-gradient" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width={width} height={height} rx="14" fill="rgba(255,255,255,0.02)" />
      {[0, 1, 2, 3].map((step) => {
        const y = padding + (step * (height - padding * 2)) / 3;
        return <line key={step} x1={padding} y1={y} x2={width - padding} y2={y} className={styles.gridLine} />;
      })}
      <polyline points={polyline} fill="none" stroke={color} strokeWidth="3.5" strokeLinejoin="round" />
      {values.map((value, index) => (
        <circle key={`${value}-${index}`} cx={toX(index)} cy={toY(value)} r="3.2" fill={color} />
      ))}
    </svg>
  );
}

function DeltaBars({ values }: { values: number[] }) {
  const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 1);

  return (
    <div className={styles.deltaBars}>
      {values.map((value, index) => {
        // Clamp each side to half of the track so bars grow from center without overflow.
        const size = `${(Math.abs(value) / maxAbs) * 50}%`;
        const positive = value >= 0;

        return (
          <div key={`${value}-${index}`} className={styles.deltaRow}>
            <span className={styles.deltaLabel}>M{index + 1}</span>
            <div className={styles.deltaTrack}>
              <span
                className={positive ? styles.deltaPositive : styles.deltaNegative}
                style={positive ? { width: size } : { marginLeft: `calc(50% - ${size})`, width: size }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Radar({ points }: { points: RoleAxis[] }) {
  const size = 260;
  const center = size / 2;
  const radius = 90;
  const angleStep = (Math.PI * 2) / points.length;

  const toPoint = (magnitude: number, index: number, multiplier = 1): [number, number] => {
    const angle = -Math.PI / 2 + index * angleStep;
    const scaled = (radius * multiplier * magnitude) / 100;
    const x = center + Math.cos(angle) * scaled;
    const y = center + Math.sin(angle) * scaled;
    return [x, y];
  };

  const plot = points
    .map((point, index) => {
      const [x, y] = toPoint(point.value, index);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className={styles.radarSvg} role="img" aria-label="Role radar chart">
      {[20, 40, 60, 80, 100].map((level) => {
        const ring = points
          .map((_, index) => {
            const [x, y] = toPoint(level, index);
            return `${x},${y}`;
          })
          .join(" ");

        return <polygon key={level} points={ring} className={styles.radarRing} />;
      })}

      {points.map((point, index) => {
        const [x, y] = toPoint(100, index);
        return (
          <line
            key={point.label}
            x1={center}
            y1={center}
            x2={x}
            y2={y}
            className={styles.radarAxis}
          />
        );
      })}

      <polygon points={plot} className={styles.radarArea} />

      {points.map((point, index) => {
        const [x, y] = toPoint(111, index, 1);
        return (
          <text key={point.label} x={x} y={y} className={styles.radarText} textAnchor="middle">
            {point.label}
          </text>
        );
      })}
    </svg>
  );
}

export default function DashboardPage() {
  const params = useParams<{ game: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const gameParam = Array.isArray(params.game) ? params.game[0] : params.game;
  const game = isGameSlug(gameParam) ? gameParam : "league-of-legends";
  const config = GAME_CONFIG[game];
  const initialRiotId = searchParams.get("riotId")?.trim() || "18178178";

  const [riotIdInput, setRiotIdInput] = useState(initialRiotId);
  const [activeRiotId, setActiveRiotId] = useState(initialRiotId);
  const [roleFilter, setRoleFilter] = useState("All");
  const [matchWindow, setMatchWindow] = useState<MatchWindow>(10);
  const [resultFilter, setResultFilter] = useState<ResultFilter>("All");
  const [sortKey, setSortKey] = useState<SortKey>("matchId");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const dashboardData = useMemo(
    () => generateDashboardData(activeRiotId, game, matchWindow, roleFilter),
    [activeRiotId, game, matchWindow, roleFilter],
  );

  const filteredHistory = useMemo(() => {
    const resultFiltered =
      resultFilter === "All"
        ? dashboardData.matchHistory
        : dashboardData.matchHistory.filter((row) => row.result === resultFilter);

    return sortRows(resultFiltered, sortKey, sortDirection);
  }, [dashboardData.matchHistory, resultFilter, sortKey, sortDirection]);

  const onApplyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const cleanRiotId = riotIdInput.trim();
    if (!cleanRiotId) {
      return;
    }

    setActiveRiotId(cleanRiotId);
    const query = new URLSearchParams({ riotId: cleanRiotId });
    router.replace(`/dashboard/${game}?${query.toString()}`);
  };

  const onGameChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextGame = event.target.value as GameSlug;
    const cleanRiotId = riotIdInput.trim() || activeRiotId;
    const query = new URLSearchParams({ riotId: cleanRiotId });
    router.push(`/dashboard/${nextGame}?${query.toString()}`);
  };

  const onSort = (nextSortKey: SortKey) => {
    if (nextSortKey === sortKey) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection("desc");
  };

  if (!isGameSlug(gameParam)) {
    return (
      <main className={styles.invalidPage}>
        <h1>Unsupported game route</h1>
        <p>Use League of Legends or Valorant from the landing page.</p>
        <Link href="/">Back to Landing</Link>
      </main>
    );
  }

  return (
    <main className={`${styles.page} ${game === "valorant" ? styles.valorant : styles.league}`}>
      <div className={styles.overlayOne} aria-hidden="true" />
      <div className={styles.overlayTwo} aria-hidden="true" />

      <section className={styles.shell}>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Player Analytics Dashboard</p>
            <h1 className={styles.title}>{config.label}</h1>
            <p className={styles.subtitle}>
              Riot ID <strong>{activeRiotId}</strong> with metrics over the last {matchWindow} matches.
            </p>
          </div>
          <Link className={styles.landingLink} href="/">
            Change Player
          </Link>
        </header>

        <form className={styles.filters} onSubmit={onApplyFilters}>
          <label className={styles.filterField}>
            Riot ID
            <input
              value={riotIdInput}
              onChange={(event) => setRiotIdInput(event.target.value)}
              placeholder="Riot ID"
              required
            />
          </label>

          <label className={styles.filterField}>
            Game
            <select value={game} onChange={onGameChange}>
              <option value="league-of-legends">League of Legends</option>
              <option value="valorant">Valorant</option>
            </select>
          </label>

          <label className={styles.filterField}>
            Role Filter
            <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
              {config.roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.filterField}>
            Match Window
            <select
              value={matchWindow}
              onChange={(event) => setMatchWindow(Number(event.target.value) as MatchWindow)}
            >
              <option value={5}>Last 5</option>
              <option value={10}>Last 10</option>
              <option value={20}>Last 20</option>
            </select>
          </label>

          <button className={styles.applyButton} type="submit">
            Refresh
          </button>
        </form>

        <section className={styles.kpiGrid}>
          {dashboardData.metrics.map((metric, index) => (
            <article
              key={metric.label}
              className={styles.kpiCard}
              style={{ animationDelay: `${index * 45}ms` }}
            >
              <p>{metric.label}</p>
              <strong>{formatMetric(metric)}</strong>
              <span className={metric.trend >= 0 ? styles.trendUp : styles.trendDown}>
                {metric.trend >= 0 ? "+" : ""}
                {metric.trend.toFixed(1)}%
              </span>
            </article>
          ))}
        </section>

        <section className={styles.analyticsGrid}>
          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>Performance Trend Line</h2>
              <p>Match-by-match form trajectory</p>
            </div>
            <Sparkline values={dashboardData.trendSeries} color={config.trendColor} />
          </article>

          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>Rolling Average</h2>
              <p>3-match smoothing window</p>
            </div>
            <Sparkline values={dashboardData.rollingSeries} color="#06d6a0" />
          </article>

          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>Match-to-match Comparison</h2>
              <p>Positive and negative swing index</p>
            </div>
            <DeltaBars values={dashboardData.comparisonSeries} />
          </article>

          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>Role Performance Radar</h2>
              <p>Current role focus: {roleFilter}</p>
            </div>
            <Radar points={dashboardData.roleRadar} />
          </article>

          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>{config.characterLabel} Analytics</h2>
              <p>Win rate, pick rate, and overall impact</p>
            </div>
            <div className={styles.characterList}>
              {dashboardData.characterAnalytics.map((entry) => (
                <div key={entry.name} className={styles.characterRow}>
                  <div>
                    <strong>{entry.name}</strong>
                    <p>
                      {entry.winRate.toFixed(1)}% WR, {entry.pickRate.toFixed(1)}% PR
                    </p>
                  </div>
                  <div className={styles.performanceTrack}>
                    <span style={{ width: `${entry.performance}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>AI Insights & Recommendations</h2>
              <p>Auto-generated from current profile trends</p>
            </div>
            <ul className={styles.insightsList}>
              {dashboardData.insights.map((insight) => (
                <li key={insight}>{insight}</li>
              ))}
            </ul>
          </article>
        </section>

        <section className={styles.tableCard}>
          <div className={styles.tableHeader}>
            <div>
              <h2>Match History Table</h2>
              <p>Sortable and filterable recent match records</p>
            </div>

            <label className={styles.tableFilter}>
              Result
              <select
                value={resultFilter}
                onChange={(event) => setResultFilter(event.target.value as ResultFilter)}
              >
                <option value="All">All</option>
                <option value="Win">Win</option>
                <option value="Loss">Loss</option>
              </select>
            </label>
          </div>

          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>
                    <button onClick={() => onSort("matchId")} type="button">
                      Match ID
                    </button>
                  </th>
                  <th>
                    <button onClick={() => onSort("character")} type="button">
                      {config.characterLabel}
                    </button>
                  </th>
                  <th>
                    <button onClick={() => onSort("kda")} type="button">
                      KDA
                    </button>
                  </th>
                  <th>
                    <button onClick={() => onSort("secondaryStat")} type="button">
                      {config.secondaryStatLabel}
                    </button>
                  </th>
                  <th>
                    <button onClick={() => onSort("result")} type="button">
                      Result
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredHistory.map((row) => (
                  <tr key={row.matchId}>
                    <td>{row.matchId}</td>
                    <td>{row.character}</td>
                    <td>{row.kda.toFixed(2)}</td>
                    <td>
                      {row.secondaryStat.toFixed(game === "valorant" ? 0 : 1)}
                      {config.secondaryStatUnit}
                    </td>
                    <td>
                      <span className={row.result === "Win" ? styles.winTag : styles.lossTag}>
                        {row.result}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}
