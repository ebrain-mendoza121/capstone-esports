"use client";

import Link from "next/link";
import React, { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import styles from "@/app/mvp.module.css";
import {
  DraftData,
  EarlyGamePrediction,
  MatchDetail,
  MockApiError,
  ThreatWeights,
  TimelineFrameRaw,
  WinPredictionBacktest,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}:${String(rem).padStart(2, "0")}`;
}
/** Map Riot platform_id (e.g. "NA1") to the backend Platform enum (e.g. "NA") */
const RIOT_PLATFORM_MAP: Record<string, string> = {
  NA1: "NA", BR1: "BR", LA1: "LAN", LA2: "LAS",
  KR: "KR", JP1: "JP", EUN1: "EUNE", EUW1: "EUW",
  ME1: "ME1", TR1: "TR", RU: "RU", OC1: "OCE",
  SG2: "SG2", TW2: "TW2", VN2: "VN2",
};
function normalizePlatform(id: string): string {
  return RIOT_PLATFORM_MAP[id.toUpperCase()] ?? id.toUpperCase();
}// ── Item strip ────────────────────────────────────────────────────────────────

function ItemTooltip({ name, children }: { name: string; children: React.ReactNode }) {
  const [visible, setVisible] = React.useState(false);
  return (
    <div
      style={{ position: "relative", display: "inline-block" }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      {visible && name && (
        <div style={{
          position: "absolute",
          bottom: "calc(100% + 6px)",
          left: "50%",
          transform: "translateX(-50%)",
          background: "rgba(8, 14, 36, 0.95)",
          border: "1px solid rgba(255,255,255,0.18)",
          borderRadius: 6,
          padding: "4px 8px",
          fontSize: 11,
          fontWeight: 600,
          whiteSpace: "nowrap",
          color: "#f3f4ef",
          pointerEvents: "none",
          zIndex: 10,
        }}>
          {name}
        </div>
      )}
    </div>
  );
}

function ItemStrip({ items, version, itemNames }: { items: number[]; version: string; itemNames: Record<number, string> }) {
  const filtered = items.filter((id) => id && id !== 0);
  if (!filtered.length) return <span style={{ opacity: 0.3 }}>—</span>;
  return (
    <div style={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
      {filtered.map((id, i) => (
        <ItemTooltip key={i} name={itemNames[id] ?? ""}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`https://ddragon.leagueoflegends.com/cdn/${version}/img/item/${id}.png`}
            alt={itemNames[id] ?? String(id)}
            width={24}
            height={24}
            style={{ borderRadius: 4, display: "block" }}
          />
        </ItemTooltip>
      ))}
    </div>
  );
}
// ── Champion chip row (draft section) ───────────────────────────────────────

function ChampionChipRow({
  ids,
  champMap,
  dim = false,
}: {
  ids: number[];
  champMap: Record<number, { name: string; image_url: string }>;
  dim?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {ids.map((id, i) => {
        const champ = champMap[id];
        return (
          <div
            key={i}
            title={champ?.name ?? String(id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              background: "rgba(255,255,255,0.07)",
              borderRadius: 8,
              padding: "3px 8px 3px 3px",
              opacity: dim ? 0.55 : 1,
            }}
          >
            {champ?.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={champ.image_url}
                alt={champ.name}
                width={28}
                height={28}
                style={{ borderRadius: 6, display: "block", objectFit: "cover" }}
              />
            ) : (
              <div style={{ width: 28, height: 28, borderRadius: 6, background: "rgba(255,255,255,0.1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, opacity: 0.5 }}>?</div>
            )}
            <span style={{ fontSize: "0.78rem", fontWeight: 600 }}>
              {champ?.name ?? id}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Gold Differential Chart ──────────────────────────────────────────────────

interface GoldDiffPoint {
  minute: number;
  diff: number; // team100_total_gold - team200_total_gold
}

const CHART_W = 600;
const CHART_H = 140;
const PAD_L = 44;
const PAD_R = 8;
const PAD_T = 14;
const PAD_B = 28;

function GoldDiffChart({ points }: { points: GoldDiffPoint[] }) {
  if (points.length < 2) {
    return (
      <p style={{ opacity: 0.5, fontSize: 13, padding: 8 }}>Not enough frame data to render chart.</p>
    );
  }

  const innerW = CHART_W - PAD_L - PAD_R;
  const innerH = CHART_H - PAD_T - PAD_B;
  const maxMin = Math.max(...points.map((p) => p.minute));
  const absMax = Math.max(...points.map((p) => Math.abs(p.diff)), 1);

  const toX = (m: number) => PAD_L + (m / maxMin) * innerW;
  const toY = (d: number) => PAD_T + (1 - (d + absMax) / (2 * absMax)) * innerH;
  const zeroY = toY(0);

  type Seg = { x1: number; y1: number; x2: number; y2: number; color: string };
  const segs: Seg[] = [];
  const svgPts = points.map((p) => ({ x: toX(p.minute), y: toY(p.diff), diff: p.diff }));

  for (let i = 0; i < svgPts.length - 1; i++) {
    const a = svgPts[i];
    const b = svgPts[i + 1];
    if (a.diff >= 0 === b.diff >= 0) {
      segs.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y, color: a.diff >= 0 ? "#22c55e" : "#ef4444" });
    } else {
      const t = a.diff / (a.diff - b.diff);
      const mx = a.x + t * (b.x - a.x);
      segs.push({ x1: a.x, y1: a.y, x2: mx, y2: zeroY, color: a.diff >= 0 ? "#22c55e" : "#ef4444" });
      segs.push({ x1: mx, y1: zeroY, x2: b.x, y2: b.y, color: b.diff >= 0 ? "#22c55e" : "#ef4444" });
    }
  }

  const xLabels: number[] = [];
  for (let m = 0; m <= maxMin; m += 5) xLabels.push(m);
  const kMax = (absMax / 1000).toFixed(1);

  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} style={{ width: "100%", display: "block" }}>
      {/* Zero dashed line */}
      <line
        x1={PAD_L} y1={zeroY} x2={PAD_L + innerW} y2={zeroY}
        stroke="rgba(255,255,255,0.22)" strokeWidth={1} strokeDasharray="4 3"
      />
      {/* Colored segments */}
      {segs.map((s, i) => (
        <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
          stroke={s.color} strokeWidth={2.5} strokeLinecap="round" />
      ))}
      {/* X-axis minute labels every 5 min */}
      {xLabels.map((m) => (
        <text key={m} x={toX(m)} y={CHART_H - 6}
          textAnchor="middle" fontSize={10} fill="rgba(255,255,255,0.42)">
          {m}m
        </text>
      ))}
      {/* Y-axis labels */}
      <text x={PAD_L - 4} y={PAD_T + 10} textAnchor="end" fontSize={10} fill="#22c55e">+{kMax}k</text>
      <text x={PAD_L - 4} y={zeroY + 4} textAnchor="end" fontSize={10} fill="rgba(255,255,255,0.42)">0</text>
      <text x={PAD_L - 4} y={PAD_T + innerH} textAnchor="end" fontSize={10} fill="#ef4444">-{kMax}k</text>
      {/* Legend */}
      <circle cx={PAD_L + 10} cy={PAD_T + 8} r={4} fill="#22c55e" />
      <text x={PAD_L + 18} y={PAD_T + 12} fontSize={10} fill="#22c55e">Blue leads</text>
      <circle cx={PAD_L + 82} cy={PAD_T + 8} r={4} fill="#ef4444" />
      <text x={PAD_L + 90} y={PAD_T + 12} fontSize={10} fill="#ef4444">Red leads</text>
    </svg>
  );
}

export default function MatchDetailPage() {
  const params = useParams<{ match_id: string }>();
  const matchId = Array.isArray(params.match_id) ? params.match_id[0] : params.match_id;
  const router = useRouter();

  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [draft, setDraft] = useState<DraftData | null>(null);
  const [champMap, setChampMap] = useState<Record<number, { name: string; image_url: string }>>({});
  const [runeMap, setRuneMap] = useState<Record<string, string>>({});
  const [ddVersion, setDdVersion] = useState<string>("15.8.1");
  const [itemNames, setItemNames] = useState<Record<number, string>>({});
  const [timelineAvailable, setTimelineAvailable] = useState(false);
  const [goldDiffPoints, setGoldDiffPoints] = useState<GoldDiffPoint[] | null>(null);
  const [earlyGame, setEarlyGame] = useState<EarlyGamePrediction | null>(null);
  const [threatWeights, setThreatWeights] = useState<ThreatWeights | null>(null);
  const [winBacktest, setWinBacktest] = useState<WinPredictionBacktest | null>(null);


  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      const [detailResponse, draftResponse, earlyGameResponse, champsRes, runeMapRes, threatRes, backtestRes] = await Promise.all([
        frontendMvpClient.getMatch(matchId),
        frontendMvpClient.getMatchDraft(matchId).catch(() => null),
        frontendMvpClient.getEarlyGamePrediction(matchId).catch(() => null),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/champions`).then((r) => r.ok ? r.json() : { champions: [] }).catch(() => ({ champions: [] })),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/analytics/runes/map`).then((r) => r.ok ? r.json() : {}).catch(() => ({})),
        frontendMvpClient.getThreatWeights().catch(() => null),
        frontendMvpClient.getWinPredictionBacktest(80).catch(() => null),
      ]);

      const map: Record<number, { name: string; image_url: string }> = {};
      const champList = (champsRes as { champions: Array<{ id: number; name: string; image_url: string }> }).champions;
      for (const c of champList) {
        map[c.id] = { name: c.name, image_url: c.image_url };
      }
      // Parse DDragon version from first champion image URL
      const firstImgUrl = champList[0]?.image_url ?? "";
      const verMatch = firstImgUrl.match(/cdn\/([^/]+)\//);
      const parsedVersion = verMatch?.[1] ?? "15.8.1";

      // Fetch DDragon item names using the resolved version
      let parsedItemNames: Record<number, string> = {};
      try {
        const itemRes = await fetch(`https://ddragon.leagueoflegends.com/cdn/${parsedVersion}/data/en_US/item.json`);
        if (itemRes.ok) {
          const itemJson = await itemRes.json() as { data: Record<string, { name: string }> };
          for (const [idStr, entry] of Object.entries(itemJson.data)) {
            parsedItemNames[Number(idStr)] = entry.name;
          }
        }
      } catch { /* item names are optional — tooltip falls back to empty */ }

      let hasTimeline = false;
      let goldPts: GoldDiffPoint[] | null = null;
      try {
        await frontendMvpClient.getTimelineAvailability(matchId);
        hasTimeline = true;
        try {
          const rawFrames: TimelineFrameRaw[] = await frontendMvpClient.getTimelineFramesAll(matchId, 1000);
          const byMinute = new Map<number, { t100: number; t200: number }>();
          for (const f of rawFrames) {
            const min = Math.floor(f.frame_timestamp / 60000);
            if (!byMinute.has(min)) byMinute.set(min, { t100: 0, t200: 0 });
            const e = byMinute.get(min)!;
            if (f.participant_id <= 5) e.t100 += f.total_gold;
            else e.t200 += f.total_gold;
          }
          goldPts = Array.from(byMinute.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([minute, g]) => ({ minute, diff: g.t100 - g.t200 }));
        } catch {
          // frames fetch failed — chart won't render but timeline badge still shows
        }
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
      setChampMap(map);
      setRuneMap(runeMapRes as Record<string, string>);
      setDdVersion(parsedVersion);
      setItemNames(parsedItemNames);
      setTimelineAvailable(hasTimeline);
      setGoldDiffPoints(goldPts);
      setEarlyGame(earlyGameResponse);
      setThreatWeights(threatRes);
      setWinBacktest(backtestRes);
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

  const handlePlayerClick = (puuid: string, riotId: string, tagLine: string) => {
    const platform = normalizePlatform(detail?.platform_id ?? "NA1");
    // Navigate immediately — don't make the user wait
    router.push(
      `/player/${puuid}?gameName=${encodeURIComponent(riotId)}&tagLine=${encodeURIComponent(tagLine)}&platform=${encodeURIComponent(platform)}`
    );
    // Fire background ingest so the dashboard has data by the time it's needed
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/ingest/player`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gameName: riotId, tagLine, platform, count: 20, queue: 420 }),
    }).catch(() => { /* silently ignore — player dashboard will retry if needed */ });
  };

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
          <div className={styles.heroTitleRow}>
            <h1 className={`${styles.title} ${styles.heroTitle}`}>Match Detail</h1>
            <button className={styles.linkChip} onClick={() => router.back()}>
              ← Back
            </button>
          </div>
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
            <span className={styles.badgeNeutral}>{new Date(detail.game_creation).toLocaleString()}</span>
          </div>
        </section>

        {/* ── Early Game AI Prediction ── */}
        {earlyGame && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>Early Game Prediction</h2>
                <p className={styles.sectionCopy}>
                  T=10 / T=15 gold, XP, CS differential model · win probability by team
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
                  earlyGame.team_100_win_probability !== null && earlyGame.team_100_win_probability >= 0.5
                    ? styles.badgeWin : styles.badgeLoss
                }>
                  🔵 Blue Win Prob:{" "}
                  {earlyGame.team_100_win_probability !== null
                    ? `${(earlyGame.team_100_win_probability * 100).toFixed(1)}%`
                    : "—"}
                </span>
                <span className={
                  earlyGame.team_200_win_probability !== null && earlyGame.team_200_win_probability >= 0.5
                    ? styles.badgeWin : styles.badgeLoss
                }>
                  🔴 Red Win Prob:{" "}
                  {earlyGame.team_200_win_probability !== null
                    ? `${(earlyGame.team_200_win_probability * 100).toFixed(1)}%`
                    : "—"}
                </span>
                <span className={styles.badge}>Confidence: {earlyGame.confidence}</span>
              </div>
            )}
          </section>
        )}

        {/* ── AI Explainability ── */}
        {(threatWeights || winBacktest) && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>AI Explainability</h2>
                <p className={styles.sectionCopy}>
                  Live model behavior signals for rubric evidence: threat weighting and calibration backtest
                </p>
              </div>
            </div>

            <div className={styles.twoCol}>
              <article className={styles.dataCard}>
                <h3 style={{ marginBottom: 8 }}>Threat Weights</h3>
                {!threatWeights ? (
                  <p className={styles.small}>Unavailable.</p>
                ) : (
                  <>
                    <div className={styles.inlineList} style={{ marginBottom: 10 }}>
                      <span className={threatWeights.source === "model" ? styles.badgeWin : styles.badgeLoss}>
                        Source: {threatWeights.source}
                      </span>
                      <span className={styles.badge}>Win Rate Weight: {threatWeights.win_rate_weight.toFixed(2)}</span>
                      <span className={styles.badge}>KDA Weight: {threatWeights.kda_weight.toFixed(2)}</span>
                      <span className={styles.badge}>AUC: {threatWeights.model_auc !== null ? threatWeights.model_auc.toFixed(3) : "—"}</span>
                    </div>
                    <p className={styles.small} style={{ lineHeight: 1.6 }}>{threatWeights.interpretation}</p>
                  </>
                )}
              </article>

              <article className={styles.dataCard}>
                <h3 style={{ marginBottom: 8 }}>Win-Prediction Backtest</h3>
                {!winBacktest ? (
                  <p className={styles.small}>Unavailable.</p>
                ) : !winBacktest.model_trained ? (
                  <p className={styles.small}>Model not trained yet{winBacktest.reason ? `: ${winBacktest.reason}` : "."}</p>
                ) : (
                  <>
                    <div className={styles.inlineList} style={{ marginBottom: 10 }}>
                      <span className={styles.badge}>Samples: {winBacktest.summary?.total ?? 0}</span>
                      <span className={styles.badge}>Accuracy: {winBacktest.summary?.accuracy !== null && winBacktest.summary?.accuracy !== undefined ? `${(winBacktest.summary.accuracy * 100).toFixed(1)}%` : "—"}</span>
                      <span className={styles.badge}>Brier: {winBacktest.summary?.brier_score !== null && winBacktest.summary?.brier_score !== undefined ? winBacktest.summary.brier_score.toFixed(4) : "—"}</span>
                    </div>
                    <p className={styles.small} style={{ marginBottom: 8 }}>
                      Calibration buckets (predicted range vs actual win rate):
                    </p>
                    <div className={styles.inlineList}>
                      {(winBacktest.calibration_buckets ?? []).slice(0, 6).map((bucket) => (
                        <span key={bucket.bucket} className={styles.badgeNeutral}>
                          {bucket.bucket}: {bucket.actual_win_rate !== null ? `${(bucket.actual_win_rate * 100).toFixed(0)}%` : "—"} ({bucket.n_matches})
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </article>
            </div>
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
                <h3 style={{ marginBottom: 8 }}>Blue Team Bans</h3>
                <ChampionChipRow ids={draft.team100_bans} champMap={champMap} dim />
                <h3 style={{ margin: "12px 0 8px" }}>Blue Team Picks</h3>
                <ChampionChipRow ids={draft.team100_picks} champMap={champMap} />
              </article>
              <article className={styles.dataCard}>
                <h3 style={{ marginBottom: 8 }}>Red Team Bans</h3>
                <ChampionChipRow ids={draft.team200_bans} champMap={champMap} dim />
                <h3 style={{ margin: "12px 0 8px" }}>Red Team Picks</h3>
                <ChampionChipRow ids={draft.team200_picks} champMap={champMap} />
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
                <h3>{team.team_id === 100 ? "Blue Team" : "Red Team"}</h3>
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
                    <td>
                      <button
                        className={styles.rowButton}
                        style={{ color: "inherit", cursor: "pointer" }}
                        onClick={() => handlePlayerClick(entry.puuid, entry.riot_id, entry.tag_line)}
                        title={`View ${entry.riot_id}#${entry.tag_line}'s dashboard`}
                      >
                        {entry.riot_id}
                      </button>
                    </td>
                    <td>{entry.champion}</td>
                    <td>{entry.role}</td>
                    <td>
                      {entry.kills}/{entry.deaths}/{entry.assists}
                    </td>
                    <td>{entry.cs}</td>
                    <td>{entry.gold_earned.toLocaleString()}</td>
                    <td>{entry.total_damage.toLocaleString()}</td>
                    <td>{entry.vision_score}</td>
                    <td><ItemStrip items={entry.items} version={ddVersion} itemNames={itemNames} /></td>
                    <td>{runeMap[entry.perks.keystone] ?? entry.perks.keystone}</td>
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
                    <td>
                      <button
                        className={styles.rowButton}
                        style={{ color: "inherit", cursor: "pointer" }}
                        onClick={() => handlePlayerClick(entry.puuid, entry.riot_id, entry.tag_line)}
                        title={`View ${entry.riot_id}#${entry.tag_line}'s dashboard`}
                      >
                        {entry.riot_id}
                      </button>
                    </td>
                    <td>{entry.champion}</td>
                    <td>{entry.role}</td>
                    <td>
                      {entry.kills}/{entry.deaths}/{entry.assists}
                    </td>
                    <td>{entry.cs}</td>
                    <td>{entry.gold_earned.toLocaleString()}</td>
                    <td>{entry.total_damage.toLocaleString()}</td>
                    <td>{entry.vision_score}</td>
                    <td><ItemStrip items={entry.items} version={ddVersion} itemNames={itemNames} /></td>
                    <td>{runeMap[entry.perks.keystone] ?? entry.perks.keystone}</td>
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

        {/* ── Gold Differential Timeline ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Gold Differential Timeline</h2>
              <p className={styles.sectionCopy}>
                Blue Team total gold minus Red Team total gold · per minute
              </p>
            </div>
          </div>
          {!timelineAvailable ? (
            <article className={styles.dataCard}>
              <p className={styles.small} style={{ lineHeight: 1.7 }}>
                Timeline data is not available for this match. To enable the gold differential
                chart, re-ingest this player with{" "}
                <code>fetch_timeline=true</code> via{" "}
                <code>POST /ingest/player</code>.
              </p>
            </article>
          ) : goldDiffPoints && goldDiffPoints.length >= 2 ? (
            <GoldDiffChart points={goldDiffPoints} />
          ) : (
            <p style={{ opacity: 0.5, fontSize: 13, padding: 8 }}>Loading gold differential…</p>
          )}
        </section>
      </div>
    </main>
  );
}
