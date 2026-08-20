"""Tests: schema retrieval, SQL execution, and the validate-then-execute pipeline.

No LLM dependency -- runs against the live database and readonly_user role.
"""

from __future__ import annotations

from app.tools.schema_tool import get_schema_for_question
from app.tools.sql_tool import execute_sql, validate_and_execute


def test_schema_tool_returns_relevant_tables_only() -> None:
    text = get_schema_for_question("Which customers are repeat buyers?")
    assert "customers(" in text
    assert "employees(" not in text


def test_schema_tool_falls_back_to_full_schema() -> None:
    text = get_schema_for_question("asdkj qwoieu nonsense")
    for table in ("customers", "orders", "products", "categories", "stores", "employees", "order_items", "payments"):
        assert f"{table}(" in text


def test_execute_sql_success() -> None:
    result = execute_sql("SELECT count(*) AS n FROM customers")
    assert result.success
    assert result.row_count == 1
    assert result.rows[0]["n"] == 3000


def test_execute_sql_reports_db_errors_without_raising() -> None:
    # Passes our lenient validator (email exists globally, just not on this
    # table) but fails at the database -- exactly the class of error that
    # validation intentionally defers to execution rather than trying to
    # fully solve with static alias/type resolution.
    result = execute_sql("SELECT email FROM orders LIMIT 1")
    assert not result.success
    assert result.error


def test_execute_sql_enforces_statement_timeout() -> None:
    # Deliberately expensive cross join (~21k x 21k rows) with a short timeout.
    result = execute_sql(
        "SELECT count(*) FROM order_items a, order_items b",
        timeout_ms=200,
    )
    assert not result.success
    assert "time" in result.error.lower() or "cancel" in result.error.lower()


def test_validate_and_execute_never_executes_invalid_sql() -> None:
    outcome = validate_and_execute("DROP TABLE customers")
    assert not outcome.validation_passed
    assert outcome.execution is None


def test_validate_and_execute_happy_path() -> None:
    outcome = validate_and_execute("SELECT count(*) AS n FROM products")
    assert outcome.validation_passed
    assert outcome.execution is not None
    assert outcome.execution.success
    assert outcome.execution.rows[0]["n"] == 200
