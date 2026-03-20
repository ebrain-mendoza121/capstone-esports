from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db, SessionLocal
from app.schemas.ingest import (
    IngestPlayerRequest,
    IngestPlayerResponse,
    BatchIngestPlayerResult,
    BatchIngestResponse,
)
from app.services.ingestion_service import ingest_player
from app.services.riot_client import RiotApiError

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/player", response_model=IngestPlayerResponse)
async def ingest_player_route(payload: IngestPlayerRequest, db: Session = Depends(get_db)):
    """
    Ingest a player and their match history from Riot API.
    
    Populates: players, matches, participant_stats, team_objectives tables only.
    
    Args:
        payload: Request containing gameName, tagLine, platform, count, and queue
        
    Returns:
        Response with puuid, platform, routing, and ingestion statistics
        
    Example:
        {
            "gameName": "Doublelift",
            "tagLine": "NA1",
            "platform": "NA",
            "count": 5,
            "queue": 420
        }
        
    Queue IDs:
        - 420: Ranked Solo/Duo (default)
        - 440: Ranked Flex
    """
    try:
        puuid, platform, routing, inserted, skipped, failed = await ingest_player(
            session=db,
            game_name=payload.gameName,
            tag_line=payload.tagLine,
            platform=payload.platform,
            count=payload.count,
            queue=payload.queue,
            fetch_timeline=payload.fetch_timeline,
        )
        return IngestPlayerResponse(
            puuid=puuid,
            platform=platform,
            routing=routing,
            inserted=inserted,
            skipped=skipped,
            failed=failed
        )

    except RiotApiError as e:
        msg = str(e)

        if "error 404" in msg or "status_code\":404" in msg:
            raise HTTPException(
                status_code=404,
                detail=f"Riot player not found for {payload.gameName}#{payload.tagLine}",
            )

        if "error 429" in msg or "status_code\":429" in msg:
            raise HTTPException(
                status_code=503,
                detail="Rate limited by Riot API. Try again in a bit.",
            )

        if "error 401" in msg or "error 403" in msg:
            raise HTTPException(
                status_code=502,
                detail="Riot API auth/permission error (check RIOT_API_KEY).",
            )

        raise HTTPException(status_code=502, detail=f"Riot API error: {msg}")


@router.post("/players/batch", response_model=BatchIngestResponse)
async def ingest_players_batch(
    players: List[IngestPlayerRequest],
) -> BatchIngestResponse:
    """
    Ingest multiple players in a single request, processed sequentially.

    Each player runs in its own DB session so a failure on one player
    does not roll back others. Players are processed one at a time to
    respect Riot API rate limits — do not send more than ~20 players
    per request if count is 20, as each player can make up to 41 API
    calls (1 PUUID + 1 match list + 20 matches + up to 20 timelines).

    Returns a per-player result list with status, counts, and any errors.
    """
    results: List[BatchIngestPlayerResult] = []
    succeeded = 0
    errored = 0

    for req in players:
        db: Session = SessionLocal()
        try:
            puuid, platform, routing, inserted, skipped, failed = await ingest_player(
                session=db,
                game_name=req.gameName,
                tag_line=req.tagLine,
                platform=req.platform,
                count=req.count,
                queue=req.queue,
                fetch_timeline=req.fetch_timeline,
            )
            status = "success" if not failed else "partial"
            results.append(BatchIngestPlayerResult(
                gameName=req.gameName,
                tagLine=req.tagLine,
                platform=req.platform,
                status=status,
                puuid=puuid,
                inserted=inserted,
                skipped=skipped,
                failed=failed,
            ))
            succeeded += 1
        except Exception as exc:
            db.rollback()
            results.append(BatchIngestPlayerResult(
                gameName=req.gameName,
                tagLine=req.tagLine,
                platform=req.platform,
                status="error",
                error=str(exc),
            ))
            errored += 1
        finally:
            db.close()

    return BatchIngestResponse(
        total=len(players),
        succeeded=succeeded,
        errored=errored,
        results=results,
    )
