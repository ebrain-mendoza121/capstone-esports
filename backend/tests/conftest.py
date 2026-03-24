"""
Shared pytest fixtures for the esports analytics backend test suite.

Unit tests (tests/unit/) use no fixtures — they test pure functions only.
Integration tests (tests/integration/) use the `client` fixture which
spins up a FastAPI TestClient backed by an in-memory SQLite database,
overriding the production PostgreSQL dependency.
"""

import os
import pytest

# ------------------------------------------------------------------
# Set minimal environment variables BEFORE importing the app so that
# pydantic-settings does not raise a validation error for missing vars.
# These are test-only values and never reach production.
# ------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("RIOT_API_KEY", "TEST_KEY_NOT_USED_IN_UNIT_TESTS")

from fastapi.testclient import TestClient                        # noqa: E402
from sqlalchemy import create_engine, Text                       # noqa: E402
from sqlalchemy.orm import sessionmaker                          # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB                 # noqa: E402
from sqlalchemy import event                                     # noqa: E402
from sqlalchemy.engine import Engine                             # noqa: E402
from sqlalchemy.pool import StaticPool                           # noqa: E402

from app.main import app                                         # noqa: E402
from app.db.session import Base, get_db                          # noqa: E402

# ------------------------------------------------------------------
# SQLite does not support PostgreSQL's JSONB type.
# Register a type override so SQLite stores JSONB columns as TEXT.
# This only affects the test database — production PostgreSQL is unchanged.
# ------------------------------------------------------------------
from sqlalchemy.ext.compiler import compiles                     # noqa: E402


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"


# ------------------------------------------------------------------
# In-memory SQLite engine for integration tests.
# SQLite is sufficient for endpoint smoke-tests; it cannot replicate
# PostgreSQL window functions used by the ML training pipeline.
# ------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite://"  # pure in-memory, no file needed

# StaticPool forces all requests to reuse the same underlying connection,
# which means the in-memory database (and its tables) is shared across the
# engine, the session fixture, and the FastAPI TestClient's get_db override.
# Without StaticPool, every new connection spawns an isolated blank database
# and the tables created in db_session are invisible to the app.
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


@pytest.fixture(scope="function")
def db_session():
    """Provide a transactional test database session, rolled back after each test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient wired to the in-memory SQLite test database."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
