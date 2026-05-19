"use client";

import { ChangeEvent, FormEvent, useState } from "react";
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

function PlaystyleBadge({ label }: { label: string | null }) {
  if (!label || label === "unknown" || label === "insufficient_data") {
    return <span className={styles.badge}>—</span>;
  }
  return (
    <span className={styles.badgeNeutral} title={`Recommended: ${label}`}>
      {label}
    </span>
  );
}

function PlayerRow({ p }: { p: TeamPlayerResult }) {
  return (
    <tr>
      <td>
        <strong>{p.summoner_name ?? "—"}</strong>
        {p.error ? <span className={styles.badgeLoss}> error</span> : null}
      </td>
      <td>
        {p.declared_role ?? p.primary_role ?? "—"}
        {p.role_mismatch && p.playstyle_recommended_roles.length > 0 && (
          <span
            className={styles.badgeLoss}
            style={{ marginLeft: 6, fontSize: "0.75em" }}
            title={`Better fit: ${p.playstyle_recommended_roles.join(" / ")}`}
          >
            mismatch
          </span>
        )}
      </td>
      <td>{p.champion_meta?.name ?? "—"}</td>
      <td><PlaystyleBadge label={p.playstyle_label ?? null} /></td>
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

function RoleFitBadge({ fit }: { fit: string }) {
  if (fit === "native")   return <span className={styles.badgeWin}>native</span>;
  if (fit === "flex")     return <span className={styles.badge}>~ flex</span>;
  if (fit === "off-meta") return <span className={styles.badgeLoss}>off-meta</span>;
  return <span className={styles.badge}>—</span>;
}

function ChampionPickCard({ player }: { player: TeamPlayerResult }) {
  const hasChampion = !!player.champion_meta;
  const recs        = player.recommended_champions ?? [];

  return (
    <article className={styles.dataCard} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: "0.9rem" }}>{player.summoner_name ?? "—"}</strong>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {player.primary_role && (
            <span className={styles.badge} style={{ fontSize: "0.68rem" }}>
              {player.primary_role}
            </span>
          )}
          {player.playstyle_label && player.playstyle_label !== "insufficient_data" && (
            <span className={styles.badgeNeutral} style={{ fontSize: "0.68rem" }}>
              {player.playstyle_label}
            </span>
          )}
        </div>
      </div>

      {/* Divider */}
      <hr style={{ border: "none", borderTop: "1px solid rgba(255,255,255,0.07)", margin: 0 }} />

      {/* Champion row */}
      {hasChampion ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <strong style={{ fontSize: "0.92rem" }}>{player.champion_meta!.name}</strong>
          <RoleFitBadge fit={player.role_champion_fit} />
          {player.champion_meta!.tags.length > 0 && (
            <span className={styles.badge} style={{ fontSize: "0.68rem" }}>
              {player.champion_meta!.tags.join(" / ")}
            </span>
          )}
        </div>
      ) : (
        <>
          <p style={{ margin: 0, fontSize: "0.78rem", opacity: 0.5 }}>No champion selected</p>
          {recs.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <p style={{ margin: 0, fontSize: "0.68rem", textTransform: "uppercase", opacity: 0.5 }}>
                AI Suggestions
              </p>
              {recs.map((r, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "5px 8px",
                    background: "rgba(255,255,255,0.04)",
                    borderRadius: 5,
                  }}
                >
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <strong style={{ fontSize: "0.83rem" }}>{r.champion_name}</strong>
                    {r.playstyle_match && (
                      <span className={styles.badgeWin} style={{ fontSize: "0.65rem" }}>playstyle</span>
                    )}
                  </div>
                  <span style={{ fontSize: "0.7rem", opacity: 0.7 }}>
                    {(r.smoothed_win_rate * 100).toFixed(1)}% · {r.games_played}g
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.emptyState} style={{ margin: 0, fontSize: "0.75rem" }}>
              No history — ingest more matches
            </p>
          )}
        </>
      )}
    </article>
  );
}

function createEmptyPlayer(): PlayerInsightInputForm {
  return { gameName: "", tagLine: "", role: "", champion: "" };
}

const defaultRoster = Array.from({ length: 5 }, createEmptyPlayer);

const VALID_ROLES = new Set<PlayerRoleCode>(["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"]);
const VALID_PLATFORMS = new Set<PlatformCode>([
  "NA", "EUW", "EUNE", "KR", "BR", "LAN", "LAS", "JP", "OCE", "TR", "RU",
]);

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (ch === "," && !inQuotes) {
      out.push(cur.trim());
      cur = "";
      continue;
    }
    cur += ch;
  }
  out.push(cur.trim());
  return out;
}

function parseRole(raw: string): PlayerRoleCode | null {
  const value = raw.trim().toUpperCase();
  if (value === "MIDDLE") return "MID";
  if (value === "ADC") return "BOT";
  if (value === "SUP") return "SUPPORT";
  if (VALID_ROLES.has(value as PlayerRoleCode)) return value as PlayerRoleCode;
  return null;
}

export default function TeamInsightsPage() {
  const { championOptions, loadingChampionOptions } = useChampionOptions();
  const [teamPlatform, setTeamPlatform] = useState<PlatformCode | "">("");
  const [players, setPlayers] = useState<PlayerInsightInputForm[]>(defaultRoster);
  const [result, setResult] = useState<TeamBuildResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [csvStatus, setCsvStatus] = useState<string | null>(null);
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
      champion: p.champion.trim() || undefined,
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

  const handleCsvUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setErrorMessage(null);
    setCsvStatus(null);

    try {
      const raw = await file.text();
      const lines = raw
        .replace(/^\uFEFF/, "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.length > 0);

      if (lines.length < 2) {
        throw new Error("CSV must include a header and 5 player rows.");
      }

      const headers = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
      const idx = {
        platform: headers.indexOf("platform"),
        gameName: headers.indexOf("game_name"),
        tagLine: headers.indexOf("tag_line"),
        role: headers.indexOf("role"),
        champion: headers.indexOf("champion"),
      };

      if (idx.platform < 0 || idx.gameName < 0 || idx.tagLine < 0 || idx.role < 0) {
        throw new Error(
          "Missing required columns. Use: platform,game_name,tag_line,role,champion",
        );
      }

      const dataRows = lines.slice(1);
      if (dataRows.length !== 5) {
        throw new Error("Team Insights CSV must contain exactly 5 players.");
      }

      const parsedPlayers: PlayerInsightInputForm[] = [];
      let detectedPlatform: PlatformCode | null = null;

      for (let rowIdx = 0; rowIdx < dataRows.length; rowIdx += 1) {
        const row = splitCsvLine(dataRows[rowIdx]);
        const rowNum = rowIdx + 2;

        const platform = (row[idx.platform] ?? "").toUpperCase().trim();
        const gameName = (row[idx.gameName] ?? "").trim();
        const tagLine = (row[idx.tagLine] ?? "").trim();
        const roleRaw = row[idx.role] ?? "";
        const champion = idx.champion >= 0 ? (row[idx.champion] ?? "").trim() : "";

        if (!VALID_PLATFORMS.has(platform as PlatformCode)) {
          throw new Error(`Row ${rowNum}: invalid platform '${platform}'.`);
        }
        if (!gameName || !tagLine) {
          throw new Error(`Row ${rowNum}: game_name and tag_line are required.`);
        }
        const role = parseRole(roleRaw);
        if (!role) {
          throw new Error(`Row ${rowNum}: invalid role '${roleRaw}'.`);
        }

        if (!detectedPlatform) {
          detectedPlatform = platform as PlatformCode;
        } else if (detectedPlatform !== platform) {
          throw new Error("All rows must use the same platform for Team Insights.");
        }

        parsedPlayers.push({
          gameName,
          tagLine,
          role,
          champion,
        });
      }

      setTeamPlatform(detectedPlatform ?? "");
      setPlayers(parsedPlayers);
      setCsvStatus(`Loaded ${parsedPlayers.length} players from ${file.name}.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to parse CSV.";
      setErrorMessage(msg);
    } finally {
      event.target.value = "";
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Flow 2"
        title="Team Insights"
        description="Enter 5 players with role to analyze team composition, stats, strengths, and AI-driven threat scores."
        backHref="/tools"
        backLabel="Back to Tools"
      />

      <form onSubmit={handleSubmit} className={styles.formStack}>
        <section className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>Upload Team CSV</h2>
          <p className={styles.sectionText}>
            Format required: <strong>platform,game_name,tag_line,role,champion</strong>
          </p>
          <p className={styles.sectionText}>
            Use exactly 5 rows. Role accepted: TOP, JUNGLE, MID, BOT, SUPPORT.
          </p>
          <pre
            style={{
              marginTop: 10,
              padding: 12,
              borderRadius: 8,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              overflowX: "auto",
              fontSize: 12,
              lineHeight: 1.45,
            }}
          >
{`platform,game_name,tag_line,role,champion
KR,T1 Zeus,KR1,TOP,Renekton
KR,T1 Oner,KR1,JUNGLE,Viego
KR,T1 Faker,KR1,MID,Ahri
KR,T1 Gumayusi,KR1,BOT,Jinx
KR,T1 Keria,KR1,SUPPORT,Rakan`}
          </pre>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={handleCsvUpload}
            style={{ marginTop: 10 }}
          />
          {csvStatus && <p className={styles.statusInfo}>{csvStatus}</p>}
        </section>

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
                  {result.team_dna.label} — {result.team_dna.tagline}
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
                    <th>Playstyle</th>
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

          {/* Playstyle Archetypes + Role Recommendations */}
          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Playstyle Archetypes</h2>

            {/* Per-player role recommendations */}
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Declared Role</th>
                    <th>Archetype</th>
                    <th>Recommended Roles</th>
                    <th>Fit</th>
                  </tr>
                </thead>
                <tbody>
                  {result.players.map((p, i) => {
                    const hasPlaystyle = p.playstyle_label && p.playstyle_label !== "insufficient_data";
                    return (
                      <tr key={i}>
                        <td><strong>{p.summoner_name ?? "—"}</strong></td>
                        <td>{p.declared_role ?? p.primary_role ?? "—"}</td>
                        <td><PlaystyleBadge label={p.playstyle_label ?? null} /></td>
                        <td>
                          {hasPlaystyle && p.playstyle_recommended_roles.length > 0
                            ? p.playstyle_recommended_roles.join(", ")
                            : <span className={styles.emptyState}>No data</span>}
                        </td>
                        <td>
                          {hasPlaystyle
                            ? p.role_mismatch
                              ? <span className={styles.badgeLoss}>Mismatch</span>
                              : <span className={styles.badgeWin}>Aligned</span>
                            : <span className={styles.badge}>—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Team-level playstyle warnings */}
            {result.playstyle_warnings && result.playstyle_warnings.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <h3 style={{ marginBottom: 8, fontSize: "0.9rem", fontWeight: 600 }}>
                  Composition Warnings
                </h3>
                <ul className={styles.bulletList}>
                  {result.playstyle_warnings.map((w, i) => (
                    <li key={i} className={styles.badgeLoss} style={{ padding: "6px 10px", marginBottom: 6, borderRadius: 6 }}>
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Champion Picks & Recommendations */}
          <section className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>Champion Picks</h2>
            <p className={styles.sectionText} style={{ marginBottom: 16 }}>
              Players without a selected champion receive AI-driven suggestions filtered to their declared role and playstyle.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
              {result.players.map((p, i) => <ChampionPickCard key={i} player={p} />)}
            </div>
          </section>

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
