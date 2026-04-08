"""
ddragon.py — Data Dragon static-data service.

Caches all DDragon data once per process lifetime (never re-fetched).
All getters are safe to call concurrently; on any network failure they
return empty dicts/None so callers never crash.

Public API
----------
get_champion_map()        → {champion_key_int: name}
get_champion_full_map()   → {champion_key_int: ChampionMeta dict}
get_rune_map()            → {rune_id_int: name}
get_latest_version()      → "15.1.1"  (current patch string)
resolve(id, map)          → name or None
get_champion_image_url(key_int) → CDN image URL or None
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, TypedDict

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDragon URL constants
# ---------------------------------------------------------------------------

_VERSIONS_URL  = "https://ddragon.leagueoflegends.com/api/versions.json"
_CHAMPION_URL  = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
_RUNES_URL     = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json"
_IMAGE_URL     = "https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{filename}"

# ---------------------------------------------------------------------------
# LoL role affinity: champion tags → primary roles they can play.
# Sourced from Riot's own tag taxonomy + meta conventions.
# This is used for champion-to-role recommendations in the team builder.
# ---------------------------------------------------------------------------

# Tags come directly from DDragon champion.json["data"][name]["tags"] list.
_TAG_ROLE_AFFINITY: Dict[str, List[str]] = {
    "Fighter":   ["TOP", "JUNGLE"],
    "Tank":      ["TOP", "JUNGLE", "UTILITY"],
    "Mage":      ["MIDDLE", "UTILITY"],
    "Assassin":  ["MIDDLE", "JUNGLE"],
    "Marksman":  ["BOTTOM"],
    "Support":   ["UTILITY"],
    "Specialist":["TOP", "JUNGLE", "MIDDLE"],
}

# ---------------------------------------------------------------------------
# TypedDict for full champion metadata record
# ---------------------------------------------------------------------------

class ChampionMeta(TypedDict):
    id:             int            # Riot numeric key, e.g. 1 (Annie)
    key:            str            # Riot string key, e.g. "Annie"
    name:           str            # Display name, e.g. "Annie"
    title:          str            # e.g. "the Dark Child"
    tags:           List[str]      # e.g. ["Mage", "Support"]
    image_url:      Optional[str]  # Full CDN URL to splash icon
    image_filename: str            # e.g. "Annie.png"
    role_affinity:  List[str]      # Inferred LoL roles, e.g. ["MIDDLE","UTILITY"]
    blurb:          str            # Short lore blurb
    stats:          dict           # Base stats dict from DDragon


# ---------------------------------------------------------------------------
# Module-level caches — populated once, never re-fetched
# ---------------------------------------------------------------------------

_champion_map:      Dict[int, str]          = {}   # {key_int: name}
_champion_full_map: Dict[int, ChampionMeta] = {}   # {key_int: ChampionMeta}
_champion_loaded:   bool = False

_rune_map:    Dict[int, str] = {}
_rune_loaded: bool = False

_latest_version: Optional[str] = None

# Backward-compat alias used by ai_service.py
_loaded: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_role_affinity(tags: List[str]) -> List[str]:
    """Map DDragon tag list to LoL role list, deduped and ordered."""
    roles: List[str] = []
    seen: set = set()
    for tag in tags:
        for role in _TAG_ROLE_AFFINITY.get(tag, []):
            if role not in seen:
                roles.append(role)
                seen.add(role)
    return roles or ["FILL"]


async def _fetch_latest_version(client: httpx.AsyncClient) -> str:
    global _latest_version
    if _latest_version:
        return _latest_version
    resp = await client.get(_VERSIONS_URL)
    resp.raise_for_status()
    _latest_version = resp.json()[0]
    return _latest_version


# ---------------------------------------------------------------------------
# Public getters
# ---------------------------------------------------------------------------

async def get_latest_version() -> Optional[str]:
    """Return the current DDragon patch string, e.g. '15.1.1'."""
    global _latest_version
    if _latest_version:
        return _latest_version
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await _fetch_latest_version(client)
    except Exception as exc:
        logger.warning("DDragon version fetch failed: %s", exc)
        return None


async def get_champion_map() -> Dict[int, str]:
    """
    Return {champion_key_int: champion_name}.
    Fetches once per process; subsequent calls are O(1).
    Returns empty dict on any DDragon failure.
    """
    global _champion_map, _champion_loaded, _loaded
    if _champion_loaded:
        return _champion_map

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            version = await _fetch_latest_version(client)
            champ_resp = await client.get(_CHAMPION_URL.format(version=version))
            champ_resp.raise_for_status()
            data: dict = champ_resp.json().get("data", {})

        mapping: Dict[int, str] = {}
        for entry in data.values():
            key = entry.get("key")
            name = entry.get("name")
            if key is not None and name:
                try:
                    mapping[int(key)] = name
                except (ValueError, TypeError):
                    pass

        _champion_map = mapping
        _champion_loaded = True
        _loaded = True
        logger.info("DDragon champion map loaded: %d champions (patch %s)", len(_champion_map), version)
    except Exception as exc:
        logger.warning("DDragon champion map fetch failed: %s", exc)

    return _champion_map


async def get_champion_full_map() -> Dict[int, ChampionMeta]:
    """
    Return full champion metadata keyed by numeric champion id.
    Includes: name, title, tags, image_url, role_affinity, blurb, base stats.
    Fetches once per process; O(1) after first call.
    Returns empty dict on any DDragon failure.

    Used by:
      - GET /champions              (list all)
      - GET /champions/{id}         (single champion detail)
      - champion synergy scoring in teams router
      - role affinity checks in AI analysis
    """
    global _champion_full_map, _champion_map, _champion_loaded, _loaded

    # If full map already populated, return it immediately
    if _champion_full_map:
        return _champion_full_map

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            version = await _fetch_latest_version(client)
            champ_resp = await client.get(_CHAMPION_URL.format(version=version))
            champ_resp.raise_for_status()
            data: dict = champ_resp.json().get("data", {})

        full_map:    Dict[int, ChampionMeta] = {}
        simple_map:  Dict[int, str]          = {}

        for entry in data.values():
            raw_key = entry.get("key")
            name    = entry.get("name", "")
            if raw_key is None or not name:
                continue
            try:
                key_int = int(raw_key)
            except (ValueError, TypeError):
                continue

            tags          = entry.get("tags", [])
            image_file    = entry.get("image", {}).get("full", f"{entry.get('id','')}.png")
            image_url_str = _IMAGE_URL.format(version=version, filename=image_file)
            role_affinity = _build_role_affinity(tags)

            meta: ChampionMeta = {
                "id":             key_int,
                "key":            entry.get("id", ""),       # string key e.g. "Annie"
                "name":           name,
                "title":          entry.get("title", ""),
                "tags":           tags,
                "image_url":      image_url_str,
                "image_filename": image_file,
                "role_affinity":  role_affinity,
                "blurb":          entry.get("blurb", ""),
                "stats":          entry.get("stats", {}),
            }
            full_map[key_int]   = meta
            simple_map[key_int] = name

        _champion_full_map = full_map
        # Also keep simple map in sync so callers of get_champion_map() don't need a second fetch
        _champion_map    = simple_map
        _champion_loaded = True
        _loaded          = True
        logger.info(
            "DDragon full champion map loaded: %d champions (patch %s)",
            len(_champion_full_map),
            version,
        )
    except Exception as exc:
        logger.warning("DDragon full champion map fetch failed: %s", exc)

    return _champion_full_map


async def get_rune_map() -> Dict[int, str]:
    """
    Return {rune_id_int: rune_name} from runesReforged.json.
    Covers both path IDs (e.g. 8000 → 'Precision') and individual perk IDs.
    Returns empty dict on any DDragon failure.
    """
    global _rune_map, _rune_loaded
    if _rune_loaded:
        return _rune_map

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            version = await _fetch_latest_version(client)
            runes_resp = await client.get(_RUNES_URL.format(version=version))
            runes_resp.raise_for_status()
            paths: list = runes_resp.json()

        mapping: Dict[int, str] = {}
        for path in paths:
            path_id = path.get("id")
            if path_id is not None:
                mapping[int(path_id)] = path.get("name", "")
            for slot in path.get("slots", []):
                for rune in slot.get("runes", []):
                    rune_id = rune.get("id")
                    if rune_id is not None:
                        mapping[int(rune_id)] = rune.get("name", "")

        _rune_map    = mapping
        _rune_loaded = True
        logger.info("DDragon rune map loaded: %d entries (patch %s)", len(_rune_map), version)
    except Exception as exc:
        logger.warning("DDragon rune fetch failed: %s", exc)

    return _rune_map


def resolve(champion_id: int, champion_map: Dict[int, str]) -> Optional[str]:
    """Look up champion name from a pre-loaded map. Returns None if not found."""
    return champion_map.get(champion_id)


def get_champion_image_url(champion_key_int: int) -> Optional[str]:
    """
    Return the CDN image URL for a champion from the in-process cache.
    Returns None if the full map hasn't been loaded yet or key not found.
    Frontend can use this directly as <img src=...>.
    """
    meta = _champion_full_map.get(champion_key_int)
    return meta["image_url"] if meta else None
