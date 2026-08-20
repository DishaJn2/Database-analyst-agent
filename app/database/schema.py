"""Schema inspection utilities feeding schema-aware prompting.

Reads the *live* database schema via SQLAlchemy's Inspector (not the ORM
model definitions) so the prompt always reflects what's actually in
PostgreSQL, not what the code thinks should be there. Business-meaning
descriptions and keyword-based relevance are the only hardcoded parts --
everything structural (columns, types, keys) is introspected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.database.connection import readonly_engine

TABLE_BUSINESS_CONTEXT: dict[str, str] = {
    "customers": "People who place orders. One row per customer.",
    "categories": "Product categories, e.g. Electronics, Apparel.",
    "products": "Items for sale, each belonging to one category.",
    "stores": "Physical retail locations, grouped into regions.",
    "employees": "Staff assigned to a store; may be linked to the orders they handled.",
    "orders": "One row per customer order. total_amount is the pre-computed order total.",
    "order_items": "Line items within an order; one row per product per order.",
    "payments": "Payment record for an order (method, amount, status).",
}

# Keyword -> table relevance hints, used to avoid injecting the full schema into
# every prompt. With only 8 tables this matters less than it would at scale, but
# it's the same mechanism that would matter at 80 tables, and keeps prompts smaller.
RELEVANCE_KEYWORDS: dict[str, list[str]] = {
    "customers": ["customer", "client", "buyer", "signup", "repeat", "loyal", "retention", "new vs"],
    "categories": ["category", "categories"],
    "products": ["product", "sku", "item", "inventory", "catalog", "best-selling", "bestselling", "declining"],
    "stores": ["store", "region", "location", "branch"],
    "employees": ["employee", "staff", "manager", "sales rep", "salesperson"],
    "orders": ["order", "revenue", "sales", "purchase", "aov", "average order", "growth", "trend"],
    "order_items": ["order item", "line item", "quantity", "units sold"],
    "payments": ["payment", "paid", "refund", "transaction", "method"],
}


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    primary_key: bool


@dataclass(frozen=True)
class TableInfo:
    name: str
    description: str
    columns: list[ColumnInfo] = field(default_factory=list)
    foreign_keys: list[str] = field(default_factory=list)  # "col -> other_table.other_col"


def _inspect_tables(engine: Engine = readonly_engine) -> list[TableInfo]:
    inspector = inspect(engine)
    tables: list[TableInfo] = []
    for table_name in sorted(inspector.get_table_names()):
        pk_cols = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or [])
        columns = [
            ColumnInfo(
                name=col["name"],
                type=str(col["type"]),
                nullable=col["nullable"],
                primary_key=col["name"] in pk_cols,
            )
            for col in inspector.get_columns(table_name)
        ]
        foreign_keys = [
            f"{fk['constrained_columns'][0]} -> {fk['referred_table']}.{fk['referred_columns'][0]}"
            for fk in inspector.get_foreign_keys(table_name)
        ]
        tables.append(
            TableInfo(
                name=table_name,
                description=TABLE_BUSINESS_CONTEXT.get(table_name, ""),
                columns=columns,
                foreign_keys=foreign_keys,
            )
        )
    return tables


def get_all_tables() -> list[TableInfo]:
    """Live introspection of every table in the public schema."""
    return _inspect_tables()


def format_table(table: TableInfo) -> str:
    header = f"{table.name}(  -- {table.description}" if table.description else f"{table.name}("
    lines = [header]
    for col in table.columns:
        markers = []
        if col.primary_key:
            markers.append("PK")
        if not col.nullable:
            markers.append("NOT NULL")
        marker_str = f"  -- {', '.join(markers)}" if markers else ""
        lines.append(f"    {col.name} {col.type},{marker_str}")
    if table.foreign_keys:
        lines.append(f"    -- foreign keys: {'; '.join(table.foreign_keys)}")
    lines.append(")")
    return "\n".join(lines)


def get_schema_text(table_names: list[str] | None = None) -> str:
    """Full schema, or a filtered subset, formatted for LLM prompting."""
    tables = get_all_tables()
    if table_names:
        wanted = {name.lower() for name in table_names}
        tables = [t for t in tables if t.name in wanted]
    return "\n\n".join(format_table(t) for t in tables)


def _build_fk_graph(tables: list[TableInfo]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {t.name: set() for t in tables}
    for t in tables:
        for fk in t.foreign_keys:
            other_table = fk.split("->")[1].strip().split(".")[0]
            graph[t.name].add(other_table)
            graph.setdefault(other_table, set()).add(t.name)
    return graph


def get_relevant_tables(question: str) -> list[str]:
    """Keyword match, then expand one FK hop so joins implied by the match stay valid
    (e.g. a "products" match pulls in "categories" via the FK between them).

    Falls back to every table when nothing matches -- with 8 tables that's cheap,
    and a wrong/empty guess should never silently starve the LLM of schema context.
    """
    tables = get_all_tables()
    q = question.lower()
    matched = {name for name, keywords in RELEVANCE_KEYWORDS.items() if any(kw in q for kw in keywords)}
    if not matched:
        return [t.name for t in tables]

    graph = _build_fk_graph(tables)
    expanded = set(matched)
    for name in matched:
        expanded |= graph.get(name, set())
    return sorted(expanded)
