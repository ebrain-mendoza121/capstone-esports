from fastapi import APIRouter

from app.api.routes.players import router as players_router
from app.api.routes.matches import router as matches_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.backfill import router as backfill_router
from app.api.routes.analytics import router as analytics_router

api_router = APIRouter()

api_router.include_router(ingest_router)
api_router.include_router(players_router)
api_router.include_router(matches_router)
api_router.include_router(metrics_router)
api_router.include_router(backfill_router)
api_router.include_router(analytics_router)
