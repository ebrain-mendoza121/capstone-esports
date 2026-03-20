import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
_CHAMPION_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
_RUNES_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json"

# Module-level cache — populated once per process lifetime, never re-fetched.
_champion_map: Dict[int, str] = {}
_champion_loaded: bool = False

# Rune cache: covers both path IDs and individual perk IDs → name.
# {rune_id_int: name_str}  e.g. {8000: "Precision", 8005: "Press the Attack", ...}
_rune_map: Dict[int, str] = {}
_rune_loaded: bool = False

# Keep old _loaded alias for backward compatibility with callers that inspect it directly.
_loaded: bool = False


async def get_champion_map() -> Dict[int, str]:
    """
    Return {champion_key_int: champion_name} mapping from Data Dragon.
    Fetches once per process lifetime; subsequent calls return the cached dict
    instantly with no I/O.  On any DDragon failure the empty dict is returned
    and champion_name fields will be None — callers never break.
    """
    global _champion_map, _champion_loaded, _loaded
    if _champion_loaded:
        return _champion_map

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            versions_resp = await client.get(_VERSIONS_URL)
            versions_resp.raise_for_status()
            latest: str = versions_resp.json()[0]

            champ_resp = await client.get(_CHAMPION_URL.format(version=latest))
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
        _loaded = True  # backward compat
        logger.info(
            "DDragon champion map loaded: %d champions (patch %s)",
            len(_champion_map),
            latest,
        )
    except Exception as exc:
        logger.warning("DDragon fetch failed, champion_name will be None: %s", exc)

    return _champion_map


async def get_rune_map() -> Dict[int, str]:
    """
    Return {rune_id_int: rune_name} mapping from Data Dragon runesReforged.json.
    Covers both rune path IDs (e.g. 8000 → "Precision") and individual perk IDs
    (e.g. 8005 → "Press the Attack").  Fetches once per process lifetime; on any
    DDragon failure the empty dict is returned and name fields will be None.
    """
    global _rune_map, _rune_loaded
    if _rune_loaded:
        return _rune_map

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            versions_resp = await client.get(_VERSIONS_URL)
            versions_resp.raise_for_status()
            latest: str = versions_resp.json()[0]

            runes_resp = await client.get(_RUNES_URL.format(version=latest))
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

        _rune_map = mapping
        _rune_loaded = True
        logger.info(
            "DDragon rune map loaded: %d entries (patch %s)",
            len(_rune_map),
            latest,
        )
    except Exception as exc:
        logger.warning("DDragon rune fetch failed, rune_name will be None: %s", exc)

    return _rune_map


def resolve(champion_id: int, champion_map: Dict[int, str]) -> Optional[str]:
    """Look up champion name from a pre-loaded map. Returns None if not found."""
    return champion_map.get(champion_id)
