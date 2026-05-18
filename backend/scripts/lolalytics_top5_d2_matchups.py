#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOLALYTICS_BASE = "https://lolalytics.com"
DDRAGON_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_CHAMPION_JSON = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"

LOLALYTICS_TO_OUTPUT_ROLE = {
    "top": "TOP",
    "jungle": "JUNGLE",
    "middle": "MIDDLE",
    "bottom": "BOTTOM",
    "support": "UTILITY",
}

SLUG_OVERRIDES_BY_DDRAGON_ID = {
    "AurelionSol": "aurelionsol",
    "Belveth": "belveth",
    "Chogath": "chogath",
    "DrMundo": "drmundo",
    "JarvanIV": "jarvaniv",
    "Kaisa": "kaisa",
    "Khazix": "khazix",
    "KogMaw": "kogmaw",
    "Leblanc": "leblanc",
    "LeeSin": "leesin",
    "MasterYi": "masteryi",
    "MissFortune": "missfortune",
    "MonkeyKing": "wukong",
    "Nunu": "nunu",
    "RekSai": "reksai",
    "Renata": "renata",
    "TahmKench": "tahmkench",
    "TwistedFate": "twistedfate",
    "Velkoz": "velkoz",
    "XinZhao": "xinzhao",
    "KSante": "ksante",
}
SLUG_OVERRIDES_BY_NAME = {
    "Nunu & Willump": "nunu",
    "Renata Glasc": "renata",
}

MAIN_ROLE_RE = re.compile(
    r"(?P<name>.+?)\s+(?P<role>top|jungle|middle|bottom|support)\s+has a\s+[\d.]+%\s+win rate in D2\+\s+on Patch\s+(?P<patch>\d+\.\d+)",
    re.IGNORECASE,
)
ANCHOR_COUNTER_RE = re.compile(
    r"^(?P<opponent>.+?)\s+(?P<wr>\d+\.\d+)\s*%\s*VS\b.*?(?P<games>[\d,]+)\s+Games$",
    re.IGNORECASE,
)

@dataclass
class Champion:
    ddragon_id: str
    name: str
    slug: str

@dataclass
class MatchupRow:
    champion_a: str
    champion_b: str
    role: str
    win_rate_a_vs_b: float
    games_played: int
    patch: str
    source: str = "lolalytics"

def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }
    )
    return session

def normalize_slug_from_name(name: str) -> str:
    slug = name.lower().replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "", slug)
    return slug

def get_latest_ddragon_version(session: requests.Session) -> str:
    r = session.get(DDRAGON_VERSIONS_URL, timeout=30)
    r.raise_for_status()
    versions = r.json()
    if not versions:
        raise RuntimeError("No Data Dragon versions returned.")
    return versions[0]

def get_champions(session: requests.Session, version: str) -> List[Champion]:
    url = DDRAGON_CHAMPION_JSON.format(version=version)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()["data"]

    champions: List[Champion] = []
    for champ_id, info in data.items():
        display_name = info["name"]
        slug = (
            SLUG_OVERRIDES_BY_DDRAGON_ID.get(champ_id)
            or SLUG_OVERRIDES_BY_NAME.get(display_name)
            or normalize_slug_from_name(display_name)
        )
        champions.append(Champion(ddragon_id=champ_id, name=display_name, slug=slug))

    champions.sort(key=lambda c: c.name)
    return champions

def fetch_html(session: requests.Session, url: str, sleep_seconds: float) -> str:
    r = session.get(url, timeout=30)
    if r.status_code == 404:
        raise FileNotFoundError(f"404 for {url}")
    r.raise_for_status()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return r.text

def extract_main_role_and_patch(html: str) -> Tuple[str, str]:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = MAIN_ROLE_RE.search(text)
    if not match:
        raise ValueError("Could not determine main role / patch from build page.")
    return match.group("role").lower(), match.group("patch")

def parse_counter_rows(html: str) -> List[Tuple[str, float, int]]:
    soup = BeautifulSoup(html, "html.parser")
    dedup: Dict[str, Tuple[float, int]] = {}

    for a in soup.find_all("a"):
        text = " ".join(a.get_text(" ", strip=True).split())
        m = ANCHOR_COUNTER_RE.match(text)
        if not m:
            continue
        opponent = m.group("opponent").strip()
        wr = float(m.group("wr")) / 100.0
        games = int(m.group("games").replace(",", ""))
        current = dedup.get(opponent)
        if current is None or games > current[1]:
            dedup[opponent] = (wr, games)

    if dedup:
        return [(opp, wr, games) for opp, (wr, games) in dedup.items()]

    text = soup.get_text("\n", strip=True)
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        m = ANCHOR_COUNTER_RE.match(line)
        if not m:
            continue
        opponent = m.group("opponent").strip()
        wr = float(m.group("wr")) / 100.0
        games = int(m.group("games").replace(",", ""))
        current = dedup.get(opponent)
        if current is None or games > current[1]:
            dedup[opponent] = (wr, games)

    return [(opp, wr, games) for opp, (wr, games) in dedup.items()]

def find_main_role(session: requests.Session, champion: Champion, sleep_seconds: float) -> Tuple[str, str]:
    url = f"{LOLALYTICS_BASE}/lol/{champion.slug}/build/?tier=d2_plus"
    html = fetch_html(session, url, sleep_seconds=sleep_seconds)
    return extract_main_role_and_patch(html)

def fetch_top_matchups(
    session: requests.Session,
    champion: Champion,
    main_role: str,
    patch: str,
    min_games: int,
    top_n: int,
    sleep_seconds: float,
) -> List[MatchupRow]:
    url = f"{LOLALYTICS_BASE}/lol/{champion.slug}/counters/?lane={main_role}&tier=d2_plus"
    html = fetch_html(session, url, sleep_seconds=sleep_seconds)

    parsed_rows = parse_counter_rows(html)
    if not parsed_rows:
        raise ValueError(f"No counter rows parsed for {champion.name} ({main_role}).")

    role_out = LOLALYTICS_TO_OUTPUT_ROLE[main_role]
    filtered = [
        MatchupRow(
            champion_a=champion.name,
            champion_b=opponent,
            role=role_out,
            win_rate_a_vs_b=wr,
            games_played=games,
            patch=patch,
        )
        for opponent, wr, games in parsed_rows
        if games > min_games and opponent != champion.name
    ]
    filtered.sort(key=lambda x: (-x.win_rate_a_vs_b, -x.games_played, x.champion_b))
    return filtered[:top_n]

def generate_dataset(
    session: requests.Session,
    min_games: int,
    top_n: int,
    sleep_seconds: float,
    champion_limit: Optional[int] = None,
) -> pd.DataFrame:
    version = get_latest_ddragon_version(session)
    champions = get_champions(session, version)
    if champion_limit is not None:
        champions = champions[:champion_limit]

    logging.info("Loaded %s champions from Data Dragon %s", len(champions), version)

    all_rows: List[MatchupRow] = []
    failures: List[str] = []

    for idx, champion in enumerate(champions, start=1):
        try:
            main_role, patch = find_main_role(session, champion, sleep_seconds=sleep_seconds)
            top_rows = fetch_top_matchups(
                session=session,
                champion=champion,
                main_role=main_role,
                patch=patch,
                min_games=min_games,
                top_n=top_n,
                sleep_seconds=sleep_seconds,
            )
            if top_rows:
                all_rows.extend(top_rows)
            logging.info("[%s/%s] %s -> %s (%s rows)", idx, len(champions), champion.name, main_role, len(top_rows))
        except Exception as exc:
            failures.append(f"{champion.name}: {exc}")
            logging.warning("[%s/%s] Failed %s: %s", idx, len(champions), champion.name, exc)

    df = pd.DataFrame(
        [
            {
                "champion_a": row.champion_a,
                "champion_b": row.champion_b,
                "role": row.role,
                "win_rate_a_vs_b": round(row.win_rate_a_vs_b, 3),
                "games_played": row.games_played,
                "patch": row.patch,
                "source": row.source,
            }
            for row in all_rows
        ]
    )
    if not df.empty:
        df = df.sort_values(
            by=["champion_a", "win_rate_a_vs_b", "games_played", "champion_b"],
            ascending=[True, False, False, True],
        ).reset_index(drop=True)

    if failures:
        logging.warning("Completed with %s failures.", len(failures))
        for failure in failures[:20]:
            logging.warning("Failure: %s", failure)

    return df

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate top D2+ LoL matchup CSV from LoLalytics.")
    parser.add_argument("--min-games", type=int, default=31, help="Minimum games threshold.")
    parser.add_argument("--top-n", type=int, default=5, help="Rows to keep per champion.")
    parser.add_argument("--sleep", type=float, default=1.25, help="Delay between requests in seconds.")
    parser.add_argument("--champion-limit", type=int, default=None, help="Optional limit for testing.")
    parser.add_argument("--out", type=str, default="lol_top5_d2_matchups.csv", help="Output CSV path.")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    session = build_session()
    df = generate_dataset(
        session=session,
        min_games=args.min_games,
        top_n=args.top_n,
        sleep_seconds=args.sleep,
        champion_limit=args.champion_limit,
    )
    df.to_csv(args.out, index=False, quoting=csv.QUOTE_MINIMAL)
    logging.info("Wrote %s rows to %s", len(df), args.out)

if __name__ == "__main__":
    main()
