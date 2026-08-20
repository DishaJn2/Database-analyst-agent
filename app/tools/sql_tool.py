"""Tool: generate and execute validated read-only SQL.

SQL generation (LLM call) is added once the Llama integration is verified
against a live API key -- see app/agent/llm.py. Execution has no LLM
dependency and is implemented here now.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import readonly_engine
from app.tools.validation_tool import validate_sql

DEFAULT_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    error: str | None = None
    elapsed_ms: float = 0.0


def execute_sql(sql: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> ExecutionResult:
    """Execute already-validated, read-only SQL against the readonly_user role.

    Sets a server-side statement_timeout per connection (not just a Python-side
    timeout), so Postgres itself kills a runaway query even if the driver is
    blocked waiting on it.
    """
    start = time.perf_counter()
    try:
        with readonly_engine.connect() as conn:
            conn.execute(text(f"SET statement_timeout = {int(timeout_ms)}"))
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
        elapsed_ms = (time.perf_counter() - start) * 1000
        return ExecutionResult(success=True, columns=columns, rows=rows, row_count=len(rows), elapsed_ms=elapsed_ms)
    except SQLAlchemyError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        original = getattr(exc, "orig", exc)
        return ExecutionResult(success=False, error=str(original), elapsed_ms=elapsed_ms)


@dataclass(frozen=True)
class QueryOutcome:
    sql: str
    validation_passed: bool
    validation_reason: str | None
    execution: ExecutionResult | None


def validate_and_execute(raw_sql: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> QueryOutcome:
    """Deterministic validate -> execute pipeline. Never executes SQL that
    failed validation, no matter what called it.
    """
    validation = validate_sql(raw_sql)
    if not validation.is_valid:
        return QueryOutcome(sql=raw_sql, validation_passed=False, validation_reason=validation.reason, execution=None)

    execution = execute_sql(validation.sql, timeout_ms=timeout_ms)
    return QueryOutcome(sql=validation.sql, validation_passed=True, validation_reason=None, execution=execution)
