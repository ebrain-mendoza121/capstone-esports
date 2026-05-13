"use client";

import { FormEvent, useState } from "react";
import AppFrame from "@/components/layout/AppFrame";
import RosterInputGroup from "@/components/forms/RosterInputGroup";
import PageHeader from "@/components/ui/PageHeader";
import {
  PlatformCode,
  PlayerInsightInput,
  PlayerInsightInputForm,
  PlayerRoleCode,
  RoleMatchup,
  TeamMatchupResponse,
  TeamPlayerResult,
  ChampionMatchupFlag,
  requestMatchupInsights,
} from "@/lib/insightsApi";
import useChampionOptions from "@/lib/useChampionOptions";
import styles from "@/styles/analytics-flow.module.css";

function pct(v: number | null) {
  return v !== null && v !== undefined ? `${(v * 100).toFixed(1)}%` : "—";
}
function fmt(v: number | null, d = 2) {
  return v !== null && v !== undefined ? v.toFixed(d) : "—";
}

function WinBar({ blueProb, redProb }: { blueProb: number; redProb: number }) {
  const blueWidth = Math.round(blueProb * 100);
  return (
    <div style={{ display: "flex", borderRadius: 8, overflow: "hidden", height: 32, marginTop: 12 }}>
      <div style={{ width: `${blueWidth}%`, background: "var(--color-win)", display: "flex", alignItems: "center", justifyContent: "center", color: "#061014", fontWeight: 700, fontSize: 14 }}>
        Blue {(blueProb * 100).toFixed(1)}%
      </div>
      <div style={{ width: `${100 - blueWidth}%`, background: "var(--color-loss)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 14 }}>
        Red {(redProb * 100).toFixed(1)}%
      </div>
    </div>
  );
}

function RoleMatchupRow({ m }: { m: RoleMatchup }) {
  const edgeCls =
    m.overall_edge === "blue" ? styles.badgeWin
    : m.overall_edge === "red" ? styles.badgeLoss
    : styles.badge;
  return (
    <tr>
      <td><strong>{m.role}</strong></td>
      <td>{m.blue_player ?? "—"}</td>
      <td>{pct(m.win_rate?.blue ?? null)}</td>
      <td>{fmt(m.kda?.blue ?? null)}</td>
      <td><span className={edgeCls}>{m.edge_label ?? m.overall_edge}</span></td>
      <td>{m.red_player ?? "—"}</td>
      <td>{pct(m.win_rate?.red ?? null)}</td>
      <td>{fmt(m.kda?.red ?? null)}</td>
    </tr>
  );
}

function RoleFitBadge({ fit }: { fit: string }) {
  if (fit === "native")   return <span className={styles.badgeWin} style={{ fontSize: "0.72rem" }}>native</span>;
  if (fit === "flex")     return <span className={styles.badge}    style={{ fontSize: "0.72rem" }}>~ flex</span>;
  if (fit === "off-meta") return <span className={styles.badgeLoss} style={{ fontSize: "0.72rem" }}>off-meta</span>;
  return null;
}

/** Compact rec card shown below the table for players who didn't pick a champion */
function MiniRecCard({ player, side }: { player: TeamPlayerResult; side: "blue" | "red" }) {
  const borderColor = side === "blue" ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)";
  const fitBadge    = side === "blue" ? styles.badgeWin : styles.badgeLoss;
  return (
    <article
      className={styles.dataCard}
      style={{ border: `1px solid ${borderColor}`, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{player.summoner_name}</span>
        <span className={styles.badgeNeutral} style={{ fontSize: "0.68rem" }}>
          {player.declared_role ?? player.primary_role ?? "?"}
        </span>
      </div>
      {(player.recommended_champions ?? []).map((r, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "4px 8px",
            background: "rgba(255,255,255,0.04)",
            borderRadius: 4,
          }}
        >
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <strong style={{ fontSize: "0.82rem" }}>{r.champion_name}</strong>
            {r.playstyle_match && (
              <span className={fitBadge} style={{ fontSize: "0.65rem" }}>fits playstyle</span>
            )}
          </div>
          <span style={{ fontSize: "0.7rem", opacity: 0.7 }}>
            {(r.smoothed_win_rate * 100).toFixed(1)}% · {r.games_played}g
          </span>
        </div>
      ))}
    </article>
  );
}

/** Lane-by-lane champion comparison table */
function ChampionPicksMatchup({
  bluePlayers,
  redPlayers,
}: {
  bluePlayers: TeamPlayerResult[];
  redPlayers: TeamPlayerResult[];
}) {
  const playersWithoutChampion = [
    ...bluePlayers.filter((p) => !p.champion_meta && (p.recommended_champions ?? []).length > 0).map((p) => ({ p, side: "blue" as const })),
    ...redPlayers.filter((p) => !p.champion_meta && (p.recommended_champions ?? []).length > 0).map((p) => ({ p, side: "red" as const })),
  ];

  return (
    <section className={styles.sectionCard}>
      <h2 className={styles.sectionTitle}>Champion Picks</h2>

      {/* Lane-by-lane table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th style={{ color: "var(--color-win)", textAlign: "left" }}>Blue</th>
              <th>Role</th>
              <th>Champion</th>
              <th>Type</th>
              <th>Fit</th>
              <th style={{ width: 32, textAlign: "center" }}></th>
              <th style={{ color: "var(--color-loss)", textAlign: "right" }}>Red</th>
              <th style={{ textAlign: "right" }}>Role</th>
              <th style={{ textAlign: "right" }}>Champion</th>
              <th style={{ textAlign: "right" }}>Type</th>
              <th style={{ textAlign: "right" }}>Fit</th>
            </tr>
          </thead>
          <tbody>
            {bluePlayers.map((blue, i) => {
              const red = redPlayers[i];
              if (!red) return null;
              const blueChamp = blue.champion_meta;
              const redChamp  = red.champion_meta;
              const blueRec   = (blue.recommended_champions ?? [])[0];
              const redRec    = (red.recommended_champions ?? [])[0];
              return (
                <tr key={i}>
                  {/* Blue side */}
                  <td style={{ fontWeight: 600 }}>{blue.summoner_name ?? "—"}</td>
                  <td>
                    <span className={styles.badgeNeutral} style={{ fontSize: "0.72rem" }}>
                      {blue.declared_role ?? blue.primary_role ?? "—"}
                    </span>
                  </td>
                  <td>
                    {blueChamp ? (
                      <strong>{blueChamp.name}</strong>
                    ) : blueRec ? (
                      <span style={{ opacity: 0.6, fontStyle: "italic" }}>{blueRec.champion_name}</span>
                    ) : (
                      <span className={styles.emptyState}>—</span>
                    )}
                  </td>
                  <td>
                    {blueChamp?.tags && blueChamp.tags.length > 0 ? (
                      <span className={styles.badge} style={{ fontSize: "0.7rem" }}>
                        {blueChamp.tags.join(" / ")}
                      </span>
                    ) : "—"}
                  </td>
                  <td><RoleFitBadge fit={blueChamp ? blue.role_champion_fit : "unknown"} /></td>

                  {/* Divider */}
                  <td style={{ textAlign: "center", fontWeight: 700, opacity: 0.4 }}>vs</td>

                  {/* Red side (right-aligned) */}
                  <td style={{ fontWeight: 600, textAlign: "right" }}>{red.summoner_name ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    <span className={styles.badgeNeutral} style={{ fontSize: "0.72rem" }}>
                      {red.declared_role ?? red.primary_role ?? "—"}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {redChamp ? (
                      <strong>{redChamp.name}</strong>
                    ) : redRec ? (
                      <span style={{ opacity: 0.6, fontStyle: "italic" }}>{redRec.champion_name}</span>
                    ) : (
                      <span className={styles.emptyState}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {redChamp?.tags && redChamp.tags.length > 0 ? (
                      <span className={styles.badge} style={{ fontSize: "0.7rem" }}>
                        {redChamp.tags.join(" / ")}
                      </span>
                    ) : "—"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <RoleFitBadge fit={redChamp ? red.role_champion_fit : "unknown"} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* AI suggestions grid — only for players without a champion */}
      {playersWithoutChampion.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: "0.82rem", fontWeight: 600, opacity: 0.7, marginBottom: 12 }}>
            AI Champion Suggestions (players without a pick)
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
            {playersWithoutChampion.map(({ p, side }, i) => (
              <MiniRecCard key={i} player={p} side={side} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function CounterFlagsSection({ flags }: { flags: ChampionMatchupFlag[] }) {
  if (!flags || flags.length === 0) return null;
  const favorable   = flags.filter((f) => f.type === "favorable_for_blue");
  const unfavorable = flags.filter((f) => f.type === "unfavorable_for_blue");

  return (
    <section className={styles.sectionCard}>
      <h2 className={styles.sectionTitle}>Champion Matchup Counter Intel</h2>
      {favorable.length > 0 && (
        <>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: 8, color: "var(--color-win)" }}>
            Favorable for Blue
          </h3>
          <ul className={styles.bulletList} style={{ marginBottom: 16 }}>
            {favorable.map((f, i) => (
              <li key={i}>
                <strong>{f.blue_champion_name}</strong> vs <strong>{f.red_champion_name}</strong>
                {f.role ? ` (${f.role})` : ""} — Blue wins {(f.blue_win_rate * 100).toFixed(1)}%
                <span className={styles.badge} style={{ marginLeft: 8, fontSize: "0.72rem" }}>
                  {f.confidence} · {f.games_played} games
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {unfavorable.length > 0 && (
        <>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: 8, color: "var(--color-loss)" }}>
            Unfavorable for Blue
          </h3>
          <ul className={styles.bulletList}>
            {unfavorable.map((f, i) => (
              <li key={i}>
                <strong>{f.blue_champion_name}</strong> vs <strong>{f.red_champion_name}</strong>
                {f.role ? ` (${f.role})` : ""} — Blue wins only {(f.blue_win_rate * 100).toFixed(1)}%
                <span className={styles.badge} style={{ marginLeft: 8, fontSize: "0.72rem" }}>
                  {f.confidence} · {f.games_played} games
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function MiniPlayerTable({ players }: { players: TeamPlayerResult[] }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Player</th><th>Role</th><th>Champion</th>
            <th>Games</th><th>Win Rate</th><th>KDA</th><th>CS/Min</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => (
            <tr key={i}>
              <td>{p.summoner_name ?? "—"}</td>
              <td>{p.declared_role ?? p.primary_role ?? "—"}</td>
              <td>{p.champion_meta?.name ?? "—"}</td>
              <td>{p.games_in_window}</td>
              <td>{pct(p.win_rate_20)}</td>
              <td>{fmt(p.avg_kda_20)}</td>
              <td>{fmt(p.avg_cs_per_min_20)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function createEmptyPlayer(): PlayerInsightInputForm {
  return { gameName: "", tagLine: "", role: "", champion: "" };
}
const emptyTeam = Array.from({ length: 5 }, createEmptyPlayer);

function normalizePlayers(players: PlayerInsightInputForm[]): PlayerInsightInput[] | null {
  const normalized = players.map((p) => ({
    gameName: p.gameName.trim(),
    tagLine: p.tagLine.trim(),
    role: p.role,
    champion: p.champion.trim() || undefined,
  }));
  if (normalized.some((p) => !p.gameName || !p.tagLine || !p.role)) return null;
  return normalized.map((p) => ({ ...p, role: p.role as PlayerRoleCode }));
}

export default function MatchupInsightsPage() {
  const { championOptions, loadingChampionOptions } = useChampionOptions();
  const [teamAPlatform, setTeamAPlatform] = useState<PlatformCode | "">("");
  const [teamBPlatform, setTeamBPlatform] = useState<PlatformCode | "">("");
  const [teamAPlayers, setTeamAPlayers] = useState<PlayerInsightInputForm[]>(emptyTeam);
  const [teamBPlayers, setTeamBPlayers] = useState<PlayerInsightInputForm[]>(emptyTeam);
  const [result, setResult] = useState<TeamMatchupResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateA = (i: number, f: keyof PlayerInsightInputForm, v: string) =>
    setTeamAPlayers((prev) => prev.map((p, idx) => (idx === i ? { ...p, [f]: v } : p)));
  const updateB = (i: number, f: keyof PlayerInsightInputForm, v: string) =>
    setTeamBPlayers((prev) => prev.map((p, idx) => (idx === i ? { ...p, [f]: v } : p)));

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    const cleanA = normalizePlayers(teamAPlayers);
    const cleanB = normalizePlayers(teamBPlayers);
    if (!cleanA || !cleanB) {
      setErrorMessage("Complete Game Name, Tag Line, and Role for all players on both teams.");
      return;
    }
    if (!teamAPlatform || !teamBPlatform) {
      setErrorMessage("Select a platform for both Blue Team and Red Team.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await requestMatchupInsights({
        teamAPlatform,
        teamBPlatform,
        teamAPlayers: cleanA,
        teamBPlayers: cleanB,
      });
      setResult(response);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to generate matchup insights.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Flow 3"
        title="Matchup Insights"
        description="Compare two 5-player teams head-to-head. Get win probability, per-role edges, composition archetypes, and threat scores."
        backHref="/tools"
        backLabel="Back to Tools"
      />

      <form onSubmit={handleSubmit}>
        <section className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>5v5 Matchup Input</h2>
          <hr className={styles.divider} />
          <div className={styles.teamGrid}>
            <RosterInputGroup
              title="Blue Team"
              description="Primary lineup. All players share Blue Team platform."
              players={teamAPlayers}
              idPrefix="team-a-player"
              platform={teamAPlatform}
              championOptions={championOptions}
              loadingChampions={loadingChampionOptions}
              onPlatformChange={(p) => setTeamAPlatform(p as PlatformCode | "")}
              onPlayerChange={updateA}
            />
            <RosterInputGroup
              title="Red Team"
              description="Opposition lineup. All players share Red Team platform."
              players={teamBPlayers}
              idPrefix="team-b-player"
              platform={teamBPlatform}
              championOptions={championOptions}
              loadingChampions={loadingChampionOptions}
              onPlatformChange={(p) => setTeamBPlatform(p as PlatformCode | "")}
              onPlayerChange={updateB}
            />
          </div>
          <hr className={styles.divider} />
          {errorMessage && <p className={styles.statusError}>{errorMessage}</p>}
          <div className={styles.submitRow}>
            <button
              className={`${styles.buttonPrimary} ${styles.buttonLarge}`}
              type="submit"
              disabled={submitting}
            >
              {submitting ? "Analyzing matchup…" : "Generate Matchup Insights"}
            </button>
          </div>
        </section>
      </form>

      {/* ── Results ── */}
      {result && (
        <>
          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Win Probability</h2>
            <p className={styles.sectionText}>
              Method: <strong>{result.prediction_method.replace("_", " ")}</strong>
            </p>
            <WinBar blueProb={result.blue_win_probability} redProb={result.red_win_probability} />
            <div className={styles.twoCol} style={{ marginTop: 16 }}>
              <article className={styles.dataCard}>
                <h3>Blue Team Advantages</h3>
                {result.key_advantages.blue.length === 0
                  ? <p className={styles.emptyState}>No clear edge</p>
                  : <ul className={styles.bulletList}>{result.key_advantages.blue.map((a, i) => <li key={i}>{a}</li>)}</ul>}
              </article>
              <article className={styles.dataCard}>
                <h3>Red Team Advantages</h3>
                {result.key_advantages.red.length === 0
                  ? <p className={styles.emptyState}>No clear edge</p>
                  : <ul className={styles.bulletList}>{result.key_advantages.red.map((a, i) => <li key={i}>{a}</li>)}</ul>}
              </article>
            </div>
          </section>

          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Lane Edge Summary</h2>
            <div className={styles.kpiGrid}>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Blue Lanes Winning</p>
                <strong className={styles.kpiValue}>{result.lane_edges.blue_lanes_winning}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Red Lanes Winning</p>
                <strong className={styles.kpiValue}>{result.lane_edges.red_lanes_winning}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Even Lanes</p>
                <strong className={styles.kpiValue}>{result.lane_edges.even_lanes}</strong>
              </article>
            </div>
          </section>

          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Role-by-Role Breakdown</h2>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Blue Player</th><th>Blue WR</th><th>Blue KDA</th>
                    <th>Edge</th>
                    <th>Red Player</th><th>Red WR</th><th>Red KDA</th>
                  </tr>
                </thead>
                <tbody>
                  {result.role_matchups.map((m, i) => <RoleMatchupRow key={i} m={m} />)}
                </tbody>
              </table>
            </div>
          </section>

          {/* Champion Matchup Counter Intel */}
          <CounterFlagsSection flags={result.champion_matchup_flags ?? []} />

          {/* Champion Picks — lane-by-lane comparison table */}
          <ChampionPicksMatchup
            bluePlayers={result.blue_team.players}
            redPlayers={result.red_team.players}
          />

          <section className={styles.sectionCard}>
            <div className={styles.twoCol}>
              <article className={styles.dataCard}>
                <h3>Blue Team — {result.blue_team.composition_archetype}</h3>
                {result.blue_team.team_dna && (
                  <p className={styles.sectionText}>
                    {result.blue_team.team_dna.label} — {result.blue_team.team_dna.tagline}
                  </p>
                )}
                <MiniPlayerTable players={result.blue_team.players} />
                {result.blue_team.synergy_flags.length > 0 && (
                  <>
                    <h4 style={{ marginTop: 12 }}>Synergy</h4>
                    <ul className={styles.bulletList}>
                      {result.blue_team.synergy_flags.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </>
                )}
                {result.blue_team.gaps.length > 0 && (
                  <>
                    <h4 style={{ marginTop: 8 }}>Gaps</h4>
                    <ul className={styles.bulletList}>
                      {result.blue_team.gaps.map((g, i) => <li key={i}>{g}</li>)}
                    </ul>
                  </>
                )}
                {result.blue_team.predicted_carry && (
                  <p style={{ marginTop: 8 }}>
                    <span className={styles.badgeWin}>
                      Predicted Carry: {result.blue_team.predicted_carry.summoner_name}
                    </span>
                  </p>
                )}
              </article>

              <article className={styles.dataCard}>
                <h3>Red Team — {result.red_team.composition_archetype}</h3>
                {result.red_team.team_dna && (
                  <p className={styles.sectionText}>
                    {result.red_team.team_dna.label} — {result.red_team.team_dna.tagline}
                  </p>
                )}
                <MiniPlayerTable players={result.red_team.players} />
                {result.red_team.synergy_flags.length > 0 && (
                  <>
                    <h4 style={{ marginTop: 12 }}>Synergy</h4>
                    <ul className={styles.bulletList}>
                      {result.red_team.synergy_flags.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </>
                )}
                {result.red_team.gaps.length > 0 && (
                  <>
                    <h4 style={{ marginTop: 8 }}>Gaps</h4>
                    <ul className={styles.bulletList}>
                      {result.red_team.gaps.map((g, i) => <li key={i}>{g}</li>)}
                    </ul>
                  </>
                )}
                {result.red_team.predicted_carry && (
                  <p style={{ marginTop: 8 }}>
                    <span className={styles.badgeLoss}>
                      Predicted Carry: {result.red_team.predicted_carry.summoner_name}
                    </span>
                  </p>
                )}
              </article>
            </div>
          </section>
        </>
      )}

      {submitting && (
        <section className={styles.sectionCard}>
          <p className={styles.statusInfo}>Fetching stats for all 10 players and running matchup model…</p>
        </section>
      )}

      {!submitting && !result && !errorMessage && (
        <section className={styles.sectionCard}>
          <p className={styles.emptyState}>Enter both teams above and click Generate Matchup Insights.</p>
        </section>
      )}
    </AppFrame>
  );
}
