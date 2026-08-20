"""Synthetic, internally-consistent 20,000+ record data generation.

Record counts (deliberately >> 20,000 to leave headroom for meaningful
analytics -- trend/seasonality queries need enough order history to be
non-trivial):

    categories      8
    products        200
    stores          15
    employees       ~60-70
    customers       3,000
    orders          9,000
    order_items     ~21,000 (1-5 line items per order)
    payments        9,000 (one per order)

Design choices that make the data usable for the 25+ analytical use cases:
  - order dates span ~2.6 years with a Nov/Dec seasonal boost and a mild
    year-over-year growth trend, so month/quarter/YoY growth queries have
    something real to measure.
  - customers are drawn for orders via skewed (lognormal) weights, so a
    minority of customers naturally become repeat/VIP buyers -- supports
    "top customers", "repeat-customer rate", "customer lifetime value".
  - stores get randomized traffic weights, so "store performance" queries
    show real variance instead of a flat distribution.
  - order_items.unit_price snapshots the product's price at generation
    time; orders.total_amount and payments.amount are computed as the
    exact sum, so revenue figures are internally consistent by construction.
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from faker import Faker
from sqlalchemy import text

from app.database.connection import engine, get_session
from app.database.models import (
    Category,
    Customer,
    Employee,
    Order,
    OrderItem,
    Payment,
    Product,
    Store,
)

SEED = 42

CATEGORIES: list[tuple[str, int, int]] = [
    ("Electronics", 20, 1200),
    ("Apparel", 10, 150),
    ("Home & Kitchen", 8, 400),
    ("Sports & Outdoors", 10, 500),
    ("Beauty & Personal Care", 5, 120),
    ("Books & Media", 5, 60),
    ("Toys & Games", 5, 150),
    ("Grocery", 2, 40),
]
PRODUCTS_PER_CATEGORY = 25  # 8 * 25 = 200 products

PRODUCT_NOUNS: dict[str, list[str]] = {
    "Electronics": ["Headphones", "Speaker", "Smartwatch", "Laptop", "Tablet", "Camera", "Monitor", "Charger", "Router", "Drone"],
    "Apparel": ["T-Shirt", "Jeans", "Jacket", "Sweater", "Dress", "Sneakers", "Hat", "Scarf", "Shorts", "Hoodie"],
    "Home & Kitchen": ["Blender", "Toaster", "Cookware Set", "Vacuum", "Lamp", "Bedding Set", "Knife Set", "Air Fryer", "Coffee Maker", "Storage Bin"],
    "Sports & Outdoors": ["Yoga Mat", "Tent", "Bicycle", "Dumbbell Set", "Backpack", "Running Shoes", "Water Bottle", "Camping Chair", "Fishing Rod", "Helmet"],
    "Beauty & Personal Care": ["Shampoo", "Moisturizer", "Perfume", "Hair Dryer", "Lipstick", "Sunscreen", "Electric Razor", "Face Mask", "Toothbrush", "Body Wash"],
    "Books & Media": ["Novel", "Cookbook", "Journal", "Comic Book", "Biography", "Board Game", "Puzzle", "Audiobook", "Magazine", "Graphic Novel"],
    "Toys & Games": ["Action Figure", "Building Blocks", "Board Game", "Puzzle", "Doll", "RC Car", "Card Game", "Stuffed Animal", "Toy Train", "Play Set"],
    "Grocery": ["Coffee Beans", "Pasta", "Olive Oil", "Cereal", "Snack Bars", "Tea", "Spice Set", "Canned Soup", "Rice", "Chocolate"],
}

STORES: list[tuple[str, str, str, str]] = [
    ("Boston Downtown", "Boston", "MA", "Northeast"),
    ("New York Fifth Ave", "New York", "NY", "Northeast"),
    ("Philadelphia Center", "Philadelphia", "PA", "Northeast"),
    ("Chicago Loop", "Chicago", "IL", "Midwest"),
    ("Detroit Riverside", "Detroit", "MI", "Midwest"),
    ("Minneapolis North", "Minneapolis", "MN", "Midwest"),
    ("Columbus Main", "Columbus", "OH", "Midwest"),
    ("Atlanta Midtown", "Atlanta", "GA", "South"),
    ("Houston Galleria", "Houston", "TX", "South"),
    ("Dallas Uptown", "Dallas", "TX", "South"),
    ("Miami Beach", "Miami", "FL", "South"),
    ("Charlotte Central", "Charlotte", "NC", "South"),
    ("Los Angeles West", "Los Angeles", "CA", "West"),
    ("San Francisco Bay", "San Francisco", "CA", "West"),
    ("Seattle Downtown", "Seattle", "WA", "West"),
]

EMPLOYEE_STAFF_ROLES = ["Sales Associate", "Sales Associate", "Cashier"]

PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "cash", "bank_transfer", "gift_card"]
PAYMENT_METHOD_WEIGHTS = [0.40, 0.20, 0.15, 0.10, 0.10, 0.05]

N_CUSTOMERS = 3000
N_ORDERS = 9000

ALL_TABLES_CHILD_FIRST = [
    "payments",
    "order_items",
    "orders",
    "employees",
    "stores",
    "products",
    "categories",
    "customers",
]


def _truncate_all() -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(ALL_TABLES_CHILD_FIRST)} RESTART IDENTITY CASCADE"))


def build_categories() -> list[Category]:
    return [Category(category_name=name, description=f"{name} products") for name, _, _ in CATEGORIES]


def build_products(rng: random.Random, faker: Faker, categories: list[Category]) -> list[Product]:
    products: list[Product] = []
    sku_counter = 1
    for category, (name, lo, hi) in zip(categories, CATEGORIES):
        nouns = PRODUCT_NOUNS[name]
        for i in range(PRODUCTS_PER_CATEGORY):
            unit_price = Decimal(str(round(rng.uniform(lo, hi), 2)))
            margin = round(rng.uniform(0.45, 0.75), 4)
            cost_price = (unit_price * Decimal(str(margin))).quantize(Decimal("0.01"))
            noun = nouns[i % len(nouns)]
            products.append(
                Product(
                    category=category,
                    product_name=f"{faker.word().capitalize()} {noun}",
                    sku=f"SKU-{sku_counter:05d}",
                    unit_price=unit_price,
                    cost_price=cost_price,
                    is_active=rng.random() > 0.05,
                )
            )
            sku_counter += 1
    return products


def build_stores(rng: random.Random, today: dt.date) -> list[Store]:
    stores: list[Store] = []
    for name, city, state, region in STORES:
        opened_date = today - dt.timedelta(days=rng.randint(365, 6 * 365))
        stores.append(Store(store_name=name, city=city, state=state, region=region, opened_date=opened_date))
    return stores


def build_employees(rng: random.Random, faker: Faker, stores: list[Store], today: dt.date) -> list[Employee]:
    employees: list[Employee] = []
    for store in stores:
        n_staff = rng.randint(3, 6)
        opened = store.opened_date or (today - dt.timedelta(days=365))
        hire_window = max(1, (today - opened).days - 30)
        for i in range(n_staff):
            role = "Store Manager" if i == 0 else rng.choice(EMPLOYEE_STAFF_ROLES)
            hire_date = opened + dt.timedelta(days=rng.randint(0, hire_window))
            employees.append(
                Employee(
                    store=store,
                    first_name=faker.first_name(),
                    last_name=faker.last_name(),
                    role=role,
                    hire_date=hire_date,
                    email=faker.unique.email(),
                )
            )
    return employees


def build_customers(rng: random.Random, faker: Faker, today: dt.date) -> list[Customer]:
    customers: list[Customer] = []
    signup_start = today - dt.timedelta(days=1200)
    signup_end = today - dt.timedelta(days=1)
    span = (signup_end - signup_start).days
    for _ in range(N_CUSTOMERS):
        signup_date = signup_start + dt.timedelta(days=rng.randint(0, span))
        customers.append(
            Customer(
                first_name=faker.first_name(),
                last_name=faker.last_name(),
                email=faker.unique.email(),
                phone=faker.phone_number()[:20],
                city=faker.city(),
                state=faker.state_abbr(),
                country="USA",
                signup_date=signup_date,
            )
        )
    return customers


def _order_date_weight(d: dt.date) -> float:
    """Nov/Dec seasonal boost + mild year-over-year growth, for realistic trend queries."""
    year_weight = {2024: 0.85, 2025: 1.0, 2026: 1.15}.get(d.year, 1.0)
    if d.month in (11, 12):
        month_weight = 1.6
    elif d.month == 1:
        month_weight = 0.85
    else:
        month_weight = 1.0
    return year_weight * month_weight


def _random_order_datetime(rng: random.Random, start: dt.date, end: dt.date) -> dt.datetime:
    span_days = (end - start).days
    if span_days <= 0:
        chosen_date = start
    else:
        max_weight = 1.15 * 1.6
        while True:
            candidate = start + dt.timedelta(days=rng.randint(0, span_days))
            if rng.random() <= _order_date_weight(candidate) / max_weight:
                chosen_date = candidate
                break
    seconds = rng.randint(8 * 3600, 21 * 3600)  # store hours: 8am-9pm
    return dt.datetime.combine(chosen_date, dt.time(), tzinfo=dt.timezone.utc) + dt.timedelta(seconds=seconds)


def build_orders(
    rng: random.Random,
    customers: list[Customer],
    stores: list[Store],
    employees: list[Employee],
    products: list[Product],
    today: dt.date,
) -> list[Order]:
    order_start = today - dt.timedelta(days=960)
    order_end = today - dt.timedelta(days=1)

    customer_weights = [rng.lognormvariate(0, 0.9) for _ in customers]
    store_weights = [rng.uniform(0.6, 1.6) for _ in stores]

    employees_by_store: dict[int, list[Employee]] = {}
    for emp in employees:
        employees_by_store.setdefault(emp.store_id, []).append(emp)

    orders: list[Order] = []
    for _ in range(N_ORDERS):
        customer = rng.choices(customers, weights=customer_weights, k=1)[0]
        store = rng.choices(stores, weights=store_weights, k=1)[0]

        cust_start = max(order_start, customer.signup_date)
        if cust_start > order_end:
            cust_start = order_end
        order_dt = _random_order_datetime(rng, cust_start, order_end)

        is_recent = (today - order_dt.date()).days <= 5
        if is_recent:
            status = rng.choices(["completed", "pending"], weights=[0.5, 0.5])[0]
        else:
            status = rng.choices(
                ["completed", "pending", "cancelled", "refunded"],
                weights=[0.85, 0.04, 0.06, 0.05],
            )[0]

        store_employees = employees_by_store.get(store.store_id, [])
        employee = rng.choice(store_employees) if store_employees and rng.random() > 0.10 else None

        n_items = rng.choices([1, 2, 3, 4, 5], weights=[0.30, 0.30, 0.20, 0.12, 0.08])[0]
        chosen_products = rng.sample(products, k=min(n_items, len(products)))

        items: list[OrderItem] = []
        total = Decimal("0.00")
        for product in chosen_products:
            quantity = rng.choices([1, 2, 3, 4, 5], weights=[0.40, 0.30, 0.15, 0.10, 0.05])[0]
            unit_price = product.unit_price
            line_total = (unit_price * quantity).quantize(Decimal("0.01"))
            total += line_total
            items.append(OrderItem(product=product, quantity=quantity, unit_price=unit_price, line_total=line_total))

        order = Order(
            customer=customer,
            store=store,
            employee=employee,
            order_date=order_dt,
            status=status,
            total_amount=total,
        )
        order.items = items

        payment_status = {
            "completed": "paid",
            "pending": "pending",
            "cancelled": "failed",
            "refunded": "refunded",
        }[status]
        payment_dt = order_dt + dt.timedelta(minutes=rng.randint(1, 180))
        method = rng.choices(PAYMENT_METHODS, weights=PAYMENT_METHOD_WEIGHTS)[0]
        order.payments = [
            Payment(payment_method=method, amount=total, payment_date=payment_dt, payment_status=payment_status)
        ]

        orders.append(order)

    return orders


def seed_all(reset: bool = False) -> dict[str, int]:
    with get_session() as session:
        existing = session.query(Category).count()
        if existing and not reset:
            raise RuntimeError("Database already contains data. Re-run with --reset to truncate and reseed.")

    if reset:
        _truncate_all()

    rng = random.Random(SEED)
    faker = Faker("en_US")
    Faker.seed(SEED)
    today = dt.date.today()

    with get_session() as session:
        categories = build_categories()
        session.add_all(categories)
        session.flush()

        products = build_products(rng, faker, categories)
        session.add_all(products)
        session.flush()

        stores = build_stores(rng, today)
        session.add_all(stores)
        session.flush()

        employees = build_employees(rng, faker, stores, today)
        session.add_all(employees)
        session.flush()

        customers = build_customers(rng, faker, today)
        session.add_all(customers)
        session.flush()

        orders = build_orders(rng, customers, stores, employees, products, today)
        session.add_all(orders)
        session.flush()

        counts = {
            "categories": len(categories),
            "products": len(products),
            "stores": len(stores),
            "employees": len(employees),
            "customers": len(customers),
            "orders": len(orders),
            "order_items": sum(len(o.items) for o in orders),
            "payments": sum(len(o.payments) for o in orders),
        }

    return counts
