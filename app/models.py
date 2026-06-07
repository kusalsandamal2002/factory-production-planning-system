from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    role: Mapped[Role] = relationship(back_populates="users")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TireType(Base):
    __tablename__ = "tire_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tire_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    tire_name: Mapped[str] = mapped_column(String(120), nullable=False)
    curing_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("curing_minutes > 0", name="ck_tire_curing_minutes_positive"),
    )


class Oven(Base):
    __tablename__ = "ovens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    oven_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    oven_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shift_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    max_working_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("max_working_minutes > 0", name="ck_shift_max_minutes_positive"),
    )


class ProductionRule(Base):
    __tablename__ = "production_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    rule_value: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="minutes")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    order_received_date: Mapped[date] = mapped_column(Date, nullable=False)
    system_can_receive_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    manager_confirmed_receive_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="CONFIRMED")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="NORMAL")
    manager_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)

    customer: Mapped[Customer] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    tire_type_id: Mapped[int] = mapped_column(ForeignKey("tire_types.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Manager tire priority logic:
    # NORMAL = 0
    # HIGH   = 50
    # URGENT = 100
    # Higher number means this tire item is scheduled earlier during auto rebuild.
    manager_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manager_priority_label: Mapped[str] = mapped_column(String(30), nullable=False, default="NORMAL")
    priority_reason: Mapped[str | None] = mapped_column(Text)
    priority_updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    priority_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    order: Mapped[Order] = relationship(back_populates="items")
    tire_type: Mapped[TireType] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity_positive"),
        CheckConstraint("manager_priority >= 0", name="ck_order_item_manager_priority_non_negative"),
        UniqueConstraint("order_id", "tire_type_id", name="uq_order_item_tire_type"),
    )


class OrderItemPriorityLog(Base):
    __tablename__ = "order_item_priority_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_priority: Mapped[int | None] = mapped_column(Integer)
    new_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    old_priority_label: Mapped[str | None] = mapped_column(String(30))
    new_priority_label: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    order_item: Mapped[OrderItem] = relationship()


class OvenSchedule(Base):
    __tablename__ = "oven_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), nullable=False)
    oven_id: Mapped[int] = mapped_column(ForeignKey("ovens.id"), nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    order_item_id: Mapped[int | None] = mapped_column(ForeignKey("order_items.id"))
    tire_type_id: Mapped[int | None] = mapped_column(ForeignKey("tire_types.id"))
    slot_type: Mapped[str] = mapped_column(String(30), nullable=False, default="PRODUCTION")
    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PLANNED")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shift: Mapped[Shift] = relationship()
    oven: Mapped[Oven] = relationship()
    order: Mapped[Order | None] = relationship()
    order_item: Mapped[OrderItem | None] = relationship()
    tire_type: Mapped[TireType | None] = relationship()

    __table_args__ = (
        CheckConstraint("end_datetime > start_datetime", name="ck_schedule_end_after_start"),
    )


class ScheduleChangeLog(Base):
    __tablename__ = "schedule_change_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("oven_schedule.id"), nullable=False)
    old_oven_id: Mapped[int | None] = mapped_column(Integer)
    new_oven_id: Mapped[int | None] = mapped_column(Integer)
    old_start_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    new_start_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    old_end_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    new_end_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    change_reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status: Mapped[str | None] = mapped_column(String(50))
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "mpps_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[str | None] = mapped_column(String(100))
    old_values: Mapped[str | None] = mapped_column(Text)
    new_values: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


