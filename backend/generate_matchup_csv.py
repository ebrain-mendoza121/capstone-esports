"""
generate_matchup_csv.py — Champion matchup CSV generator.

Pass 1: Derive real win rates from participant_stats (same match, same role, opposite teams).
Pass 2: Fill every remaining (champ_a, champ_b, role) pair with a neutral 0.5 win rate.

Champion names from participant_stats (Riot API display names) are validated
against the DDragon name list so the import endpoint accepts them all.
"""

import csv, os, requests
from collections import defaultdict
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

HOST         = "https://capstone-esports-production-5631.up.railway.app"
DATABASE_URL = os.environ["DATABASE_URL"]
PATCH        = "25.9"
ROLES        = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

engine  = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def fetch_valid_names():
    """Return a set of all valid DDragon champion display names."""
    print("Fetching DDragon champion list from backend...")
    resp = requests.get(f"{HOST}/champions", timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Response: {"count": N, "champions": [...], "filters": {...}}
    champions = data["champions"]
    valid = {c["name"] for c in champions}
    print(f"  Loaded {len(valid)} valid champion names from DDragon")
    return valid


def main():
    valid_names = fetch_valid_names()
    db = Session()

    # ── Pass 1: real win rates ────────────────────────────────────────────
    print("\nPass 1: computing real matchup win rates...")
    rows = db.execute(text("""
        SELECT ps_a.champion, ps_b.champion, ps_a.role, ps_a.win
        FROM participant_stats ps_a
        JOIN participant_stats ps_b
          ON  ps_a.match_id = ps_b.match_id
          AND ps_a.team_id  = 100
          AND ps_b.team_id  = 200
          AND ps_a.role     = ps_b.role
        WHERE ps_a.champion IS NOT NULL
          AND ps_b.champion IS NOT NULL
          AND ps_a.role IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
    """)).fetchall()
    print(f"  Head-to-head instances: {len(rows)}")

    stats   = defaultdict(lambda: {"wins": 0, "games": 0})
    skipped = 0
    for champ_a, champ_b, role, won in rows:
        if champ_a not in valid_names or champ_b not in valid_names:
            skipped += 1
            continue
        stats[(champ_a, champ_b, role)]["games"] += 1
        if won:
            stats[(champ_a, champ_b, role)]["wins"] += 1

    print(f"  Skipped (name not in DDragon): {skipped}")

    real_rows, covered = [], set()
    for (a, b, role), s in stats.items():
        wr  = round(s["wins"] / s["games"], 4)
        conf = "high" if s["games"] >= 30 else "medium" if s["games"] >= 10 else "low"
        real_rows.append({"champion_a": a, "champion_b": b, "role": role,
                          "win_rate_a_vs_b": wr, "games_played": s["games"],
                          "patch": PATCH, "source": "derived",
                          "notes": f"Derived from {s['games']} ingested matches"})
        covered.add((a, b, role))
    print(f"  Real matchup pairs written: {len(real_rows)}")

    # ── Pass 2: neutral fill ──────────────────────────────────────────────
    print("\nPass 2: neutral fill for missing pairs...")
    champ_role = db.execute(text("""
        SELECT DISTINCT champion, role FROM participant_stats
        WHERE champion IS NOT NULL
          AND role IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
    """)).fetchall()

    role_champs = defaultdict(set)
    for champ, role in champ_role:
        if champ in valid_names:
            role_champs[role].add(champ)

    for role in ROLES:
        print(f"    {role}: {len(role_champs[role])} champions")

    neutral_rows = []
    for role, champs in role_champs.items():
        for a in sorted(champs):
            for b in sorted(champs):
                if a != b and (a, b, role) not in covered:
                    neutral_rows.append({"champion_a": a, "champion_b": b, "role": role,
                                         "win_rate_a_vs_b": 0.5, "games_played": 0,
                                         "patch": PATCH, "source": "derived",
                                         "notes": "Neutral prior — no direct matchup data"})
    print(f"  Neutral rows: {len(neutral_rows)}")

    # ── Write CSV ─────────────────────────────────────────────────────────
    real_rows.sort(key=lambda r: r["games_played"], reverse=True)
    all_rows  = real_rows + neutral_rows
    out_path  = "matchup_data_derived.csv"
    fields    = ["champion_a","champion_b","role","win_rate_a_vs_b",
                 "games_played","patch","source","notes"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writeheader()
        csv.DictWriter(f, fieldnames=fields).writerows(all_rows)

    print(f"\n✅  {len(all_rows)} rows → {out_path}")
    print(f"    Real: {len(real_rows)}   Neutral: {len(neutral_rows)}")
    print(f"\nNext:")
    print(f"  python import_matchups_batched.py")
    print(f'  curl -X POST "{HOST}/ai/train/matchup-predictor"')
    db.close()

if __name__ == "__main__":
    main()
