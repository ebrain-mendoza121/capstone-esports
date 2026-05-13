import Link from "next/link";
import Image from "next/image";
import AppFrame from "@/components/layout/AppFrame";
import styles from "@/styles/analytics-flow.module.css";

const proofPoints = [
  { label: "LoL workflows", value: "4" },
  { label: "Core roles", value: "5" },
  { label: "Draft analysis", value: "Live" },
];

const platformSignals = [
  {
    title: "Lane-by-lane player form",
    description: "Compare recent role performance so coaches can spot stable lanes, pressure points, and players trending up.",
  },
  {
    title: "Draft and matchup risk",
    description: "Surface risky champion pairings, pressure lanes, and draft angles before a lineup locks into the wrong plan.",
  },
  {
    title: "Champion pool depth",
    description: "Review comfort picks, matchup coverage, and role fit to understand what each player can actually pilot.",
  },
  {
    title: "Riot match history ingestion",
    description: "Pull fresh match data into the workflow so analysis starts from real games instead of manual notes.",
  },
];

const blueDraft = [
  { role: "TOP", champion: "K'Sante", note: "frontline anchor" },
  { role: "JNG", champion: "Sejuani", note: "engage bridge" },
  { role: "MID", champion: "Orianna", note: "teamfight control" },
  { role: "BOT", champion: "Kai'Sa", note: "late DPS" },
  { role: "SUP", champion: "Rakan", note: "start fights" },
];

const redDraft = [
  { role: "TOP", champion: "Renekton", note: "lane pressure" },
  { role: "JNG", champion: "Lee Sin", note: "early tempo" },
  { role: "MID", champion: "Azir", note: "scaling control" },
  { role: "BOT", champion: "Jinx", note: "reset threat" },
  { role: "SUP", champion: "Nautilus", note: "pick threat" },
];

const draftIntel = [
  { label: "Ban priority", value: "Maokai" },
  { label: "Target lane", value: "Bot" },
  { label: "Objective timer", value: "Dragon" },
];

const pressureSummary = [
  { label: "Top lane", value: "Stable", level: 44 },
  { label: "Mid lane", value: "Even", level: 52 },
  { label: "Bot lane", value: "Attack", level: 78 },
];

export default function LandingPage() {
  return (
    <AppFrame>
      <div className={styles.landingPage}>
        <section className={styles.landingHero} aria-labelledby="landing-title">
          <div className={styles.landingHeroCopy}>
            <p className={styles.landingEyebrow}>Esports analytics SaaS</p>
            <h1 id="landing-title" className={styles.landingTitle}>
              NexusIQ Esports
            </h1>
            <p className={styles.landingLead}>
              A command layer for League of Legends teams that need faster reads on lane matchups, champion pools,
              draft risk, and player form. Turn Riot match history into structured decisions before the next scrim,
              clash run, or ranked review starts.
            </p>

            <div className={styles.landingActions}>
              <Link className={styles.landingPrimaryCta} href="/tools">
                Use Analytics Tools
              </Link>
              <Link className={styles.landingSecondaryCta} href="/champions">
                Explore Champions
              </Link>
            </div>

            <div className={styles.landingProofGrid} aria-label="Platform highlights">
              {proofPoints.map((point) => (
                <div className={styles.landingProofItem} key={point.label}>
                  <strong>{point.value}</strong>
                  <span>{point.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className={styles.landingProductPanel} aria-label="League of Legends draft intelligence preview">
            <div className={styles.productPanelHeader}>
              <span>LoL Draft Intel</span>
              <span>Patch-aware</span>
            </div>

            <div className={styles.draftBoard}>
              <div className={styles.draftSide}>
                <div className={styles.draftSideHeader}>
                  <strong>Blue side</strong>
                  <span>Blue favored 68%</span>
                </div>
                {blueDraft.map((pick) => (
                  <div className={styles.draftRow} key={`blue-${pick.role}`}>
                    <span className={styles.draftRole}>{pick.role}</span>
                    <strong>{pick.champion}</strong>
                    <span>{pick.note}</span>
                  </div>
                ))}
              </div>

              <div className={styles.pressurePanel}>
                <div className={styles.pressurePanelHeader}>
                  <strong>Map pressure</strong>
                  <span>Bot lane focus</span>
                </div>
                <div className={styles.pressureRows}>
                  {pressureSummary.map((row) => (
                    <div className={styles.pressureRow} key={row.label}>
                      <div>
                        <strong>{row.label}</strong>
                        <span>{row.value}</span>
                      </div>
                      <span className={styles.pressureTrack}>
                        <span style={{ width: `${row.level}%` }} />
                      </span>
                    </div>
                  ))}
                </div>
                <p>Prioritize early vision and dragon control around bot-side pressure.</p>
              </div>

              <div className={styles.draftSide}>
                <div className={styles.draftSideHeader}>
                  <strong>Red side</strong>
                  <span>high tempo</span>
                </div>
                {redDraft.map((pick) => (
                  <div className={styles.draftRow} key={`red-${pick.role}`}>
                    <span className={styles.draftRole}>{pick.role}</span>
                    <strong>{pick.champion}</strong>
                    <span>{pick.note}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className={styles.draftIntelGrid}>
              {draftIntel.map((item) => (
                <div className={styles.draftIntelCard} key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.landingLogoSection} aria-labelledby="brand-title">
          <div className={styles.landingLogoPlate}>
            <Image
              className={styles.landingBrandLogo}
              src="/assets/logo-nexusIQ.png"
              alt="NexusIQ Esports Analytics logo"
              width={1536}
              height={1024}
              priority
            />
          </div>
          <div className={styles.landingLogoCopy}>
            <p className={styles.landingEyebrow}>League-ready intelligence</p>
            <h2 id="brand-title">A sharper identity for draft, match, and player review.</h2>
            <p>
              NexusIQ turns LoL data into a focused command center for teams that need fast answers before
              scrims, scouting blocks, and ranked reviews.
            </p>
            <div className={styles.landingLogoChips} aria-label="NexusIQ focus areas">
              <span>Draft reads</span>
              <span>Player form</span>
              <span>Champion pools</span>
            </div>
          </div>
        </section>

        <section className={styles.landingSignalBand} aria-labelledby="platform-title">
          <div>
            <p className={styles.landingEyebrow}>Built for repeatable review</p>
            <h2 id="platform-title" className={styles.landingSectionTitle}>
              One workspace for the questions coaches ask every week.
            </h2>
          </div>
          <div className={styles.landingSignalGrid}>
            {platformSignals.map((signal) => (
              <article className={styles.landingSignalCard} key={signal.title}>
                <span />
                <h3>{signal.title}</h3>
                <p>{signal.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.landingBottomCta} aria-label="Start using NexusIQ Esports">
          <div>
            <h2>Move from VOD notes to champion-specific evidence.</h2>
            <p>Open the tools hub and start with player stats, team insights, matchup analysis, or champion scouting for LoL.</p>
          </div>
          <Link className={styles.landingPrimaryCta} href="/tools">
            Use Analytics Tools
          </Link>
        </section>
      </div>
    </AppFrame>
  );
}
