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
      <div style={{ width: `${blueWidth}%`, background: "var(--color-win, #22c55e)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 14 }}>
        Blue {(blueProb * 100).toFixed(1)}%
      </div>
      <div style={{ width: `${100 - blueWidth}%`, background: "var(--color-loss, #ef4444)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 14 }}>
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
        backHref="/"
        backLabel="Back to Home"
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

          <section className={styles.sectionCard}>
            <div className={styles.twoCol}>
              <article className={styles.dataCard}>
                <h3>Blue Team — {result.blue_team.composition_archetype}</h3>
                {result.blue_team.team_dna && (
                  <p className={styles.sectionText}>
                    {result.blue_team.team_dna.emoji} {result.blue_team.team_dna.label} — {result.blue_team.team_dna.tagline}
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
                    {result.red_team.team_dna.emoji} {result.red_team.team_dna.label} — {result.red_team.team_dna.tagline}
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
