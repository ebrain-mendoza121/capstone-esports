import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# How many match-detail requests to fire concurrently.
# Riot dev keys: 100 req / 2 min = ~0.83 req/s sustained.
# Bursting to 5 concurrent is fine — we add a small inter-batch pause.
_MATCH_CONCURRENCY = 5

# ---------------------------------------------------------------------------
# Global semaphore — caps total concurrent outbound Riot API sessions across
# ALL simultaneous ingest/backfill requests.
#
# Without this, 5 concurrent /ingest/player calls each spawn up to 5 parallel
# match fetches = 25 simultaneous Riot requests, guaranteeing 429s and the
# 86-second sleep cascade.
#
# With limit=3: at most 3 ingest sessions run against Riot at once.
# The 4th caller queues and starts only when a slot frees up.
# ---------------------------------------------------------------------------
_riot_api_semaphore: asyncio.Semaphore = asyncio.Semaphore(3)


class RiotApiError(RuntimeError):
    pass


class RiotClient:
    """Riot Games API client with connection reuse and concurrent match fetching."""

    def __init__(self) -> None:
        self.headers = {"X-Riot-Token": settings.riot_api_key}
        # One shared client for the lifetime of this RiotClient instance.
        # This means a single TCP connection pool — no per-request handshake.
        self._client = httpx.AsyncClient(
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )

    async def close(self) -> None:
        """Release the underlying connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "RiotClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _request_json(
        self,
        routing: str,
        path: str,
        params: Optional[dict] = None,
    ) -> Any:
        """GET a Riot API endpoint with retry/back-off. Reuses the shared client.

        All outbound calls acquire _riot_api_semaphore first, capping total
        concurrent Riot API sessions at 3 across all simultaneous requests.
        This prevents the 429 cascade that occurs when multiple ingest calls
        fire in parallel and exhaust the dev-key rate limit simultaneously.
        """
        async with _riot_api_semaphore:
            return await self._request_json_inner(routing, path, params)

    async def _request_json_inner(
        self,
        routing: str,
        path: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Inner implementation — called only from _request_json inside the semaphore."""
        routing_host = routing.lower()
        url = f"https://{routing_host}.api.riotgames.com{path}"

        last_exc: Optional[Exception] = None
        for attempt in range(settings.riot_max_retries):
            try:
                resp = await self._client.get(url, params=params)

                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 0) or
                                 settings.riot_backoff_base_seconds * (2 ** attempt))
                    logger.warning("Rate-limited by Riot API — sleeping %.1fs", wait)
                    await asyncio.sleep(wait)
                    continue

                if 500 <= resp.status_code < 600:
                    await asyncio.sleep(settings.riot_backoff_base_seconds * (2 ** attempt))
                    continue

                if resp.status_code >= 400:
                    raise RiotApiError(
                        f"Riot API error {resp.status_code}: {resp.text}"
                    )

                return resp.json()

            except RiotApiError:
                raise
            except Exception as exc:
                last_exc = exc
                await asyncio.sleep(settings.riot_backoff_base_seconds * (2 ** attempt))

        raise RiotApiError(
            f"Riot API failed after {settings.riot_max_retries} retries. "
            f"Last error: {last_exc}"
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def get_puuid(self, game_name: str, tag_line: str, routing: str) -> str:
        data = await self._request_json(
            routing=routing,
            path=f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}",
        )
        puuid = data.get("puuid")
        if not puuid:
            raise RiotApiError("PUUID not found in Account-V1 response.")
        return puuid

    async def get_account_by_puuid(self, puuid: str, routing: str) -> Dict[str, Any]:
        """Resolve current Riot ID (gameName + tagLine) from a PUUID."""
        data = await self._request_json(
            routing=routing,
            path=f"/riot/account/v1/accounts/by-puuid/{puuid}",
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for account-by-puuid.")
        return data

    async def get_match_ids(
        self,
        puuid: str,
        routing: str,
        start: int = 0,
        count: int = 20,
        queue: Optional[int] = None,
    ) -> List[str]:
        params: dict = {"start": start, "count": count}
        if queue is not None:
            params["queue"] = queue

        logger.info(
            "get_match_ids — routing=%s puuid=%s… params=%s",
            routing, puuid[:8], params,
        )
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            params=params,
        )
        if not isinstance(data, list):
            raise RiotApiError("Unexpected response for match IDs.")
        logger.info("get_match_ids — returned %d match IDs", len(data))
        return data

    async def get_match(self, match_id: str, routing: str) -> Dict[str, Any]:
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/{match_id}",
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for match detail.")
        return data

    async def get_match_timeline(self, match_id: str, routing: str) -> Dict[str, Any]:
        data = await self._request_json(
            routing=routing,
            path=f"/lol/match/v5/matches/{match_id}/timeline",
        )
        if not isinstance(data, dict):
            raise RiotApiError("Unexpected response for match timeline.")
        return data

    async def get_matches_concurrent(
        self,
        match_ids: List[str],
        routing: str,
        concurrency: int = _MATCH_CONCURRENCY,
    ) -> Dict[str, Any]:
        """
        Fetch multiple match JSONs concurrently in batches.

        Returns a dict of {match_id: match_json | Exception} so the
        caller can handle per-match failures without aborting the batch.
        Adds a short inter-batch pause to stay within Riot rate limits.
        """
        results: Dict[str, Any] = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch_one(mid: str) -> None:
            async with semaphore:
                try:
                    results[mid] = await self.get_match(mid, routing)
                except Exception as exc:
                    results[mid] = exc

        # Fire all tasks; the semaphore limits live concurrency
        tasks = [asyncio.create_task(_fetch_one(mid)) for mid in match_ids]
        # Process in batches so we can insert a small pause between groups
        for i in range(0, len(tasks), concurrency):
            batch = tasks[i:i + concurrency]
            await asyncio.gather(*batch)
            if i + concurrency < len(tasks):
                # ~0.3s between batches — gentle on dev-key rate limits
                await asyncio.sleep(0.3)

        return results
