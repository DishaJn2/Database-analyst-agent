"""Tool: analyze returned result sets (ranking, trend, comparison, % change).

Deterministic and LLM-free by design: LLMs are unreliable at exact
arithmetic, so this tool computes real statistics in Python. The final
natural-language answer (built elsewhere, with the LLM) narrates these
numbers rather than re-deriving them from raw rows.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal

# Matches 2026, 2026-01, 2026-01-15 -- text columns from e.g. to_char(date, 'YYYY-MM')
# bucketing, which is common enough in generated SQL to need handling even though
# native DATE/TIMESTAMP columns already arrive as real date/datetime objects.
_DATE_LIKE_PATTERN = re.compile(r"^\d{4}(-\d{2}){0,2}$")

# Matches "id", "customer_id", "order_id", etc. An identifier is numeric but
# not a *measure* -- ranking or averaging by customer_id is meaningless, and
# treating it as one previously caused a real bug: a "top customers by spend"
# query got ranked by customer_id instead of total_spent, because it was the
# first numeric column and customer_id happened to come before the real
# measure in the SELECT list.
_ID_LIKE_PATTERN = re.compile(r"(^id$|_id$)", re.IGNORECASE)


def _is_id_like(column: str) -> bool:
    return bool(_ID_LIKE_PATTERN.search(column))


@dataclass(frozen=True)
class ColumnStats:
    column: str
    minimum: float
    maximum: float
    total: float
    average: float


@dataclass(frozen=True)
class TopEntry:
    label: str
    value: float


@dataclass(frozen=True)
class TrendPoint:
    period: str
    value: float


@dataclass(frozen=True)
class AnalysisSummary:
    row_count: int
    is_empty: bool
    numeric_stats: list[ColumnStats] = field(default_factory=list)
    top_entries: list[TopEntry] = field(default_factory=list)
    trend: list[TrendPoint] = field(default_factory=list)
    trend_change_pct: float | None = None


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


def _is_period_like(value: object) -> bool:
    if isinstance(value, (dt.date, dt.datetime)):
        return True
    if isinstance(value, str):
        return bool(_DATE_LIKE_PATTERN.match(value.strip()))
    return False


def _classify_columns(columns: list[str], rows: list[dict]) -> tuple[list[str], str | None]:
    """Returns (numeric_columns, period_column) using the first row as a sample.
    period_column is the first non-numeric column that looks like a date/label.
    """
    if not rows:
        return [], None

    sample = rows[0]
    numeric_columns = [
        c for c in columns if not _is_id_like(c) and _to_float(sample.get(c)) is not None
    ]
    period_column = next(
        (c for c in columns if c not in numeric_columns and _is_period_like(sample.get(c))),
        None,
    )
    return numeric_columns, period_column


def analyze_result(rows: list[dict], columns: list[str], top_n: int = 5) -> AnalysisSummary:
    if not rows:
        return AnalysisSummary(row_count=0, is_empty=True)

    numeric_columns, period_column = _classify_columns(columns, rows)

    numeric_stats: list[ColumnStats] = []
    for col in numeric_columns:
        values = [v for v in (_to_float(r.get(col)) for r in rows) if v is not None]
        if not values:
            continue
        numeric_stats.append(
            ColumnStats(
                column=col,
                minimum=min(values),
                maximum=max(values),
                total=sum(values),
                average=sum(values) / len(values),
            )
        )

    top_entries: list[TopEntry] = []
    # Prefer a real, non-id label (e.g. first_name over customer_id); fall back
    # to an id-like column only if nothing else is available to label rows with.
    label_candidates = [c for c in columns if c not in numeric_columns]
    label_column = next((c for c in label_candidates if not _is_id_like(c)), None) or (
        label_candidates[0] if label_candidates else None
    )
    if label_column and numeric_columns and len(rows) > 1:
        primary_measure = numeric_columns[0]
        ranked = sorted(
            (r for r in rows if _to_float(r.get(primary_measure)) is not None),
            key=lambda r: _to_float(r[primary_measure]),
            reverse=True,
        )
        top_entries = [
            TopEntry(label=str(r.get(label_column)), value=_to_float(r[primary_measure]) or 0.0)
            for r in ranked[:top_n]
        ]

    trend: list[TrendPoint] = []
    trend_change_pct: float | None = None
    if period_column and numeric_columns:
        primary_measure = numeric_columns[0]
        ordered = sorted(rows, key=lambda r: str(r.get(period_column)))
        trend = [
            TrendPoint(period=str(r.get(period_column)), value=_to_float(r.get(primary_measure)) or 0.0)
            for r in ordered
        ]
        if len(trend) >= 2 and trend[0].value:
            trend_change_pct = ((trend[-1].value - trend[0].value) / trend[0].value) * 100

    return AnalysisSummary(
        row_count=len(rows),
        is_empty=False,
        numeric_stats=numeric_stats,
        top_entries=top_entries,
        trend=trend,
        trend_change_pct=trend_change_pct,
    )
