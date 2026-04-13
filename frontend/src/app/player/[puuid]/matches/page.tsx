"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import styles from "@/app/mvp.module.css";
import {
  MatchHistoryEntry,
  QueueCode,
  WinPrediction,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

type QueueFilter = "all" | QueueCode;
type ResultFilter = "all" | "win" | "loss";

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}:${String(rem).padStart(2, "0")}`;
}

function pct(value: number | null) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function fmt(value: number | null, decimals = 2) {
  if (value === null || value === undefined) return "—";
  return value.toFixed(decimals);
}

export default function MatchHistoryPage() {
  const params = useParams<{ puuid: string }>();
  const router = useRouter();
  const puuid = Array.isArray(params.puuid) ? params.puuid[0] : params.puuid;

  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [matches, setMatches] = useState<MatchHistoryEntry[]>([]);
  const [predictions, setPredictions] = useState<Record<string, WinPrediction>>({});
  const [loadingPredictions, setLoadingPredictions] = useState(false);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("all");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");

  useEffect(() => {
    let mounted = true;

    const loadMatches = async () => {
      setLoading(true);
      const response = await frontendMvpClient.getMatchesByPlayer(puuid, limit);
      if (!mounted) return;
      setMatches(response);
      setLoading(false);

      // Load win predictions for all matches in parallel
      setLoadingPredictions(true);
      const predResults = await Promise.allSettled(
        response.map((m) => frontendMvpClient.getWinPrediction(puuid, m.match_id))
      );
      if (!mounted) return;
      const predMap: Record<string, WinPrediction> = {};
      predResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          predMap[response[idx].match_id] = result.value;
        }
      });
      setPredictions(predMap);
      setLoadingPredictions(false);
    };

    void loadMatches();
    return () => { mounted = false; };
  }, [limit, puuid]);

  const filteredMatches = useMemo(() => {
    return matches.filter((match) => {
      const queuePass = queueFilter === "all" ? true : match.queue_id === queueFilter;
      const resultPass =
        resultFilter === "all" ? true : resultFilter === "win" ? match.win : !match.win;
      return queuePass && resultPass;
    });
  }, [matches, queueFilter, resultFilter]);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Player · Match History</p>
          <div className={styles.heroTitleRow}>
            <h1 className={styles.title}>Match History</h1>
            <Link className={styles.linkChip} href={`/player/${puuid}`}>
              ← Back to Dashboard
            </Link>
          </div>
        </header>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Filters</h2>
            </div>
            <span className={styles.badgeNeutral}>
              {loadingPredictions ? "Loading AI predictions…" : `${filteredMatches.length} rows`}
            </span>
          </div>

          <div className={styles.threeCol}>
            <label className={styles.field}>
              Queue
              <select
                className={styles.select}
                value={queueFilter}
                onChange={(e) => {
                  const v = e.target.value;
                  setQueueFilter(v === "all" ? "all" : (Number(v) as QueueCode));
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
                onChange={(e) => setResultFilter(e.target.value as ResultFilter)}
              >
                <option value="all">All</option>
                <option value="win">Win</option>
                <option value="loss">Loss</option>
              </select>
            </label>

            <button
              className={styles.buttonPrimary}
              type="button"
              onClick={() => setLimit((v) => v + 20)}
            >
              Load More
            </button>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Matches</h2>
              <p className={styles.sectionCopy}>
                Win Prob. column shows AI model output — shows "—" until model is trained.
              </p>
            </div>
          </div>

          {loading ? (
            <p className={styles.loading}>Loading matches…</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Side</th>
                    <th>Champion</th>
                    <th>Role</th>
                    <th>K/D/A</th>
                    <th>CS</th>
                    <th>CS/Min</th>
                    <th>Gold</th>
                    <th>Gold/Min</th>
                    <th>Damage</th>
                    <th>Dmg Share</th>
                    <th>Kill Part.</th>
                    <th>Vision</th>
                    <th>Wards</th>
                    <th>KDA</th>
                    <th>Win Prob.</th>
                    <th>Result</th>
                    <th>Duration</th>
                    <th>Patch</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMatches.map((match) => {
                    const pred = predictions[match.match_id];
                    const winProb =
                      pred?.model_trained && pred?.win_probability !== null
                        ? `${(pred.win_probability * 100).toFixed(1)}%`
                        : "—";

                    return (
                      <tr
                        key={match.match_id}
                        onClick={() => router.push(`/match/${match.match_id}`)}
                        style={{ cursor: "pointer" }}
                      >
                        <td>
                          <span style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 700,
                            background: match.team_id === 100 ? "rgba(59,130,246,0.2)" : "rgba(239,68,68,0.2)",
                            color: match.team_id === 100 ? "#93c5fd" : "#fca5a5",
                            letterSpacing: "0.04em",
                          }}>
                            {match.team_id === 100 ? "Blue" : "Red"}
                          </span>
                        </td>
                        <td>{match.champion}</td>
                        <td>{match.role}</td>
                        <td>{match.kills}/{match.deaths}/{match.assists}</td>
                        <td>{match.cs}</td>
                        <td>{fmt(match.cs_per_min)}</td>
                        <td>{match.gold_earned.toLocaleString()}</td>
                        <td>{fmt(match.gold_per_min, 0)}</td>
                        <td>{match.total_damage?.toLocaleString() ?? "—"}</td>
                        <td>{pct(match.damage_share)}</td>
                        <td>{pct(match.kill_participation)}</td>
                        <td>{match.vision_score}</td>
                        <td>{match.wards_placed ?? "—"}</td>
                        <td>{fmt(match.kda)}</td>
                        <td>
                          <span className={
                            pred?.model_trained && pred?.win_probability !== null
                              ? (pred.win_probability >= 0.5 ? styles.badgeWin : styles.badgeLoss)
                              : styles.badge
                          }>
                            {winProb}
                          </span>
                        </td>
                        <td>
                          <span className={match.win ? styles.badgeWin : styles.badgeLoss}>
                            {match.win ? "Win" : "Loss"}
                          </span>
                        </td>
                        <td>{formatDuration(match.game_duration)}</td>
                        <td>{match.patch_version}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
