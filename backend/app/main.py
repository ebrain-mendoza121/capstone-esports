from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.settings import get_settings
from app.db.session import engine

# Ensure all ORM models are imported so SQLAlchemy registers their metadata
import app.models.match          # noqa: F401
import app.models.player         # noqa: F401
import app.models.participant_stats  # noqa: F401
import app.models.team_objectives    # noqa: F401
import app.models.team_bans          # noqa: F401
import app.models.derived_metrics    # noqa: F401
import app.models.match_timeline     # noqa: F401
import app.models.draft_actions       # noqa: F401
import app.models.participant_perks   # noqa: F401

settings = get_settings()

app = FastAPI(title="Esports Analytics API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(api_router)


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        return {"result": conn.execute(text("SELECT 1")).scalar()}
