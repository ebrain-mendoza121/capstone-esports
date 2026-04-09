import { LOL_ROLE_OPTIONS, PLATFORM_OPTIONS } from "@/lib/lolData";
import { PlayerInsightInputForm, PlayerRoleCode } from "@/lib/insightsApi";
import styles from "@/styles/analytics-flow.module.css";

interface RosterInputGroupProps {
  title: string;
  description: string;
  players: PlayerInsightInputForm[];
  idPrefix: string;
  championOptions: string[];
  loadingChampionOptions?: boolean;
  platform: string;
  onPlatformChange: (platform: string) => void;
  onPlayerChange: (playerIndex: number, field: keyof PlayerInsightInputForm, value: string) => void;
}

export default function RosterInputGroup({
  title,
  description,
  players,
  idPrefix,
  championOptions,
  loadingChampionOptions = false,
  platform,
  onPlatformChange,
  onPlayerChange,
}: RosterInputGroupProps) {
  return (
    <article className={styles.sectionCard}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      <p className={`${styles.sectionText} ${styles.rosterDescription}`}>{description}</p>
      <div className={`${styles.fieldGroup} ${styles.platformField}`}>
        <label className={styles.label} htmlFor={`${idPrefix}-platform`}>
          Team Platform
        </label>
        <select
          className={styles.select}
          id={`${idPrefix}-platform`}
          value={platform}
          required
          onChange={(event) => onPlatformChange(event.target.value)}
        >
          <option value="">Select platform</option>
          {PLATFORM_OPTIONS.map((platformOption) => (
            <option key={platformOption.value} value={platformOption.value}>
              {platformOption.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.rosterGrid}>
        {players.map((player, index) => (
          <section className={styles.playerCard} key={`${idPrefix}-${index}`}>
            <h3 className={styles.playerCardTitle}>Player {index + 1}</h3>
            <div className={styles.playerFieldGrid}>
              <div className={styles.fieldGroup}>
                <label className={styles.label} htmlFor={`${idPrefix}-${index}-game-name`}>
                  Game Name
                </label>
                <input
                  className={styles.input}
                  id={`${idPrefix}-${index}-game-name`}
                  placeholder={`Summoner ${index + 1}`}
                  value={player.gameName}
                  required
                  onChange={(event) => onPlayerChange(index, "gameName", event.target.value)}
                />
              </div>

              <div className={styles.fieldGroup}>
                <label className={styles.label} htmlFor={`${idPrefix}-${index}-tag-line`}>
                  Tag Line
                </label>
                <input
                  className={styles.input}
                  id={`${idPrefix}-${index}-tag-line`}
                  placeholder="e.g. NA1"
                  value={player.tagLine}
                  required
                  onChange={(event) => onPlayerChange(index, "tagLine", event.target.value)}
                />
              </div>

              <div className={styles.fieldGroup}>
                <label className={styles.label} htmlFor={`${idPrefix}-${index}-role`}>
                  Role
                </label>
                <select
                  className={styles.select}
                  id={`${idPrefix}-${index}-role`}
                  value={player.role}
                  required
                  onChange={(event) => onPlayerChange(index, "role", event.target.value as PlayerRoleCode)}
                >
                  <option value="">Select role</option>
                  {LOL_ROLE_OPTIONS.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className={`${styles.fieldGroup} ${styles.fieldSpanFull}`}>
                <label className={styles.label} htmlFor={`${idPrefix}-${index}-champion`}>
                  Champion
                </label>
                <select
                  className={styles.select}
                  id={`${idPrefix}-${index}-champion`}
                  value={player.champion}
                  required
                  disabled={loadingChampionOptions || championOptions.length === 0}
                  onChange={(event) => onPlayerChange(index, "champion", event.target.value)}
                >
                  <option value="">
                    {loadingChampionOptions ? "Loading champions..." : "Select champion"}
                  </option>
                  {championOptions.map((champion) => (
                    <option key={champion} value={champion}>
                      {champion}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </section>
        ))}
      </div>
    </article>
  );
}
