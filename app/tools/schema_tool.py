"""Tool: retrieve relevant schema metadata for a request."""

from __future__ import annotations

from app.database.schema import get_relevant_tables, get_schema_text


def get_schema_for_question(question: str) -> str:
    """Schema-retrieval tool: given a natural-language question, return schema
    text for the tables relevant to it (or the full schema when nothing
    matches -- see schema.get_relevant_tables for the fallback rationale).
    """
    tables = get_relevant_tables(question)
    return get_schema_text(tables)
