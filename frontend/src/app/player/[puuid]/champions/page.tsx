"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import {
  ChampionStat,
  PlayerChampionStats,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";
import { buildApiUrl } from "@/lib/apiBaseUrl";

const ROLES = ["ALL", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] as const;
type RoleFilter = (typeof ROLES)[number];

function winRateCellStyle(winRate: number | null): React.CSSProperties {
  if (winRate === null) return {};
  if (winRate > 0.55)
    return {
      background: "rgba(184, 255, 69, 0.16)",
      color: "#efffc7",
      borderRadius: 6,
      padding: "2px 8px",
      display: "inline-block",
    };
  if (winRate < 0.45)
    return {
      background: "rgba(255, 95, 111, 0.2)",
      color: "#ffd9de",
      borderRadius: 6,
      padding: "2px 8px",
      display: "inline-block",
    };
  return {
    background: "rgba(255, 255, 255, 0.1)",
    color: "#f2f4ff",
    borderRadius: 6,
    padding: "2px 8px",
    display: "inline-block",
  };
}

function fmt(val: number | null, decimals: number): string {
  return val !== null ? val.toFixed(decimals) : "—";
}

export default function ChampionStatsPage() {
  const params = useParams<{ puuid: string }>();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [data, setData] = useState<PlayerChampionStats | null>(null);
  const [roleMap, setRoleMap] = useState<Record<number, string[]>>({});
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      try {
        const [statsData, champsRes] = await Promise.all([
          frontendMvpClient.getPlayerChampionStats(puuid, 1),
          fetch(buildApiUrl("/champions")),
        ]);

        const champsJson = champsRes.ok
          ? ((await champsRes.json()) as { champions: Array<{ id: number; role_affinity: string[] }> })
          : { champions: [] };

        if (!mounted) return;

        setData(statsData);

        const map: Record<number, string[]> = {};
        for (const c of champsJson.champions) {
          map[c.id] = c.role_affinity ?? [];
        }
        setRoleMap(map);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load champion stats.");
      }
    };

    void loadData();
    return () => {
      mounted = false;
    };
  }, [puuid]);

  const filtered: ChampionStat[] = data
    ? roleFilter === "ALL"
      ? data.champions
      : data.champions.filter((c) => (roleMap[c.champion_id] ?? []).includes(roleFilter))
    : [];

  if (error) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <p className={styles.loading}>{error}</p>
          <Link className={styles.linkChip} href={`/player/${puuid}`}>
            ← Dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Player Analytics</p>
          <div className={styles.heroTitleRow}>
            <h1 className={`${styles.title} ${styles.heroTitle}`}>Champion Stats</h1>
            <Link className={styles.linkChip} href={`/player/${puuid}`}>
              ← Dashboard
            </Link>
          </div>
        </header>

        {!data ? (
          <p className={styles.loading}>Loading champion stats…</p>
        ) : (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>Champion Pool</h2>
                <p className={styles.sectionCopy}>
                  {data.champions_found} champion{data.champions_found !== 1 ? "s" : ""} · Ranked
                  Solo/Duo (Queue 420) · min 1 game
                </p>
              </div>
            </div>

            {/* Role filter */}
            <div className={styles.inlineList} style={{ marginBottom: 16 }}>
              {ROLES.map((role) => (
                <button
                  key={role}
                  className={roleFilter === role ? styles.linkChip : styles.buttonGhost}
                  style={{ fontSize: "0.78rem", padding: "6px 14px" }}
                  onClick={() => setRoleFilter(role)}
                >
                  {role}
                </button>
              ))}
            </div>

            <div className={`${styles.tableWrap} ${styles.dashboardDesktopOnly}`}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Champion</th>
                    <th>Games</th>
                    <th>Win Rate</th>
                    <th>KDA</th>
                    <th>CS / Min</th>
                    <th>Gold / Min</th>
                    <th>K / D / A</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", opacity: 0.5, padding: 24 }}>
                        {data.champions_found === 0
                          ? "No ranked games found for this player."
                          : "No champions match the selected role."}
                      </td>
                    </tr>
                  ) : (
                    filtered.map((champ) => (
                      <tr key={champ.champion_id}>
                        <td style={{ fontWeight: 600 }}>{champ.champion_name}</td>
                        <td>{champ.games_played}</td>
                        <td>
                          <span style={winRateCellStyle(champ.win_rate)}>
                            {champ.win_rate !== null
                              ? `${(champ.win_rate * 100).toFixed(1)}%`
                              : "—"}
                          </span>
                        </td>
                        <td>{fmt(champ.avg_kda, 2)}</td>
                        <td>{fmt(champ.avg_cs_per_min, 2)}</td>
                        <td>{fmt(champ.avg_gold_per_min, 0)}</td>
                        <td>
                          {fmt(champ.avg_kills, 1)} / {fmt(champ.avg_deaths, 1)} /{" "}
                          {fmt(champ.avg_assists, 1)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {filtered.length === 0 ? (
              <p className={`${styles.emptyState} ${styles.dashboardMobileList}`}>
                {data.champions_found === 0
                  ? "No ranked games found for this player."
                  : "No champions match the selected role."}
              </p>
            ) : (
              <div className={styles.dashboardMobileList}>
                {filtered.map((champ) => (
                  <article className={styles.dashboardMobileCard} key={champ.champion_id}>
                    <div className={styles.dashboardMobileHeader}>
                      <strong>{champ.champion_name}</strong>
                      <span style={winRateCellStyle(champ.win_rate)}>
                        {champ.win_rate !== null
                          ? `${(champ.win_rate * 100).toFixed(1)}%`
                          : "—"}
                      </span>
                    </div>

                    <div className={styles.dashboardMetricGrid}>
                      <div>
                        <span>Games</span>
                        <strong>{champ.games_played}</strong>
                      </div>
                      <div>
                        <span>KDA</span>
                        <strong>{fmt(champ.avg_kda, 2)}</strong>
                      </div>
                      <div>
                        <span>CS / Min</span>
                        <strong>{fmt(champ.avg_cs_per_min, 2)}</strong>
                      </div>
                      <div>
                        <span>Gold / Min</span>
                        <strong>{fmt(champ.avg_gold_per_min, 0)}</strong>
                      </div>
                      <div>
                        <span>Kills</span>
                        <strong>{fmt(champ.avg_kills, 1)}</strong>
                      </div>
                      <div>
                        <span>Deaths</span>
                        <strong>{fmt(champ.avg_deaths, 1)}</strong>
                      </div>
                      <div>
                        <span>Assists</span>
                        <strong>{fmt(champ.avg_assists, 1)}</strong>
                      </div>
                      <div>
                        <span>K / D / A</span>
                        <strong>
                          {fmt(champ.avg_kills, 1)} / {fmt(champ.avg_deaths, 1)} /{" "}
                          {fmt(champ.avg_assists, 1)}
                        </strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
