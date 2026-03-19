import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RiotApiError(RuntimeError):
    pass


class RiotClient:
    """Riot Games API client with retry logic."""
    
    def __init__(self):
        self.headers = {"X-Riot-Token": settings.riot_api_key}

    async def _request_json(
        self, 
        routing: str, 
        path: str, 
        params: Optional[dict] = None
    ) -> Any:
        """Make HTTP GET request with retry logic."""
        routing_host = routing.lower()
        base_url = f"https://{routing_host}.api.riotgames.com"
        url = f"{base_url}{path}"

        last_exc: Optional[Exception] = None
        for attempt in range(settings.riot_max_retries):
            try:
                async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                    resp = await client.get(url, headers=self.headers, params=params)

                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                    else:
                        await asyncio.sleep(settings.riot_backoff_base_seconds * (2**attempt))
                    continue

                if 500 <= resp.status_code < 600:
                    await asyncio.sleep(settings.riot_backoff_base_seconds * (2**attempt))
                    continue

                if resp.status_code >= 400:
                    raise RiotApiError(f"Riot API error {resp.status_code}: {resp.text}")

                return resp.json()

            except Exception as e:
                last_exc = e
                await asyncio.sleep(settings.riot_backoff_base_seconds * (2**attempt))

        raise RiotApiError(f"Riot API failed after retries. Last error: {last_exc}")

    async def get_puuid(self, game_name: str, tag_line: str, routing: str) -> str:
        """Get player PUUID from Riot ID."""
        data = await self._request_json(
            routing=routing,
            path=f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        )
        puuid = data.get("puuid")
        if not puuid:
            raise RiotApiError("PUUID not found in Account-V1 response.")
        return puuid

    async def get_match_ids(
        self,
        puuid: str,
        routing: str,
        start: int = 0,
        count: int = 20,
        queue: Optional[int] = None,
    ) -> List[str]:
        """Get list of match IDs for a player."""
        params = {"start": start, "count": count}
        
        if queue is not None:
            params["queue"] = queue
        
        logger.info(f"get_match_ids - routing={routing}, puuid={puuid[:8]}..., params={params}")
        
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            params=params
        )
        if not isinstance(data, list):
            raise RiotApiError("Unexpected response for match IDs.")
        
        logger.info(f"get_match_ids - returned {len(data)} match IDs")
        return data

    async def get_match(self, match_id: str, routing: str) -> Dict[str, Any]:
        """Get detailed match data."""
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/{match_id}"
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for match detail.")
        return data

    async def get_match_timeline(self, match_id: str, routing: str) -> Dict[str, Any]:
        """Get match timeline (per-minute frames + events)."""
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/{match_id}/timeline"
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for match timeline.")
        return data
