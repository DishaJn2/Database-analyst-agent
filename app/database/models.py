"""SQLAlchemy ORM models for the 8-table schema."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(primary_key=True)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.category_id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    sku: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(back_populates="products")
    order_items: Mapped[list[OrderItem]] = relationship(back_populates="product")

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_products_unit_price_nonneg"),
        CheckConstraint("cost_price >= 0", name="ck_products_cost_price_nonneg"),
        Index("ix_products_category_id", "category_id"),
    )


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    signup_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list[Order]] = relationship(back_populates="customer")

    __table_args__ = (Index("ix_customers_signup_date", "signup_date"),)


class Store(Base):
    __tablename__ = "stores"

    store_id: Mapped[int] = mapped_column(primary_key=True)
    store_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    opened_date: Mapped[dt.date | None] = mapped_column(Date)

    employees: Mapped[list[Employee]] = relationship(back_populates="store")
    orders: Mapped[list[Order]] = relationship(back_populates="store")

    __table_args__ = (Index("ix_stores_region", "region"),)


class Employee(Base):
    __tablename__ = "employees"

    employee_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.store_id"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    hire_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    email: Mapped[str | None] = mapped_column(String(150), unique=True)

    store: Mapped[Store] = relationship(back_populates="employees")
    orders: Mapped[list[Order]] = relationship(back_populates="employee")

    __table_args__ = (Index("ix_employees_store_id", "store_id"),)


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.store_id"), nullable=False)
    # Nullable: some orders (e.g. self-checkout) aren't handled by a specific employee.
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.employee_id"))
    order_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Denormalized sum of order_items.line_total, fixed by the seed script at insert time.
    # 25+ analytical use cases (AOV, revenue trends) read this directly rather than
    # re-aggregating order_items on every query.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    store: Mapped[Store] = relationship(back_populates="orders")
    employee: Mapped[Employee | None] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('completed','pending','cancelled','refunded')",
            name="ck_orders_status_valid",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_nonneg"),
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_store_id", "store_id"),
        Index("ix_orders_order_date", "order_date"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    # Price snapshot at time of sale, intentionally independent of products.unit_price
    # (which may change later) -- matches how real order-history systems work.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="order_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_nonneg"),
        CheckConstraint("line_total >= 0", name="ck_order_items_line_total_nonneg"),
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
    )


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False)

    order: Mapped[Order] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint(
            "payment_method IN ('credit_card','debit_card','paypal','cash','bank_transfer','gift_card')",
            name="ck_payments_method_valid",
        ),
        CheckConstraint(
            "payment_status IN ('paid','failed','refunded','pending')",
            name="ck_payments_status_valid",
        ),
        CheckConstraint("amount >= 0", name="ck_payments_amount_nonneg"),
        Index("ix_payments_order_id", "order_id"),
        Index("ix_payments_payment_method", "payment_method"),
    )
