import Link from "next/link";
import styles from "@/styles/analytics-flow.module.css";

interface ActionCardProps {
  href: string;
  title: string;
  description: string;
  ctaLabel?: string;
}

export default function ActionCard({ href, title, description, ctaLabel = "Open Flow" }: ActionCardProps) {
  return (
    <Link className={styles.actionCard} href={href}>
      <div>
        <h2 className={styles.actionTitle}>{title}</h2>
        <p className={styles.actionDescription}>{description}</p>
      </div>
      <p className={styles.actionCta}>{ctaLabel}</p>
    </Link>
  );
}
