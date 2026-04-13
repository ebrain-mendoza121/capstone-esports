"use client";

import { useEffect, useMemo, useState } from "react";
import AppFrame from "@/components/layout/AppFrame";
import PageHeader from "@/components/ui/PageHeader";
import styles from "@/styles/analytics-flow.module.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChampionEntry {
  id: number;
  key: string;
  name: string;
  title: string;
  tags: string[];
  image_url: string;
  role_affinity: string[];
}

interface TrackedStats {
  games_played: number;
  win_rate: number | null;
  avg_kda: number | null;
  avg_cs_per_min: number | null;
  avg_gold_per_min: number | null;
  avg_kills: number | null;
  avg_deaths: number | null;
  avg_assists: number | null;
}

interface ChampionDetail extends ChampionEntry {
  blurb: string;
  base_stats: Record<string, number>;
  tracked_stats: TrackedStats;
}

// ---------------------------------------------------------------------------
// Filter constants
// ---------------------------------------------------------------------------

const ROLE_OPTS = ["ALL", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] as const;
const TAG_OPTS  = ["ALL", "Fighter", "Mage", "Marksman", "Support", "Tank", "Assassin", "Specialist"] as const;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function pct(v: number | null) {
  return v !== null && v !== undefined ? `${(v * 100).toFixed(1)}%` : "—";
}
function fmt(v: number | null, d = 2) {
  return v !== null && v !== undefined ? v.toFixed(d) : "—";
}

function RoleBadge({ role }: { role: string }) {
  const colour: Record<string, string> = {
    TOP:     "#f59e0b",
    JUNGLE:  "#22c55e",
    MIDDLE:  "#818cf8",
    BOTTOM:  "#38bdf8",
    UTILITY: "#f472b6",
  };
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 700,
      marginRight: 3,
      background: colour[role] ?? "#6b7280",
      color: "#fff",
    }}>
      {role}
    </span>
  );
}

function TagBadge({ tag }: { tag: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 600,
      marginRight: 3,
      background: "var(--color-surface-raised, #1e293b)",
      color: "var(--color-text-secondary, #94a3b8)",
      border: "1px solid var(--color-border, #334155)",
    }}>
      {tag}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Champion card (grid item)
// ---------------------------------------------------------------------------

function ChampionCard({
  champ,
  selected,
  onClick,
}: {
  champ: ChampionEntry;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        padding: "12px 8px",
        borderRadius: 10,
        border: selected
          ? "2px solid var(--color-primary, #6366f1)"
          : "1px solid var(--color-border, #334155)",
        background: selected
          ? "var(--color-primary-muted, #1e1b4b)"
          : "var(--color-surface, #0f172a)",
        cursor: "pointer",
        width: "100%",
        textAlign: "center",
        transition: "border-color 0.15s, background 0.15s",
      }}
    >
      {/* Champion portrait */}
      <div style={{
        width: 56,
        height: 56,
        borderRadius: 8,
        overflow: "hidden",
        background: "#1e293b",
        flexShrink: 0,
      }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={champ.image_url}
          alt={champ.name}
          width={56}
          height={56}
          style={{ objectFit: "cover" }}
          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
        />
      </div>

      <strong style={{ fontSize: 12, lineHeight: 1.3, color: "var(--color-text, #f1f5f9)" }}>
        {champ.name}
      </strong>

      {/* Role affinity chips */}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 2 }}>
        {champ.role_affinity.map((r) => <RoleBadge key={r} role={r} />)}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function DetailPanel({
  detail,
  loading,
  onClose,
}: {
  detail: ChampionDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  if (loading) {
    return (
      <div className={styles.sectionCard} style={{ marginTop: 0 }}>
        <p className={styles.statusInfo}>Loading champion detail…</p>
      </div>
    );
  }
  if (!detail) return null;

  const ts = detail.tracked_stats;
  const hasData = ts.games_played > 0;

  return (
    <div className={styles.sectionCard} style={{ marginTop: 0, position: "relative" }}>
      {/* Close button */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Close detail"
        style={{
          position: "absolute",
          top: 12,
          right: 12,
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--color-text-secondary, #94a3b8)",
          fontSize: 18,
          lineHeight: 1,
        }}
      >
        ✕
      </button>

      {/* Header */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", marginBottom: 12 }}>
        <div style={{ width: 80, height: 80, borderRadius: 12, overflow: "hidden", background: "#1e293b", flexShrink: 0 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={detail.image_url}
            alt={detail.name}
            width={80}
            height={80}
            style={{ objectFit: "cover" }}
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>
        <div>
          <h2 className={styles.sectionTitle} style={{ marginBottom: 2 }}>{detail.name}</h2>
          <p style={{ margin: 0, fontSize: 13, color: "var(--color-text-secondary, #94a3b8)", fontStyle: "italic" }}>
            {detail.title}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
            {detail.role_affinity.map((r) => <RoleBadge key={r} role={r} />)}
            {detail.tags.map((t) => <TagBadge key={t} tag={t} />)}
          </div>
        </div>
      </div>

      {detail.blurb && (
        <p style={{ fontSize: 13, color: "var(--color-text-secondary, #94a3b8)", marginBottom: 12, lineHeight: 1.5 }}>
          {detail.blurb}
        </p>
      )}

      <hr className={styles.divider} />

      {/* Tracked stats */}
      <h3 className={styles.sectionTitle} style={{ fontSize: 14 }}>
        Tracked Performance (Ranked Solo/Duo — Queue 420)
      </h3>

      {!hasData ? (
        <p className={styles.emptyState}>No ranked match data yet for this champion.</p>
      ) : (
        <div className={styles.kpiGrid} style={{ marginTop: 8 }}>
          <article className={styles.kpiCard}>
            <p className={styles.kpiLabel}>Games</p>
            <strong className={styles.kpiValue}>{ts.games_played}</strong>
          </article>
          <article className={styles.kpiCard}>
            <p className={styles.kpiLabel}>Win Rate</p>
            <strong className={styles.kpiValue}>{pct(ts.win_rate)}</strong>
          </article>
          <article className={styles.kpiCard}>
            <p className={styles.kpiLabel}>KDA</p>
            <strong className={styles.kpiValue}>{fmt(ts.avg_kda)}</strong>
          </article>
          <article className={styles.kpiCard}>
            <p className={styles.kpiLabel}>CS/Min</p>
            <strong className={styles.kpiValue}>{fmt(ts.avg_cs_per_min)}</strong>
          </article>
          <article className={styles.kpiCard}>
            <p className={styles.kpiLabel}>Gold/Min</p>
            <strong className={styles.kpiValue}>{fmt(ts.avg_gold_per_min, 0)}</strong>
          </article>
          <article className={styles.kpiCard}>
            <p className={styles.kpiLabel}>K / D / A</p>
            <strong className={styles.kpiValue}>
              {fmt(ts.avg_kills, 1)} / {fmt(ts.avg_deaths, 1)} / {fmt(ts.avg_assists, 1)}
            </strong>
          </article>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ChampionsPage() {
  const API = process.env.NEXT_PUBLIC_API_URL ?? "";

  const [champions, setChampions]   = useState<ChampionEntry[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

  const [search, setSearch]         = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("ALL");
  const [tagFilter, setTagFilter]   = useState<string>("ALL");

  const [selectedId, setSelectedId]       = useState<number | null>(null);
  const [detail, setDetail]               = useState<ChampionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Fetch all champions on mount
  useEffect(() => {
    setLoading(true);
    fetch(`${API}/champions`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        const list: ChampionEntry[] = Array.isArray(data)
          ? data
          : (data.champions ?? []);
        setChampions(list);
      })
      .catch(() => setError("Failed to load champion list from the backend."))
      .finally(() => setLoading(false));
  }, [API]);

  // Client-side filtering
  const filtered = useMemo(() => {
    const lc = search.toLowerCase();
    return champions.filter((c) => {
      if (roleFilter !== "ALL" && !c.role_affinity.includes(roleFilter)) return false;
      if (tagFilter  !== "ALL" && !c.tags.includes(tagFilter))           return false;
      if (lc && !c.name.toLowerCase().includes(lc))                      return false;
      return true;
    });
  }, [champions, roleFilter, tagFilter, search]);

  // Fetch champion detail when card is clicked
  const handleSelect = async (champ: ChampionEntry) => {
    if (selectedId === champ.id) {
      // Toggle off
      setSelectedId(null);
      setDetail(null);
      return;
    }
    setSelectedId(champ.id);
    setDetail(null);
    setLoadingDetail(true);
    try {
      const res = await fetch(`${API}/champions/${champ.id}`);
      if (res.ok) setDetail(await res.json());
    } catch { /* ignore */ } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Champions"
        title="Champion Browser"
        description="Explore the champion roster with role affinities, class tags, and live tracked performance data from your ingested matches."
        backHref="/"
        backLabel="Back to Home"
      />

      {/* ── Filters ── */}
      <section className={styles.sectionCard}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          {/* Search */}
          <div className={styles.fieldGroup} style={{ flex: "1 1 180px", minWidth: 160 }}>
            <label className={styles.label} htmlFor="champ-search">Search</label>
            <input
              className={styles.input}
              id="champ-search"
              type="text"
              placeholder="e.g. Ahri"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Role filter */}
          <div className={styles.fieldGroup} style={{ flex: "0 0 auto" }}>
            <label className={styles.label} htmlFor="role-filter">Role</label>
            <select
              className={styles.select}
              id="role-filter"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            >
              {ROLE_OPTS.map((r) => (
                <option key={r} value={r}>{r === "ALL" ? "All Roles" : r}</option>
              ))}
            </select>
          </div>

          {/* Tag / class filter */}
          <div className={styles.fieldGroup} style={{ flex: "0 0 auto" }}>
            <label className={styles.label} htmlFor="tag-filter">Class</label>
            <select
              className={styles.select}
              id="tag-filter"
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
            >
              {TAG_OPTS.map((t) => (
                <option key={t} value={t}>{t === "ALL" ? "All Classes" : t}</option>
              ))}
            </select>
          </div>

          {/* Result count */}
          <p className={styles.helper} style={{ marginBottom: 6 }}>
            {loading ? "Loading…" : `${filtered.length} champion${filtered.length !== 1 ? "s" : ""}`}
          </p>
        </div>
      </section>

      {error && (
        <section className={styles.sectionCard}>
          <p className={styles.statusError}>{error}</p>
        </section>
      )}

      {/* ── Detail panel (sticky below filters, above grid) ── */}
      {(selectedId !== null) && (
        <DetailPanel
          detail={detail}
          loading={loadingDetail}
          onClose={() => { setSelectedId(null); setDetail(null); }}
        />
      )}

      {/* ── Champion grid ── */}
      {!loading && !error && filtered.length === 0 && (
        <section className={styles.sectionCard}>
          <p className={styles.emptyState}>No champions match the current filters.</p>
        </section>
      )}

      {!loading && filtered.length > 0 && (
        <section className={styles.sectionCard}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))",
            gap: 10,
          }}>
            {filtered.map((champ) => (
              <ChampionCard
                key={champ.id}
                champ={champ}
                selected={selectedId === champ.id}
                onClick={() => handleSelect(champ)}
              />
            ))}
          </div>
        </section>
      )}
    </AppFrame>
  );
}
