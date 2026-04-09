import { InsightResponse } from "@/lib/insightsApi";
import styles from "@/styles/analytics-flow.module.css";

interface InsightResponsePanelProps {
  title: string;
  description: string;
  loading: boolean;
  errorMessage: string | null;
  result: InsightResponse | null;
  emptyMessage: string;
}

export default function InsightResponsePanel({
  title,
  description,
  loading,
  errorMessage,
  result,
  emptyMessage,
}: InsightResponsePanelProps) {
  return (
    <section className={styles.sectionCard}>
      <div className={styles.responseHeader}>
        <div>
          <h2 className={styles.sectionTitle}>{title}</h2>
          <p className={styles.sectionText}>{description}</p>
        </div>
      </div>

      <hr className={styles.divider} />

      {loading ? <p className={styles.statusInfo}>Analyzing roster data model...</p> : null}
      {!loading && errorMessage ? <p className={styles.statusError}>{errorMessage}</p> : null}

      {!loading && !errorMessage && result ? (
        <div>
          <h3 className={styles.responseHeadline}>{result.headline}</h3>
          <p className={styles.responseSummary}>{result.summary}</p>
          <ul className={styles.bulletList}>
            {result.bullets.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <p className={styles.responseMeta}>Generated: {new Date(result.generatedAt).toLocaleString()}</p>
        </div>
      ) : null}

      {!loading && !errorMessage && !result ? <p className={styles.emptyState}>{emptyMessage}</p> : null}
    </section>
  );
}
