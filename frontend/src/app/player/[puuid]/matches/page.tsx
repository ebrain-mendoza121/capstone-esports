"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import styles from "@/app/mvp.module.css";
import {
  CsPrediction,
  KdaPrediction,
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
  const [kdaPredictions, setKdaPredictions] = useState<Record<string, KdaPrediction>>({});
  const [csPredictions, setCsPredictions] = useState<Record<string, CsPrediction>>({});
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

      // Load all AI predictions for every match in parallel
      setLoadingPredictions(true);
      const predResults = await Promise.allSettled(
        response.map(async (m) => {
          const [win, kda, cs] = await Promise.allSettled([
            frontendMvpClient.getWinPrediction(puuid, m.match_id),
            frontendMvpClient.getKdaPrediction(puuid, m.match_id),
            frontendMvpClient.getCsPrediction(puuid, m.match_id),
          ]);
          return {
            matchId: m.match_id,
            win,
            kda,
            cs,
          };
        })
      );
      if (!mounted) return;
      const winPredMap: Record<string, WinPrediction> = {};
      const kdaPredMap: Record<string, KdaPrediction> = {};
      const csPredMap: Record<string, CsPrediction> = {};
      predResults.forEach((result) => {
        if (result.status === "fulfilled") {
          const { matchId, win, kda, cs } = result.value;
          if (win.status === "fulfilled") {
            winPredMap[matchId] = win.value;
          }
          if (kda.status === "fulfilled") {
            kdaPredMap[matchId] = kda.value;
          }
          if (cs.status === "fulfilled") {
            csPredMap[matchId] = cs.value;
          }
        }
      });
      setPredictions(winPredMap);
      setKdaPredictions(kdaPredMap);
      setCsPredictions(csPredMap);
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
                Win Prob. column shows AI model output — shows &quot;—&quot; until model is trained.
              </p>
            </div>
          </div>

          {loading ? (
            <p className={styles.loading}>Loading matches…</p>
          ) : (
            <>
              <div className={`${styles.tableWrap} ${styles.dashboardDesktopOnly}`}>
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
                      <th>Exp KDA</th>
                      <th>Exp CS/Min</th>
                      <th>Win Prob.</th>
                      <th>Result</th>
                      <th>Duration</th>
                      <th>Patch</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMatches.map((match) => {
                      const pred = predictions[match.match_id];
                      const kdaPred = kdaPredictions[match.match_id];
                      const csPred = csPredictions[match.match_id];
                      const winProb =
                        pred?.model_trained && pred?.win_probability !== null
                          ? `${(pred.win_probability * 100).toFixed(1)}%`
                          : "—";
                      const expectedKda =
                        kdaPred?.model_trained && kdaPred?.expected_kda !== null
                          ? fmt(kdaPred.expected_kda)
                          : "—";
                      const expectedCsPerMin =
                        csPred?.model_trained && csPred?.expected_cs_per_min !== null
                          ? fmt(csPred.expected_cs_per_min)
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
                          <td>{expectedKda}</td>
                          <td>{expectedCsPerMin}</td>
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

              <div className={styles.dashboardMobileList}>
                {filteredMatches.map((match) => {
                  const pred = predictions[match.match_id];
                  const kdaPred = kdaPredictions[match.match_id];
                  const csPred = csPredictions[match.match_id];
                  const winProb =
                    pred?.model_trained && pred?.win_probability !== null
                      ? `${(pred.win_probability * 100).toFixed(1)}%`
                      : "—";
                  const expectedKda =
                    kdaPred?.model_trained && kdaPred?.expected_kda !== null
                      ? fmt(kdaPred.expected_kda)
                      : "—";
                  const expectedCsPerMin =
                    csPred?.model_trained && csPred?.expected_cs_per_min !== null
                      ? fmt(csPred.expected_cs_per_min)
                      : "—";

                  return (
                    <article className={styles.dashboardMobileCard} key={match.match_id}>
                      <div className={styles.dashboardMobileHeader}>
                        <strong>{match.champion}</strong>
                        <span className={match.win ? styles.badgeWin : styles.badgeLoss}>
                          {match.win ? "Win" : "Loss"}
                        </span>
                      </div>

                      <div className={styles.dashboardMetricGrid}>
                        <div>
                          <span>Side</span>
                          <strong>{match.team_id === 100 ? "Blue" : "Red"}</strong>
                        </div>
                        <div>
                          <span>Role</span>
                          <strong>{match.role}</strong>
                        </div>
                        <div>
                          <span>K/D/A</span>
                          <strong>{match.kills}/{match.deaths}/{match.assists}</strong>
                        </div>
                        <div>
                          <span>KDA</span>
                          <strong>{fmt(match.kda)}</strong>
                        </div>
                        <div>
                          <span>CS/Min</span>
                          <strong>{fmt(match.cs_per_min)}</strong>
                        </div>
                        <div>
                          <span>Gold/Min</span>
                          <strong>{fmt(match.gold_per_min, 0)}</strong>
                        </div>
                        <div>
                          <span>Damage</span>
                          <strong>{match.total_damage?.toLocaleString() ?? "—"}</strong>
                        </div>
                        <div>
                          <span>Damage Share</span>
                          <strong>{pct(match.damage_share)}</strong>
                        </div>
                        <div>
                          <span>Kill Part.</span>
                          <strong>{pct(match.kill_participation)}</strong>
                        </div>
                        <div>
                          <span>Vision</span>
                          <strong>{match.vision_score}</strong>
                        </div>
                        <div>
                          <span>Expected KDA</span>
                          <strong>{expectedKda}</strong>
                        </div>
                        <div>
                          <span>Exp CS/Min</span>
                          <strong>{expectedCsPerMin}</strong>
                        </div>
                        <div>
                          <span>Win Prob.</span>
                          <strong>{winProb}</strong>
                        </div>
                        <div>
                          <span>Duration</span>
                          <strong>{formatDuration(match.game_duration)}</strong>
                        </div>
                      </div>

                      <Link
                        className={`${styles.linkChip} ${styles.dashboardMobileAction}`}
                        href={`/match/${match.match_id}`}
                      >
                        Open Match
                      </Link>
                    </article>
                  );
                })}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
