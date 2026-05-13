"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import styles from "@/app/mvp.module.css";
import {
  PlayerTrends,
  TrendGamePoint,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

// ── helpers ────────────────────────────────────────────────────────────────

function pct(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}
function fmt(v: number | null | undefined, d = 2) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(d);
}
function trendArrow(slope: number) {
  if (slope > 0.01) return "▲";
  if (slope < -0.01) return "▼";
  return "→";
}
function trendColor(slope: number) {
  if (slope > 0.01) return "var(--color-win)";
  if (slope < -0.01) return "var(--color-loss)";
  return "#8899bb";
}
function streakLabel(streak: number) {
  if (streak > 0) return `W${streak}`;
  if (streak < 0) return `L${Math.abs(streak)}`;
  return "—";
}
function streakColor(streak: number) {
  if (streak > 0) return "var(--color-win)";
  if (streak < 0) return "var(--color-loss)";
  return "#8899bb";
}

// ── Recharts shared config ─────────────────────────────────────────────────

const CHART_COLORS = {
  kda:              "var(--racing-blue-400)",
  cs:               "var(--racing-blue-300)",
  kp:               "var(--signal-lime-400)",
  gold:             "var(--warning-500)",
  win:              "var(--color-win)",
  loss:             "var(--color-loss)",
  grid:             "rgba(255,255,255,0.06)",
  axis:             "rgba(255,255,255,0.35)",
  tooltip_bg:       "var(--carbon-900)",
  tooltip_border:   "var(--color-border)",
};

const CHART_STYLE = { fontSize: 11, fill: CHART_COLORS.axis };

function chartDate(ts: number) {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ── Custom tooltip ─────────────────────────────────────────────────────────

type ChartPayloadEntry = {
  color?: string;
  name?: string;
  value?: number | null;
};

type ChartTooltipProps = {
  active?: boolean;
  payload?: ChartPayloadEntry[];
  label?: string;
  formatter?: (value: number) => string;
};

type DotRenderProps = {
  cx?: number;
  cy?: number;
  payload?: {
    win?: boolean;
  };
};

type WinLossTooltipEntry = {
  payload: {
    win: boolean;
    date: string;
    champion: string | null;
    kda: number | null;
  };
};

function ChartTooltip({ active, payload, label, formatter }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: CHART_COLORS.tooltip_bg,
      border: `1px solid ${CHART_COLORS.tooltip_border}`,
      borderRadius: 8,
      padding: "8px 12px",
      fontSize: 12,
    }}>
      <p style={{ marginBottom: 4, opacity: 0.6, fontSize: 11 }}>{label}</p>
      {payload.map((entry, i) => {
        const value =
          typeof entry.value === "number"
            ? formatter
              ? formatter(entry.value)
              : entry.value.toFixed(2)
            : "—";

        return (
          <p key={i} style={{ color: entry.color, margin: "2px 0" }}>
            {entry.name}: <strong>{value}</strong>
          </p>
        );
      })}
    </div>
  );
}

// ── Metric area chart ──────────────────────────────────────────────────────

interface MetricChartProps {
  data: { game: number; value: number | null; win: boolean; date: string }[];
  color: string;
  label: string;
  formatter?: (v: number) => string;
  referenceY?: number;
  referenceLabel?: string;
  yDomain?: [number | "auto" | "dataMin" | "dataMax", number | "auto" | "dataMin" | "dataMax"];
}

function MetricChart({ data, color, label, formatter, referenceY, referenceLabel, yDomain }: MetricChartProps) {
  const valid = data.filter((d) => d.value !== null);
  if (valid.length < 2) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 160, opacity: 0.4, fontSize: 13 }}>
        Not enough data
      </div>
    );
  }

  return (
    <div>
      <p style={{ fontSize: 11, opacity: 0.55, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </p>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${label.replace(/\s/g, "")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
          <XAxis dataKey="date" tick={CHART_STYLE} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={CHART_STYLE} tickLine={false} axisLine={false} domain={yDomain ?? ["auto", "auto"]} width={40} />
          <Tooltip content={<ChartTooltip formatter={formatter} />} />
          {referenceY !== undefined && (
            <ReferenceLine y={referenceY} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4"
              label={{ value: referenceLabel ?? "", position: "insideTopRight", fontSize: 10, fill: "rgba(255,255,255,0.4)" }} />
          )}
          <Area
            type="monotone"
            dataKey="value"
            name={label}
            stroke={color}
            strokeWidth={2}
            fill={`url(#grad-${label.replace(/\s/g, "")})`}
            dot={(props: DotRenderProps) => {
              const { cx, cy, payload } = props;
              return (
                <circle
                  key={`dot-${cx}-${cy}`}
                  cx={cx} cy={cy} r={3.5}
                  fill={payload?.win ? CHART_COLORS.win : CHART_COLORS.loss}
                  stroke="#050b1d"
                  strokeWidth={1.5}
                />
              );
            }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Win/loss bar chart ─────────────────────────────────────────────────────

function WinLossChart({ series }: { series: TrendGamePoint[] }) {
  const data = series.map((g, i) => ({
    game: i + 1,
    date: chartDate(g.game_creation),
    result: g.win ? 1 : -1,
    win: g.win,
    kda: g.kda,
    champion: g.champion,
  }));

  return (
    <div>
      <p style={{ fontSize: 11, opacity: 0.55, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Win / Loss per game
      </p>
      <ResponsiveContainer width="100%" height={100}>
        <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
          <XAxis dataKey="date" tick={CHART_STYLE} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis hide domain={[-1.5, 1.5]} />
          <Tooltip
            content={({ active, payload }: { active?: boolean; payload?: readonly WinLossTooltipEntry[] }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload;
              return (
                <div style={{ background: CHART_COLORS.tooltip_bg, border: `1px solid ${CHART_COLORS.tooltip_border}`, borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
                  <p style={{ margin: 0, color: d.win ? CHART_COLORS.win : CHART_COLORS.loss }}>
                    <strong>{d.win ? "Win" : "Loss"}</strong> — {d.date}
                  </p>
                  {d.champion && <p style={{ margin: "2px 0", opacity: 0.7 }}>{d.champion}</p>}
                  {d.kda != null && <p style={{ margin: 0, opacity: 0.7 }}>KDA {d.kda.toFixed(2)}</p>}
                </div>
              );
            }}
          />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
          <Line
            type="step"
            dataKey="result"
            name="Result"
            stroke="transparent"
            dot={(props: DotRenderProps) => {
              const { cx, cy, payload } = props;
              return (
                <circle
                  key={`wl-${cx}-${cy}`}
                  cx={cx} cy={cy} r={5}
                  fill={payload?.win ? CHART_COLORS.win : CHART_COLORS.loss}
                  stroke="#050b1d"
                  strokeWidth={1.5}
                />
              );
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── KPI card ───────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <article className={styles.kpiCard}>
      <p className={styles.kpiLabel}>{label}</p>
      <strong className={styles.kpiValue} style={color ? { color } : undefined}>
        {value}
      </strong>
      {sub && <p style={{ fontSize: 11, opacity: 0.5, marginTop: 2 }}>{sub}</p>}
    </article>
  );
}

// ── Game history row ───────────────────────────────────────────────────────

function GameRow({ g }: { g: TrendGamePoint }) {
  const date = new Date(g.game_creation).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return (
    <tr>
      <td>
        <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: g.win ? "var(--color-win)" : "var(--color-loss)", marginRight: 6 }} />
        {g.win ? "Win" : "Loss"}
      </td>
      <td>{date}</td>
      <td>{g.champion ?? "—"}</td>
      <td>{g.role ?? "—"}</td>
      <td>{g.kills ?? "—"}/{g.deaths ?? "—"}/{g.assists ?? "—"}</td>
      <td>{fmt(g.kda)}</td>
      <td>{fmt(g.cs_per_min)}</td>
      <td>{pct(g.kill_participation)}</td>
    </tr>
  );
}

function GameMobileCard({ g }: { g: TrendGamePoint }) {
  const date = new Date(g.game_creation).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

  return (
    <article className={styles.dashboardMobileCard}>
      <div className={styles.dashboardMobileHeader}>
        <strong>{g.champion ?? "Unknown champion"}</strong>
        <span className={g.win ? styles.badgeWin : styles.badgeLoss}>
          {g.win ? "Win" : "Loss"}
        </span>
      </div>

      <div className={styles.dashboardMetricGrid}>
        <div>
          <span>Date</span>
          <strong>{date}</strong>
        </div>
        <div>
          <span>Role</span>
          <strong>{g.role ?? "—"}</strong>
        </div>
        <div>
          <span>K/D/A</span>
          <strong>{g.kills ?? "—"}/{g.deaths ?? "—"}/{g.assists ?? "—"}</strong>
        </div>
        <div>
          <span>KDA</span>
          <strong>{fmt(g.kda)}</strong>
        </div>
        <div>
          <span>CS/Min</span>
          <strong>{fmt(g.cs_per_min)}</strong>
        </div>
        <div>
          <span>Kill Part.</span>
          <strong>{pct(g.kill_participation)}</strong>
        </div>
      </div>
    </article>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function TrendsPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [trends, setTrends] = useState<PlayerTrends | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    frontendMvpClient
      .getPlayerTrends(puuid, 20)
      .then((data) => { if (mounted) setTrends(data); })
      .catch((err) => { if (mounted) setError(err instanceof Error ? err.message : "Failed to load trends."); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [puuid]);

  if (loading) return (
    <main className={styles.page}><div className={styles.container}>
      <p className={styles.loading}>Loading trends…</p>
    </div></main>
  );

  if (error) return (
    <main className={styles.page}><div className={styles.container}>
      <p className={styles.loading}>{error}</p>
      <Link className={styles.linkChip} href={`/player/${puuid}`}>← Back to Dashboard</Link>
    </div></main>
  );

  const rolling = trends?.rolling;
  const series  = trends?.series ?? [];

  // Build per-metric chart data (oldest → newest, already sorted by backend)
  const chartData = series.map((g, i) => ({
    game:  i + 1,
    date:  chartDate(g.game_creation),
    win:   g.win,
    kda:   g.kda,
    cs:    g.cs_per_min,
    kp:    g.kill_participation != null ? +(g.kill_participation * 100).toFixed(1) : null,
    gold:  g.gold_per_min,
  }));

  return (
    <main className={styles.page}>
      <div className={styles.container}>

        {/* ── Header ── */}
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Performance Trends</p>
          <div className={styles.heroTitleRow}>
            <h1 className={`${styles.title} ${styles.heroTitle}`}>
              {trends?.summoner_name ?? "Player"} — Last {trends?.games_in_window ?? 0} Games
            </h1>
            <Link className={`${styles.buttonPrimary} ${styles.heroAction}`} href={`/player/${puuid}`}>
              ← Dashboard
            </Link>
          </div>
          {!trends?.has_full_window && (
            <p style={{ opacity: 0.55, fontSize: 13, marginTop: 6 }}>
              Fewer than 20 ranked games — window may be partial.
            </p>
          )}
          {trends?.message && (
            <p style={{ color: "#f59e0b", fontSize: 13, marginTop: 6 }}>{trends.message}</p>
          )}
        </header>

        {rolling ? (
          <>
            {/* ── Rolling KPIs ── */}
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Rolling Window — Last {trends?.games_in_window} Games</h2>
                  <p className={styles.sectionCopy}>The exact feature vector fed into every ML model.</p>
                </div>
              </div>
              <div className={styles.kpiGrid}>
                <KpiCard label="Win Rate"      value={pct(rolling.win_rate_20)} />
                <KpiCard label="Avg KDA"       value={fmt(rolling.avg_kda_20)} />
                <KpiCard label="Avg CS/Min"    value={fmt(rolling.avg_cs_per_min_20)} />
                <KpiCard label="Kill Part."    value={pct(rolling.avg_kill_part_20)} />
                <KpiCard label="Gold/Min"      value={fmt(rolling.avg_gold_per_min_20, 0)} />
                <KpiCard label="Vision/Min"    value={fmt(rolling.vision_per_min_20)} />
                <KpiCard label="Win Streak"    value={streakLabel(rolling.win_streak)}    color={streakColor(rolling.win_streak)} />
                <KpiCard label="CS Trend (10g)" value={`${trendArrow(rolling.cs_trend_10)} ${fmt(rolling.cs_trend_10, 4)}`} sub="slope of cs/min" color={trendColor(rolling.cs_trend_10)} />
                <KpiCard label="KDA Volatility" value={fmt(rolling.kda_std_10)} sub="std dev last 10" />
                <KpiCard label="Death Rate"    value={fmt(rolling.death_rate_20)} sub="avg deaths/game" />
              </div>
            </section>

            {/* ── Charts ── */}
            {series.length >= 2 && (
              <section className={styles.section}>
                <div className={styles.sectionHeader}>
                  <div>
                    <h2 className={styles.sectionTitle}>Trend Charts</h2>
                    <p className={styles.sectionCopy}>
                      Hover for exact values. Dots: <span style={{ color: CHART_COLORS.win }}>●</span> win &nbsp;
                      <span style={{ color: CHART_COLORS.loss }}>●</span> loss.
                    </p>
                  </div>
                </div>

                {/* Win/loss timeline */}
                <div className={styles.dataCard} style={{ marginBottom: 16 }}>
                  <WinLossChart series={series} />
                </div>

                {/* 2-column metric charts */}
                <div className={styles.twoCol}>
                  <div className={styles.dataCard}>
                    <MetricChart
                      data={chartData.map((d) => ({ ...d, value: d.kda }))}
                      color={CHART_COLORS.kda}
                      label="KDA per game"
                      referenceY={rolling.avg_kda_20 ?? undefined}
                      referenceLabel="avg"
                    />
                  </div>
                  <div className={styles.dataCard}>
                    <MetricChart
                      data={chartData.map((d) => ({ ...d, value: d.cs }))}
                      color={CHART_COLORS.cs}
                      label="CS/min per game"
                      referenceY={rolling.avg_cs_per_min_20 ?? undefined}
                      referenceLabel="avg"
                    />
                  </div>
                </div>

                <div className={styles.twoCol} style={{ marginTop: 16 }}>
                  <div className={styles.dataCard}>
                    <MetricChart
                      data={chartData.map((d) => ({ ...d, value: d.kp }))}
                      color={CHART_COLORS.kp}
                      label="Kill participation % per game"
                      formatter={(v) => `${v.toFixed(1)}%`}
                      yDomain={[0, 100]}
                      referenceY={rolling.avg_kill_part_20 != null ? +(rolling.avg_kill_part_20 * 100).toFixed(1) : undefined}
                      referenceLabel="avg"
                    />
                  </div>
                  <div className={styles.dataCard}>
                    <MetricChart
                      data={chartData.map((d) => ({ ...d, value: d.gold }))}
                      color={CHART_COLORS.gold}
                      label="Gold/min per game"
                      formatter={(v) => v.toFixed(0)}
                      referenceY={rolling.avg_gold_per_min_20 ?? undefined}
                      referenceLabel="avg"
                    />
                  </div>
                </div>
              </section>
            )}
          </>
        ) : (
          <section className={styles.section}>
            <p style={{ opacity: 0.5, fontStyle: "italic" }}>
              {trends?.message ?? "No ranked data found. Ingest at least 5 ranked games to see trends."}
            </p>
          </section>
        )}

        {/* ── Game-by-game table ── */}
        {series.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>Game Log (oldest → newest)</h2>
                <p className={styles.sectionCopy}>Last {series.length} ranked solo/duo games.</p>
              </div>
            </div>
            <div className={`${styles.tableWrap} ${styles.dashboardDesktopOnly}`}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Result</th>
                    <th>Date</th>
                    <th>Champion</th>
                    <th>Role</th>
                    <th>K/D/A</th>
                    <th>KDA</th>
                    <th>CS/Min</th>
                    <th>Kill Part.</th>
                  </tr>
                </thead>
                <tbody>
                  {series.map((g, i) => <GameRow key={i} g={g} />)}
                </tbody>
              </table>
            </div>

            <div className={styles.dashboardMobileList}>
              {series.map((g, i) => (
                <GameMobileCard key={i} g={g} />
              ))}
            </div>
          </section>
        )}

      </div>
    </main>
  );
}
