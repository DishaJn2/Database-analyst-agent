"""LangChain agent: tool selection and controlled workflow orchestration.

Design: SQL generation happens as part of the LLM's own reasoning (writing
the query text is genuinely its job), but every *tool* the LLM can call
enforces deterministic safety regardless of what the LLM asked for --
run_sql always goes through validate_and_execute, so even a successfully
prompt-injected LLM cannot bypass validation, because the bypass would have
to happen in the tool, not in the LLM's judgment.

Result rows are kept out of the LLM's context after the first exchange:
run_sql returns a compact summary (row count, computed stats/ranking/trend,
a 5-row sample) to the model, while the full result set and any chart are
stashed in a per-request RunState the orchestration layer reads afterward.
This keeps token usage bounded and stops the LLM from having to transcribe
(and potentially garble) numbers it already has no further use for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from matplotlib.figure import Figure

from app.agent.llm import get_llm
from app.tools.analysis_tool import AnalysisSummary, analyze_result
from app.tools.schema_tool import get_schema_for_question
from app.tools.sql_tool import ExecutionResult, validate_and_execute
from app.tools.visualization_tool import build_chart, should_visualize

MAX_ITERATIONS = 6  # bounds the tool-calling loop -- no uncontrolled agent loops

AGENT_SYSTEM_PROMPT = """You are a database analyst agent for a PostgreSQL retail analytics database.

Given a user's natural-language question:
1. Call get_schema to retrieve the relevant tables/columns for the question.
2. Write a PostgreSQL SELECT (or WITH ... SELECT) query using only tables/columns
   that appeared in the schema you retrieved, and call run_sql with it.
   - If run_sql reports the SQL was rejected or failed, fix the query and call
     run_sql again. If it keeps failing after a couple of attempts, explain the
     problem to the user instead of guessing indefinitely.
3. If the result is a ranking or a trend over time (not a single aggregate number),
   consider calling create_visualization.
4. Give a concise, concrete natural-language answer grounded in the actual numbers
   returned by run_sql. Never invent figures that weren't in the result, and never
   invent rows/values that run_sql didn't actually return, even to fill out a table.
   All monetary values in this database are USD -- use $, not any other currency.

Never write INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE,
or any other statement that modifies data or schema.
"""


@dataclass
class RunState:
    """Per-request scratch space the tools write into. A fresh instance is
    created for every question, so concurrent Streamlit sessions don't share
    state.
    """

    sql: str | None = None
    validation_passed: bool | None = None
    execution: ExecutionResult | None = None
    analysis: AnalysisSummary | None = None
    chart: Figure | None = None
    tools_used: list[str] = field(default_factory=list)


def _make_tools(state: RunState) -> list:
    @tool
    def get_schema(question: str) -> str:
        """Look up the relevant database schema (tables, columns, foreign keys)
        for a natural-language question. Always call this before writing SQL.
        """
        state.tools_used.append("get_schema")
        return get_schema_for_question(question)

    @tool
    def run_sql(sql: str) -> str:
        """Validate and execute a PostgreSQL SELECT query, returning a compact
        summary: row count, computed statistics/ranking/trend, and a small
        sample of rows. The query must only use tables/columns from the
        schema returned by get_schema.
        """
        state.tools_used.append("run_sql")
        outcome = validate_and_execute(sql)
        state.sql = outcome.sql
        state.validation_passed = outcome.validation_passed

        if not outcome.validation_passed:
            return f"SQL REJECTED: {outcome.validation_reason}. Fix the query and call run_sql again."

        state.execution = outcome.execution
        if not outcome.execution.success:
            return f"EXECUTION FAILED: {outcome.execution.error}. Fix the query and call run_sql again."

        summary = analyze_result(outcome.execution.rows, outcome.execution.columns)
        state.analysis = summary

        if summary.is_empty:
            return "Query executed successfully but returned 0 rows."

        lines = [f"Success. {summary.row_count} row(s) returned."]
        for s in summary.numeric_stats:
            lines.append(f"  {s.column}: total={s.total:.2f}, avg={s.average:.2f}, min={s.minimum:.2f}, max={s.maximum:.2f}")
        if summary.trend:
            pct = f", change: {summary.trend_change_pct:.1f}%" if summary.trend_change_pct is not None else ""
            trend_str = "; ".join(f"{t.period}={t.value:.2f}" for t in summary.trend)
            lines.append(f"  Trend ({len(summary.trend)} periods{pct}): {trend_str}")
        elif summary.top_entries:
            lines.append("  Ranked entries: " + ", ".join(f"{e.label}={e.value:.2f}" for e in summary.top_entries))

        # Give the model the real rows it needs, not just a sample -- a 5-row sample
        # on a 12-row trend result previously caused it to hallucinate the other 7
        # rather than report actual numbers. Below the cap, show everything; above
        # it, fall back to a sample (the computed stats above still cover the whole
        # result either way).
        row_cap = 30
        if outcome.execution.row_count <= row_cap:
            lines.append(f"  All rows: {outcome.execution.rows}")
        else:
            lines.append(f"  Sample rows (of {outcome.execution.row_count} total): {outcome.execution.rows[:5]}")
        return "\n".join(lines)

    @tool
    def create_visualization(reason: str) -> str:
        """Create a chart for the most recent query result, if the data is
        suitable (a ranking or a trend -- not a single aggregate number).
        `reason` is a short note on why a chart would help.
        """
        state.tools_used.append("create_visualization")
        if state.analysis is None:
            return "No query result available yet -- call run_sql first."
        if not should_visualize(state.analysis):
            return "This result isn't chart-suitable (e.g. a single aggregate value) -- skipping."
        state.chart = build_chart(state.analysis)
        return "Chart created."

    return [get_schema, run_sql, create_visualization]


def build_agent_executor(state: RunState) -> AgentExecutor:
    llm = get_llm()
    tools = _make_tools(state)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", AGENT_SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=MAX_ITERATIONS,
        handle_parsing_errors=True,
    )


@dataclass
class AgentAnswer:
    answer: str
    sql: str | None
    validation_passed: bool | None
    execution: ExecutionResult | None
    analysis: AnalysisSummary | None
    chart: Figure | None
    tools_used: list[str]


def ask(question: str) -> AgentAnswer:
    """Run the full agentic workflow for one natural-language question."""
    state = RunState()
    executor = build_agent_executor(state)
    result = executor.invoke({"input": question})
    return AgentAnswer(
        answer=result["output"],
        sql=state.sql,
        validation_passed=state.validation_passed,
        execution=state.execution,
        analysis=state.analysis,
        chart=state.chart,
        tools_used=state.tools_used,
    )
