"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "@/styles/analytics-flow.module.css";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/individual-stats", label: "Individual Stats" },
  { href: "/team-insights", label: "Team Insights" },
  { href: "/matchup-insights", label: "Matchup Insights" },
  { href: "/champions", label: "Champions" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppNavbar() {
  const pathname = usePathname();

  return (
    <header className={styles.navbar}>
      <div className={styles.navInner}>
        <Link className={styles.brand} href="/">
          NexusIQ Esports
        </Link>

        <nav className={styles.navLinks} aria-label="Main">
          {navItems.map((item) => {
            const active = isActive(pathname, item.href);

            return (
              <Link
                key={item.href}
                className={`${styles.navLink} ${active ? styles.navLinkActive : ""}`}
                href={item.href}
                aria-current={active ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
