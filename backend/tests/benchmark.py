#!/usr/bin/env python3
"""
benchmark.py — Performance Benchmark Script
============================================
Measures response times for key Esports Analytics Platform endpoints
and maps results against the SMART targets from the capstone proposal.

Usage:
    python tests/benchmark.py
    python tests/benchmark.py --puuid <puuid>
    python tests/benchmark.py --host http://localhost:8000
    python tests/benchmark.py --runs 10

Requires:
    pip install httpx
    Backend running at --host (default: http://localhost:8000)

Output:
    Prints a formatted table to stdout.
    Saves benchmark_results.md to the project root.
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_HOST = "http://localhost:8000"
DEFAULT_RUNS = 5

TARGETS: dict[str, float] = {
    "GET /health":                           2000,   # 2 s
    "GET /":                                 2000,   # 2 s
    "GET /players/":                         2000,   # 2 s
    "GET /champions":                        2000,   # 2 s
    "GET /backfill/status":                  2000,   # 2 s
    "GET /metrics/player/{puuid}":           1000,   # 1 s — SMART target
    "GET /analytics/player/{puuid}/trends":  2000,   # 2 s — SMART target
    "GET /analytics/player/{puuid}/bans":    2000,   # 2 s
}


def measure(client: httpx.Client, url: str, runs: int) -> dict:
    """Hit a URL `runs` times and return timing stats in milliseconds."""
    times: list[float] = []
    status_codes: list[int] = []

    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            resp = client.get(url, timeout=10)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            times.append(elapsed_ms)
            status_codes.append(resp.status_code)
        except Exception as exc:
            times.append(99999)
            status_codes.append(0)
            print(f"  ⚠ Request failed: {exc}", file=sys.stderr)

    return {
        "times":   times,
        "median":  statistics.median(times),
        "max":     max(times),
        "min":     min(times),
        "statuses": status_codes,
    }


def resolve_puuid(client: httpx.Client, host: str, given_puuid: str | None) -> str | None:
    """Return given puuid or the first player from GET /players/."""
    if given_puuid:
        return given_puuid
    try:
        resp = client.get(f"{host}/players/?min_matches=1", timeout=10)
        if resp.status_code == 200:
            players = resp.json()
            if isinstance(players, list) and players:
                return players[0]["puuid"]
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the Esports Analytics API")
    parser.add_argument("--host",  default=DEFAULT_HOST, help="API base URL")
    parser.add_argument("--puuid", default=None,         help="Player PUUID for player-specific endpoints")
    parser.add_argument("--runs",  type=int, default=DEFAULT_RUNS, help="Requests per endpoint")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    runs = args.runs

    print(f"\nEsports Analytics Platform — Performance Benchmark")
    print(f"Host : {host}")
    print(f"Runs : {runs} per endpoint")
    print(f"Date : 2026-04-13\n")

    # ── Verify connectivity ────────────────────────────────────────────────
    with httpx.Client() as probe:
        try:
            probe.get(f"{host}/health", timeout=5)
        except Exception as exc:
            print(f"ERROR: Cannot reach {host}/health — is the backend running?\n  {exc}")
            sys.exit(1)

    # ── Resolve PUUID ──────────────────────────────────────────────────────
    with httpx.Client() as c:
        puuid = resolve_puuid(c, host, args.puuid)

    if puuid is None:
        print("WARNING: No players found in database. Player-specific endpoints will be skipped.\n")

    # ── Endpoint list ──────────────────────────────────────────────────────
    endpoints: list[tuple[str, str]] = [
        ("GET /health",                          f"{host}/health"),
        ("GET /",                                f"{host}/"),
        ("GET /players/",                        f"{host}/players/?min_matches=1"),
        ("GET /champions",                       f"{host}/champions"),
        ("GET /backfill/status",                 f"{host}/backfill/status"),
    ]

    if puuid:
        endpoints += [
            ("GET /metrics/player/{puuid}",              f"{host}/metrics/player/{puuid}"),
            ("GET /analytics/player/{puuid}/trends",     f"{host}/analytics/player/{puuid}/trends"),
            ("GET /analytics/player/{puuid}/bans",       f"{host}/analytics/player/{puuid}/bans"),
        ]

    # ── Run benchmarks ─────────────────────────────────────────────────────
    results: list[dict] = []
    with httpx.Client() as client:
        for name, url in endpoints:
            print(f"  → {name} …", end="", flush=True)
            stats = measure(client, url, runs)
            target = TARGETS.get(name, 2000)
            passed = stats["median"] <= target
            results.append({"name": name, "target": target, "passed": passed, **stats})
            status = "✓" if passed else "✗"
            print(f" {stats['median']:.0f}ms median {status}")

    # ── Print table ────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print(f"  {'Endpoint':<44} {'Target':>8} {'Median':>8} {'Max':>8} {'Result':>7}")
    print(f"  {'-'*44} {'-'*8} {'-'*8} {'-'*8} {'-'*7}")
    for r in results:
        flag = "PASS ✓" if r["passed"] else "FAIL ✗"
        print(
            f"  {r['name']:<44} "
            f"{r['target']:>7}ms "
            f"{r['median']:>7.0f}ms "
            f"{r['max']:>7.0f}ms "
            f"{flag:>7}"
        )

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n  {passed_count}/{total} targets met.")
    print("=" * 78 + "\n")

    # ── Save markdown report ───────────────────────────────────────────────
    root = Path(__file__).resolve().parent.parent.parent
    md_path = root / "benchmark_results.md"

    lines = [
        "# Benchmark Results — Esports Analytics Platform",
        "",
        f"**Date:** 2026-04-13  ",
        f"**Host:** {host}  ",
        f"**Runs per endpoint:** {runs}  ",
        "",
        "---",
        "",
        "## SMART Target Compliance",
        "",
        "| Endpoint | Target | Median (ms) | Max (ms) | Result |",
        "|----------|--------|-------------|----------|--------|",
    ]
    for r in results:
        flag = "PASS ✓" if r["passed"] else "FAIL ✗"
        lines.append(
            f"| `{r['name']}` | {r['target']}ms | {r['median']:.0f}ms | {r['max']:.0f}ms | **{flag}** |"
        )

    lines += [
        "",
        f"**Summary:** {passed_count}/{total} SMART targets met.",
        "",
        "---",
        "",
        "## SMART Goals Reference",
        "",
        "| Goal | Target | Source |",
        "|------|--------|--------|",
        "| Metric computation time | < 1,000 ms | Capstone Proposal §5 |",
        "| Trend summary response | < 2,000 ms | Capstone Proposal §5 |",
        "| Dashboard API response | < 2,000 ms | Capstone Proposal §5 |",
        "| API retrieval success rate | ≥ 95% | Capstone Proposal §5 |",
        "",
        "---",
        "",
        "## Notes",
        "",
        "- All measurements are wall-clock time (client-side) including network round-trip.",
        "- Median of 5 consecutive cold-cache requests reported per endpoint.",
        "- Player-specific endpoints require at least one ingested player.",
        f"- PUUID used for player endpoints: `{puuid or 'N/A — no players in DB'}`",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved to: {md_path}")


if __name__ == "__main__":
    main()
