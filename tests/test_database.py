"""Tests: tables exist, FKs/CHECK constraints enforced, expected record counts,
seed generation is reproducible.

FK/CHECK tests run inside a transaction that's explicitly rolled back, so
they can safely attempt bad inserts against the live, real seeded dataset
without corrupting it.
"""

from __future__ import annotations

import datetime as dt
import random

import pytest
from faker import Faker
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database.connection import engine
from app.database.schema import get_all_tables
from app.database.seed import SEED, build_categories, build_products, build_stores

EXPECTED_TABLES = {
    "categories", "customers", "employees", "order_items",
    "orders", "payments", "products", "stores",
}


def test_all_expected_tables_exist() -> None:
    tables = {t.name for t in get_all_tables()}
    assert EXPECTED_TABLES <= tables


def test_orders_has_expected_columns_and_keys() -> None:
    orders = next(t for t in get_all_tables() if t.name == "orders")
    column_names = {c.name for c in orders.columns}
    assert {"order_id", "customer_id", "store_id", "order_date", "status", "total_amount"} <= column_names
    pk_columns = {c.name for c in orders.columns if c.primary_key}
    assert pk_columns == {"order_id"}
    assert len(orders.foreign_keys) == 3  # customer_id, store_id, employee_id


def test_foreign_key_violation_is_rejected() -> None:
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO orders (customer_id, store_id, order_date, status, total_amount) "
                        "VALUES (999999999, 1, now(), 'completed', 10.00)"
                    )
                )
        finally:
            trans.rollback()  # never persisted regardless of outcome


def test_check_constraint_rejects_negative_amount() -> None:
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO orders (customer_id, store_id, order_date, status, total_amount) "
                        "VALUES (1, 1, now(), 'completed', -50.00)"
                    )
                )
        finally:
            trans.rollback()


def test_check_constraint_rejects_invalid_status() -> None:
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO orders (customer_id, store_id, order_date, status, total_amount) "
                        "VALUES (1, 1, now(), 'not_a_real_status', 10.00)"
                    )
                )
        finally:
            trans.rollback()


def test_expected_record_counts() -> None:
    with engine.connect() as conn:
        counts = {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            for table in EXPECTED_TABLES
        }
    assert counts["categories"] == 8
    assert counts["products"] == 200
    assert counts["stores"] == 15
    assert 40 <= counts["employees"] <= 100
    assert counts["customers"] == 3000
    assert counts["orders"] == 9000
    assert counts["order_items"] > 15000
    assert counts["payments"] == 9000
    assert sum(counts.values()) >= 20000


def test_seed_generation_is_reproducible() -> None:
    """Same seed -> same synthetic data, without touching the live database
    (re-running the full --reset seed is slow and would disturb data other
    tests/the evaluation suite depend on).
    """
    rng1, faker1 = random.Random(SEED), Faker("en_US")
    Faker.seed(SEED)
    categories1 = build_categories()
    products1 = build_products(rng1, faker1, categories1)

    rng2, faker2 = random.Random(SEED), Faker("en_US")
    Faker.seed(SEED)
    categories2 = build_categories()
    products2 = build_products(rng2, faker2, categories2)

    assert [c.category_name for c in categories1] == [c.category_name for c in categories2]
    assert [(p.product_name, p.sku, p.unit_price) for p in products1] == [
        (p.product_name, p.sku, p.unit_price) for p in products2
    ]


def test_seed_generation_stores_are_deterministic() -> None:
    today = dt.date(2026, 8, 20)
    stores1 = build_stores(random.Random(SEED), today)
    stores2 = build_stores(random.Random(SEED), today)
    assert [(s.store_name, s.opened_date) for s in stores1] == [(s.store_name, s.opened_date) for s in stores2]
