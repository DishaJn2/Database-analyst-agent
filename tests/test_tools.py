"""Tests: schema retrieval, SQL execution, and the validate-then-execute pipeline.

No LLM dependency -- runs against the live database and readonly_user role.
"""

from __future__ import annotations

from app.tools.analysis_tool import analyze_result
from app.tools.schema_tool import get_schema_for_question
from app.tools.sql_tool import execute_sql, validate_and_execute
from app.tools.visualization_tool import build_chart, should_visualize


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


def test_analyze_result_empty() -> None:
    summary = analyze_result(rows=[], columns=["a"])
    assert summary.is_empty
    assert summary.row_count == 0


def test_analyze_result_single_aggregate_has_no_ranking_or_trend() -> None:
    summary = analyze_result(rows=[{"n": 9000}], columns=["n"])
    assert not summary.is_empty
    assert summary.numeric_stats and summary.numeric_stats[0].total == 9000
    assert summary.top_entries == []
    assert summary.trend == []


def test_analyze_result_ranking() -> None:
    rows = [
        {"category_name": "Electronics", "revenue": 500.0},
        {"category_name": "Grocery", "revenue": 100.0},
        {"category_name": "Apparel", "revenue": 300.0},
    ]
    summary = analyze_result(rows=rows, columns=["category_name", "revenue"])
    assert [e.label for e in summary.top_entries] == ["Electronics", "Apparel", "Grocery"]
    assert summary.numeric_stats[0].maximum == 500.0


def test_analyze_result_trend_and_change_pct() -> None:
    rows = [
        {"month": "2026-01", "revenue": 100.0},
        {"month": "2026-03", "revenue": 150.0},
        {"month": "2026-02", "revenue": 120.0},
    ]
    summary = analyze_result(rows=rows, columns=["month", "revenue"])
    assert [t.period for t in summary.trend] == ["2026-01", "2026-02", "2026-03"]
    assert summary.trend_change_pct == 50.0


def test_analyze_real_query_result_end_to_end() -> None:
    outcome = validate_and_execute(
        "SELECT c.category_name, SUM(oi.line_total) AS revenue "
        "FROM order_items oi "
        "JOIN products p ON p.product_id = oi.product_id "
        "JOIN categories c ON c.category_id = p.category_id "
        "GROUP BY c.category_name ORDER BY revenue DESC"
    )
    assert outcome.execution.success
    summary = analyze_result(outcome.execution.rows, outcome.execution.columns)
    assert len(summary.top_entries) == 5  # top_n default, 8 categories returned
    assert summary.top_entries[0].value >= summary.top_entries[-1].value


def test_should_visualize_false_for_single_aggregate() -> None:
    summary = analyze_result(rows=[{"n": 42}], columns=["n"])
    assert should_visualize(summary) is False
    assert build_chart(summary) is None


def test_should_visualize_true_for_ranking_and_chart_builds() -> None:
    rows = [{"category_name": "Electronics", "revenue": 500.0}, {"category_name": "Grocery", "revenue": 100.0}]
    summary = analyze_result(rows=rows, columns=["category_name", "revenue"])
    assert should_visualize(summary) is True
    fig = build_chart(summary, title="Revenue by category")
    assert fig is not None
    assert len(fig.axes[0].patches) == 2  # one bar per category
