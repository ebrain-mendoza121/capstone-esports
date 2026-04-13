"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import styles from "@/app/mvp.module.css";
import { DraftData, EarlyGamePrediction, MatchDetail, MockApiError, frontendMvpClient } from "@/lib/frontendMvpClient";

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}:${String(rem).padStart(2, "0")}`;
}

export default function MatchDetailPage() {
  const params = useParams<{ match_id: string }>();
  const matchId = Array.isArray(params.match_id) ? params.match_id[0] : params.match_id;

  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [draft, setDraft] = useState<DraftData | null>(null);
  const [timelineAvailable, setTimelineAvailable] = useState(false);
  const [earlyGame, setEarlyGame] = useState<EarlyGamePrediction | null>(null);

  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      const [detailResponse, draftResponse, earlyGameResponse] = await Promise.all([
        frontendMvpClient.getMatch(matchId),
        frontendMvpClient.getMatchDraft(matchId).catch(() => null),
        frontendMvpClient.getEarlyGamePrediction(matchId).catch(() => null),
      ]);

      let hasTimeline = false;
      try {
        await frontendMvpClient.getTimelineAvailability(matchId);
        hasTimeline = true;
      } catch (error) {
        if (error instanceof MockApiError && error.status === 404) {
          hasTimeline = false;
        }
      }

      if (!mounted) {
        return;
      }

      setDetail(detailResponse);
      setDraft(draftResponse);
      setTimelineAvailable(hasTimeline);
      setEarlyGame(earlyGameResponse);
    };

    void loadData();

    return () => {
      mounted = false;
    };
  }, [matchId]);

  const blueTeam = useMemo(
    () => detail?.participants.filter((entry) => entry.team_id === 100) ?? [],
    [detail],
  );
  const redTeam = useMemo(
    () => detail?.participants.filter((entry) => entry.team_id === 200) ?? [],
    [detail],
  );

  if (!detail) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <p className={styles.loading}>Loading match detail…</p>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 4</p>
          <h1 className={styles.title}>Match Detail</h1>
        </header>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Match Header</h2>
              <p className={styles.sectionCopy}>Core metadata for this match snapshot.</p>
            </div>
            {timelineAvailable ? (
              <Link className={styles.linkChip} href={`/match/${matchId}/timeline`}>
                View Timeline
              </Link>
            ) : (
              <span className={styles.badgeLoss}>Timeline unavailable</span>
            )}
          </div>
          <div className={styles.inlineList}>
            <span className={styles.badgeNeutral}>Queue {detail.queue_id}</span>
            <span className={styles.badgeNeutral}>Patch {detail.patch_version}</span>
            <span className={styles.badgeNeutral}>Duration {formatDuration(detail.game_duration)}</span>
            <span className={styles.badgeNeutral}>{new Date(detail.date).toLocaleString()}</span>
          </div>
        </section>

        {/* ── Early Game AI Prediction ── */}
        {earlyGame && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>Early Game Prediction</h2>
                <p className={styles.sectionCopy}>
                  T=10 / T=15 gold, XP, CS differential model · Blue Team win probability
                </p>
              </div>
            </div>
            {!earlyGame.model_trained ? (
              <p className={styles.emptyState}>
                Early game model not trained yet — run <code>POST /ai/train/early-game</code>.
              </p>
            ) : earlyGame.error === "no_timeline_data" ? (
              <p className={styles.emptyState}>
                No timeline data for this match — re-ingest with <code>fetch_timeline=true</code>.
              </p>
            ) : (
              <div className={styles.inlineList}>
                <span className={
                  earlyGame.team100_win_probability !== null && earlyGame.team100_win_probability >= 0.5
                    ? styles.badgeWin
                    : styles.badgeLoss
                }>
                  Blue Team Win Prob:{" "}
                  {earlyGame.team100_win_probability !== null
                    ? `${(earlyGame.team100_win_probability * 100).toFixed(1)}%`
                    : "—"}
                </span>
                <span className={styles.badge}>Confidence: {earlyGame.confidence}</span>
              </div>
            )}
          </section>
        )}

        {/* ── Draft / Bans ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Draft / Bans</h2>
              <p className={styles.sectionCopy}>Finalized picks and bans by team.</p>
            </div>
          </div>

          {!draft ? (
            <p className={styles.emptyState}>
              No draft data — run <code>POST /backfill/draft-actions</code>.
            </p>
          ) : (
            <div className={styles.twoCol}>
              <article className={styles.dataCard}>
                <h3>Blue Team Bans</h3>
                <p className={styles.small}>{draft.team100_bans.join(" · ")}</p>
                <h3 style={{ marginTop: "10px" }}>Blue Team Picks</h3>
                <p className={styles.small}>{draft.team100_picks.join(" · ")}</p>
              </article>
              <article className={styles.dataCard}>
                <h3>Red Team Bans</h3>
                <p className={styles.small}>{draft.team200_bans.join(" · ")}</p>
                <h3 style={{ marginTop: "10px" }}>Red Team Picks</h3>
                <p className={styles.small}>{draft.team200_picks.join(" · ")}</p>
              </article>
            </div>
          )}
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Team Objectives</h2>
              <p className={styles.sectionCopy}>Blue vs Red objective profile</p>
            </div>
          </div>

          <div className={styles.twoCol}>
            {detail.teams.map((team) => (
              <article className={styles.dataCard} key={team.team_id}>
                <h3>Team {team.team_id}</h3>
                <p className={styles.small}>
                  Towers {team.towers} · Dragons {team.dragons} · Barons {team.barons} · Rift Herald {team.rift_herald_kills} · Inhibs {team.inhibitor_kills}
                </p>
                <p style={{ marginTop: "8px" }}>
                  <span className={team.win ? styles.badgeWin : styles.badgeLoss}>
                    {team.win ? "WIN" : "LOSS"}
                  </span>
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Scoreboard — Blue Team</h2>
              <p className={styles.sectionCopy}>All five participants with item strip and keystone</p>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Riot ID</th>
                  <th>Champion</th>
                  <th>Role</th>
                  <th>K/D/A</th>
                  <th>CS</th>
                  <th>Gold</th>
                  <th>Damage</th>
                  <th>Vision</th>
                  <th>Items</th>
                  <th>Keystone</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {blueTeam.map((entry) => (
                  <tr key={entry.puuid}>
                    <td>{entry.riot_id}</td>
                    <td>{entry.champion}</td>
                    <td>{entry.role}</td>
                    <td>
                      {entry.kills}/{entry.deaths}/{entry.assists}
                    </td>
                    <td>{entry.cs}</td>
                    <td>{entry.gold_earned.toLocaleString()}</td>
                    <td>{entry.total_damage.toLocaleString()}</td>
                    <td>{entry.vision_score}</td>
                    <td>{entry.items.join(" · ")}</td>
                    <td>{entry.perks.keystone}</td>
                    <td>
                      <span className={entry.win ? styles.badgeWin : styles.badgeLoss}>
                        {entry.win ? "Win" : "Loss"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Scoreboard — Red Team</h2>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Riot ID</th>
                  <th>Champion</th>
                  <th>Role</th>
                  <th>K/D/A</th>
                  <th>CS</th>
                  <th>Gold</th>
                  <th>Damage</th>
                  <th>Vision</th>
                  <th>Items</th>
                  <th>Keystone</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {redTeam.map((entry) => (
                  <tr key={entry.puuid}>
                    <td>{entry.riot_id}</td>
                    <td>{entry.champion}</td>
                    <td>{entry.role}</td>
                    <td>
                      {entry.kills}/{entry.deaths}/{entry.assists}
                    </td>
                    <td>{entry.cs}</td>
                    <td>{entry.gold_earned.toLocaleString()}</td>
                    <td>{entry.total_damage.toLocaleString()}</td>
                    <td>{entry.vision_score}</td>
                    <td>{entry.items.join(" · ")}</td>
                    <td>{entry.perks.keystone}</td>
                    <td>
                      <span className={entry.win ? styles.badgeWin : styles.badgeLoss}>
                        {entry.win ? "Win" : "Loss"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
