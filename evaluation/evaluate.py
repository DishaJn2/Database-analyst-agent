"""Runs the 30+ query benchmark and prints measured metrics."""

from __future__ import annotations

from app.services.evaluation_service import run_evaluation, save_results


def main() -> None:
    print(f"Running evaluation ({run_evaluation.__module__})...\n")
    summary = run_evaluation()
    save_results(summary)

    print("\nEvaluation Results")
    print("------------------")
    print(f"Total queries:            {summary.total}")
    print(f"Valid SQL:                {summary.valid_sql_count}/{summary.total} ({summary.valid_sql_rate:.1f}%)")
    print(f"Successful execution:     {summary.execution_success_count}/{summary.total} ({summary.execution_success_rate:.1f}%)")
    if summary.correctness_checked:
        print(f"Result correctness:      {summary.correctness_passed}/{summary.correctness_checked} ({summary.correctness_rate:.1f}%)")
    if summary.schema_relevance_checked:
        print(f"Schema relevance:        {summary.schema_relevance_passed}/{summary.schema_relevance_checked} ({summary.schema_relevance_rate:.1f}%)")
    print(f"Average latency:          {summary.avg_latency_ms:.0f} ms")

    failed = [r for r in summary.results if not r.execution_success]
    if failed:
        print(f"\nFailed queries ({len(failed)}):")
        for r in failed:
            print(f"  [{r.id}] {r.question}")
            if r.error:
                print(f"      error: {r.error}")


if __name__ == "__main__":
    main()
