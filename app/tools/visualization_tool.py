"""Tool: decide on and produce a chart when data is suitable.

Chart-type selection is a fixed rule, not an LLM decision: the right chart
type follows mechanically from the shape of the analyzed result (a trend ->
line chart, a ranking -> bar chart), so there's no judgment call worth
spending an LLM call on, and a rule is trivially testable where an LLM
decision wouldn't be.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless: this module must not require a display

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from app.tools.analysis_tool import AnalysisSummary


def should_visualize(summary: AnalysisSummary) -> bool:
    """A single aggregate number (e.g. "total revenue") has nothing to chart --
    only rankings and trends do.
    """
    if summary.is_empty:
        return False
    return bool(summary.trend) or bool(summary.top_entries)


def build_chart(summary: AnalysisSummary, title: str = "") -> Figure | None:
    if not should_visualize(summary):
        return None

    fig, ax = plt.subplots(figsize=(7, 4))

    if summary.trend:
        periods = [p.period for p in summary.trend]
        values = [p.value for p in summary.trend]
        ax.plot(periods, values, marker="o")
        ax.set_xlabel("Period")
        ax.tick_params(axis="x", rotation=45)
    else:
        labels = [e.label for e in summary.top_entries]
        values = [e.value for e in summary.top_entries]
        ax.barh(labels[::-1], values[::-1])
        ax.set_xlabel("Value")

    ax.set_title(title or "Result")
    fig.tight_layout()
    return fig
