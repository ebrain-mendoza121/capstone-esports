"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import {
  GlobalBanEntry,
  PlayerBanAnalytics,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

function maxCount(entries: Array<{ count: number }> | Array<{ ban_count: number }>): number {
  if (entries.length === 0) {
    return 1;
  }

  const values = entries.map((entry) => ("count" in entry ? entry.count : entry.ban_count));
  return Math.max(...values, 1);
}

function aggregateCountEntries(
  entries: Array<{ champion_id: number; champion_name: string; count: number }>,
): Array<{ champion_id: number; champion_name: string; count: number }> {
  const byChampion = new Map<string, { champion_id: number; champion_name: string; count: number }>();

  for (const entry of entries) {
    const existing = byChampion.get(entry.champion_name);
    if (!existing) {
      byChampion.set(entry.champion_name, { ...entry });
      continue;
    }

    existing.count += entry.count;
  }

  return Array.from(byChampion.values()).sort((left, right) => right.count - left.count);
}

function aggregateGlobalEntries(
  entries: GlobalBanEntry[],
): Array<{ champion_id: number; champion_name: string; ban_count: number }> {
  const byChampion = new Map<string, { champion_id: number; champion_name: string; ban_count: number }>();

  for (const entry of entries) {
    const existing = byChampion.get(entry.champion_name);
    if (!existing) {
      byChampion.set(entry.champion_name, { ...entry });
      continue;
    }

    existing.ban_count += entry.ban_count;
  }

  return Array.from(byChampion.values()).sort((left, right) => right.ban_count - left.ban_count);
}

export default function BanAnalyticsPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [playerBans, setPlayerBans] = useState<PlayerBanAnalytics | null>(null);
  const [globalBans, setGlobalBans] = useState<GlobalBanEntry[]>([]);
  const [globalBanRates, setGlobalBanRates] = useState<Record<string, number>>({});

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      const [playerResponse, globalResponse] = await Promise.all([
        frontendMvpClient.getPlayerBanAnalytics(puuid, 100),
        frontendMvpClient.getGlobalMostBanned(20),
      ]);

      const dedupedPlayerBans: PlayerBanAnalytics = {
        ...playerResponse,
        banned_against: aggregateCountEntries(playerResponse.banned_against).slice(0, 10),
        banned_by_team: aggregateCountEntries(playerResponse.banned_by_team).slice(0, 10),
      };

      const dedupedGlobalBans = aggregateGlobalEntries(globalResponse).slice(0, 20);
      const banRatePairs = await Promise.all(
        dedupedGlobalBans.map(async (entry) => {
          const details = await frontendMvpClient.getChampionBanRate(entry.champion_id);
          return [entry.champion_name, details.ban_rate] as const;
        }),
      );

      if (!mounted) {
        return;
      }

      setPlayerBans(dedupedPlayerBans);
      setGlobalBans(dedupedGlobalBans);
      setGlobalBanRates(Object.fromEntries(banRatePairs));
    };

    void loadData();

    return () => {
      mounted = false;
    };
  }, [puuid]);

  const againstMax = maxCount(playerBans?.banned_against ?? []);
  const byTeamMax = maxCount(playerBans?.banned_by_team ?? []);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 5</p>
          <h1 className={styles.title}>Ban Analytics</h1>
        </header>

        {!playerBans ? (
          <p className={styles.loading}>Loading ban analytics...</p>
        ) : (
          <>
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Player Ban Context</h2>
                  <p className={styles.sectionCopy}>Matches analyzed: {playerBans.matches_analyzed}</p>
                </div>
                <Link className={styles.linkChip} href={`/player/${puuid}`}>
                  Back to Dashboard
                </Link>
              </div>

              <div className={styles.twoCol}>
                <article className={styles.dataCard}>
                  <h3>Most banned against this player</h3>
                  <div className={styles.chartStack}>
                    {playerBans.banned_against.map((entry) => (
                      <div className={styles.barRow} key={`against-${entry.champion_name}`}>
                        <span className={styles.barLabel}>{entry.champion_name}</span>
                        <span className={styles.barTrack}>
                          <span
                            className={styles.barFill}
                            style={{ width: `${(entry.count / againstMax) * 100}%` }}
                          />
                        </span>
                        <span className={styles.small}>{entry.count}</span>
                      </div>
                    ))}
                  </div>
                </article>

                <article className={styles.dataCard}>
                  <h3>Most banned by this player team</h3>
                  <div className={styles.chartStack}>
                    {playerBans.banned_by_team.map((entry) => (
                      <div className={styles.barRow} key={`byteam-${entry.champion_name}`}>
                        <span className={styles.barLabel}>{entry.champion_name}</span>
                        <span className={styles.barTrack}>
                          <span
                            className={styles.barFill}
                            style={{ width: `${(entry.count / byTeamMax) * 100}%` }}
                          />
                        </span>
                        <span className={styles.small}>{entry.count}</span>
                      </div>
                    ))}
                  </div>
                </article>
              </div>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 className={styles.sectionTitle}>Global Ban Leaderboard</h2>
                  <p className={styles.sectionCopy}>Top champions by total bans across all sampled matches.</p>
                </div>
              </div>

              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Champion</th>
                      <th>Ban Count</th>
                      <th>Ban Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {globalBans.map((entry) => (
                      <tr key={entry.champion_name}>
                        <td>{entry.champion_name}</td>
                        <td>{entry.ban_count}</td>
                        <td>
                          {globalBanRates[entry.champion_name] !== undefined
                            ? `${globalBanRates[entry.champion_name]}%`
                            : "..."}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
