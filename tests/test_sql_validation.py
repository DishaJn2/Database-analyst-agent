"""Tests: SELECT/CTE allowed, mutating/admin statements rejected, injection-style
edge cases (stacked queries, writable CTEs) rejected, schema-hallucination caught.

Runs against the live introspected schema (readonly_engine) -- no LLM involved.
"""

from __future__ import annotations

import pytest

from app.tools.validation_tool import validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customers",
        "SELECT customer_id, first_name FROM customers WHERE state = 'CA'",
        "WITH totals AS (SELECT customer_id, SUM(total_amount) AS total FROM orders GROUP BY customer_id) "
        "SELECT * FROM totals ORDER BY total DESC",
    ],
)
def test_allows_read_only_queries(sql: str) -> None:
    result = validate_sql(sql)
    assert result.is_valid, result.reason


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO customers (first_name) VALUES ('x')",
        "UPDATE customers SET first_name = 'x'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "ALTER TABLE customers ADD COLUMN x TEXT",
        "TRUNCATE TABLE customers",
        "CREATE TABLE evil (id INT)",
        "GRANT SELECT ON customers TO PUBLIC",
        "REVOKE SELECT ON customers FROM PUBLIC",
    ],
)
def test_rejects_mutating_and_admin_statements(sql: str) -> None:
    result = validate_sql(sql)
    assert not result.is_valid
    assert result.reason


def test_rejects_stacked_queries() -> None:
    result = validate_sql("SELECT * FROM customers; DROP TABLE customers;")
    assert not result.is_valid


def test_rejects_writable_cte() -> None:
    # A top-level SELECT that smuggles a DELETE inside a CTE -- would slip past
    # a check that only inspects the root statement type.
    sql = "WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted"
    result = validate_sql(sql)
    assert not result.is_valid


def test_rejects_dangerous_functions() -> None:
    result = validate_sql("SELECT pg_sleep(10)")
    assert not result.is_valid
    assert "pg_sleep" in result.reason


def test_rejects_unknown_table() -> None:
    result = validate_sql("SELECT * FROM this_table_does_not_exist")
    assert not result.is_valid
    assert "table" in result.reason.lower()


def test_rejects_unknown_column() -> None:
    result = validate_sql("SELECT customer_lifetime_value_made_up FROM customers")
    assert not result.is_valid
    assert "column" in result.reason.lower()


def test_order_by_alias_is_not_flagged_as_unknown_column() -> None:
    sql = "SELECT customer_id, SUM(total_amount) AS total_revenue FROM orders GROUP BY customer_id ORDER BY total_revenue DESC"
    result = validate_sql(sql)
    assert result.is_valid, result.reason


def test_missing_limit_is_auto_added() -> None:
    result = validate_sql("SELECT * FROM customers")
    assert result.is_valid
    assert "LIMIT" in result.sql.upper()


def test_existing_limit_is_preserved() -> None:
    result = validate_sql("SELECT * FROM customers LIMIT 5")
    assert result.is_valid
    assert "LIMIT 5" in result.sql.upper()


def test_empty_query_is_rejected() -> None:
    result = validate_sql("   ")
    assert not result.is_valid
