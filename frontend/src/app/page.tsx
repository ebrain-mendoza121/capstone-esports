"use client";

import { useEffect, useMemo, useState } from "react";
import { buildApiUrl, getApiBaseUrl } from "@/lib/apiBaseUrl";

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

  const envRaw = process.env.NEXT_PUBLIC_API_URL ?? "";

  useEffect(() => {
    setProtocol(window.location.protocol);
    setResolvedApiBase(getApiBaseUrl());
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
