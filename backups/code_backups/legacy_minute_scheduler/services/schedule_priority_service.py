from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Order,
    OrderItem,
    OrderItemPriorityLog,
    Oven,
    OvenSchedule,
    ProductionRule,
    Shift,
    TireType,
)


PRIORITY_WEIGHTS: dict[str, int] = {
    "NORMAL": 0,
    "HIGH": 50,
    "URGENT": 100,
}

OPEN_EXCLUDED_STATUSES = (
    "COMPLETED",
    "PRODUCTION_COMPLETED",
    "CLOSED",
    "CANCELLED",
    "CANCELED",
    "SHIPPED",
    "DISPATCHED",
    "DELIVERED",
    "RECEIVED",
)


@dataclass(frozen=True)
class PriorityItemRow:
    order_item_id: int
    order_id: int
    order_no: str
    customer_name: str
    tire_code: str
    tire_name: str
    quantity: int
    curing_minutes: int
    manager_priority_label: str
    manager_priority: int
    priority_reason: str
    manager_confirmed_receive_date: date
    current_estimated_completion: datetime


@dataclass(frozen=True)
class DelayRiskRow:
    order_id: int
    order_no: str
    customer_name: str
    manager_confirmed_receive_date: date
    new_estimated_completion: datetime
    delay_days: int
    risk_status: str


@dataclass(frozen=True)
class RebuildResult:
    created_slots_count: int
    production_slots_count: int
    break_slots_count: int
    delay_risks: list[DelayRiskRow]


@dataclass
class _ScheduleUnit:
    order_id: int
    order_item_id: int
    tire_type_id: int
    tire_code: str
    tire_name: str
    curing_minutes: int
    manager_priority: int
    manager_priority_label: str
    order_received_date: date
    manager_confirmed_receive_date: date


@dataclass
class _GapCandidate:
    start_datetime: datetime
    end_datetime: datetime
    window_date: date
    shift: Shift
    oven: Oven


def priority_label_to_weight(priority_label: str) -> int:
    label = (priority_label or "NORMAL").strip().upper()
    return PRIORITY_WEIGHTS.get(label, 0)


def normalize_priority_label(priority_label: str) -> str:
    label = (priority_label or "NORMAL").strip().upper()

    if label not in PRIORITY_WEIGHTS:
        raise ValueError("Priority must be NORMAL, HIGH or URGENT.")

    return label


def set_order_item_priority(
    session: Session,
    *,
    order_item_id: int,
    priority_label: str,
    reason: str,
    user_id: int | None,
) -> OrderItem:
    label = normalize_priority_label(priority_label)
    weight = priority_label_to_weight(label)

    item = session.get(OrderItem, order_item_id)

    if item is None:
        raise ValueError("Selected tire item was not found.")

    old_priority = int(getattr(item, "manager_priority", 0) or 0)
    old_label = str(getattr(item, "manager_priority_label", "NORMAL") or "NORMAL").upper()

    item.manager_priority = weight
    item.manager_priority_label = label
    item.priority_reason = reason.strip() if reason else None
    item.priority_updated_by = user_id
    item.priority_updated_at = datetime.utcnow()

    session.add(
        OrderItemPriorityLog(
            order_item_id=item.id,
            old_priority=old_priority,
            new_priority=weight,
            old_priority_label=old_label,
            new_priority_label=label,
            reason=reason.strip() if reason else None,
            changed_by=user_id,
        )
    )

    return item


def load_priority_items(session: Session) -> list[PriorityItemRow]:
    items = list(
        session.scalars(
            select(OrderItem)
            .join(OrderItem.order)
            .join(OrderItem.tire_type)
            .options(
                joinedload(OrderItem.order).joinedload(Order.customer),
                joinedload(OrderItem.tire_type),
            )
            .where(
                ~func.upper(Order.status).in_(OPEN_EXCLUDED_STATUSES),
                TireType.is_active.is_(True),
            )
            .order_by(
                OrderItem.manager_priority.desc(),
                Order.manager_confirmed_receive_date.asc(),
                Order.order_received_date.asc(),
                Order.id.asc(),
                OrderItem.id.asc(),
            )
        )
    )

    rows: list[PriorityItemRow] = []

    for item in items:
        order = item.order
        tire = item.tire_type

        rows.append(
            PriorityItemRow(
                order_item_id=int(item.id),
                order_id=int(order.id),
                order_no=str(order.order_no),
                customer_name=str(order.customer.customer_name if order.customer else "-"),
                tire_code=str(tire.tire_code if tire else "-"),
                tire_name=str(tire.tire_name if tire else "-"),
                quantity=int(item.quantity),
                curing_minutes=int(tire.curing_minutes if tire else 0),
                manager_priority_label=str(
                    getattr(item, "manager_priority_label", "NORMAL") or "NORMAL"
                ).upper(),
                manager_priority=int(getattr(item, "manager_priority", 0) or 0),
                priority_reason=str(getattr(item, "priority_reason", None) or "-"),
                manager_confirmed_receive_date=order.manager_confirmed_receive_date,
                current_estimated_completion=order.system_can_receive_datetime,
            )
        )

    return rows


def rebuild_schedule_by_manager_priority(
    session: Session,
    *,
    start_from: datetime | None = None,
    user_id: int | None,
    horizon_days: int = 1825,
) -> RebuildResult:
    rebuild_start = start_from or datetime.now().replace(second=0, microsecond=0)

    ovens, shifts, tires_by_id = _load_masters(session)
    break_minutes = _get_break_minutes(session)

    _delete_future_planned_schedule(session, rebuild_start)

    horizon_end = rebuild_start + timedelta(days=horizon_days + 2)
    blocked = _load_existing_blocks(session, rebuild_start, horizon_end)

    units = _build_priority_units(session)

    created_slots_count = 0
    production_slots_count = 0
    break_slots_count = 0
    completion_by_order: dict[int, datetime] = {}

    for unit in units:
        tire = tires_by_id.get(unit.tire_type_id)

        if tire is None:
            continue

        curing_minutes = int(tire.curing_minutes)
        block_minutes = curing_minutes + break_minutes

        candidate = _find_earliest_gap(
            ovens=ovens,
            shifts=shifts,
            blocked=blocked,
            required_minutes=block_minutes,
            start_from=rebuild_start,
            horizon_days=horizon_days,
        )

        prod_start = candidate.start_datetime
        prod_end = prod_start + timedelta(minutes=curing_minutes)
        break_end = prod_end + timedelta(minutes=break_minutes)

        key = (candidate.oven.id, candidate.shift.id, candidate.window_date)
        blocked.setdefault(key, []).append((prod_start, break_end))

        session.add(
            OvenSchedule(
                schedule_date=candidate.window_date,
                shift_id=candidate.shift.id,
                oven_id=candidate.oven.id,
                order_id=unit.order_id,
                order_item_id=unit.order_item_id,
                tire_type_id=unit.tire_type_id,
                slot_type="PRODUCTION",
                start_datetime=prod_start,
                end_datetime=prod_end,
                duration_minutes=curing_minutes,
                status="PLANNED",
                created_by=user_id,
            )
        )
        production_slots_count += 1
        created_slots_count += 1

        if break_minutes > 0:
            session.add(
                OvenSchedule(
                    schedule_date=candidate.window_date,
                    shift_id=candidate.shift.id,
                    oven_id=candidate.oven.id,
                    order_id=None,
                    order_item_id=None,
                    tire_type_id=None,
                    slot_type="BREAK",
                    start_datetime=prod_end,
                    end_datetime=break_end,
                    duration_minutes=break_minutes,
                    status="PLANNED",
                    created_by=user_id,
                )
            )
            break_slots_count += 1
            created_slots_count += 1

        previous_completion = completion_by_order.get(unit.order_id)

        if previous_completion is None or prod_end > previous_completion:
            completion_by_order[unit.order_id] = prod_end

    for order_id, estimated_completion in completion_by_order.items():
        order = session.get(Order, order_id)

        if order is not None:
            order.system_can_receive_datetime = estimated_completion

    session.flush()

    return RebuildResult(
        created_slots_count=created_slots_count,
        production_slots_count=production_slots_count,
        break_slots_count=break_slots_count,
        delay_risks=load_delay_risks(session),
    )


def load_delay_risks(session: Session) -> list[DelayRiskRow]:
    orders = list(
        session.scalars(
            select(Order)
            .options(joinedload(Order.customer))
            .where(~func.upper(Order.status).in_(OPEN_EXCLUDED_STATUSES))
            .order_by(Order.manager_confirmed_receive_date.asc(), Order.id.asc())
        )
    )

    risks: list[DelayRiskRow] = []

    for order in orders:
        estimated = order.system_can_receive_datetime
        confirmed_date = order.manager_confirmed_receive_date

        if estimated is None or confirmed_date is None:
            continue

        delay_days = (estimated.date() - confirmed_date).days

        if delay_days <= 0:
            continue

        risk_status = "DELAY RISK"

        if delay_days >= 3:
            risk_status = "CRITICAL DELAY"

        risks.append(
            DelayRiskRow(
                order_id=int(order.id),
                order_no=str(order.order_no),
                customer_name=str(order.customer.customer_name if order.customer else "-"),
                manager_confirmed_receive_date=confirmed_date,
                new_estimated_completion=estimated,
                delay_days=int(delay_days),
                risk_status=risk_status,
            )
        )

    return risks


def _build_priority_units(session: Session) -> list[_ScheduleUnit]:
    items = list(
        session.scalars(
            select(OrderItem)
            .join(OrderItem.order)
            .join(OrderItem.tire_type)
            .options(
                joinedload(OrderItem.order),
                joinedload(OrderItem.tire_type),
            )
            .where(
                ~func.upper(Order.status).in_(OPEN_EXCLUDED_STATUSES),
                TireType.is_active.is_(True),
            )
            .order_by(
                OrderItem.manager_priority.desc(),
                Order.manager_confirmed_receive_date.asc(),
                Order.order_received_date.asc(),
                Order.id.asc(),
                OrderItem.id.asc(),
            )
        )
    )

    units: list[_ScheduleUnit] = []

    for item in items:
        order = item.order
        tire = item.tire_type

        for _ in range(int(item.quantity)):
            units.append(
                _ScheduleUnit(
                    order_id=int(order.id),
                    order_item_id=int(item.id),
                    tire_type_id=int(tire.id),
                    tire_code=str(tire.tire_code),
                    tire_name=str(tire.tire_name),
                    curing_minutes=int(tire.curing_minutes),
                    manager_priority=int(getattr(item, "manager_priority", 0) or 0),
                    manager_priority_label=str(
                        getattr(item, "manager_priority_label", "NORMAL") or "NORMAL"
                    ).upper(),
                    order_received_date=order.order_received_date,
                    manager_confirmed_receive_date=order.manager_confirmed_receive_date,
                )
            )

    units.sort(
        key=lambda unit: (
            -unit.manager_priority,
            unit.manager_confirmed_receive_date,
            unit.order_received_date,
            unit.order_id,
            unit.order_item_id,
        )
    )

    return units


def _delete_future_planned_schedule(session: Session, start_from: datetime) -> None:
    rows = list(
        session.scalars(
            select(OvenSchedule).where(
                OvenSchedule.start_datetime >= start_from,
                ~func.upper(OvenSchedule.status).in_(("COMPLETED", "DONE", "FINISHED")),
            )
        )
    )

    for row in rows:
        session.delete(row)

    session.flush()


def _load_masters(session: Session) -> tuple[list[Oven], list[Shift], dict[int, TireType]]:
    ovens = list(
        session.scalars(
            select(Oven)
            .where(Oven.is_active.is_(True))
            .order_by(Oven.oven_code)
        )
    )
    shifts = list(
        session.scalars(
            select(Shift)
            .where(Shift.is_active.is_(True))
            .order_by(Shift.start_time)
        )
    )
    tires = {
        tire.id: tire
        for tire in session.scalars(
            select(TireType).where(TireType.is_active.is_(True))
        )
    }

    if not ovens:
        raise ValueError("No active ovens found. Please add oven master data.")

    if not shifts:
        raise ValueError("No active shifts found. Please add shift master data.")

    return ovens, shifts, tires


def _get_break_minutes(session: Session) -> int:
    rule = session.scalar(
        select(ProductionRule).where(ProductionRule.rule_name == "BREAK_BETWEEN_TIRES")
    )

    if rule is None:
        return 20

    return int(rule.rule_value)


def _combine_shift_window(day: date, shift: Shift) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(day, shift.start_time)
    end_dt = datetime.combine(day, shift.end_time)

    if shift.end_time <= shift.start_time:
        end_dt += timedelta(days=1)

    return start_dt, end_dt


def _normalise_intervals(
    intervals: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    sorted_intervals = sorted(intervals, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = []

    for start, end in sorted_intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)

    return merged


def _free_gaps(
    window_start: datetime,
    window_end: datetime,
    blocked_intervals: list[tuple[datetime, datetime]],
    earliest_start: datetime,
) -> list[tuple[datetime, datetime]]:
    start = max(window_start, earliest_start)
    end = window_end

    if start >= end:
        return []

    busy = _normalise_intervals(
        (max(busy_start, start), min(busy_end, end))
        for busy_start, busy_end in blocked_intervals
        if busy_start < end and busy_end > start
    )

    gaps: list[tuple[datetime, datetime]] = []
    cursor = start

    for busy_start, busy_end in busy:
        if cursor < busy_start:
            gaps.append((cursor, busy_start))

        cursor = max(cursor, busy_end)

    if cursor < end:
        gaps.append((cursor, end))

    return gaps


def _load_existing_blocks(
    session: Session,
    start_from: datetime,
    horizon_end: datetime,
) -> dict[tuple[int, int, date], list[tuple[datetime, datetime]]]:
    schedules = session.scalars(
        select(OvenSchedule).where(
            and_(
                OvenSchedule.start_datetime < horizon_end,
                OvenSchedule.end_datetime > start_from,
                func.upper(OvenSchedule.status) != "CANCELLED",
            )
        )
    )

    blocked: dict[tuple[int, int, date], list[tuple[datetime, datetime]]] = {}

    for schedule in schedules:
        key = (schedule.oven_id, schedule.shift_id, schedule.schedule_date)
        blocked.setdefault(key, []).append(
            (schedule.start_datetime, schedule.end_datetime)
        )

    return blocked


def _find_earliest_gap(
    *,
    ovens: list[Oven],
    shifts: list[Shift],
    blocked: dict[tuple[int, int, date], list[tuple[datetime, datetime]]],
    required_minutes: int,
    start_from: datetime,
    horizon_days: int,
) -> _GapCandidate:
    best: _GapCandidate | None = None
    required_delta = timedelta(minutes=required_minutes)
    first_date = start_from.date()

    for day_index in range(horizon_days):
        day = first_date + timedelta(days=day_index)

        for shift in shifts:
            window_start, window_end = _combine_shift_window(day, shift)

            if window_end <= start_from:
                continue

            for oven in ovens:
                key = (oven.id, shift.id, day)
                gaps = _free_gaps(
                    window_start,
                    window_end,
                    blocked.get(key, []),
                    start_from,
                )

                for gap_start, gap_end in gaps:
                    if gap_end - gap_start >= required_delta:
                        candidate = _GapCandidate(
                            start_datetime=gap_start,
                            end_datetime=gap_end,
                            window_date=day,
                            shift=shift,
                            oven=oven,
                        )

                        if best is None or candidate.start_datetime < best.start_datetime:
                            best = candidate

                        break

        if best is not None:
            return best

    raise ValueError(
        "No available oven capacity found inside planning horizon. Check oven capacity, shift settings or order volume."
    )
