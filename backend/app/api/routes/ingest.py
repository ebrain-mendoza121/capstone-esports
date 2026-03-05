from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ingest import IngestPlayerRequest, IngestPlayerResponse
from app.services.ingestion_service import ingest_player
from app.services.riot_client import RiotApiError  # <-- import your custom error

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/player", response_model=IngestPlayerResponse)
async def ingest_player_route(payload: IngestPlayerRequest, db: Session = Depends(get_db)):
    """
    Ingest a player and their match history from Riot API.
    
    Args:
        payload: Request containing gameName, tagLine, platform, count, and queue
        
    Returns:
        Response with puuid, platform, routing, and ingestion statistics
        
    Example:
        {
            "gameName": "Player",
            "tagLine": "NA1",
            "platform": "NA",
            "count": 20,
            "queue": 420
        }
        
    Queue IDs:
        - 420: Ranked Solo/Duo (default)
        - 440: Ranked Flex
        - 400: Normal Draft
        - 430: Normal Blind
        - 450: ARAM
    """
    try:
        puuid, platform, routing, inserted, skipped, failed = await ingest_player(
            session=db,
            game_name=payload.gameName,
            tag_line=payload.tagLine,
            platform=payload.platform,
            count=payload.count,
            queue=payload.queue,  # Pass queue filter
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

        # Fast, user-friendly mapping
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

        # Anything else upstream
        raise HTTPException(status_code=502, detail=f"Riot API error: {msg}")