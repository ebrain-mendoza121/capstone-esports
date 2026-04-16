"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { buildApiUrl, getApiBaseUrl } from "@/lib/apiBaseUrl";

const QUICK_PUUID = "GXO6oaJPECfKU3Zr_5CAiUCEpGNGVq5zRrmXWbfoih49CX5D4_bw360rWA9skKW5Qf5PblEY7MNdtA";

type CallState = "idle" | "loading" | "ok" | "error";

interface EndpointResult {
  label: string;
  path: string;
  state: CallState;
  httpStatus: number | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  error: string | null;
}

const PUUID_ENDPOINTS = [
  { label: "Player Profile",      path: `/players/${QUICK_PUUID}/` },
  { label: "Metrics",             path: `/metrics/player/${QUICK_PUUID}/` },
  { label: "Match History (20)",  path: `/matches/player/${QUICK_PUUID}/?limit=20` },
  { label: "Role Performance",    path: `/analytics/player/${QUICK_PUUID}/role-performance` },
  { label: "Objective Control",   path: `/analytics/player/${QUICK_PUUID}/objective-control` },
  { label: "Ban Analytics",       path: `/analytics/player/${QUICK_PUUID}/bans/?limit=20` },
  { label: "Playstyle (AI)",      path: `/ai/playstyle/${QUICK_PUUID}` },
  { label: "Champion Recs (AI)",  path: `/ai/champions/${QUICK_PUUID}?top_n=5` },
];

type Probe = {
  label: string;
  path: string;
  method?: "GET" | "POST";
  body?: Record<string, unknown>;
};

const PROBES: Probe[] = [
  { label: "Root Probe", path: "/" },
  { label: "Health", path: "/health" },
  { label: "DB Health", path: "/health/db" },
  { label: "Model Status", path: "/ai/models/status" },
  { label: "Champion List", path: "/champions" },
  { label: "Player List", path: "/players/?min_matches=1" },
];

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function HomePage() {
  const [activePath, setActivePath] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<number | null>(null);
  const [output, setOutput] = useState<string>("Click a probe to test your hosted backend endpoint.");
  const [protocol, setProtocol] = useState<string>("unknown");
  const [resolvedApiBase, setResolvedApiBase] = useState<string>("");

  // Per-endpoint results for the PUUID test card
  const [results, setResults] = useState<EndpointResult[]>(
    PUUID_ENDPOINTS.map((e) => ({ ...e, state: "idle", httpStatus: null, data: null, error: null }))
  );
  const [runningAll, setRunningAll] = useState(false);

  const envRaw = process.env.NEXT_PUBLIC_API_URL ?? "";

  useEffect(() => {
    setProtocol(window.location.protocol);
    setResolvedApiBase(getApiBaseUrl());
  }, []);

  const runEndpoint = async (index: number) => {
    const ep = PUUID_ENDPOINTS[index];
    setResults((prev) => prev.map((r, i) => i === index ? { ...r, state: "loading", httpStatus: null, data: null, error: null } : r));
    try {
      const res = await fetch(buildApiUrl(ep.path));
      const httpStatus = res.status;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let data: any = null;
      try { data = await res.json(); } catch { data = null; }
      setResults((prev) => prev.map((r, i) => i === index ? { ...r, state: res.ok ? "ok" : "error", httpStatus, data, error: res.ok ? null : `HTTP ${httpStatus}` } : r));
    } catch (err) {
      setResults((prev) => prev.map((r, i) => i === index ? { ...r, state: "error", httpStatus: null, data: null, error: err instanceof Error ? err.message : "Failed" } : r));
    }
  };

  const runAll = async () => {
    setRunningAll(true);
    for (let i = 0; i < PUUID_ENDPOINTS.length; i++) {
      await runEndpoint(i);
    }
    setRunningAll(false);
  };

  const protocolWarning = useMemo(() => {
    if (protocol === "https:" && envRaw.startsWith("http://")) {
      return "Warning: NEXT_PUBLIC_API_URL is http:// while the frontend is https://. This can cause mixed-content failures in production.";
    }
    return "";
  }, [envRaw, protocol]);

  const runProbe = async (probe: Probe) => {
    setActivePath(probe.path);
    setLoading(true);
    setStatus(null);

    try {
      const response = await fetch(buildApiUrl(probe.path), {
        method: probe.method ?? "GET",
        headers: probe.body ? { "Content-Type": "application/json" } : undefined,
        body: probe.body ? JSON.stringify(probe.body) : undefined,
      });

      setStatus(response.status);

      let payload: unknown;
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        payload = await response.json();
      } else {
        payload = await response.text();
      }

      setOutput(pretty(payload));
    } catch (error) {
      setOutput(error instanceof Error ? error.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ minHeight: "100vh", background: "linear-gradient(135deg, #0f172a 0%, #111827 45%, #022c22 100%)", color: "#e5e7eb", padding: "28px 20px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <h1 style={{ margin: 0, fontSize: 34, letterSpacing: 0.5 }}>API Connection Debug Home</h1>
        <p style={{ marginTop: 10, color: "#cbd5e1" }}>
          Minimal homepage to verify frontend-to-backend connectivity from deployment.
        </p>

        {/* ── Navigation ── */}
        <section style={{ marginTop: 20, padding: 14, border: "1px solid rgba(148,163,184,0.35)", borderRadius: 10, background: "rgba(2,6,23,0.35)" }}>
          <strong style={{ fontSize: 13, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase" }}>App Routes</strong>
          <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
            {[
              { label: "Individual Stats", href: "/individual-stats", note: "Enter a player to search" },
              { label: "Team Insights", href: "/team-insights", note: "Analyze a 5-player roster" },
              { label: "Matchup Insights", href: "/matchup-insights", note: "Blue vs Red team comparison" },
              { label: "Champions", href: "/champions", note: "Browse & matchup explorer" },
            ].map(({ label, href, note }) => (
              <Link key={href} href={href} style={{
                display: "block",
                padding: "10px 12px",
                border: "1px solid rgba(148,163,184,0.25)",
                borderRadius: 8,
                background: "rgba(15,23,42,0.55)",
                textDecoration: "none",
                color: "#e5e7eb",
              }}>
                <div style={{ fontWeight: 700 }}>{label}</div>
                <div style={{ marginTop: 3, fontSize: 12, color: "#94a3b8" }}>{note}</div>
                <div style={{ marginTop: 4, fontSize: 11, color: "#60a5fa" }}>{href}</div>
              </Link>
            ))}
          </div>
          <p style={{ marginTop: 10, fontSize: 12, color: "#64748b" }}>
            Dynamic routes <code style={{ color: "#93c5fd" }}>/player/[puuid]</code> and{" "}
            <code style={{ color: "#93c5fd" }}>/match/[match_id]</code> are reached by navigating through Individual Stats.
          </p>
        </section>

        {/* ── PUUID Endpoint Test Card ── */}
        <section style={{ marginTop: 16, padding: 16, border: "1px solid rgba(148,163,184,0.35)", borderRadius: 10, background: "rgba(2,6,23,0.35)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
            <div>
              <strong style={{ fontSize: 13, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase" }}>Player Endpoint Tests</strong>
              <div style={{ marginTop: 4, fontSize: 11, color: "#475569", wordBreak: "break-all" }}>{QUICK_PUUID}</div>
            </div>
            <button
              onClick={() => void runAll()}
              disabled={runningAll}
              style={{ padding: "8px 18px", borderRadius: 8, background: "rgba(16,185,129,0.2)", border: "1px solid rgba(16,185,129,0.45)", color: "#6ee7b7", fontWeight: 700, cursor: runningAll ? "wait" : "pointer", fontSize: 13 }}
            >
              {runningAll ? "Running…" : "▶ Run All"}
            </button>
          </div>

          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
            {results.map((r, i) => (
              <div key={r.path} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: 8, background: "rgba(15,23,42,0.5)", border: `1px solid ${r.state === "ok" ? "rgba(16,185,129,0.3)" : r.state === "error" ? "rgba(239,68,68,0.3)" : "rgba(148,163,184,0.15)"}` }}>
                {/* Status dot */}
                <div style={{ marginTop: 3, width: 10, height: 10, borderRadius: "50%", flexShrink: 0, background: r.state === "ok" ? "#22c55e" : r.state === "error" ? "#ef4444" : r.state === "loading" ? "#facc15" : "#334155" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{r.label}</span>
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>{r.path}</span>
                  </div>
                  {r.state === "ok" && r.httpStatus && (
                    <div style={{ marginTop: 4, fontSize: 12, color: "#86efac" }}>
                      HTTP {r.httpStatus} ·{" "}
                      {r.data !== null ? (
                        Array.isArray(r.data)
                          ? `Array[${r.data.length}]`
                          : typeof r.data === "object"
                            ? Object.keys(r.data).slice(0, 4).join(", ") + (Object.keys(r.data).length > 4 ? "…" : "")
                            : String(r.data)
                      ) : "ok"}
                    </div>
                  )}
                  {r.state === "error" && (
                    <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>{r.error ?? "Failed"}{r.httpStatus ? ` · HTTP ${r.httpStatus}` : ""}</div>
                  )}
                  {r.state === "loading" && (
                    <div style={{ marginTop: 4, fontSize: 12, color: "#fde68a" }}>Loading…</div>
                  )}
                </div>
                <button
                  onClick={() => void runEndpoint(i)}
                  disabled={r.state === "loading" || runningAll}
                  style={{ flexShrink: 0, padding: "4px 10px", borderRadius: 6, background: "rgba(99,102,241,0.2)", border: "1px solid rgba(99,102,241,0.35)", color: "#a5b4fc", fontSize: 11, cursor: "pointer" }}
                >
                  Test
                </button>
              </div>
            ))}
          </div>

          {/* Nav links */}
          <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              { label: "→ Player Dashboard", href: `/player/${QUICK_PUUID}` },
              { label: "→ Match History",    href: `/player/${QUICK_PUUID}/matches` },
              { label: "→ Champion Stats",   href: `/player/${QUICK_PUUID}/champions` },
              { label: "→ Trends",           href: `/player/${QUICK_PUUID}/trends` },
              { label: "→ Bans",             href: `/player/${QUICK_PUUID}/bans` },
            ].map(({ label, href }) => (
              <Link key={href} href={href} style={{ padding: "6px 12px", borderRadius: 8, background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", color: "#c7d2fe", textDecoration: "none", fontSize: 12, fontWeight: 600 }}>
                {label}
              </Link>
            ))}
          </div>
        </section>

        <div style={{ marginTop: 16, padding: 14, border: "1px solid rgba(148,163,184,0.35)", borderRadius: 10, background: "rgba(2,6,23,0.35)" }}>
          <div><strong>Browser protocol:</strong> {protocol}</div>
          <div><strong>NEXT_PUBLIC_API_URL:</strong> {envRaw || "(empty)"}</div>
          <div><strong>Resolved API base:</strong> {resolvedApiBase || "(empty)"}</div>
          {protocolWarning ? (
            <p style={{ margin: "10px 0 0", color: "#fca5a5", fontWeight: 600 }}>{protocolWarning}</p>
          ) : null}
        </div>

        <section style={{ marginTop: 20, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10 }}>
          {PROBES.map((probe) => (
            <button
              key={probe.path}
              onClick={() => void runProbe(probe)}
              disabled={loading}
              style={{
                border: "1px solid rgba(148,163,184,0.35)",
                borderRadius: 10,
                background: activePath === probe.path ? "rgba(16,185,129,0.24)" : "rgba(15,23,42,0.55)",
                color: "#e5e7eb",
                padding: "12px 10px",
                textAlign: "left",
                cursor: loading ? "wait" : "pointer",
              }}
            >
              <div style={{ fontWeight: 700 }}>{probe.label}</div>
              <div style={{ marginTop: 4, fontSize: 12, color: "#93c5fd" }}>{probe.path}</div>
            </button>
          ))}
        </section>

        <section style={{ marginTop: 18, border: "1px solid rgba(148,163,184,0.35)", borderRadius: 10, background: "rgba(2,6,23,0.55)" }}>
          <header style={{ padding: 12, borderBottom: "1px solid rgba(148,163,184,0.25)", display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <strong>Response</strong>
            <span style={{ color: status && status >= 400 ? "#fca5a5" : "#86efac" }}>
              {loading ? "Loading..." : status ? `HTTP ${status}` : "No request yet"}
            </span>
          </header>
          <pre style={{ margin: 0, padding: 12, overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 13, lineHeight: 1.5 }}>
            {output}
          </pre>
        </section>
      </div>
    </main>
  );
}
