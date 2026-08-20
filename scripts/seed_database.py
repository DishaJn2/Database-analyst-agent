"""One-shot script: populate the schema with 20,000+ consistent records."""

from __future__ import annotations

import argparse

from app.database.seed import seed_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the database with synthetic data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Truncate all tables before seeding (required if data already exists).",
    )
    args = parser.parse_args()

    counts = seed_all(reset=args.reset)
    total = sum(counts.values())

    print("Seed complete.")
    for table, count in counts.items():
        print(f"  {table:<15} {count:>7,}")
    print(f"  {'TOTAL':<15} {total:>7,}")


if __name__ == "__main__":
    main()
