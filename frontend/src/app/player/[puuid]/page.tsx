"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import { PlayerDetail, PlayerMetrics, RuneEntry, frontendMvpClient } from "@/lib/frontendMvpClient";

export default function PlayerDashboardPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [player, setPlayer] = useState<PlayerDetail | null>(null);
  const [metrics, setMetrics] = useState<PlayerMetrics | null>(null);
  const [recentRunes, setRecentRunes] = useState<RuneEntry[]>([]);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      const [playerData, metricData, runeData] = await Promise.all([
        frontendMvpClient.getPlayer(puuid),
        frontendMvpClient.getPlayerMetrics(puuid),
        frontendMvpClient.getPlayerRunes(puuid, 5),
      ]);

      if (!mounted) {
        return;
      }

      setPlayer(playerData);
      setMetrics(metricData);
      setRecentRunes(runeData);
    };

    void loadData();

    return () => {
      mounted = false;
    };
  }, [puuid]);

  const createdAtLabel = useMemo(() => {
    if (!player) {
      return "—";
    }

    return new Date(player.created_at).toLocaleDateString();
  }, [player]);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 2</p>
          <div className={styles.heroTitleRow}>
            <h1 className={`${styles.title} ${styles.heroTitle}`}>Player Dashboard</h1>
            <Link className={`${styles.buttonPrimary} ${styles.heroAction}`} href="/individual-stats">
              Back to Individual Stats
            </Link>
          </div>
        </header>

        {!player || !metrics ? (
          <p className={styles.loading}>Loading player identity and core stats...</p>
        ) : (
          <>
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

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Core Stats</h2>
                  <p className={styles.sectionCopy}>Recent match performance averages</p>
                </div>
              </div>
              <div className={styles.kpiGrid}>
                <article className={styles.kpiCard}>
                  <p className={styles.kpiLabel}>Matches</p>
                  <strong className={styles.kpiValue}>{metrics.matches_played}</strong>
                </article>
                <article className={styles.kpiCard}>
                  <p className={styles.kpiLabel}>Win Rate</p>
                  <strong className={styles.kpiValue}>{metrics.win_rate*100}%</strong>
                </article>
                <article className={styles.kpiCard}>
                  <p className={styles.kpiLabel}>KDA</p>
                  <strong className={styles.kpiValue}>{metrics.avg_kda}</strong>
                </article>
                <article className={styles.kpiCard}>
                  <p className={styles.kpiLabel}>CS / Min</p>
                  <strong className={styles.kpiValue}>{metrics.avg_cs_per_min}</strong>
                </article>
                <article className={styles.kpiCard}>
                  <p className={styles.kpiLabel}>Gold / Min</p>
                  <strong className={styles.kpiValue}>{metrics.avg_gold_per_min}</strong>
                </article>
                <article className={styles.kpiCard}>
                  <p className={styles.kpiLabel}>Vision / Min</p>
                  <strong className={styles.kpiValue}>{metrics.avg_vision_per_min}</strong>
                </article>
              </div>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Recent Runes (last 5)</h2>
                  <p className={styles.sectionCopy}>Latest rune setups from recent games</p>
                </div>
              </div>
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
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Quick Links</h2>
                  <p className={styles.sectionCopy}>Navigation hierarchy from guide</p>
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
                  Rune History
                </Link>
              </nav>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>AI Placeholder · Phase 2</h2>
                  <p className={styles.sectionCopy}>Reserved cards only — no fetch wiring yet</p>
                </div>
              </div>
              <div className={styles.placeholderGrid}>
                <article className={styles.placeholderCard}>Playstyle Model<br />Coming in Phase 2</article>
                <article className={styles.placeholderCard}>Win Prediction<br />Coming in Phase 2</article>
                <article className={styles.placeholderCard}>Champion Picks<br />Coming in Phase 2</article>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
