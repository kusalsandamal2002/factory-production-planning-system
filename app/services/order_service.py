from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, OrderStatusHistory, OvenSchedule
from app.services.scheduler import OrderLineInput, SchedulePreviewResult, build_schedule_preview


def generate_next_order_no(session: Session) -> str:
    current_count = session.scalar(select(func.count(Order.id))) or 0
    return f"ORD-{current_count + 1:05d}"


def preview_order_capacity(session: Session, order_lines: list[OrderLineInput]) -> SchedulePreviewResult:
    return build_schedule_preview(session, order_lines)


def create_confirmed_order(
    session: Session,
    *,
    customer_id: int,
    order_received_date: date,
    order_lines: list[OrderLineInput],
    manager_confirmed_receive_date: date,
    priority: str,
    manager_note: str,
    user_id: int | None,
) -> Order:
    preview = build_schedule_preview(session, order_lines)
    system_date = preview.can_receive_datetime.date()
    if manager_confirmed_receive_date < system_date:
        raise ValueError(
            "Manager confirmed receive date cannot be earlier than the system calculated Company Can Receive Date."
        )
    if not preview.production_slots:
        raise ValueError("Cannot confirm an order with no tire items.")

    order = Order(
        order_no=generate_next_order_no(session),
        customer_id=customer_id,
        order_received_date=order_received_date,
        system_can_receive_datetime=preview.can_receive_datetime,
        manager_confirmed_receive_date=manager_confirmed_receive_date,
        status="CONFIRMED",
        priority=priority,
        manager_note=manager_note,
        created_by=user_id,
        confirmed_by=user_id,
        confirmed_at=datetime.utcnow(),
    )
    session.add(order)
    session.flush()

    item_by_tire_id: dict[int, OrderItem] = {}
    for line in order_lines:
        if line.quantity <= 0:
            continue
        item = OrderItem(order_id=order.id, tire_type_id=line.tire_type_id, quantity=line.quantity)
        session.add(item)
        session.flush()
        item_by_tire_id[line.tire_type_id] = item

    for slot in preview.all_slots:
        order_item_id = None
        if slot.tire_type_id is not None:
            order_item_id = item_by_tire_id[slot.tire_type_id].id
        session.add(
            OvenSchedule(
                schedule_date=slot.schedule_date,
                shift_id=slot.shift_id,
                oven_id=slot.oven_id,
                order_id=order.id if slot.slot_type == "PRODUCTION" else None,
                order_item_id=order_item_id,
                tire_type_id=slot.tire_type_id,
                slot_type=slot.slot_type,
                start_datetime=slot.start_datetime,
                end_datetime=slot.end_datetime,
                duration_minutes=slot.duration_minutes,
                status="PLANNED",
                created_by=user_id,
            )
        )

    session.add(
        OrderStatusHistory(
            order_id=order.id,
            old_status=None,
            new_status="CONFIRMED",
            note="Order confirmed by operation manager.",
            changed_by=user_id,
        )
    )
    return order
