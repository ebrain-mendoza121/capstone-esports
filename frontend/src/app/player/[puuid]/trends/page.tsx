"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
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
  if (slope > 0.01) return "var(--color-win, #22c55e)";
  if (slope < -0.01) return "var(--color-loss, #ef4444)";
  return "#8899bb";
}
function streakLabel(streak: number) {
  if (streak > 0) return `W${streak}`;
  if (streak < 0) return `L${Math.abs(streak)}`;
  return "—";
}
function streakColor(streak: number) {
  if (streak > 0) return "var(--color-win, #22c55e)";
  if (streak < 0) return "var(--color-loss, #ef4444)";
  return "#8899bb";
}

// ── SVG sparkline ──────────────────────────────────────────────────────────

interface SparklineProps {
  data: (number | null)[];
  wins: boolean[];
  width?: number;
  height?: number;
  label?: string;
}

function Sparkline({ data, wins, width = 520, height = 90, label }: SparklineProps) {
  const valid = data.map((v, i) => ({ v, i, win: wins[i] })).filter((d) => d.v !== null);
  if (valid.length < 2) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height, opacity: 0.4, fontSize: 13 }}>
        Not enough data to render chart
      </div>
    );
  }

  const values = valid.map((d) => d.v as number);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;

  const padX = 8;
  const padY = 8;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const points = valid.map((d, idx) => {
    const x = padX + (idx / (valid.length - 1)) * innerW;
    const y = padY + (1 - ((d.v as number) - minV) / range) * innerH;
    return { x, y, win: d.win, v: d.v as number };
  });

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <div>
      {label && <p style={{ fontSize: 11, opacity: 0.55, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>}
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height, display: "block" }}>
        {/* baseline */}
        <line x1={padX} y1={padY + innerH} x2={padX + innerW} y2={padY + innerH}
          stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
        {/* area fill */}
        <path
          d={`${pathD} L${points[points.length - 1].x.toFixed(1)},${padY + innerH} L${points[0].x.toFixed(1)},${padY + innerH} Z`}
          fill="url(#sparkGrad)"
          opacity={0.3}
        />
        <defs>
          <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1fadff" stopOpacity={0.6} />
            <stop offset="100%" stopColor="#1fadff" stopOpacity={0} />
          </linearGradient>
        </defs>
        {/* line */}
        <path d={pathD} fill="none" stroke="#1fadff" strokeWidth={2} strokeLinejoin="round" />
        {/* dots — colored by win/loss */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={4}
            fill={p.win ? "#22c55e" : "#ef4444"}
            stroke="#050b1d"
            strokeWidth={1.5}
          />
        ))}
      </svg>
    </div>
  );
}

// ── KPI card ───────────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
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
  const date = new Date(g.game_creation).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
  return (
    <tr>
      <td>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: g.win ? "var(--color-win, #22c55e)" : "var(--color-loss, #ef4444)",
            marginRight: 6,
          }}
        />
        {g.win ? "Win" : "Loss"}
      </td>
      <td>{date}</td>
      <td>{g.champion ?? "—"}</td>
      <td>{g.role ?? "—"}</td>
      <td>
        {g.kills ?? "—"}/{g.deaths ?? "—"}/{g.assists ?? "—"}
      </td>
      <td>{fmt(g.kda)}</td>
      <td>{fmt(g.cs_per_min)}</td>
      <td>{pct(g.kill_participation)}</td>
    </tr>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function TrendsPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [trends, setTrends] = useState<PlayerTrends | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    frontendMvpClient
      .getPlayerTrends(puuid, 20)
      .then((data) => {
        if (mounted) setTrends(data);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load trends.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [puuid]);

  if (loading) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <p className={styles.loading}>Loading trends…</p>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <p className={styles.loading}>{error}</p>
          <Link className={styles.linkChip} href={`/player/${puuid}`}>← Back to Dashboard</Link>
        </div>
      </main>
    );
  }

  const rolling = trends?.rolling;
  const series = trends?.series ?? [];
  const wins = series.map((g) => g.win);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        {/* header */}
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
                  <p className={styles.sectionCopy}>
                    The exact feature vector fed into every ML model (temporal leakage guard applied).
                  </p>
                </div>
              </div>
              <div className={styles.kpiGrid}>
                <KpiCard label="Win Rate" value={pct(rolling.win_rate_20)} />
                <KpiCard label="Avg KDA" value={fmt(rolling.avg_kda_20)} />
                <KpiCard label="Avg CS/Min" value={fmt(rolling.avg_cs_per_min_20)} />
                <KpiCard label="Kill Part." value={pct(rolling.avg_kill_part_20)} />
                <KpiCard label="Gold/Min" value={fmt(rolling.avg_gold_per_min_20, 0)} />
                <KpiCard label="Vision/Min" value={fmt(rolling.vision_per_min_20)} />
                <KpiCard
                  label="Win Streak"
                  value={streakLabel(rolling.win_streak)}
                  color={streakColor(rolling.win_streak)}
                />
                <KpiCard
                  label="CS Trend (10g)"
                  value={`${trendArrow(rolling.cs_trend_10)} ${fmt(rolling.cs_trend_10, 4)}`}
                  sub="slope of cs/min"
                  color={trendColor(rolling.cs_trend_10)}
                />
                <KpiCard
                  label="KDA Volatility"
                  value={fmt(rolling.kda_std_10)}
                  sub="std dev last 10"
                />
                <KpiCard
                  label="Death Rate"
                  value={fmt(rolling.death_rate_20)}
                  sub="avg deaths/game"
                />
              </div>
            </section>

            {/* ── Sparkline charts ── */}
            {series.length >= 2 && (
              <section className={styles.section}>
                <div className={styles.sectionHeader}>
                  <div>
                    <h2 className={styles.sectionTitle}>Trend Charts</h2>
                    <p className={styles.sectionCopy}>
                      Dots colored green (win) / red (loss). Older games on left.
                    </p>
                  </div>
                </div>

                <div className={styles.twoCol}>
                  <div className={styles.dataCard}>
                    <Sparkline
                      data={series.map((g) => g.kda)}
                      wins={wins}
                      label="KDA per game"
                    />
                  </div>
                  <div className={styles.dataCard}>
                    <Sparkline
                      data={series.map((g) => g.cs_per_min)}
                      wins={wins}
                      label="CS/min per game"
                    />
                  </div>
                </div>

                <div className={styles.twoCol} style={{ marginTop: 16 }}>
                  <div className={styles.dataCard}>
                    <Sparkline
                      data={series.map((g) => g.kill_participation)}
                      wins={wins}
                      label="Kill participation per game"
                    />
                  </div>
                  <div className={styles.dataCard}>
                    <Sparkline
                      data={series.map((g) => g.gold_per_min)}
                      wins={wins}
                      label="Gold/min per game"
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
            <div className={styles.tableWrap}>
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
                  {series.map((g, i) => (
                    <GameRow key={i} g={g} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
