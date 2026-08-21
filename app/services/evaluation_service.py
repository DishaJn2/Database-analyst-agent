"""Reproducible evaluation run: metrics over the benchmark question set.

Measures, per the spec's requirements:
  - valid SQL rate (validation_passed)
  - execution success rate (the required baseline metric)
  - result correctness, where a question has a precomputed expected_value
    (deterministic against the fixed-seed dataset)
  - schema-relevance accuracy: does our schema tool's table selection
    (app/database/schema.get_relevant_tables) actually include the tables a
    question needs, checked against curated expected_tables
  - average latency per question

Never hard-codes a target percentage -- run_evaluation() always reports what
actually happened.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.agent.agent import ask
from app.database.schema import get_relevant_tables

QUESTIONS_PATH = Path(__file__).resolve().parent.parent.parent / "evaluation" / "questions.json"
RESULTS_PATH = Path(__file__).resolve().parent.parent.parent / "evaluation" / "results.json"

CORRECTNESS_RELATIVE_TOLERANCE = 0.01


@dataclass
class QuestionResult:
    id: int
    question: str
    category: str
    valid_sql: bool
    execution_success: bool
    row_count: int | None
    elapsed_ms: float
    tools_used: list[str]
    retries: int
    schema_relevance_checked: bool
    schema_relevance_passed: bool
    correctness: str  # "pass" | "fail" | "not_checked"
    error: str | None = None


@dataclass
class EvaluationSummary:
    total: int
    valid_sql_count: int
    execution_success_count: int
    correctness_checked: int
    correctness_passed: int
    schema_relevance_checked: int
    schema_relevance_passed: int
    avg_latency_ms: float
    results: list[QuestionResult] = field(default_factory=list)

    @property
    def valid_sql_rate(self) -> float:
        return 100.0 * self.valid_sql_count / self.total if self.total else 0.0

    @property
    def execution_success_rate(self) -> float:
        return 100.0 * self.execution_success_count / self.total if self.total else 0.0

    @property
    def correctness_rate(self) -> float | None:
        return 100.0 * self.correctness_passed / self.correctness_checked if self.correctness_checked else None

    @property
    def schema_relevance_rate(self) -> float | None:
        if not self.schema_relevance_checked:
            return None
        return 100.0 * self.schema_relevance_passed / self.schema_relevance_checked


def _extract_scalar(rows: list[dict]) -> object | None:
    if len(rows) != 1 or len(rows[0]) != 1:
        return None
    return next(iter(rows[0].values()))


def _check_correctness(expected: object, execution) -> str:
    if expected is None:
        return "not_checked"
    if not execution or not execution.success:
        return "fail"
    actual = _extract_scalar(execution.rows)
    if actual is None:
        return "fail"
    try:
        actual_f, expected_f = float(actual), float(expected)
        tolerance = max(CORRECTNESS_RELATIVE_TOLERANCE * abs(expected_f), 0.01)
        return "pass" if abs(actual_f - expected_f) <= tolerance else "fail"
    except (TypeError, ValueError):
        return "pass" if str(actual).strip().lower() == str(expected).strip().lower() else "fail"


def load_questions() -> list[dict]:
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_evaluation(questions: list[dict] | None = None, verbose: bool = True) -> EvaluationSummary:
    questions = questions if questions is not None else load_questions()
    results: list[QuestionResult] = []

    for q in questions:
        start = time.perf_counter()
        error = None
        try:
            answer = ask(q["question"])
        except Exception as exc:
            answer = None
            error = str(exc)
        elapsed_ms = (time.perf_counter() - start) * 1000

        expected_tables = set(q.get("expected_tables") or [])
        relevance_checked = bool(expected_tables)
        relevance_passed = expected_tables.issubset(set(get_relevant_tables(q["question"]))) if relevance_checked else False

        if answer is None:
            result = QuestionResult(
                id=q["id"], question=q["question"], category=q["category"],
                valid_sql=False, execution_success=False, row_count=None,
                elapsed_ms=elapsed_ms, tools_used=[], retries=0,
                schema_relevance_checked=relevance_checked, schema_relevance_passed=relevance_passed,
                correctness="not_checked", error=error,
            )
        else:
            correctness = _check_correctness(q.get("expected_value"), answer.execution)
            result = QuestionResult(
                id=q["id"], question=q["question"], category=q["category"],
                valid_sql=bool(answer.validation_passed),
                execution_success=bool(answer.execution and answer.execution.success),
                row_count=answer.execution.row_count if answer.execution else None,
                elapsed_ms=elapsed_ms,
                tools_used=answer.tools_used,
                retries=max(0, answer.tools_used.count("run_sql") - 1),
                schema_relevance_checked=relevance_checked, schema_relevance_passed=relevance_passed,
                correctness=correctness,
            )
        results.append(result)
        if verbose:
            status = "OK" if result.execution_success else "FAIL"
            print(f"  [{q['id']:>2}] {status:<4} {q['category']:<20} {q['question'][:60]}")

    total = len(results)
    return EvaluationSummary(
        total=total,
        valid_sql_count=sum(1 for r in results if r.valid_sql),
        execution_success_count=sum(1 for r in results if r.execution_success),
        correctness_checked=sum(1 for r in results if r.correctness != "not_checked"),
        correctness_passed=sum(1 for r in results if r.correctness == "pass"),
        schema_relevance_checked=sum(1 for r in results if r.schema_relevance_checked),
        schema_relevance_passed=sum(1 for r in results if r.schema_relevance_passed),
        avg_latency_ms=(sum(r.elapsed_ms for r in results) / total) if total else 0.0,
        results=results,
    )


def save_results(summary: EvaluationSummary) -> None:
    payload = {
        "total": summary.total,
        "valid_sql_count": summary.valid_sql_count,
        "valid_sql_rate": round(summary.valid_sql_rate, 1),
        "execution_success_count": summary.execution_success_count,
        "execution_success_rate": round(summary.execution_success_rate, 1),
        "correctness_checked": summary.correctness_checked,
        "correctness_passed": summary.correctness_passed,
        "correctness_rate": summary.correctness_rate,
        "schema_relevance_checked": summary.schema_relevance_checked,
        "schema_relevance_passed": summary.schema_relevance_passed,
        "schema_relevance_rate": summary.schema_relevance_rate,
        "avg_latency_ms": round(summary.avg_latency_ms, 1),
        "results": [asdict(r) for r in summary.results],
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
