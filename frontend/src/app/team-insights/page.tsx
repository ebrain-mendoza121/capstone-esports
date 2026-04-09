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
  requestTeamInsights,
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

const defaultRoster: PlayerInsightInputForm[] = Array.from({ length: 5 }, createEmptyPlayer);

export default function TeamInsightsPage() {
  const { championOptions, loadingChampionOptions, championOptionsError } = useChampionOptions();
  const [teamPlatform, setTeamPlatform] = useState<PlatformCode | "">("");
  const [players, setPlayers] = useState<PlayerInsightInputForm[]>(defaultRoster);
  const [result, setResult] = useState<InsightResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updatePlayer = (index: number, field: keyof PlayerInsightInputForm, value: string) => {
    setPlayers((previous) =>
      previous.map((player, playerIndex) => (playerIndex === index ? { ...player, [field]: value } : player)),
    );
  };

  const normalizePlayers = (): PlayerInsightInput[] | null => {
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
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    if (championOptions.length === 0) {
      setResult(null);
      setErrorMessage("Champion options are unavailable right now. Please check backend connectivity and try again.");
      return;
    }

    const payloadPlayers = normalizePlayers();
    if (!payloadPlayers) {
      setResult(null);
      setErrorMessage("Please complete Game Name, Tag Line, Role, and Champion for all 5 players.");
      return;
    }
    if (!teamPlatform) {
      setResult(null);
      setErrorMessage("Select one platform for the full team. All 5 players must be on the same platform.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await requestTeamInsights({
        platform: teamPlatform,
        players: payloadPlayers,
      });
      setResult(response);
    } catch {
      setResult(null);
      setErrorMessage("Unable to generate team insights right now. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Flow 2"
        title="Team Insights"
        description="Enter the 5 players you want to analyze as a team. Each player requires game name, tag line, role, and champion."
        backHref="/"
        backLabel="Back to Home"
      />

      <form onSubmit={handleSubmit} className={styles.formStack}>
        <RosterInputGroup
          title="Team Insights"
          description="Enter the 5 players you want to analyze as a team and choose one shared platform."
          players={players}
          idPrefix="team-player"
          championOptions={championOptions}
          loadingChampionOptions={loadingChampionOptions}
          platform={teamPlatform}
          onPlatformChange={(platform) => setTeamPlatform(platform as PlatformCode | "")}
          onPlayerChange={updatePlayer}
        />

        <section className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>Submit Team Analysis</h2>
          <p className={styles.sectionText}>
            Champion dropdowns load from `/champions` to include the full League roster.
          </p>
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
              {submitting ? "Generating Team Insights..." : "Generate Team Insights"}
            </button>
          </div>
        </section>
      </form>

      <InsightResponsePanel
        title="Future AI Team Response"
        description="Large placeholder area reserved for model output."
        loading={submitting}
        errorMessage={errorMessage}
        result={result}
        emptyMessage="No team insights submitted yet. Enter five players and click Generate Team Insights."
      />
    </AppFrame>
  );
}
