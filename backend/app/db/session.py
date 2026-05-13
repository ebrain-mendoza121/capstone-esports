from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from app.core.settings import get_settings

settings = get_settings()

# Connection pool tuned for Supabase's Transaction Mode PgBouncer (port 6543).
#
# Transaction Mode vs Session Mode:
#   - Session Mode (port 5432): 1 server connection per SQLAlchemy pool slot.
#     Free tier hard cap ~15 server connections → pool_size=15 already maxes it out.
#   - Transaction Mode (port 6543): connections are returned to PgBouncer's shared
#     pool after EVERY transaction. One server connection multiplexes many clients.
#     A pool of 10 handles 50+ concurrent FastAPI workers comfortably.
#
# IMPORTANT: Transaction Mode does not support PostgreSQL prepared statements.
#   `prepare_threshold=0` tells psycopg to never prepare statements, which is
#   required for PgBouncer Transaction Mode compatibility.
#
# SQLite (used by tests via conftest.py DATABASE_URL override) does NOT support
# pool_size / max_overflow / pool_timeout / connect_args — those are PG-only.
# We detect the dialect prefix and only pass pool kwargs for real databases.
_is_sqlite = settings.database_url.startswith("sqlite")

_pool_kwargs = (
    {}
    if _is_sqlite
    else dict(
        pool_pre_ping=True,
        pool_size=10,        # Transaction Mode: PgBouncer multiplexes — 10 slots handles 50+ concurrent users
        max_overflow=10,     # burst headroom → 20 max — well under Supabase free-tier limits
        pool_timeout=5,      # fail fast: raise QueuePool error after 5 s instead of blocking for 30 s.
                             # This keeps the Uvicorn thread pool healthy — threads fail quickly and free
                             # up so DB-free endpoints (/ and /health) aren't starved by stalled waiters.
        pool_recycle=1800,   # recycle every 30 min to avoid server-side idle timeouts
        connect_args={"prepare_threshold": None},  # disable prepared statements for PgBouncer Transaction Mode
    )
)

engine = create_engine(settings.database_url, **_pool_kwargs)

# ---------------------------------------------------------------------------
# Per-connection statement timeout
# ---------------------------------------------------------------------------
# Set a 20-second statement_timeout on every newly opened PostgreSQL
# connection.  This is well under the 60-s request timeout in main.py (so
# callers get a proper DB error, not a gateway 504), and queries that hit the
# timeout release the connection before the 5-s pool_timeout fires.
#
# Skipped for SQLite (tests) — SQLite has no statement_timeout support.
if not _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_statement_timeout(dbapi_conn, _connection_record):
        """Apply a 20 s statement timeout on every fresh connection."""
        with dbapi_conn.cursor() as cur:
            cur.execute("SET statement_timeout = 20000")  # milliseconds

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
