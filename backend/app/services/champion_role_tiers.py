from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

logger = logging.getLogger(__name__)

CSV_PATH_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "data" / "champion_role_tiers.csv",  # backend/data
    Path(__file__).resolve().parent.parent / "data" / "champion_role_tiers.csv",  # backend/app/data (legacy)
]

_ALLOWED_TIERS = {"S", "A", "B"}
_TIER_RANK = {"S": 0, "A": 1, "B": 2}
_ROLE_ORDER = {"TOP": 0, "JUNGLE": 1, "MID": 2, "BOTTOM": 3, "SUPPORT": 4}

_ROLE_ALIASES = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MID": "MID",
    "MIDDLE": "MID",
    "BOTTOM": "BOTTOM",
    "BOT": "BOTTOM",
    "ADC": "BOTTOM",
    "DUO_CARRY": "BOTTOM",
    "SUPPORT": "SUPPORT",
    "UTILITY": "SUPPORT",
    "DUO_SUPPORT": "SUPPORT",
}

_DDRAGON_TO_DISPLAY_ROLE = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "BOTTOM": "BOTTOM",
    "UTILITY": "SUPPORT",
}


class ChampionRoleTier(TypedDict):
    role: str
    tier: str


def _normalize_name(raw: str) -> str:
    return "".join(ch for ch in raw.lower() if ch.isalnum())


def normalize_role(raw_role: Optional[str]) -> Optional[str]:
    if not raw_role:
        return None
    return _ROLE_ALIASES.get(raw_role.strip().upper())


def convert_ddragon_roles_to_display(roles: List[str]) -> List[str]:
    mapped: List[str] = []
    seen: set[str] = set()
    for role in roles:
        display_role = _DDRAGON_TO_DISPLAY_ROLE.get(role.upper())
        if display_role and display_role not in seen:
            mapped.append(display_role)
            seen.add(display_role)
    return mapped


def _resolve_csv_path() -> Optional[Path]:
    for candidate in CSV_PATH_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _csv_cache_token() -> str:
    csv_path = _resolve_csv_path()
    if csv_path is None:
        return "missing"
    return f"{csv_path}:{csv_path.stat().st_mtime_ns}"


@lru_cache(maxsize=2)
def _load_csv_indexes(cache_token: str) -> Tuple[Dict[int, List[ChampionRoleTier]], Dict[str, List[ChampionRoleTier]]]:
    by_id: Dict[int, Dict[str, str]] = {}
    by_name: Dict[str, Dict[str, str]] = {}

    csv_path = _resolve_csv_path()

    if csv_path is None:
        logger.warning("Champion role tier CSV not found in any expected path: %s", CSV_PATH_CANDIDATES)
        return {}, {}

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("champion_name") or "").strip()
                role = normalize_role(row.get("role"))
                tier = (row.get("tier") or "").strip().upper()
                champion_id_raw = (row.get("champion_id") or "").strip()

                if not name or not role or tier not in _ALLOWED_TIERS:
                    continue

                champion_id: Optional[int] = None
                if champion_id_raw:
                    try:
                        champion_id = int(champion_id_raw)
                    except ValueError:
                        champion_id = None

                if champion_id is not None:
                    by_id.setdefault(champion_id, {})
                    prev = by_id[champion_id].get(role)
                    if prev is None or _TIER_RANK[tier] < _TIER_RANK[prev]:
                        by_id[champion_id][role] = tier

                name_key = _normalize_name(name)
                if name_key:
                    by_name.setdefault(name_key, {})
                    prev = by_name[name_key].get(role)
                    if prev is None or _TIER_RANK[tier] < _TIER_RANK[prev]:
                        by_name[name_key][role] = tier
    except Exception as exc:
        logger.warning("Failed to load champion role tier CSV (%s): %s", csv_path, exc)
        return {}, {}

    def _sorted_rows(role_tier_map: Dict[str, str]) -> List[ChampionRoleTier]:
        entries = [{"role": role, "tier": tier} for role, tier in role_tier_map.items()]
        entries.sort(key=lambda e: (_TIER_RANK.get(e["tier"], 99), _ROLE_ORDER.get(e["role"], 99)))
        return entries

    by_id_rows = {cid: _sorted_rows(role_tier_map) for cid, role_tier_map in by_id.items()}
    by_name_rows = {name_key: _sorted_rows(role_tier_map) for name_key, role_tier_map in by_name.items()}
    return by_id_rows, by_name_rows


def get_champion_role_tiers(champion_id: int, champion_name: str) -> List[ChampionRoleTier]:
    by_id, by_name = _load_csv_indexes(_csv_cache_token())

    from_id = by_id.get(champion_id)
    if from_id:
        return from_id

    return by_name.get(_normalize_name(champion_name), [])


def visible_roles_from_tiers(role_tiers: List[ChampionRoleTier]) -> List[str]:
    high_confidence_roles = [entry["role"] for entry in role_tiers if entry["tier"] in {"S", "A"}]
    if high_confidence_roles:
        return high_confidence_roles

    # Fall back to B tiers so champions without S/A entries still surface a role.
    return [entry["role"] for entry in role_tiers if entry["tier"] == "B"]
