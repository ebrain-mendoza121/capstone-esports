"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

type GameSlug = "league-of-legends" | "valorant";

const GAME_OPTIONS: Array<{ value: GameSlug; label: string; tag: string }> = [
  { value: "league-of-legends", label: "League of Legends", tag: "Macro + Objective" },
  { value: "valorant", label: "Valorant", tag: "Entry + Utility" },
];

export default function Home() {
  const router = useRouter();
  const [riotId, setRiotId] = useState("18178178");
  const [selectedGame, setSelectedGame] = useState<GameSlug>("league-of-legends");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const cleanRiotId = riotId.trim();
    if (!cleanRiotId) {
      return;
    }

    const params = new URLSearchParams({ riotId: cleanRiotId });
    router.push(`/dashboard/${selectedGame}?${params.toString()}`);
  };

  return (
    <main className={styles.page}>
      <div className={styles.backdrop} aria-hidden="true" />
      <div className={styles.gridMask} aria-hidden="true" />

      <section className={styles.shell}>
        <aside className={styles.leadPanel}>
          <p className={styles.kicker}>Capstone Esports Lab</p>
          <h1 className={styles.title}>Competitive Form Intelligence</h1>
          <p className={styles.summary}>
            Launch a game-specific control board with KPI telemetry, role-impact radar, performance
            trends, and match-by-match diagnostics.
          </p>

          <ul className={styles.signalRail}>
            <li>
              <span>Realtime Sim</span>
              <strong>Adaptive trend modeling</strong>
            </li>
            <li>
              <span>Player Scope</span>
              <strong>Riot ID specific profile</strong>
            </li>
            <li>
              <span>Coaching Feed</span>
              <strong>Automated tactical insights</strong>
            </li>
          </ul>
        </aside>

        <section className={styles.formPanel}>
          <div className={styles.formTop}>
            <p className={styles.formEyebrow}>Session Setup</p>
            <p className={styles.formCopy}>Choose your title and deploy the analytics dashboard.</p>
          </div>

          <form className={styles.form} onSubmit={handleSubmit}>
            <label className={styles.field} htmlFor="riot-id">
              Riot Games ID
              <input
                id="riot-id"
                className={styles.input}
                placeholder="e.g. 18178178"
                value={riotId}
                onChange={(event) => setRiotId(event.target.value)}
                required
              />
            </label>

            <label className={styles.field} htmlFor="game-select">
              Game
              <select
                id="game-select"
                className={styles.select}
                value={selectedGame}
                onChange={(event) => setSelectedGame(event.target.value as GameSlug)}
              >
                {GAME_OPTIONS.map((gameOption) => (
                  <option key={gameOption.value} value={gameOption.value}>
                    {gameOption.label} - {gameOption.tag}
                  </option>
                ))}
              </select>
            </label>

            <button className={styles.button} type="submit">
              Open Tactical Dashboard
            </button>
          </form>
        </section>
      </section>
    </main>
  );
}
