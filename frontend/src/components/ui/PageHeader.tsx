import Link from "next/link";
import styles from "@/styles/analytics-flow.module.css";

interface PageHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
  backHref?: string;
  backLabel?: string;
}

export default function PageHeader({ eyebrow, title, description, backHref, backLabel }: PageHeaderProps) {
  return (
    <section className={styles.heroCard}>
      <div className={styles.headerTopRow}>
        <p className={styles.eyebrow}>{eyebrow}</p>
        {backHref && backLabel ? (
          <Link className={styles.backLink} href={backHref}>
            {backLabel}
          </Link>
        ) : null}
      </div>
      <h1 className={styles.pageTitle}>{title}</h1>
      <p className={styles.pageText}>{description}</p>
    </section>
  );
}
