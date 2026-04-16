"use client";

import { useEffect, useState } from "react";
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

  if (href === "/individual-stats") {
    return (
      pathname === href ||
      pathname.startsWith(`${href}/`) ||
      pathname.startsWith("/player/") ||
      pathname.startsWith("/match/")
    );
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppNavbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    };

    const handleResize = () => {
      if (window.innerWidth > 760) {
        setMobileOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeydown);
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("keydown", handleKeydown);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return (
    <header className={styles.navbar}>
      <div className={styles.navInner}>
        <Link className={styles.brand} href="/" onClick={() => setMobileOpen(false)}>
          NexusIQ Esports
        </Link>

        <button
          type="button"
          className={`${styles.mobileMenuButton} ${mobileOpen ? styles.mobileMenuButtonOpen : ""}`}
          aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileOpen}
          aria-controls="primary-navigation"
          onClick={() => setMobileOpen((open) => !open)}
        >
          <span className={styles.mobileMenuIcon} aria-hidden="true">
            <span className={styles.mobileMenuBarTop} />
            <span className={styles.mobileMenuBarMiddle} />
            <span className={styles.mobileMenuBarBottom} />
          </span>
        </button>

        <nav
          id="primary-navigation"
          className={`${styles.navLinks} ${mobileOpen ? styles.navLinksOpen : ""}`}
          aria-label="Main"
        >
          {navItems.map((item) => {
            const active = isActive(pathname, item.href);

            return (
              <Link
                key={item.href}
                className={`${styles.navLink} ${active ? styles.navLinkActive : ""}`}
                href={item.href}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileOpen(false)}
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
