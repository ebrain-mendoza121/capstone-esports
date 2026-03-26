"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "@/app/mvp.module.css";
import {
  QueueCode,
  IngestPlayerInput,
  MockApiError,
  PlayerSummary,
  frontendMvpClient,
} from "@/lib/frontendMvpClient";

const defaultForm: IngestPlayerInput = {
  gameName: "",
  tagLine: "",
  platform: "NA1",
  matchCount: 20,
  queue: 420,
};

export default function PlayerSearchPage() {
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
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.hero}>
          <p className={styles.eyebrow}>Frontend MVP · Page 1</p>
          <h1 className={styles.title}>League of Legends Player Search</h1>
          <p className={styles.subtitle}>
            League of Legends entry point for the flow. Ingest by Riot ID + tag, or jump into an existing player to
            generate the `puuid` required by all downstream screens.
          </p>
        </header>

        {errorMessage ? <div className={styles.error}>{errorMessage}</div> : null}

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Ingest Form</h2>
              <p className={styles.sectionCopy}>Create or refresh a player profile in the mock dataset.</p>
            </div>
          </div>

          <form className={styles.formGrid} onSubmit={handleSubmit}>
            <label className={styles.field}>
              Game Name
              <input
                className={styles.input}
                value={form.gameName}
                onChange={(event) => setForm({ ...form, gameName: event.target.value })}
                placeholder="e.g. Faker"
                required
              />
            </label>

            <label className={styles.field}>
              Tag Line
              <input
                className={styles.input}
                value={form.tagLine}
                onChange={(event) => setForm({ ...form, tagLine: event.target.value })}
                placeholder="e.g. KR1"
                required
              />
            </label>

            <label className={styles.field}>
              Platform
              <select
                className={styles.select}
                value={form.platform}
                onChange={(event) => setForm({ ...form, platform: event.target.value })}
              >
                <option value="NA1">NA1</option>
                <option value="EUW1">EUW1</option>
                <option value="KR">KR</option>
                <option value="LA1">LA1</option>
              </select>
            </label>

            <label className={styles.field}>
              Match Count
              <input
                className={styles.input}
                type="number"
                min={1}
                max={200}
                value={form.matchCount}
                onChange={(event) => setForm({ ...form, matchCount: Number(event.target.value) })}
              />
            </label>

            <label className={styles.field}>
              Queue
              <select
                className={styles.select}
                value={form.queue}
                onChange={(event) => setForm({ ...form, queue: Number(event.target.value) as QueueCode })}
              >
                <option value={420}>420 · Ranked Solo</option>
                <option value={440}>440 · Ranked Flex</option>
              </select>
            </label>

            <button className={styles.buttonPrimary} type="submit" disabled={submitting}>
              {submitting ? "Ingesting..." : "Ingest & Open Dashboard"}
            </button>
          </form>

          <p className={styles.small}>
            Tip: Enter `404`, `503`, or `502` as Game Name to test error-state UI messages.
          </p>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2 className={styles.sectionTitle}>Existing Players</h2>
              <p className={styles.sectionCopy}>Previously ingested player profiles.</p>
            </div>
          </div>

          {loadingPlayers ? (
            <p className={styles.loading}>Loading player registry...</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Riot ID</th>
                    <th>Tag</th>
                    <th>Region</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((player) => (
                    <tr key={player.puuid}>
                      <td>{player.riot_id}</td>
                      <td>#{player.tag_line}</td>
                      <td>{player.region}</td>
                      <td>
                        <button
                          className={styles.buttonGhost}
                          onClick={() => router.push(`/player/${player.puuid}`)}
                          type="button"
                        >
                          Go to Dashboard
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
