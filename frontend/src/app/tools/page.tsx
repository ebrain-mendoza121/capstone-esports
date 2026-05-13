import AppFrame from "@/components/layout/AppFrame";
import ActionCard from "@/components/ui/ActionCard";
import PageHeader from "@/components/ui/PageHeader";
import styles from "@/styles/analytics-flow.module.css";

export default function ToolsPage() {
  return (
    <AppFrame>
      <div className={styles.homeCenteredLayout}>
        <PageHeader
          eyebrow="AI Esports Analytics"
          title="League Performance Intelligence, Built for Decision Speed"
          description="Run individual, team, and matchup workflows from one command center. Each flow is pre-structured for direct backend API integration as your analytics endpoints go live."
        />

        <section className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>Choose Your Analysis Flow</h2>
          <p className={styles.sectionText}>
            Start with one of the four entry points below. Each route includes submission handling and a dedicated
            placeholder panel for future AI responses.
          </p>

          <div className={styles.actionGrid}>
            <ActionCard
              href="/individual-stats"
              title="See Your Individual Stats"
              description="Analyze one player&apos;s historical performance."
              ctaLabel="Open Individual Flow"
            />
            <ActionCard
              href="/team-insights"
              title="Insights for Your Team"
              description="Analyze synergy and trends for a 5-player roster."
              ctaLabel="Open Team Flow"
            />
            <ActionCard
              href="/matchup-insights"
              title="Matchup-Based Insights"
              description="Compare two 5-player teams for matchup-based analysis."
              ctaLabel="Open Matchup Flow"
            />
            <ActionCard
              href="/champions"
              title="Champion Browser"
              description="Explore the full champion roster with DB-backed win rates, KDA, and role affinities."
              ctaLabel="Browse Champions"
            />
          </div>
        </section>
      </div>
    </AppFrame>
  );
}
