"use client";

import { FormEvent, useState } from "react";
import AppFrame from "@/components/layout/AppFrame";
import RosterInputGroup from "@/components/forms/RosterInputGroup";
import InsightResponsePanel from "@/components/ui/InsightResponsePanel";
import PageHeader from "@/components/ui/PageHeader";
import {
  InsightResponse,
  PlatformCode,
  PlayerInsightInput,
  PlayerInsightInputForm,
  PlayerRoleCode,
  requestMatchupInsights,
} from "@/lib/insightsApi";
import useChampionOptions from "@/lib/useChampionOptions";
import styles from "@/styles/analytics-flow.module.css";

function createEmptyPlayer(): PlayerInsightInputForm {
  return {
    gameName: "",
    tagLine: "",
    role: "",
    champion: "",
  };
}

const emptyTeam: PlayerInsightInputForm[] = Array.from({ length: 5 }, createEmptyPlayer);

function normalizePlayers(players: PlayerInsightInputForm[]): PlayerInsightInput[] | null {
  const normalized = players.map((player) => ({
    gameName: player.gameName.trim(),
    tagLine: player.tagLine.trim(),
    role: player.role,
    champion: player.champion.trim(),
  }));

  const hasMissingField = normalized.some(
    (player) => !player.gameName || !player.tagLine || !player.role || !player.champion,
  );

  if (hasMissingField) {
    return null;
  }

  return normalized.map((player) => ({
    ...player,
    role: player.role as PlayerRoleCode,
  }));
}

export default function MatchupInsightsPage() {
  const { championOptions, loadingChampionOptions, championOptionsError } = useChampionOptions();
  const [teamAPlatform, setTeamAPlatform] = useState<PlatformCode | "">("");
  const [teamBPlatform, setTeamBPlatform] = useState<PlatformCode | "">("");
  const [teamAPlayers, setTeamAPlayers] = useState<PlayerInsightInputForm[]>(emptyTeam);
  const [teamBPlayers, setTeamBPlayers] = useState<PlayerInsightInputForm[]>(emptyTeam);
  const [result, setResult] = useState<InsightResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateTeamAPlayer = (index: number, field: keyof PlayerInsightInputForm, value: string) => {
    setTeamAPlayers((previous) =>
      previous.map((player, playerIndex) => (playerIndex === index ? { ...player, [field]: value } : player)),
    );
  };

  const updateTeamBPlayer = (index: number, field: keyof PlayerInsightInputForm, value: string) => {
    setTeamBPlayers((previous) =>
      previous.map((player, playerIndex) => (playerIndex === index ? { ...player, [field]: value } : player)),
    );
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    if (championOptions.length === 0) {
      setResult(null);
      setErrorMessage("Champion options are unavailable right now. Please check backend connectivity and try again.");
      return;
    }

    const cleanTeamA = normalizePlayers(teamAPlayers);
    const cleanTeamB = normalizePlayers(teamBPlayers);

    if (!cleanTeamA || !cleanTeamB) {
      setResult(null);
      setErrorMessage("Please complete Game Name, Tag Line, Role, and Champion for all Team A and Team B players.");
      return;
    }
    if (!teamAPlatform || !teamBPlatform) {
      setResult(null);
      setErrorMessage("Please select a platform for Team A and Team B before generating matchup insights.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await requestMatchupInsights({
        teamAPlatform,
        teamBPlatform,
        teamAPlayers: cleanTeamA,
        teamBPlayers: cleanTeamB,
      });
      setResult(response);
    } catch {
      setResult(null);
      setErrorMessage("Unable to generate matchup insights right now. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Flow 3"
        title="Matchup-Based Insights"
        description="Compare Team A and Team B rosters in a 5 versus 5 setup. Each player requires game name, tag line, role, and champion."
        backHref="/"
        backLabel="Back to Home"
      />

      <form onSubmit={handleSubmit}>
        <section className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>5v5 Matchup Input</h2>
          <p className={styles.sectionText}>
            This flow compares two 5-player teams and is prepared for future matchup endpoint integration.
          </p>
          <hr className={styles.divider} />

          <div className={styles.teamGrid}>
            <RosterInputGroup
              title="Team A"
              description="Primary lineup under evaluation. All players must share Team A platform."
              players={teamAPlayers}
              idPrefix="team-a-player"
              championOptions={championOptions}
              loadingChampionOptions={loadingChampionOptions}
              platform={teamAPlatform}
              onPlatformChange={(platform) => setTeamAPlatform(platform as PlatformCode | "")}
              onPlayerChange={updateTeamAPlayer}
            />
            <RosterInputGroup
              title="Team B"
              description="Team B lineup for matchup comparison. All players must share Team B platform."
              players={teamBPlayers}
              idPrefix="team-b-player"
              championOptions={championOptions}
              loadingChampionOptions={loadingChampionOptions}
              platform={teamBPlatform}
              onPlatformChange={(platform) => setTeamBPlatform(platform as PlatformCode | "")}
              onPlayerChange={updateTeamBPlayer}
            />
          </div>

          <hr className={styles.divider} />
          {loadingChampionOptions ? (
            <p className={styles.statusInfo}>Loading full champion list...</p>
          ) : null}
          {championOptionsError ? <p className={styles.statusError}>{championOptionsError}</p> : null}
          <div className={styles.submitRow}>
            <button
              className={`${styles.buttonPrimary} ${styles.buttonLarge}`}
              type="submit"
              disabled={submitting || loadingChampionOptions || championOptions.length === 0}
            >
              {submitting ? "Generating Matchup Insights..." : "Generate Matchup Insights"}
            </button>
          </div>
        </section>
      </form>

      <InsightResponsePanel
        title="Future AI Matchup Response"
        description="This response panel is intentionally large for long-form AI matchup analysis."
        loading={submitting}
        errorMessage={errorMessage}
        result={result}
        emptyMessage="No matchup insights submitted yet. Enter both teams and click Generate Matchup Insights."
      />
    </AppFrame>
  );
}
