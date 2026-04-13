from collections.abc import Generator

from sqlalchemy import create_engine
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
#     A pool of 5 handles 50+ concurrent FastAPI workers comfortably.
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
        pool_size=5,         # Transaction Mode: 5 server connections handles 50+ concurrent users
        max_overflow=5,      # burst headroom → 10 max — well under Supabase free-tier limits
        pool_timeout=30,     # raise after 30 s queue wait instead of blocking forever
        pool_recycle=1800,   # recycle every 30 min to avoid server-side idle timeouts
        connect_args={"prepare_threshold": 0},  # disable prepared statements for PgBouncer Transaction Mode
    )
)

engine = create_engine(settings.database_url, **_pool_kwargs)
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
