"""SQLAlchemy engine/session setup, read-only DB role handling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Read-write engine: schema creation and seeding only. The agent's SQL tool must
# never be given this engine -- it always executes against `readonly_engine`.
engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Read-only engine, backed by the `readonly_user` Postgres role (SELECT-only,
# enforced at the database level -- see Phase 4). This is the only connection
# the agent is allowed to run generated SQL against.
readonly_engine: Engine = create_engine(settings.readonly_database_url, pool_pre_ping=True)
ReadOnlySessionLocal = sessionmaker(bind=readonly_engine, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """Read-write session for setup/seeding code."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_readonly_session() -> Iterator[Session]:
    """Read-only session for agent-executed, validated SQL."""
    session = ReadOnlySessionLocal()
    try:
        yield session
    finally:
        session.close()
