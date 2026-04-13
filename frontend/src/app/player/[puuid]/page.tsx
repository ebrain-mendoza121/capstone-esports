"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import {
  ChampionRecommendation,
  PlayerDetail,
  PlayerMetrics,
  PlayerRolePerformance,
  PlaystyleResult,
  RuneEntry,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function delta(value: number) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function playstyleBadgeStyle(label: string): string {
  if (label === "insufficient_data" || label === "unknown") return styles.badge;
  return styles.badgeWin;
}

export default function PlayerDashboardPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [player, setPlayer] = useState<PlayerDetail | null>(null);
  const [metrics, setMetrics] = useState<PlayerMetrics | null>(null);
  const [recentRunes, setRecentRunes] = useState<RuneEntry[]>([]);
  const [rolePerf, setRolePerf] = useState<PlayerRolePerformance | null>(null);
  const [playstyle, setPlaystyle] = useState<PlaystyleResult | null | "loading">("loading");
  const [champRecs, setChampRecs] = useState<ChampionRecommendation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      try {
        const [playerData, metricData, runeData, roleData, playstyleData, champData] =
          await Promise.all([
            frontendMvpClient.getPlayer(puuid),
            frontendMvpClient.getPlayerMetrics(puuid),
            frontendMvpClient.getPlayerRunes(puuid, 5),
            frontendMvpClient.getPlayerRolePerformance(puuid),
            frontendMvpClient.getPlayerPlaystyle(puuid),
            frontendMvpClient.getChampionRecommendations(puuid, 8),
          ]);

        if (!mounted) return;

        setPlayer(playerData);
        setMetrics(metricData);
        setRecentRunes(runeData);
        setRolePerf(roleData);
        setPlaystyle(playstyleData);
        setChampRecs(champData);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load player data.");
      }
    };

    void loadData();
    return () => { mounted = false; };
  }, [puuid]);

  const createdAtLabel = useMemo(() => {
    if (!player) return "—";
    return new Date(player.created_at).toLocaleDateString();
  }, [player]);

  if (error) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <p className={styles.loading}>{error}</p>
          <Link className={styles.linkChip} href="/individual-stats">← Back</Link>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Player Dashboard</p>
          <div className={styles.heroTitleRow}>
            <h1 className={`${styles.title} ${styles.heroTitle}`}>
              {player ? `${player.riot_id}#${player.tag_line}` : "Loading…"}
            </h1>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Link className={styles.linkChip} href={`/player/${puuid}/trends`}>
                📈 Performance Trends
              </Link>
              <Link className={`${styles.buttonPrimary} ${styles.heroAction}`} href="/individual-stats">
                Back to Individual Stats
              </Link>
            </div>
          </div>
        </header>

        {/* ── Identity ── */}
        {player && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>Player Identity</h2>
                <p className={styles.sectionCopy}>Registered account snapshot</p>
              </div>
            </div>
            <div className={styles.inlineList}>
              <span className={styles.badgeNeutral}>{player.riot_id}#{player.tag_line}</span>
              <span className={styles.badge}>Region: {player.region}</span>
              <span className={styles.badge}>Created: {createdAtLabel}</span>
            </div>
          </section>
        )}

        {/* ── Core Stats KPI grid ── */}
        {metrics ? (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>Core Stats</h2>
                <p className={styles.sectionCopy}>Averages across all ingested ranked matches</p>
              </div>
            </div>
            <div className={styles.kpiGrid}>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Matches</p>
                <strong className={styles.kpiValue}>{metrics.matches_played}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Win Rate</p>
                <strong className={styles.kpiValue}>{pct(metrics.win_rate)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>KDA</p>
                <strong className={styles.kpiValue}>{metrics.avg_kda.toFixed(2)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>CS / Min</p>
                <strong className={styles.kpiValue}>{metrics.avg_cs_per_min.toFixed(2)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Gold / Min</p>
                <strong className={styles.kpiValue}>{metrics.avg_gold_per_min.toFixed(0)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Vision / Min</p>
                <strong className={styles.kpiValue}>{metrics.avg_vision_per_min.toFixed(2)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Kill Participation</p>
                <strong className={styles.kpiValue}>{pct(metrics.kill_participation)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Damage Share</p>
                <strong className={styles.kpiValue}>{pct(metrics.damage_share)}</strong>
              </article>
            </div>
          </section>
        ) : (
          <p className={styles.loading}>Loading core stats…</p>
        )}

        {/* ── Role Performance ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Role Performance</h2>
              <p className={styles.sectionCopy}>
                Per-role breakdown with percentile rank vs all tracked players
                {rolePerf?.primary_role ? ` · Primary role: ${rolePerf.primary_role}` : ""}
              </p>
            </div>
          </div>

          {!rolePerf ? (
            <p className={styles.loading}>Loading role data…</p>
          ) : rolePerf.roles.length === 0 ? (
            <p className={styles.emptyState}>No role data yet — run backfill/derived first.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Games</th>
                    <th>Win Rate</th>
                    <th>vs Peers</th>
                    <th>KDA</th>
                    <th>KDA Δ</th>
                    <th>CS/Min</th>
                    <th>CS Δ</th>
                    <th>Kill Part.</th>
                    <th>Vision</th>
                  </tr>
                </thead>
                <tbody>
                  {rolePerf.roles.map((row) => (
                    <tr key={row.role}>
                      <td><strong>{row.role}</strong></td>
                      <td>{row.games_played}</td>
                      <td>{pct(row.win_rate)}</td>
                      <td>
                        <span className={
                          row.vs_peers.win_rate_vs_peers.startsWith("top")
                            ? styles.badgeWin
                            : styles.badgeLoss
                        }>
                          {row.vs_peers.win_rate_vs_peers}
                        </span>
                      </td>
                      <td>{row.avg_kda.toFixed(2)}</td>
                      <td style={{ color: row.vs_peers.kda_delta >= 0 ? "var(--color-win, #22c55e)" : "var(--color-loss, #ef4444)" }}>
                        {delta(row.vs_peers.kda_delta)}
                      </td>
                      <td>{row.avg_cs_per_min.toFixed(2)}</td>
                      <td style={{ color: row.vs_peers.cs_delta >= 0 ? "var(--color-win, #22c55e)" : "var(--color-loss, #ef4444)" }}>
                        {delta(row.vs_peers.cs_delta)}
                      </td>
                      <td>{pct(row.avg_kill_part)}</td>
                      <td>{row.avg_vision.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Playstyle ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Playstyle Profile</h2>
              <p className={styles.sectionCopy}>KMeans cluster assigned by the playstyle model</p>
            </div>
          </div>

          {playstyle === "loading" ? (
            <p className={styles.loading}>Loading playstyle…</p>
          ) : playstyle === null ? (
            <p className={styles.emptyState}>
              Playstyle model not trained yet — run{" "}
              <code>POST /ai/train/playstyle</code> to enable this section.
            </p>
          ) : !playstyle.meets_min_sample ? (
            <p className={styles.emptyState}>
              Not enough data — needs 10+ ranked matches. Currently {playstyle.games_played} games.
            </p>
          ) : (
            <div className={styles.inlineList}>
              <span className={playstyleBadgeStyle(playstyle.playstyle_label)}>
                {playstyle.playstyle_label.replace(/_/g, " ")}
              </span>
              <span className={styles.badge}>Cluster #{playstyle.cluster_id}</span>
              <span className={styles.badge}>{playstyle.games_played} games analyzed</span>
              {playstyle.feature_snapshot && Object.entries(playstyle.feature_snapshot).slice(0, 4).map(([k, v]) => (
                <span key={k} className={styles.badge}>
                  {k.replace(/_/g, " ")}: {typeof v === "number" ? v.toFixed(2) : v}
                </span>
              ))}
            </div>
          )}
        </section>

        {/* ── Champion Recommendations ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Champion Recommendations</h2>
              <p className={styles.sectionCopy}>
                Ranked by Bayesian win rate, KDA, CS efficiency, experience, and recency
              </p>
            </div>
          </div>

          {champRecs.length === 0 ? (
            <p className={styles.emptyState}>
              No champion data yet — ingest more matches to populate recommendations.
            </p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Champion</th>
                    <th>Role</th>
                    <th>Score</th>
                    <th>Win Rate</th>
                    <th>Smoothed WR</th>
                    <th>Games</th>
                    <th>Playstyle Fit</th>
                  </tr>
                </thead>
                <tbody>
                  {champRecs.map((rec, idx) => (
                    <tr key={`${rec.champion_name}-${rec.role ?? idx}`}>
                      <td><strong>{rec.champion_name}</strong></td>
                      <td>{rec.role ?? "—"}</td>
                      <td>{(rec.score * 100).toFixed(1)}</td>
                      <td>{pct(rec.win_rate)}</td>
                      <td>{pct(rec.smoothed_win_rate)}</td>
                      <td>{rec.games_played}</td>
                      <td>
                        {rec.playstyle_match
                          ? <span className={styles.badgeWin}>✓ Match</span>
                          : <span className={styles.badge}>—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Recent Runes ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Recent Runes</h2>
              <p className={styles.sectionCopy}>Last 5 games</p>
            </div>
            <Link className={styles.linkChip} href={`/player/${puuid}/runes`}>
              Full Rune History →
            </Link>
          </div>
          {recentRunes.length === 0 ? (
            <p className={styles.emptyState}>No rune data yet — run backfill/participant-perks.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Champion</th>
                    <th>Keystone</th>
                    <th>Primary Path</th>
                    <th>Sub Path</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRunes.map((entry) => (
                    <tr key={entry.match_id}>
                      <td>{entry.champion}</td>
                      <td>{entry.keystone_name}</td>
                      <td>{entry.primary_style_name}</td>
                      <td>{entry.sub_style_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Quick Links ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>More</h2>
            </div>
          </div>
          <nav className={styles.linkRail}>
            <Link className={styles.linkChip} href={`/player/${puuid}/matches`}>
              Match History
            </Link>
            <Link className={styles.linkChip} href={`/player/${puuid}/bans`}>
              Ban Analytics
            </Link>
            <Link className={styles.linkChip} href={`/player/${puuid}/runes`}>
              Full Rune History
            </Link>
          </nav>
        </section>
      </div>
    </main>
  );
}
