import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.settings import settings

# Set up logger
logger = logging.getLogger(__name__)


class RiotApiError(RuntimeError):
    pass


class RiotClient:
    """
    Riot Games API client with per-request routing support.
    
    This client handles:
    - Account-V1 API (PUUID lookup)
    - Match-V5 API (match history and details)
    - Automatic retry logic with exponential backoff
    - Rate limit handling
    
    Note: Match-V5 calls require routing parameter to target correct regional endpoint.
    """
    
    def __init__(self):
        """Initialize RiotClient with API key from settings."""
        self.headers = {"X-Riot-Token": settings.RIOT_API_KEY}

    async def _request_json(
        self, 
        routing: str, 
        path: str, 
        params: Optional[dict] = None
    ) -> Any:
        """
        Make an HTTP GET request to Riot API with retry logic.
        
        Args:
            routing: Regional routing (americas, europe, asia, sea)
            path: API endpoint path (e.g., "/lol/match/v5/matches/{id}")
            params: Optional query parameters
            
        Returns:
            JSON response data
            
        Raises:
            RiotApiError: If request fails after all retries
        """
        routing_host = routing.lower()
        base_url = f"https://{routing_host}.api.riotgames.com"
        url = f"{base_url}{path}"

        last_exc: Optional[Exception] = None
        for attempt in range(settings.RIOT_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
                    resp = await client.get(url, headers=self.headers, params=params)

                # Rate limit / transient errors
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                    else:
                        await asyncio.sleep(settings.RIOT_BACKOFF_BASE_SECONDS * (2**attempt))
                    continue

                if 500 <= resp.status_code < 600:
                    await asyncio.sleep(settings.RIOT_BACKOFF_BASE_SECONDS * (2**attempt))
                    continue

                if resp.status_code >= 400:
                    raise RiotApiError(f"Riot API error {resp.status_code}: {resp.text}")

                return resp.json()

            except Exception as e:
                last_exc = e
                await asyncio.sleep(settings.RIOT_BACKOFF_BASE_SECONDS * (2**attempt))

        raise RiotApiError(f"Riot API failed after retries. Last error: {last_exc}")

    async def get_puuid(self, game_name: str, tag_line: str, routing: str) -> str:
        """
        Get player PUUID from Riot ID using Account-V1 API.
        
        Args:
            game_name: Riot ID game name
            tag_line: Riot ID tag line
            routing: Regional routing (americas, europe, asia, sea)
            
        Returns:
            Player's PUUID
            
        Raises:
            RiotApiError: If player not found or API error
        """
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
        type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[str]:
        """
        Get list of match IDs for a player using Match-V5 API.
        
        Args:
            puuid: Player's PUUID
            routing: Regional routing (americas, europe, asia, sea)
            start: Starting index (for pagination)
            count: Number of matches to return (max 100)
            queue: Optional queue ID filter
            type: Optional match type filter (ranked, normal, tourney, tutorial)
            start_time: Optional epoch timestamp (seconds) - matches after this time
            end_time: Optional epoch timestamp (seconds) - matches before this time
            
        Returns:
            List of match IDs
            
        Raises:
            RiotApiError: If API error occurs
        """
        params = {"start": start, "count": count}
        
        if queue is not None:
            params["queue"] = queue
        if type is not None:
            params["type"] = type
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        # Log request parameters for debugging
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
        """
        Get detailed match data using Match-V5 API.
        
        Args:
            match_id: Match ID (e.g., "NA1_1234567890")
            routing: Regional routing (americas, europe, asia, sea)
            
        Returns:
            Match data dictionary
            
        Raises:
            RiotApiError: If match not found or API error
        """
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/{match_id}"
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for match detail.")
        return data

    async def get_timeline(self, match_id: str, routing: str) -> Dict[str, Any]:
        """
        Get match timeline data using Match-V5 API.
        
        Args:
            match_id: Match ID (e.g., "NA1_1234567890")
            routing: Regional routing (americas, europe, asia, sea)
            
        Returns:
            Timeline data dictionary
            
        Raises:
            RiotApiError: If timeline not found or API error
            
        Note: Optional feature - not currently used in ingestion pipeline.
        """
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/{match_id}/timeline"
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for match timeline.")
        return data