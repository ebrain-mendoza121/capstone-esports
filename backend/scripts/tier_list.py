from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "champion_role_tiers.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
}

ROLE_URLS = {
    "TOP": "https://mobalytics.gg/lol/tier-list/top",
    "JUNGLE": "https://mobalytics.gg/lol/tier-list/jungle",
    "MID": "https://mobalytics.gg/lol/tier-list/mid",
    "BOTTOM": "https://mobalytics.gg/lol/tier-list/adc",
    "SUPPORT": "https://mobalytics.gg/lol/tier-list/support",
}

SOURCE_NAME = "mobalytics_high_elo"
TIER_BY_ROW_INDEX = {0: "S", 1: "A", 2: "B"}

ROLE_HEADING_MAP = {
    "TOP": "Top Tier List",
    "JUNGLE": "Jungle Tier List",
    "MID": "Mid Tier List",
    "BOTTOM": "Bot Tier List",
    "SUPPORT": "Support Tier List",
}

NAME_ALIASES = {
    "Wukong": "MonkeyKing",
    "Nunu & Willump": "Nunu",
    "Renata Glasc": "Renata",
    "Bel'Veth": "Belveth",
    "Cho'Gath": "Chogath",
    "Kai'Sa": "Kaisa",
    "Kha'Zix": "Khazix",
    "Kog'Maw": "KogMaw",
    "K'Sante": "KSante",
    "LeBlanc": "Leblanc",
    "Rek'Sai": "RekSai",
    "Vel'Koz": "Velkoz",
    "Tahm Kench": "TahmKench",
    "Dr. Mundo": "DrMundo",
    "Jarvan IV": "JarvanIV",
    "Aurelion Sol": "AurelionSol",
    "Master Yi": "MasterYi",
    "Miss Fortune": "MissFortune",
    "Twisted Fate": "TwistedFate",
    "Xin Zhao": "XinZhao",
}

SKIP_NAMES = {"Zaahen"}


@dataclass(frozen=True)
class CsvRow:
    champion_id: int
    champion_name: str
    role: str
    tier: str
    source: str
    patch: str


def _normalize_name(raw: str) -> str:
    return "".join(ch for ch in raw.lower() if ch.isalnum())


def _extract_patch(text: str) -> str:
    for pattern in (
        r"Current patch\s+(\d+\.\d+)",
        r"Our Patch\s+(\d+\.\d+)\s+Tier List",
        r"Patch\s+(\d+\.\d+)",
    ):
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    raise RuntimeError("Could not extract patch from page text.")


def _get_ddragon_version_for_patch(patch_short: str) -> str:
    versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    resp = requests.get(versions_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    versions: List[str] = resp.json()
    matches = [v for v in versions if v.startswith(f"{patch_short}.")]
    return matches[0] if matches else versions[0]


def _load_champion_lookup(dd_version: str) -> Dict[str, Tuple[int, str]]:
    champ_url = f"https://ddragon.leagueoflegends.com/cdn/{dd_version}/data/en_US/champion.json"
    resp = requests.get(champ_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()["data"]

    lookup: Dict[str, Tuple[int, str]] = {}
    for slug, champion in payload.items():
        champion_id = int(champion["key"])
        champion_name = champion["name"]

        for candidate in {
            slug,
            champion_name,
            _normalize_name(slug),
            _normalize_name(champion_name),
        }:
            lookup[candidate] = (champion_id, champion_name)

    return lookup


def _map_champion_name(raw_name: str, lookup: Dict[str, Tuple[int, str]]) -> Tuple[int, str]:
    key = _normalize_name(raw_name)
    if key in lookup:
        return lookup[key]

    alias = NAME_ALIASES.get(raw_name, raw_name)
    alias_key = _normalize_name(alias)
    if alias_key in lookup:
        return lookup[alias_key]

    raise KeyError(f"Champion not found in Data Dragon mapping: {raw_name}")



def _get_rendered_html_and_text(url: str) -> tuple[str, str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])

        # Speed up navigation by blocking unnecessary assets
        def handle_route(route):
            req = route.request
            resource_type = req.resource_type
            if resource_type in {"image", "media", "font"}:
                route.abort()
            else:
                route.continue_()

        page.route("**/*", handle_route)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Wait for the actual tier columns, not for the whole network to go idle
            page.wait_for_selector("div.m-k6csmr img[alt='S']", timeout=20000)
            page.wait_for_selector("div.m-k6csmr img[alt='A']", timeout=20000)
            page.wait_for_selector("div.m-k6csmr img[alt='B']", timeout=20000)

        except PlaywrightTimeoutError:
            # Fallback: still try to extract whatever rendered HTML is present
            pass

        html = page.content()
        text = page.locator("body").inner_text()
        browser.close()

    return html, text


def _extract_role_rows_from_html(html: str, role: str) -> list[list[str]]:
    soup = BeautifulSoup(html, "html.parser")

    tier_blocks = soup.find_all("div", class_="m-k6csmr")

    rows_by_tier = {}

    for block in tier_blocks:
        img = block.find("img")
        if not img:
            continue

        tier = img.get("alt")
        if tier not in {"S", "A", "B"}:
            continue

        champions = []
        seen = set()

        # find all champion links inside this tier block
        for a in block.find_all("a", href=True):
            href = a.get("href")

            if not href.startswith("/lol/champions/"):
                continue

            # extract champion name from URL
            # /lol/champions/aatrox/build → aatrox
            slug = href.split("/")[3]
            name = slug.replace("-", " ").title()

            # manual fixes
            name = name.replace("K Sante", "K'Sante")
            name = name.replace("Chogath", "Cho'Gath")
            name = name.replace("Kaisa", "Kai'Sa")
            name = name.replace("Khazix", "Kha'Zix")

            

            if name not in seen:
                seen.add(name)
                champions.append(name)

        if champions:
            rows_by_tier[tier] = champions

    # enforce order S, A, B
    rows = []
    for tier in ["S", "A", "B"]:
        if tier not in rows_by_tier:
            raise RuntimeError(f"{role} missing tier {tier}")
        rows.append(rows_by_tier[tier])

    return rows

def _build_rows_for_role(
    role: str,
    patch: str,
    role_rows: List[List[str]],
    champ_lookup: Dict[str, Tuple[int, str]],
) -> List[CsvRow]:
    output: List[CsvRow] = []
    for row_index, champion_names in enumerate(role_rows):
        tier = TIER_BY_ROW_INDEX[row_index]
        for raw_name in champion_names:
            try:
                champion_id, champion_name = _map_champion_name(raw_name, champ_lookup)
            except KeyError:
                continue
            output.append(
                CsvRow(
                    champion_id=champion_id,
                    champion_name=champion_name,
                    role=role,
                    tier=tier,
                    source=SOURCE_NAME,
                    patch=patch,
                )
            )
    return output


def _dedupe_best_rows(rows: Iterable[CsvRow]) -> List[CsvRow]:
    tier_rank = {"S": 0, "A": 1, "B": 2}
    best: Dict[Tuple[int, str], CsvRow] = {}

    for row in rows:
        key = (row.champion_id, row.role)
        prev = best.get(key)
        if prev is None or tier_rank[row.tier] < tier_rank[prev.tier]:
            best[key] = row

    out = list(best.values())
    out.sort(key=lambda r: (r.role, tier_rank[r.tier], r.champion_name))
    return out


def write_csv(path: Path = CSV_PATH) -> Path:
    all_rows: List[CsvRow] = []

    for role, url in ROLE_URLS.items():
        logger.info("Scraping %s from %s", role, url)
        rendered_html, page_text = _get_rendered_html_and_text(url)
        patch = _extract_patch(page_text)
        dd_version = _get_ddragon_version_for_patch(patch)
        champ_lookup = _load_champion_lookup(dd_version)

        role_rows = _extract_role_rows_from_html(rendered_html, role)
        logger.info("%s row sizes: %s", role, [len(r) for r in role_rows])
        logger.info("%s rows: %s", role, role_rows)

        all_rows.extend(_build_rows_for_role(role, patch, role_rows, champ_lookup))

    final_rows = _dedupe_best_rows(all_rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["champion_id", "champion_name", "role", "tier", "source", "patch"],
        )
        writer.writeheader()
        for row in final_rows:
            writer.writerow(
                {
                    "champion_id": row.champion_id,
                    "champion_name": row.champion_name,
                    "role": row.role,
                    "tier": row.tier,
                    "source": row.source,
                    "patch": row.patch,
                }
            )

    logger.info("Wrote %s rows to %s", len(final_rows), path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output_path = write_csv()
    print(f"Wrote CSV to {output_path}")