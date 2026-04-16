"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppFrame from "@/components/layout/AppFrame";
import FormTextField from "@/components/forms/FormTextField";
import PageHeader from "@/components/ui/PageHeader";
import {
  IngestPlayerInput,
  MockApiError,
  PlayerSummary,
  QueueCode,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";
import { PLATFORM_OPTIONS } from "@/lib/lolData";
import styles from "@/styles/analytics-flow.module.css";

const defaultForm: IngestPlayerInput = {
  gameName: "",
  tagLine: "",
  platform: "NA",
  matchCount: 20,
  queue: 420,
};

export default function IndividualStatsPage() {
  const router = useRouter();

  const [form, setForm] = useState<IngestPlayerInput>(defaultForm);
  const [players, setPlayers] = useState<PlayerSummary[]>([]);
  const [loadingPlayers, setLoadingPlayers] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const loadPlayers = async () => {
      try {
        const response = await frontendMvpClient.listPlayers();
        if (mounted) {
          setPlayers(response);
        }
      } catch {
        if (mounted) {
          setErrorMessage("Could not load existing player profiles. Please refresh.");
        }
      } finally {
        if (mounted) {
          setLoadingPlayers(false);
        }
      }
    };

    void loadPlayers();

    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage(null);

    try {
      const player = await frontendMvpClient.ingestPlayer(form);
      router.push(`/player/${player.puuid}`);
    } catch (error) {
      if (error instanceof MockApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unexpected ingest error. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Flow 1"
        title="See Your Individual Stats"
        description="Analyze one player profile by Riot ID and move directly into dashboard-level stats. This route keeps the original ingest flow and remains ready for player endpoint integration."
        backHref="/"
        backLabel="Back to Home"
      />

      <section className={styles.sectionCard}>
        <div className={styles.inlineActionRow}>
          <div>
            <h2 className={styles.sectionTitle}>Player Lookup</h2>
            <p className={styles.sectionText}>Submit a player to ingest and open the individual dashboard.</p>
          </div>
        </div>

        <hr className={styles.divider} />

        {errorMessage ? (
          <p className={styles.statusError} role="alert">
            {errorMessage}
          </p>
        ) : null}

        <form onSubmit={handleSubmit}>
          <div className={styles.formGridTwo}>
            <FormTextField
              id="gameName"
              label="Game Name"
              value={form.gameName}
              placeholder="e.g. Faker"
              required
              onChange={(value) => setForm({ ...form, gameName: value })}
            />
            <FormTextField
              id="tagLine"
              label="Tag Line"
              value={form.tagLine}
              placeholder="e.g. KR1"
              required
              onChange={(value) => setForm({ ...form, tagLine: value })}
            />

            <div className={styles.fieldGroup}>
              <label className={styles.label} htmlFor="platform">
                Platform
              </label>
              <select
                className={styles.select}
                id="platform"
                value={form.platform}
                onChange={(event) => setForm({ ...form, platform: event.target.value })}
              >
                {PLATFORM_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.label} htmlFor="matchCount">
                Match Count
              </label>
              <input
                className={styles.input}
                id="matchCount"
                type="number"
                min={1}
                max={200}
                value={form.matchCount}
                onChange={(event) => setForm({ ...form, matchCount: Number(event.target.value) })}
              />
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.label} htmlFor="queue">
                Queue
              </label>
              <select
                className={styles.select}
                id="queue"
                value={form.queue}
                onChange={(event) => setForm({ ...form, queue: Number(event.target.value) as QueueCode })}
              >
                <option value={420}>420 · Ranked Solo</option>
                <option value={440}>440 · Ranked Flex</option>
              </select>
            </div>
          </div>

          <div className={styles.inlineActionRow}>
            <button className={styles.buttonPrimary} type="submit" disabled={submitting}>
              {submitting ? "Ingesting..." : "Ingest & Open Dashboard"}
            </button>
          </div>
        </form>
      </section>

      <section className={styles.sectionCard}>
        <h2 className={styles.sectionTitle}>Results</h2>
        <p className={styles.sectionText}>
          Showing players with 10+ matches — sorted by most matches. Ghost participants (opponents from ingested matches with fewer than 10 games) are hidden.
        </p>

        <hr className={styles.divider} />

        {loadingPlayers ? <p className={styles.statusInfo}>Loading player registry...</p> : null}

        {!loadingPlayers && players.length === 0 ? (
          <p className={styles.emptyState}>No players with 10+ matches yet. Ingest a player above with matchCount ≥ 10 to get started.</p>
        ) : null}

        {!loadingPlayers && players.length > 0 ? (
          <div className={styles.playerResults}>
            <div className={`${styles.tableWrap} ${styles.playerTableDesktop}`}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Riot ID</th>
                    <th>Tag</th>
                    <th>Region</th>
                    <th>Matches</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((player) => (
                    <tr key={player.puuid}>
                      <td>{player.riot_id}</td>
                      <td>#{player.tag_line}</td>
                      <td>{player.region}</td>
                      <td>{player.match_count}</td>
                      <td>
                        <button
                          className={styles.buttonSecondary}
                          type="button"
                          onClick={() => router.push(`/player/${player.puuid}`)}
                        >
                          Go to Dashboard
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className={styles.playerCardsMobile}>
              {players.map((player) => (
                <article key={player.puuid} className={styles.playerCardMobile}>
                  <div className={styles.playerCardMobileHeader}>
                    <h3 className={styles.playerCardMobileTitle}>
                      {player.riot_id}
                      <span className={styles.playerCardMobileTag}>#{player.tag_line}</span>
                    </h3>
                    <span className={styles.playerCardMobileRegion}>{player.region}</span>
                  </div>

                  <p className={styles.playerCardMobileStats}>
                    <span>Tracked Matches</span>
                    <strong>{player.match_count}</strong>
                  </p>

                  <button
                    className={`${styles.buttonSecondary} ${styles.playerCardMobileButton}`}
                    type="button"
                    onClick={() => router.push(`/player/${player.puuid}`)}
                  >
                    Go to Dashboard
                  </button>
                </article>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    </AppFrame>
  );
}
