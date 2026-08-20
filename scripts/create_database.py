"""One-shot script: create the 8-table schema in PostgreSQL.

The database and roles (app_user, readonly_user) are provisioned separately
(see docs/architecture.md, Phase 4). This script only creates tables via
SQLAlchemy metadata -- re-running it is safe, `create_all` skips tables that
already exist.
"""

from __future__ import annotations

from app.database.connection import engine
from app.database.models import Base


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    print("Schema created (or already present).")


if __name__ == "__main__":
    create_schema()
