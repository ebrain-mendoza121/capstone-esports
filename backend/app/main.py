import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.settings import get_settings
from app.db.session import engine

# Ensure all ORM models are imported so SQLAlchemy registers their metadata
import app.models.match              # noqa: F401
import app.models.player             # noqa: F401
import app.models.participant_stats  # noqa: F401
import app.models.team_objectives    # noqa: F401
import app.models.team_bans          # noqa: F401
import app.models.derived_metrics    # noqa: F401
import app.models.match_timeline     # noqa: F401
import app.models.draft_actions      # noqa: F401
import app.models.participant_perks  # noqa: F401  (registers ParticipantPerks)

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    """Pre-warm Data Dragon caches on startup so first requests pay no I/O cost."""
    try:
        from app.services.ddragon import get_champion_map, get_rune_map
        champ_map = await get_champion_map()
        rune_map  = await get_rune_map()
        logger.info(
            "DDragon caches ready: %d champions, %d rune entries",
            len(champ_map),
            len(rune_map),
        )
    except Exception as exc:                        # pragma: no cover
        logger.warning("DDragon preload failed at startup: %s", exc)
    yield  # application runs
    # (shutdown cleanup goes here if ever needed)


app = FastAPI(title="Esports Analytics API", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Global exception handler — catches unhandled errors and returns structured
# JSON instead of a bare 500 with no context.
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a structured error body and log the full traceback for every
    unhandled exception that escapes a route handler.

    The response body is safe to send to clients — it never includes the raw
    traceback, only a stable error type string and a short message.
    """
    tb = traceback.format_exc()
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        tb,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error":   type(exc).__name__,
            "message": str(exc) or "An unexpected server error occurred.",
            "path":    request.url.path,
        },
    )


# ---------------------------------------------------------------------------
# Root + DB probe endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        return {"result": conn.execute(text("SELECT 1")).scalar()}
