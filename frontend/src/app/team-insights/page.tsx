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
  TeamBuildResponse,
  TeamPlayerResult,
  requestTeamInsights,
} from "@/lib/insightsApi";
import useChampionOptions from "@/lib/useChampionOptions";
import styles from "@/styles/analytics-flow.module.css";

function pct(v: number | null) {
  return v !== null && v !== undefined ? `${(v * 100).toFixed(1)}%` : "—";
}
function fmt(v: number | null, d = 2) {
  return v !== null && v !== undefined ? v.toFixed(d) : "—";
}

function ConfidenceBadge({ level }: { level: string }) {
  const cls =
    level === "high" ? styles.badgeWin : level === "medium" ? styles.badge : styles.badgeLoss;
  return <span className={cls}>{level}</span>;
}

function PlayerRow({ p }: { p: TeamPlayerResult }) {
  return (
    <tr>
      <td>
        <strong>{p.summoner_name ?? "—"}</strong>
        {p.error ? <span className={styles.badgeLoss}> error</span> : null}
      </td>
      <td>{p.declared_role ?? p.primary_role ?? "—"}</td>
      <td>{p.champion_meta?.name ?? "—"}</td>
      <td>{p.games_in_window}</td>
      <td><ConfidenceBadge level={p.confidence} /></td>
      <td>{pct(p.win_rate_20)}</td>
      <td>{fmt(p.avg_kda_20)}</td>
      <td>{fmt(p.avg_cs_per_min_20)}</td>
      <td>{fmt(p.avg_kill_part_20)}</td>
      <td>{fmt(p.avg_vision_per_min_20)}</td>
    </tr>
  );
}

function createEmptyPlayer(): PlayerInsightInputForm {
  return { gameName: "", tagLine: "", role: "", champion: "" };
}

const defaultRoster = Array.from({ length: 5 }, createEmptyPlayer);

export default function TeamInsightsPage() {
  const { championOptions, loadingChampionOptions } = useChampionOptions();
  const [teamPlatform, setTeamPlatform] = useState<PlatformCode | "">("");
  const [players, setPlayers] = useState<PlayerInsightInputForm[]>(defaultRoster);
  const [result, setResult] = useState<TeamBuildResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updatePlayer = (index: number, field: keyof PlayerInsightInputForm, value: string) => {
    setPlayers((prev) =>
      prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)),
    );
  };

  const normalizePlayers = (): PlayerInsightInput[] | null => {
    const normalized = players.map((p) => ({
      gameName: p.gameName.trim(),
      tagLine: p.tagLine.trim(),
      role: p.role,
    }));
    if (normalized.some((p) => !p.gameName || !p.tagLine || !p.role)) return null;
    return normalized.map((p) => ({ ...p, role: p.role as PlayerRoleCode }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    const payloadPlayers = normalizePlayers();
    if (!payloadPlayers) {
      setErrorMessage("Please complete Game Name, Tag Line, and Role for all 5 players.");
      return;
    }
    if (!teamPlatform) {
      setErrorMessage("Select a platform for the team.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await requestTeamInsights({ platform: teamPlatform, players: payloadPlayers });
      setResult(response);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to generate team insights.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Flow 2"
        title="Team Insights"
        description="Enter 5 players with role to analyze team composition, stats, strengths, and AI-driven threat scores."
        backHref="/"
        backLabel="Back to Home"
      />

      <form onSubmit={handleSubmit} className={styles.formStack}>
        <RosterInputGroup
          title="Team Roster"
          description="Enter Game Name, Tag Line, Role, and optionally Champion for all 5 players."
          players={players}
          idPrefix="team-player"
          platform={teamPlatform}
          championOptions={championOptions}
          loadingChampions={loadingChampionOptions}
          onPlatformChange={(p) => setTeamPlatform(p as PlatformCode | "")}
          onPlayerChange={updatePlayer}
        />

        <section className={styles.sectionCard}>
          {errorMessage && <p className={styles.statusError}>{errorMessage}</p>}
          <div className={styles.submitRow}>
            <button
              className={`${styles.buttonPrimary} ${styles.buttonLarge}`}
              type="submit"
              disabled={submitting}
            >
              {submitting ? "Analyzing…" : "Analyze Team"}
            </button>
          </div>
        </section>
      </form>

      {/* ── Results ── */}
      {result && (
        <>
          {/* Composition header */}
          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Composition</h2>
            <div className={styles.inlineList}>
              <span className={styles.badgeNeutral}>
                Archetype: <strong>{result.composition_archetype}</strong>
              </span>
              {result.team_dna && (
                <span className={styles.badge}>
                  {result.team_dna.emoji} {result.team_dna.label} — {result.team_dna.tagline}
                </span>
              )}
              {result.predicted_carry && (
                <span className={styles.badgeWin}>
                  Predicted Carry: {result.predicted_carry.summoner_name}
                  {" "}(score {result.predicted_carry.carry_score.toFixed(2)})
                </span>
              )}
            </div>
          </section>

          {/* Per-player stats */}
          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Player Stats (last 20 games)</h2>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Role</th>
                    <th>Champion</th>
                    <th>Games</th>
                    <th>Conf.</th>
                    <th>Win Rate</th>
                    <th>KDA</th>
                    <th>CS/Min</th>
                    <th>Kill Part.</th>
                    <th>Vision/Min</th>
                  </tr>
                </thead>
                <tbody>
                  {result.players.map((p, i) => <PlayerRow key={i} p={p} />)}
                </tbody>
              </table>
            </div>
          </section>

          {/* Team aggregates */}
          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Team Averages</h2>
            <div className={styles.kpiGrid}>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Win Rate</p>
                <strong className={styles.kpiValue}>{pct(result.team_stats.win_rate_20)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>KDA</p>
                <strong className={styles.kpiValue}>{fmt(result.team_stats.avg_kda_20)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>CS/Min</p>
                <strong className={styles.kpiValue}>{fmt(result.team_stats.avg_cs_per_min_20)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Kill Part.</p>
                <strong className={styles.kpiValue}>{pct(result.team_stats.avg_kill_part_20)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Gold/Min</p>
                <strong className={styles.kpiValue}>{fmt(result.team_stats.avg_gold_per_min_20, 0)}</strong>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Players w/ Data</p>
                <strong className={styles.kpiValue}>{result.team_stats.players_with_data}</strong>
              </article>
            </div>
          </section>

          {/* Strengths + Gaps */}
          <section className={styles.sectionCard}>
            <div className={styles.twoCol}>
              <article className={styles.dataCard}>
                <h3>Strengths</h3>
                {result.strengths.length === 0
                  ? <p className={styles.emptyState}>No strong signals detected.</p>
                  : <ul className={styles.bulletList}>{result.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>}
              </article>
              <article className={styles.dataCard}>
                <h3>Gaps / Risks</h3>
                {result.gaps.length === 0
                  ? <p className={styles.emptyState}>No gaps detected.</p>
                  : <ul className={styles.bulletList}>{result.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>}
              </article>
            </div>
          </section>

          {/* Synergy flags */}
          {result.synergy_flags.length > 0 && (
            <section className={styles.sectionCard}>
              <h2 className={styles.sectionTitle}>Synergy Analysis</h2>
              <ul className={styles.bulletList}>
                {result.synergy_flags.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            </section>
          )}

          {/* Threat scores */}
          {result.threat_scores.length > 0 && (
            <section className={styles.sectionCard}>
              <h2 className={styles.sectionTitle}>Threat Scores</h2>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr><th>Player</th><th>Threat Score</th><th>Win Rate</th><th>KDA</th></tr>
                  </thead>
                  <tbody>
                    {result.threat_scores.map((t, i) => (
                      <tr key={i}>
                        <td>{t.summoner_name}</td>
                        <td><strong>{t.threat_score.toFixed(2)}</strong></td>
                        <td>{pct(t.win_rate_20)}</td>
                        <td>{fmt(t.avg_kda_20)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}

      {submitting && (
        <section className={styles.sectionCard}>
          <p className={styles.statusInfo}>Fetching player stats and analyzing composition…</p>
        </section>
      )}

      {!submitting && !result && !errorMessage && (
        <section className={styles.sectionCard}>
          <p className={styles.emptyState}>Enter five players above and click Analyze Team.</p>
        </section>
      )}
    </AppFrame>
  );
}
