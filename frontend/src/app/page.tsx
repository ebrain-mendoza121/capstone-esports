"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { buildApiUrl, getApiBaseUrl } from "@/lib/apiBaseUrl";

const QUICK_PUUID = "GXO6oaJPECfKU3Zr_5CAiUCEpGNGVq5zRrmXWbfoih49CX5D4_bw360rWA9skKW5Qf5PblEY7MNdtA";

interface QuickPlayer {
  riot_id: string;
  tag_line: string;
  region: string;
  match_count: number;
}

interface QuickMetrics {
  matches: number;
  win_rate: number;
  kda: number;
  cs_per_min: number;
}

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

  // Quick player card
  const [player, setPlayer] = useState<QuickPlayer | null>(null);
  const [metrics, setMetrics] = useState<QuickMetrics | null>(null);
  const [playerStatus, setPlayerStatus] = useState<"idle" | "loading" | "ok" | "error">("idle");

  const envRaw = process.env.NEXT_PUBLIC_API_URL ?? "";

  useEffect(() => {
    setProtocol(window.location.protocol);
    setResolvedApiBase(getApiBaseUrl());

    // Auto-load player card on mount
    setPlayerStatus("loading");
    Promise.all([
      fetch(buildApiUrl(`/players/${QUICK_PUUID}/`)).then((r) => r.ok ? r.json() : null),
      fetch(buildApiUrl(`/metrics/player/${QUICK_PUUID}/`)).then((r) => r.ok ? r.json() : null),
    ]).then(([p, m]) => {
      setPlayer(p as QuickPlayer | null);
      setMetrics(m as QuickMetrics | null);
      setPlayerStatus(p ? "ok" : "error");
    }).catch(() => setPlayerStatus("error"));
  }, []);

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

        {/* ── Quick Player Card ── */}
        <section style={{ marginTop: 16, padding: 16, border: "1px solid rgba(148,163,184,0.35)", borderRadius: 10, background: "rgba(2,6,23,0.35)" }}>
          <strong style={{ fontSize: 13, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase" }}>Quick Player Card</strong>
          {playerStatus === "loading" && (
            <p style={{ marginTop: 10, color: "#94a3b8", fontSize: 14 }}>Loading player…</p>
          )}
          {playerStatus === "error" && (
            <p style={{ marginTop: 10, color: "#fca5a5", fontSize: 14 }}>
              Player not found — make sure the backend is running and this PUUID is ingested.
            </p>
          )}
          {playerStatus === "ok" && player && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div style={{ background: "rgba(16,185,129,0.15)", border: "1px solid rgba(16,185,129,0.35)", borderRadius: 10, padding: "10px 18px" }}>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>{player.riot_id}<span style={{ color: "#64748b" }}>#{player.tag_line}</span></div>
                  <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>Region: {player.region} · {player.match_count} matches stored</div>
                </div>
                {metrics && (
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {[
                      { label: "Win Rate", value: `${(metrics.win_rate * 100).toFixed(1)}%`, highlight: metrics.win_rate >= 0.5 },
                      { label: "KDA", value: metrics.kda.toFixed(2), highlight: metrics.kda >= 3 },
                      { label: "CS/Min", value: metrics.cs_per_min.toFixed(1), highlight: false },
                      { label: "Games", value: String(metrics.matches), highlight: false },
                    ].map(({ label, value, highlight }) => (
                      <div key={label} style={{
                        padding: "8px 14px",
                        borderRadius: 8,
                        background: highlight ? "rgba(16,185,129,0.12)" : "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(148,163,184,0.2)",
                        textAlign: "center",
                      }}>
                        <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 2 }}>{label}</div>
                        <div style={{ fontSize: 18, fontWeight: 700, color: highlight ? "#34d399" : "#e5e7eb" }}>{value}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Link href={`/player/${QUICK_PUUID}`} style={{ padding: "7px 14px", borderRadius: 8, background: "rgba(99,102,241,0.25)", border: "1px solid rgba(99,102,241,0.45)", color: "#c7d2fe", textDecoration: "none", fontSize: 13, fontWeight: 600 }}>
                  → Player Dashboard
                </Link>
                <Link href={`/player/${QUICK_PUUID}/matches`} style={{ padding: "7px 14px", borderRadius: 8, background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", color: "#c7d2fe", textDecoration: "none", fontSize: 13, fontWeight: 600 }}>
                  → Match History
                </Link>
                <Link href={`/player/${QUICK_PUUID}/champions`} style={{ padding: "7px 14px", borderRadius: 8, background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", color: "#c7d2fe", textDecoration: "none", fontSize: 13, fontWeight: 600 }}>
                  → Champion Stats
                </Link>
                <Link href={`/player/${QUICK_PUUID}/trends`} style={{ padding: "7px 14px", borderRadius: 8, background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", color: "#c7d2fe", textDecoration: "none", fontSize: 13, fontWeight: 600 }}>
                  → Trends
                </Link>
              </div>
            </div>
          )}
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
