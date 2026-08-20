"""AST-based read-only SQL validation, using sqlglot rather than string matching.

Why AST over regex/substring checks: searching the query text for "DROP" is
trivially defeated by comments, case variation, or a column literally named
`dropdown_id`. Parsing into an AST and checking node *types* is immune to all
of that -- "DROP" only matters if it's actually a Drop statement node.

Why walk the whole tree instead of just checking the top-level statement type:
Postgres allows data-modifying statements inside a CTE --
    WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted
-- which still parses as a top-level SELECT. Only a full-tree walk catches
the nested Delete node.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.database.schema import get_all_tables

DIALECT = "postgres"

# Anything not isinstance(statement, exp.Select) is already rejected outright;
# this list is what the full-tree walk checks for *nested* occurrences (e.g.
# inside a writable CTE). exp.Command is sqlglot's catch-all for statements it
# can't classify into a known clause -- includes GRANT/REVOKE and malformed
# SQL, so it's rejected by default rather than allowed through.
FORBIDDEN_NODE_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,
)

# Functions with no legitimate role in a read-only analytical query --
# admin/session control, arbitrary file or network I/O.
DANGEROUS_FUNCTIONS = {
    "pg_sleep",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "dblink",
    "dblink_exec",
    "lo_import",
    "lo_export",
    "set_config",
}

DEFAULT_ROW_LIMIT = 1000


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    sql: str  # LIMIT-augmented version of the input when valid
    reason: str | None = None


def _known_schema() -> tuple[set[str], set[str]]:
    tables = get_all_tables()
    table_names = {t.name for t in tables}
    column_names = {c.name for t in tables for c in t.columns}
    return table_names, column_names


def _collect_local_names(statement: exp.Expression) -> tuple[set[str], set[str]]:
    """CTE names (usable as tables) and every output alias (usable as columns)
    anywhere in the statement, so CTEs and ORDER BY-by-alias aren't flagged
    as unknown identifiers.
    """
    local_tables = {cte.alias.lower() for cte in statement.find_all(exp.CTE) if cte.alias}
    local_columns = {a.alias.lower() for a in statement.find_all(exp.Alias) if a.alias}
    return local_tables, local_columns


def _check_unknown_identifiers(statement: exp.Expression) -> str | None:
    """Schema-membership check, not full alias/type resolution: catches clearly
    hallucinated tables/columns without needing a full binder. It won't catch
    a real column referenced on the wrong table (e.g. customers.total_amount)
    -- execution against Postgres catches that class of error instead.
    """
    known_tables, known_columns = _known_schema()
    local_tables, local_columns = _collect_local_names(statement)
    allowed_tables = known_tables | local_tables
    allowed_columns = known_columns | local_columns

    for table in statement.find_all(exp.Table):
        name = table.name.lower()
        if name and name not in allowed_tables:
            return f"Unknown table: {name}"

    for column in statement.find_all(exp.Column):
        name = column.name.lower()
        if name and name not in allowed_columns:
            return f"Unknown column: {name}"

    return None


def _check_dangerous_functions(statement: exp.Expression) -> str | None:
    for func in statement.find_all(exp.Anonymous):
        name = str(func.this).lower()
        if name in DANGEROUS_FUNCTIONS:
            return f"Disallowed function call: {name}"
    return None


def validate_sql(sql: str, row_limit: int = DEFAULT_ROW_LIMIT) -> ValidationResult:
    """Validate that `sql` is a single, read-only, schema-consistent SELECT.

    On success, returns a (possibly LIMIT-augmented) version of the query. On
    failure, `reason` explains what's wrong, to be fed back to the LLM for a
    bounded correction attempt rather than surfaced as a raw error.
    """
    sql = sql.strip().rstrip(";")
    if not sql:
        return ValidationResult(False, sql, "Empty query.")

    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except Exception as exc:
        return ValidationResult(False, sql, f"SQL failed to parse: {exc}")

    if len(statements) != 1:
        return ValidationResult(False, sql, "Only a single statement is allowed.")

    statement = statements[0]

    if not isinstance(statement, exp.Select):
        return ValidationResult(
            False, sql, f"Only SELECT/WITH queries are allowed, got {type(statement).__name__}."
        )

    for node in statement.walk():
        if isinstance(node, FORBIDDEN_NODE_TYPES):
            return ValidationResult(False, sql, "Query contains a disallowed statement type.")

    reason = _check_dangerous_functions(statement)
    if reason:
        return ValidationResult(False, sql, reason)

    reason = _check_unknown_identifiers(statement)
    if reason:
        return ValidationResult(False, sql, reason)

    if statement.args.get("limit") is None:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))

    return ValidationResult(True, statement.sql(dialect=DIALECT))
