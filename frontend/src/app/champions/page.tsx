"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
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

interface MatchupResult {
  champ_a: { id: number; name: string; image_url: string };
  champ_b: { id: number; name: string; image_url: string };
  role_scope: string | null;
  data_source: "researched" | "ingested";
  games_played: number;
  confidence: string;
  champ_a_win_rate: number | null;
  champ_a_win_rate_smoothed: number | null;
  champ_b_win_rate: number | null;
  avg_kda_diff: number | null;
  avg_kill_diff: number | null;
  avg_gold_diff_per_min: number | null;
  patch: string | null;
  source: string | null;
  note: string;
}

interface CounterEntry {
  counter_champion_id: number;
  counter_champion_name: string;
  role: string;
  counter_win_rate: number;
  smoothed_win_rate: number;
  games_played: number;
  confidence: string;
  source: string | null;
  patch: string | null;
}

interface FavorEntry {
  weak_champion_id: number;
  weak_champion_name: string;
  role: string;
  our_win_rate: number;
  smoothed_win_rate: number;
  games_played: number;
  confidence: string;
  source: string | null;
  patch: string | null;
}

// ---------------------------------------------------------------------------
// Filter constants
// ---------------------------------------------------------------------------

const ROLE_OPTS = ["ALL", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] as const;
const TAG_OPTS  = ["ALL", "Fighter", "Mage", "Marksman", "Support", "Tank", "Assassin", "Specialist"] as const;
const ROLES_SELECTABLE = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v: number | null) {
  return v !== null && v !== undefined ? `${(v * 100).toFixed(1)}%` : "—";
}
function fmt(v: number | null, d = 2) {
  return v !== null && v !== undefined ? v.toFixed(d) : "—";
}
function sign(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2);
}

const ROLE_COLOR: Record<string, string> = {
  TOP:     "#f59e0b",
  JUNGLE:  "#22c55e",
  MIDDLE:  "#818cf8",
  BOTTOM:  "#38bdf8",
  UTILITY: "#f472b6",
};

function RoleBadge({ role }: { role: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 700,
      marginRight: 3,
      background: ROLE_COLOR[role] ?? "#6b7280",
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

function ConfidencePip({ level }: { level: string }) {
  const c = level === "high" ? "#22c55e" : level === "medium" ? "#f59e0b" : "#ef4444";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 600, color: c }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: c, display: "inline-block" }} />
      {level.charAt(0).toUpperCase() + level.slice(1)} confidence
    </span>
  );
}

// ---------------------------------------------------------------------------
// Champion card — used in both browse and matchup mode
// ---------------------------------------------------------------------------

type CardVariant = "normal" | "my-pick" | "opponent";

function ChampionCard({
  champ,
  variant = "normal",
  onClick,
}: {
  champ: ChampionEntry;
  variant?: CardVariant;
  onClick: () => void;
}) {
  const borderMap: Record<CardVariant, string> = {
    "normal":   "1px solid var(--color-border, #334155)",
    "my-pick":  "2px solid #6366f1",
    "opponent": "2px solid #ef4444",
  };
  const bgMap: Record<CardVariant, string> = {
    "normal":   "var(--color-surface, #0f172a)",
    "my-pick":  "#1e1b4b",
    "opponent": "#2d0a0a",
  };

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
        border: borderMap[variant],
        background: bgMap[variant],
        cursor: "pointer",
        width: "100%",
        textAlign: "center",
        transition: "border-color 0.15s, background 0.15s",
        outline: variant === "my-pick" ? "2px solid #6366f1" : variant === "opponent" ? "2px solid #ef4444" : "none",
        outlineOffset: 1,
      }}
    >
      <div style={{
        width: 56,
        height: 56,
        borderRadius: 8,
        overflow: "hidden",
        background: "#1e293b",
        flexShrink: 0,
        border: variant === "my-pick" ? "2px solid #6366f1" : variant === "opponent" ? "2px solid #ef4444" : "none",
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

      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 2 }}>
        {champ.role_affinity.map((r) => <RoleBadge key={r} role={r} />)}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Detail panel (browse mode)
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
      <button
        type="button"
        onClick={onClose}
        aria-label="Close detail"
        style={{
          position: "absolute", top: 12, right: 12,
          background: "none", border: "none", cursor: "pointer",
          color: "var(--color-text-secondary, #94a3b8)", fontSize: 18, lineHeight: 1,
        }}
      >
        ✕
      </button>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", marginBottom: 12 }}>
        <div style={{ width: 80, height: 80, borderRadius: 12, overflow: "hidden", background: "#1e293b", flexShrink: 0 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={detail.image_url} alt={detail.name} width={80} height={80} style={{ objectFit: "cover" }}
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
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
// Matchup Results Panel
// ---------------------------------------------------------------------------

function MatchupResultsPanel({
  myChamp,
  oppChamp,
  role,
  result,
  counters,
  favors,
  loading,
  champMap,
  onReset,
}: {
  myChamp: ChampionEntry;
  oppChamp: ChampionEntry;
  role: string | null;
  result: MatchupResult | null;
  counters: CounterEntry[];
  favors: FavorEntry[];
  loading: boolean;
  champMap: Record<number, ChampionEntry>;
  onReset: () => void;
}) {
  if (loading) {
    return (
      <div className={styles.sectionCard} style={{ marginTop: 0 }}>
        <p className={styles.statusInfo}>⚔️ Fetching matchup data…</p>
      </div>
    );
  }

  const myWR  = result?.champ_a_win_rate ?? null;
  const oppWR = result?.champ_b_win_rate ?? null;
  const myWRColor  = myWR  !== null ? (myWR  >= 0.55 ? "#22c55e" : myWR  <= 0.45 ? "#ef4444" : "#f59e0b") : "#94a3b8";
  const oppWRColor = oppWR !== null ? (oppWR >= 0.55 ? "#ef4444" : oppWR <= 0.45 ? "#22c55e" : "#f59e0b") : "#94a3b8";

  return (
    <div className={styles.sectionCard} style={{ marginTop: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 className={styles.sectionTitle} style={{ margin: 0 }}>⚔️ Matchup Results</h2>
        <button
          type="button"
          onClick={onReset}
          style={{
            padding: "6px 14px", borderRadius: 6,
            border: "1px solid var(--color-border, #334155)",
            background: "transparent", color: "var(--color-text-secondary, #94a3b8)",
            cursor: "pointer", fontSize: 12,
          }}
        >
          ← New Matchup
        </button>
      </div>

      {/* VS Banner */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        gap: 24, marginBottom: 20, padding: "16px",
        background: "var(--color-surface-raised, #1e293b)", borderRadius: 12,
      }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ width: 72, height: 72, borderRadius: 10, overflow: "hidden", margin: "0 auto 8px", border: "2px solid #6366f1" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={myChamp.image_url} alt={myChamp.name} width={72} height={72} style={{ objectFit: "cover" }} />
          </div>
          <strong style={{ fontSize: 13, color: "#f1f5f9" }}>{myChamp.name}</strong>
          {role && <div style={{ marginTop: 4 }}><RoleBadge role={role} /></div>}
          {myWR !== null && (
            <div style={{ fontSize: 22, fontWeight: 800, color: myWRColor, marginTop: 6 }}>{pct(myWR)}</div>
          )}
        </div>

        <div style={{ fontSize: 28, fontWeight: 900, color: "#ef4444", textShadow: "0 0 12px #ef444466" }}>VS</div>

        <div style={{ textAlign: "center" }}>
          <div style={{ width: 72, height: 72, borderRadius: 10, overflow: "hidden", margin: "0 auto 8px", border: "2px solid #ef4444" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={oppChamp.image_url} alt={oppChamp.name} width={72} height={72} style={{ objectFit: "cover" }} />
          </div>
          <strong style={{ fontSize: 13, color: "#f1f5f9" }}>{oppChamp.name}</strong>
          {role && <div style={{ marginTop: 4 }}><RoleBadge role={role} /></div>}
          {oppWR !== null && (
            <div style={{ fontSize: 22, fontWeight: 800, color: oppWRColor, marginTop: 6 }}>{pct(oppWR)}</div>
          )}
        </div>
      </div>

      {result && (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16, alignItems: "center" }}>
            <ConfidencePip level={result.confidence} />
            <span style={{ fontSize: 11, color: "#94a3b8" }}>
              Source: <strong style={{ color: "#f1f5f9" }}>
                {result.data_source === "researched" ? result.source ?? "External Research" : "Ingested Matches"}
              </strong>
            </span>
            {result.patch && (
              <span style={{ fontSize: 11, color: "#94a3b8" }}>Patch <strong style={{ color: "#f1f5f9" }}>{result.patch}</strong></span>
            )}
            <span style={{ fontSize: 11, color: "#94a3b8" }}>{result.games_played} games</span>
          </div>

          <div className={styles.kpiGrid} style={{ marginBottom: 16 }}>
            <article className={styles.kpiCard}>
              <p className={styles.kpiLabel}>{myChamp.name} WR</p>
              <strong className={styles.kpiValue} style={{ color: myWRColor }}>{pct(result.champ_a_win_rate)}</strong>
              {result.champ_a_win_rate_smoothed !== null && (
                <p style={{ fontSize: 10, color: "#64748b", margin: "2px 0 0" }}>
                  {pct(result.champ_a_win_rate_smoothed)} smoothed
                </p>
              )}
            </article>
            <article className={styles.kpiCard}>
              <p className={styles.kpiLabel}>{oppChamp.name} WR</p>
              <strong className={styles.kpiValue} style={{ color: oppWRColor }}>{pct(result.champ_b_win_rate)}</strong>
            </article>
            {result.avg_kda_diff !== null && (
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>KDA Diff</p>
                <strong className={styles.kpiValue} style={{ color: result.avg_kda_diff >= 0 ? "#22c55e" : "#ef4444" }}>
                  {sign(result.avg_kda_diff)}
                </strong>
              </article>
            )}
            {result.avg_kill_diff !== null && (
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Kill Diff</p>
                <strong className={styles.kpiValue} style={{ color: result.avg_kill_diff >= 0 ? "#22c55e" : "#ef4444" }}>
                  {sign(result.avg_kill_diff)}
                </strong>
              </article>
            )}
            {result.avg_gold_diff_per_min !== null && (
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Gold/Min Diff</p>
                <strong className={styles.kpiValue} style={{ color: result.avg_gold_diff_per_min >= 0 ? "#22c55e" : "#ef4444" }}>
                  {sign(result.avg_gold_diff_per_min)}
                </strong>
              </article>
            )}
          </div>

          {result.note && (
            <p style={{ fontSize: 12, color: "#64748b", marginBottom: 16, fontStyle: "italic" }}>{result.note}</p>
          )}

          <hr className={styles.divider} />
        </>
      )}

      {/* Counters + Favors grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 8 }}>
        <div>
          <h3 className={styles.sectionTitle} style={{ fontSize: 13, marginBottom: 8, color: "#ef4444" }}>
            🔻 {myChamp.name}&apos;s Counters
          </h3>
          {counters.length === 0 ? (
            <p style={{ fontSize: 12, color: "#64748b" }}>No counter data available.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {counters.slice(0, 5).map((c) => {
                const cChamp = champMap[c.counter_champion_id];
                return (
                  <div key={`${c.counter_champion_id}-${c.role}`} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 10px",
                    background: "var(--color-surface-raised, #1e293b)",
                    borderRadius: 8, border: "1px solid #334155",
                  }}>
                    {cChamp && (
                      <div style={{ width: 32, height: 32, borderRadius: 6, overflow: "hidden", flexShrink: 0 }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={cChamp.image_url} alt={c.counter_champion_name} width={32} height={32} style={{ objectFit: "cover" }} />
                      </div>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong style={{ fontSize: 12, display: "block", color: "#f1f5f9", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {c.counter_champion_name}
                      </strong>
                      <RoleBadge role={c.role} />
                    </div>
                    <strong style={{ fontSize: 13, color: "#ef4444", flexShrink: 0 }}>{pct(c.counter_win_rate)}</strong>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <h3 className={styles.sectionTitle} style={{ fontSize: 13, marginBottom: 8, color: "#22c55e" }}>
            ✅ {myChamp.name}&apos;s Favors
          </h3>
          {favors.length === 0 ? (
            <p style={{ fontSize: 12, color: "#64748b" }}>No favorable matchup data available.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {favors.slice(0, 5).map((f) => {
                const fChamp = champMap[f.weak_champion_id];
                return (
                  <div key={`${f.weak_champion_id}-${f.role}`} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 10px",
                    background: "var(--color-surface-raised, #1e293b)",
                    borderRadius: 8, border: "1px solid #334155",
                  }}>
                    {fChamp && (
                      <div style={{ width: 32, height: 32, borderRadius: 6, overflow: "hidden", flexShrink: 0 }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={fChamp.image_url} alt={f.weak_champion_name} width={32} height={32} style={{ objectFit: "cover" }} />
                      </div>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong style={{ fontSize: 12, display: "block", color: "#f1f5f9", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {f.weak_champion_name}
                      </strong>
                      <RoleBadge role={f.role} />
                    </div>
                    <strong style={{ fontSize: 13, color: "#22c55e", flexShrink: 0 }}>{pct(f.our_win_rate)}</strong>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type MatchupStep = "pick-my" | "pick-opp" | "results";

export default function ChampionsPage() {
  const API = process.env.NEXT_PUBLIC_API_URL ?? "";

  // Champion list
  const [champions, setChampions] = useState<ChampionEntry[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  // Browse mode
  const [search, setSearch]             = useState("");
  const [roleFilter, setRoleFilter]     = useState<string>("ALL");
  const [tagFilter, setTagFilter]       = useState<string>("ALL");
  const [selectedId, setSelectedId]     = useState<number | null>(null);
  const [detail, setDetail]             = useState<ChampionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Matchup mode
  const [matchupMode, setMatchupMode]   = useState(false);
  const [matchupStep, setMatchupStep]   = useState<MatchupStep>("pick-my");
  const [myChamp, setMyChamp]           = useState<ChampionEntry | null>(null);
  const [oppChamp, setOppChamp]         = useState<ChampionEntry | null>(null);
  const [matchupRole, setMatchupRole]   = useState<string>("");

  // Matchup grid filter
  const [muSearch, setMuSearch]         = useState("");
  const [muRoleFilter, setMuRoleFilter] = useState<string>("ALL");

  // Matchup results
  const [matchupResult, setMatchupResult]   = useState<MatchupResult | null>(null);
  const [counters, setCounters]             = useState<CounterEntry[]>([]);
  const [favors, setFavors]                 = useState<FavorEntry[]>([]);
  const [loadingMatchup, setLoadingMatchup] = useState(false);

  // Quick lookup map
  const champMap = useMemo(
    () => Object.fromEntries(champions.map((c) => [c.id, c])) as Record<number, ChampionEntry>,
    [champions]
  );

  // Fetch champions on mount
  useEffect(() => {
    setLoading(true);
    fetch(`${API}/champions`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data) => {
        const list: ChampionEntry[] = Array.isArray(data) ? data : (data.champions ?? []);
        setChampions(list);
      })
      .catch(() => setError("Failed to load champion list from the backend."))
      .finally(() => setLoading(false));
  }, [API]);

  // Browse mode filter
  const filtered = useMemo(() => {
    const lc = search.toLowerCase();
    return champions.filter((c) => {
      if (roleFilter !== "ALL" && !c.role_affinity.includes(roleFilter)) return false;
      if (tagFilter  !== "ALL" && !c.tags.includes(tagFilter))           return false;
      if (lc && !c.name.toLowerCase().includes(lc))                      return false;
      return true;
    });
  }, [champions, roleFilter, tagFilter, search]);

  // Matchup mode filter
  const filteredMatchup = useMemo(() => {
    const lc = muSearch.toLowerCase();
    return champions.filter((c) => {
      if (muRoleFilter !== "ALL" && !c.role_affinity.includes(muRoleFilter)) return false;
      if (lc && !c.name.toLowerCase().includes(lc)) return false;
      return true;
    });
  }, [champions, muRoleFilter, muSearch]);

  // Browse: click a card
  const handleBrowseSelect = useCallback(async (champ: ChampionEntry) => {
    if (selectedId === champ.id) { setSelectedId(null); setDetail(null); return; }
    setSelectedId(champ.id); setDetail(null); setLoadingDetail(true);
    try {
      const res = await fetch(`${API}/champions/${champ.id}`);
      if (res.ok) setDetail(await res.json());
    } catch { /* ignore */ } finally { setLoadingDetail(false); }
  }, [API, selectedId]);

  // Enter matchup mode
  const enterMatchupMode = useCallback(() => {
    setMatchupMode(true);
    setMatchupStep("pick-my");
    setMyChamp(null); setOppChamp(null);
    setMatchupResult(null); setCounters([]); setFavors([]);
    setSelectedId(null); setDetail(null);
  }, []);

  // Exit matchup mode
  const exitMatchupMode = useCallback(() => {
    setMatchupMode(false);
    setMatchupStep("pick-my");
    setMyChamp(null); setOppChamp(null);
    setMatchupResult(null); setCounters([]); setFavors([]);
  }, []);

  // Matchup: click a card
  const handleMatchupSelect = useCallback(async (champ: ChampionEntry) => {
    if (matchupStep === "pick-my") {
      setMyChamp(champ);
      setMatchupStep("pick-opp");
    } else if (matchupStep === "pick-opp" && myChamp) {
      setOppChamp(champ);
      setMatchupStep("results");
      setLoadingMatchup(true);

      const roleParam = matchupRole ? `?role=${matchupRole}` : "";
      const extraAmp  = matchupRole ? "&" : "?";

      try {
        const [matchupRes, countersRes, favorsRes] = await Promise.all([
          fetch(`${API}/champions/matchup/${myChamp.id}/${champ.id}${roleParam}`),
          fetch(`${API}/matchups/${myChamp.id}/counters${roleParam}${extraAmp}limit=10`),
          fetch(`${API}/matchups/${myChamp.id}/favors${roleParam}${extraAmp}limit=10`),
        ]);
        if (matchupRes.ok)  setMatchupResult(await matchupRes.json());
        if (countersRes.ok) { const d = await countersRes.json(); setCounters(d.counters ?? []); }
        if (favorsRes.ok)   { const d = await favorsRes.json();   setFavors(d.favors ?? []); }
      } catch { /* graceful degradation */ } finally {
        setLoadingMatchup(false);
      }
    }
  }, [API, matchupStep, myChamp, matchupRole]);

  // Reset within matchup mode
  const resetMatchup = useCallback(() => {
    setMatchupStep("pick-my");
    setMyChamp(null); setOppChamp(null);
    setMatchupResult(null); setCounters([]); setFavors([]);
  }, []);

  // Card variant for matchup grid
  const getMatchupVariant = useCallback((champ: ChampionEntry): CardVariant => {
    if (myChamp?.id === champ.id)  return "my-pick";
    if (oppChamp?.id === champ.id) return "opponent";
    return "normal";
  }, [myChamp, oppChamp]);

  // Step label
  const stepLabel = useMemo(() => {
    if (matchupStep === "pick-my")  return "Step 1 of 2 — Click your champion below";
    if (matchupStep === "pick-opp") return `Step 2 of 2 — Now click the opponent you face as ${myChamp?.name ?? "?"}`;
    if (matchupStep === "results")  return `${myChamp?.name} vs ${oppChamp?.name}`;
    return "";
  }, [matchupStep, myChamp, oppChamp]);

  return (
    <AppFrame>
      <PageHeader
        eyebrow="Champions"
        title="Champion Browser"
        description="Explore the champion roster with role affinities, class tags, live tracked performance data — and head-to-head matchup analysis."
        backHref="/"
        backLabel="Back to Home"
      />

      {/* ── Mode toggle card ── */}
      <section className={styles.sectionCard} style={{ marginTop: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h3 className={styles.sectionTitle} style={{ margin: 0, fontSize: 14 }}>
              {matchupMode ? "⚔️ Matchup Mode Active" : "🗂️ Browse Mode"}
            </h3>
            {matchupMode && (
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "#94a3b8" }}>{stepLabel}</p>
            )}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            {matchupMode ? (
              <button
                type="button"
                onClick={exitMatchupMode}
                style={{
                  padding: "8px 18px", borderRadius: 8,
                  border: "1px solid var(--color-border, #334155)",
                  background: "transparent", color: "var(--color-text-secondary, #94a3b8)",
                  cursor: "pointer", fontWeight: 600, fontSize: 13,
                }}
              >
                Exit Matchup Mode
              </button>
            ) : (
              <button
                type="button"
                onClick={enterMatchupMode}
                style={{
                  padding: "8px 22px", borderRadius: 8, border: "none",
                  background: "linear-gradient(135deg, #6366f1 0%, #ef4444 100%)",
                  color: "#fff", cursor: "pointer", fontWeight: 700, fontSize: 13,
                  letterSpacing: "0.02em", boxShadow: "0 2px 12px #6366f140",
                }}
              >
                ⚔️ Begin Matchup Mode
              </button>
            )}
          </div>
        </div>

        {/* Matchup controls — role + filter */}
        {matchupMode && matchupStep !== "results" && (
          <div style={{ marginTop: 14, display: "flex", alignItems: "flex-end", gap: 12, flexWrap: "wrap" }}>
            <div className={styles.fieldGroup} style={{ margin: 0 }}>
              <label className={styles.label} htmlFor="mu-role">Your Role (optional)</label>
              <select
                className={styles.select}
                id="mu-role"
                value={matchupRole}
                onChange={(e) => setMatchupRole(e.target.value)}
              >
                <option value="">Any Role</option>
                {ROLES_SELECTABLE.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className={styles.fieldGroup} style={{ margin: 0, flex: "1 1 140px", minWidth: 120 }}>
              <label className={styles.label} htmlFor="mu-search">Filter champions</label>
              <input
                className={styles.input}
                id="mu-search"
                type="text"
                placeholder="Search…"
                value={muSearch}
                onChange={(e) => setMuSearch(e.target.value)}
              />
            </div>
            <div className={styles.fieldGroup} style={{ margin: 0 }}>
              <label className={styles.label} htmlFor="mu-role-filter">Filter by Role</label>
              <select
                className={styles.select}
                id="mu-role-filter"
                value={muRoleFilter}
                onChange={(e) => setMuRoleFilter(e.target.value)}
              >
                {ROLE_OPTS.map((r) => <option key={r} value={r}>{r === "ALL" ? "All Roles" : r}</option>)}
              </select>
            </div>
          </div>
        )}
      </section>

      {error && (
        <section className={styles.sectionCard}>
          <p className={styles.statusError}>{error}</p>
        </section>
      )}

      {/* ════════════════════════════════════════════
          MATCHUP MODE
      ════════════════════════════════════════════ */}
      {matchupMode && (
        <>
          {/* Results */}
          {matchupStep === "results" && myChamp && oppChamp && (
            <MatchupResultsPanel
              myChamp={myChamp}
              oppChamp={oppChamp}
              role={matchupRole || null}
              result={matchupResult}
              counters={counters}
              favors={favors}
              loading={loadingMatchup}
              champMap={champMap}
              onReset={resetMatchup}
            />
          )}

          {/* Selection grid */}
          {(matchupStep === "pick-my" || matchupStep === "pick-opp") && (
            <section className={styles.sectionCard}>
              {/* Step pills */}
              <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center" }}>
                <div style={{
                  padding: "4px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700,
                  background: matchupStep === "pick-my" ? "#6366f1" : "#334155", color: "#fff",
                }}>
                  1. Your Champion {myChamp ? `✓ ${myChamp.name}` : ""}
                </div>
                <span style={{ color: "#64748b", fontSize: 12 }}>→</span>
                <div style={{
                  padding: "4px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700,
                  background: matchupStep === "pick-opp" ? "#ef4444" : "#334155", color: "#fff",
                }}>
                  2. Opponent {oppChamp ? `✓ ${oppChamp.name}` : ""}
                </div>
              </div>

              {/* Instruction banner */}
              <div style={{
                padding: "10px 14px", borderRadius: 8, marginBottom: 14,
                background: matchupStep === "pick-my" ? "#1e1b4b" : "#2d0a0a",
                border: `1px solid ${matchupStep === "pick-my" ? "#6366f1" : "#ef4444"}`,
                fontSize: 13, fontWeight: 600,
                color: matchupStep === "pick-my" ? "#a5b4fc" : "#fca5a5",
              }}>
                {matchupStep === "pick-my"
                  ? "👆 Click your champion — the one you are playing"
                  : `👆 Click the opponent champion you will face as ${myChamp?.name}`}
              </div>

              <p style={{ fontSize: 11, color: "#64748b", margin: "0 0 10px" }}>
                {filteredMatchup.length} champion{filteredMatchup.length !== 1 ? "s" : ""}
              </p>

              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))",
                gap: 8,
              }}>
                {filteredMatchup.map((champ) => (
                  <ChampionCard
                    key={champ.id}
                    champ={champ}
                    variant={getMatchupVariant(champ)}
                    onClick={() => handleMatchupSelect(champ)}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {/* ════════════════════════════════════════════
          BROWSE MODE
      ════════════════════════════════════════════ */}
      {!matchupMode && (
        <>
          {/* Filters */}
          <section className={styles.sectionCard}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
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
              <div className={styles.fieldGroup} style={{ flex: "0 0 auto" }}>
                <label className={styles.label} htmlFor="role-filter">Role</label>
                <select
                  className={styles.select}
                  id="role-filter"
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                >
                  {ROLE_OPTS.map((r) => <option key={r} value={r}>{r === "ALL" ? "All Roles" : r}</option>)}
                </select>
              </div>
              <div className={styles.fieldGroup} style={{ flex: "0 0 auto" }}>
                <label className={styles.label} htmlFor="tag-filter">Class</label>
                <select
                  className={styles.select}
                  id="tag-filter"
                  value={tagFilter}
                  onChange={(e) => setTagFilter(e.target.value)}
                >
                  {TAG_OPTS.map((t) => <option key={t} value={t}>{t === "ALL" ? "All Classes" : t}</option>)}
                </select>
              </div>
              <p className={styles.helper} style={{ marginBottom: 6 }}>
                {loading ? "Loading…" : `${filtered.length} champion${filtered.length !== 1 ? "s" : ""}`}
              </p>
            </div>
          </section>

          {/* Detail panel */}
          {selectedId !== null && (
            <DetailPanel
              detail={detail}
              loading={loadingDetail}
              onClose={() => { setSelectedId(null); setDetail(null); }}
            />
          )}

          {/* Champion grid */}
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
                    variant={selectedId === champ.id ? "my-pick" : "normal"}
                    onClick={() => handleBrowseSelect(champ)}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </AppFrame>
  );
}
