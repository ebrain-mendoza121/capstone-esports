"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import styles from "@/app/mvp.module.css";
import { MatchHistoryEntry, QueueCode, frontendMvpClient } from "@/lib/frontendMvpClient";

type QueueFilter = "all" | QueueCode;
type ResultFilter = "all" | "win" | "loss";

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}:${String(rem).padStart(2, "0")}`;
}

export default function MatchHistoryPage() {
  const params = useParams<{ puuid: string }>();
  const router = useRouter();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [matches, setMatches] = useState<MatchHistoryEntry[]>([]);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("all");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");

  useEffect(() => {
    let mounted = true;

    const loadMatches = async () => {
      setLoading(true);
      const response = await frontendMvpClient.getMatchesByPlayer(puuid, limit);

      if (!mounted) {
        return;
      }

      setMatches(response);
      setLoading(false);
    };

    void loadMatches();

    return () => {
      mounted = false;
    };
  }, [limit, puuid]);

  const filteredMatches = useMemo(() => {
    return matches.filter((match) => {
      const queuePass = queueFilter === "all" ? true : match.queue_id === queueFilter;
      const resultPass =
        resultFilter === "all"
          ? true
          : resultFilter === "win"
            ? match.win
            : !match.win;

      return queuePass && resultPass;
    });
  }, [matches, queueFilter, resultFilter]);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 3</p>
          <h1 className={styles.title}>Match History</h1>
        </header>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Filters</h2>
              <p className={styles.sectionCopy}>Client-side queue/result filters + load more paging</p>
            </div>
            <Link className={styles.linkChip} href={`/player/${puuid}`}>
              Back to Dashboard
            </Link>
          </div>

          <div className={styles.threeCol}>
            <label className={styles.field}>
              Queue
              <select
                className={styles.select}
                value={queueFilter}
                onChange={(event) => {
                  const value = event.target.value;
                  setQueueFilter(value === "all" ? "all" : Number(value) as QueueCode);
                }}
              >
                <option value="all">All</option>
                <option value={420}>Ranked Solo (420)</option>
                <option value={440}>Ranked Flex (440)</option>
              </select>
            </label>

            <label className={styles.field}>
              Result
              <select
                className={styles.select}
                value={resultFilter}
                onChange={(event) => setResultFilter(event.target.value as ResultFilter)}
              >
                <option value="all">All</option>
                <option value="win">Win</option>
                <option value="loss">Loss</option>
              </select>
            </label>

            <button className={styles.buttonPrimary} type="button" onClick={() => setLimit((value) => value + 20)}>
              Load More
            </button>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Recent Matches</h2>
              <p className={styles.sectionCopy}>Recent matches based on the current filters and load limit.</p>
            </div>
            <span className={styles.badgeNeutral}>{filteredMatches.length} rows</span>
          </div>

          {loading ? (
            <p className={styles.loading}>Loading match rows...</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Champion</th>
                    <th>Role</th>
                    <th>K/D/A</th>
                    <th>CS</th>
                    <th>Gold</th>
                    <th>Vision</th>
                    <th>Items</th>
                    <th>Result</th>
                    <th>Duration</th>
                    <th>Patch</th>
                    <th>KDA</th>
                    <th>CS/Min</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMatches.map((match) => (
                    <tr key={match.match_id}>
                      <td>
                        <button
                          className={styles.rowButton}
                          type="button"
                          onClick={() => router.push(`/match/${match.match_id}`)}
                        >
                          {match.champion}
                        </button>
                      </td>
                      <td>{match.role}</td>
                      <td>
                        {match.kills}/{match.deaths}/{match.assists}
                      </td>
                      <td>{match.cs}</td>
                      <td>{match.gold_earned.toLocaleString()}</td>
                      <td>{match.vision_score}</td>
                      <td>{match.items.slice(0, 7).join(" · ")}</td>
                      <td>
                        <span className={match.win ? styles.badgeWin : styles.badgeLoss}>
                          {match.win ? "Win" : "Loss"}
                        </span>
                      </td>
                      <td>{formatDuration(match.game_duration)}</td>
                      <td>{match.patch_version}</td>
                      <td>{match.kda}</td>
                      <td>{match.cs_per_min}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
