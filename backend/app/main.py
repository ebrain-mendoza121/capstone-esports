import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter  # noqa: F401 — re-exported for backwards compat
from sqlalchemy import text
from sqlalchemy.exc import OperationalError as SAOperationalError, TimeoutError as SATimeoutError

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
import app.models.participant_perks   # noqa: F401  (registers ParticipantPerks)
import app.models.champion_matchups  # noqa: F401  (registers ChampionMatchup)

logger = logging.getLogger(__name__)
settings = get_settings()



# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    """Pre-warm Data Dragon caches on startup so first requests pay no I/O cost."""
    try:
        # Load full champion map (metadata + image URLs + role affinity) so that
        # /champions endpoints and team builder serve requests instantly.
        # get_champion_full_map() also populates the simple _champion_map cache,
        # so callers of get_champion_map() benefit too.
        from app.services.ddragon import get_champion_full_map, get_rune_map
        champ_map = await get_champion_full_map()
        rune_map  = await get_rune_map()
        logger.info(
            "DDragon caches ready: %d champions (full metadata), %d rune entries",
            len(champ_map),
            len(rune_map),
        )
    except Exception as exc:                        # pragma: no cover
        logger.warning("DDragon preload failed at startup: %s", exc)
    yield  # application runs
    # (shutdown cleanup goes here if ever needed)


app = FastAPI(title="Esports Analytics API", version="0.1.0", lifespan=_lifespan)

# Attach rate limiter state and its 429 handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request timeout middleware.
# Normal endpoints: 60 s (prevents hung Riot API calls blocking workers).
# Backfill endpoints: 600 s — these are CPU-only DB operations that can
# legitimately take several minutes when processing thousands of rows.
# Returns 504 so callers know to retry rather than wait forever.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def _timeout_middleware(request: Request, call_next):
    # Bulk import and backfill paths get a generous timeout; everything else gets 60s
    _long_timeout_prefixes = ("/backfill", "/matchups/import")
    timeout = 600.0 if any(request.url.path.startswith(p) for p in _long_timeout_prefixes) else 60.0
    try:
        return await asyncio.wait_for(call_next(request), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(
            "Request timed out after %ss: %s %s",
            int(timeout),
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=504,
            content={
                "error": "RequestTimeout",
                "message": f"The request took longer than {int(timeout)}s and was cancelled.",
                "path": request.url.path,
            },
        )


app.include_router(health_router)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Specific SQLAlchemy exception handlers — return 503 for transient DB issues
# so monitoring tools and load tests can distinguish "DB busy" from real bugs.
# ---------------------------------------------------------------------------

@app.exception_handler(SATimeoutError)
async def _db_timeout_handler(request: Request, exc: SATimeoutError) -> JSONResponse:
    """Connection pool exhausted — return 503 with Retry-After hint."""
    logger.warning(
        "DB connection pool timeout on %s %s — pool exhausted under load",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "2"},
        content={
            "error":   "DatabasePoolTimeout",
            "message": "Database connection pool exhausted. Please retry in a moment.",
            "path":    request.url.path,
        },
    )


@app.exception_handler(SAOperationalError)
async def _db_operational_handler(request: Request, exc: SAOperationalError) -> JSONResponse:
    """Transient DB connection error (e.g. PgBouncer reset, network blip)."""
    logger.warning(
        "DB operational error on %s %s: %s",
        request.method,
        request.url.path,
        str(exc)[:200],
    )
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "1"},
        content={
            "error":   "DatabaseOperationalError",
            "message": "Transient database error. Please retry.",
            "path":    request.url.path,
        },
    )


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
