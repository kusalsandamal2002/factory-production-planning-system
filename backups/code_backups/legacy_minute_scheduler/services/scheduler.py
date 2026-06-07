from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import count
from math import ceil
from typing import Iterable

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import Oven, OvenSchedule, ProductionRule, Shift, TireType


MIN_PLANNING_HORIZON_DAYS = 90
MAX_PLANNING_HORIZON_DAYS = 1825
HORIZON_BUFFER_DAYS = 30


@dataclass(frozen=True)
class OrderLineInput:
    tire_type_id: int
    quantity: int


@dataclass(frozen=True)
class ScheduleSlotPreview:
    schedule_date: date
    shift_id: int
    shift_name: str
    oven_id: int
    oven_code: str
    tire_type_id: int | None
    tire_name: str | None
    slot_type: str
    start_datetime: datetime
    end_datetime: datetime
    duration_minutes: int


@dataclass(frozen=True)
class SchedulePreviewResult:
    can_receive_datetime: datetime
    production_slots: list[ScheduleSlotPreview]
    all_slots: list[ScheduleSlotPreview]
    total_order_quantity: int
    total_curing_minutes: int
    total_break_minutes: int


@dataclass
class _FreeGap:
    start_datetime: datetime
    end_datetime: datetime
    window_date: date
    shift: Shift
    oven: Oven


def _combine_shift_window(day: date, shift: Shift) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(day, shift.start_time)
    end_dt = datetime.combine(day, shift.end_time)

    if shift.end_time <= shift.start_time:
        end_dt += timedelta(days=1)

    return start_dt, end_dt


def _minutes_between(start: datetime, end: datetime) -> int:
    if end <= start:
        return 0

    return int((end - start).total_seconds() // 60)


def _get_break_minutes(session: Session) -> int:
    rule = session.scalar(
        select(ProductionRule).where(
            ProductionRule.rule_name == "BREAK_BETWEEN_TIRES"
        )
    )

    return int(rule.rule_value) if rule else 20


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
        raise ValueError("No active ovens found. Please seed oven master data.")

    if not shifts:
        raise ValueError("No active shifts found. Please seed shift master data.")

    return ovens, shifts, tires


def _normalise_intervals(
    intervals: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    sorted_intervals = sorted(intervals, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = []

    for start, end in sorted_intervals:
        if start >= end:
            continue

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
    rows = session.scalars(
        select(OvenSchedule).where(
            and_(
                OvenSchedule.start_datetime < horizon_end,
                OvenSchedule.end_datetime > start_from,
                OvenSchedule.status != "CANCELLED",
            )
        )
    )

    blocked: dict[tuple[int, int, date], list[tuple[datetime, datetime]]] = {}

    for row in rows:
        key = (row.oven_id, row.shift_id, row.schedule_date)
        blocked.setdefault(key, []).append((row.start_datetime, row.end_datetime))

    return blocked


def _shift_duration_minutes(shift: Shift) -> int:
    sample_day = date(2026, 1, 1)
    start_dt, end_dt = _combine_shift_window(sample_day, shift)
    return _minutes_between(start_dt, end_dt)


def _estimate_required_horizon_days(
    *,
    valid_lines: list[OrderLineInput],
    tires: dict[int, TireType],
    ovens: list[Oven],
    shifts: list[Shift],
    break_minutes: int,
    requested_horizon_days: int,
) -> int:
    total_block_minutes = 0

    for line in valid_lines:
        tire = tires.get(line.tire_type_id)

        if tire is None:
            raise ValueError(f"Invalid tire type id: {line.tire_type_id}")

        curing_minutes = int(tire.curing_minutes)
        total_block_minutes += line.quantity * (curing_minutes + break_minutes)

    daily_capacity_minutes = len(ovens) * sum(
        _shift_duration_minutes(shift) for shift in shifts
    )

    if daily_capacity_minutes <= 0:
        return max(requested_horizon_days, MIN_PLANNING_HORIZON_DAYS)

    estimated_days = ceil(total_block_minutes / daily_capacity_minutes)
    estimated_with_buffer = estimated_days + HORIZON_BUFFER_DAYS

    horizon_days = max(
        requested_horizon_days,
        MIN_PLANNING_HORIZON_DAYS,
        estimated_with_buffer,
    )

    return min(horizon_days, MAX_PLANNING_HORIZON_DAYS)


def _push_gap_if_useful(
    heap: list[tuple[datetime, int, _FreeGap]],
    sequence,
    gap: _FreeGap,
    min_required_minutes: int,
) -> None:
    available_minutes = _minutes_between(gap.start_datetime, gap.end_datetime)

    if available_minutes >= min_required_minutes:
        heapq.heappush(
            heap,
            (
                gap.start_datetime,
                next(sequence),
                gap,
            ),
        )


def _build_free_gap_heap(
    *,
    ovens: list[Oven],
    shifts: list[Shift],
    blocked: dict[tuple[int, int, date], list[tuple[datetime, datetime]]],
    start_from: datetime,
    horizon_days: int,
    min_required_minutes: int,
) -> list[tuple[datetime, int, _FreeGap]]:
    heap: list[tuple[datetime, int, _FreeGap]] = []
    sequence = count()
    first_date = start_from.date()

    for day_index in range(horizon_days):
        working_day = first_date + timedelta(days=day_index)

        for shift in shifts:
            window_start, window_end = _combine_shift_window(working_day, shift)

            if window_end <= start_from:
                continue

            for oven in ovens:
                key = (oven.id, shift.id, working_day)
                existing_blocks = blocked.get(key, [])

                for gap_start, gap_end in _free_gaps(
                    window_start,
                    window_end,
                    existing_blocks,
                    start_from,
                ):
                    gap = _FreeGap(
                        start_datetime=gap_start,
                        end_datetime=gap_end,
                        window_date=working_day,
                        shift=shift,
                        oven=oven,
                    )

                    _push_gap_if_useful(
                        heap,
                        sequence,
                        gap,
                        min_required_minutes,
                    )

    return heap


def _take_earliest_gap_that_fits(
    *,
    heap: list[tuple[datetime, int, _FreeGap]],
    sequence,
    required_minutes: int,
    min_required_minutes: int,
) -> _FreeGap | None:
    skipped_gaps: list[_FreeGap] = []

    while heap:
        _, _, gap = heapq.heappop(heap)
        available_minutes = _minutes_between(gap.start_datetime, gap.end_datetime)

        if available_minutes >= required_minutes:
            for skipped_gap in skipped_gaps:
                _push_gap_if_useful(
                    heap,
                    sequence,
                    skipped_gap,
                    min_required_minutes,
                )

            return gap

        if available_minutes >= min_required_minutes:
            skipped_gaps.append(gap)

    for skipped_gap in skipped_gaps:
        _push_gap_if_useful(
            heap,
            sequence,
            skipped_gap,
            min_required_minutes,
        )

    return None


def build_schedule_preview(
    session: Session,
    order_lines: list[OrderLineInput],
    start_from: datetime | None = None,
    horizon_days: int = 365,
) -> SchedulePreviewResult:
    valid_lines = [line for line in order_lines if line.quantity > 0]

    if not valid_lines:
        now = start_from or datetime.now().replace(second=0, microsecond=0)
        return SchedulePreviewResult(now, [], [], 0, 0, 0)

    start_from = start_from or datetime.now().replace(second=0, microsecond=0)

    ovens, shifts, tires = _load_masters(session)
    break_minutes = _get_break_minutes(session)

    horizon_days = _estimate_required_horizon_days(
        valid_lines=valid_lines,
        tires=tires,
        ovens=ovens,
        shifts=shifts,
        break_minutes=break_minutes,
        requested_horizon_days=horizon_days,
    )

    horizon_end = start_from + timedelta(days=horizon_days + 2)

    blocked = _load_existing_blocks(
        session=session,
        start_from=start_from,
        horizon_end=horizon_end,
    )

    min_required_minutes = min(
        int(tires[line.tire_type_id].curing_minutes) + break_minutes
        for line in valid_lines
        if tires.get(line.tire_type_id) is not None
    )

    free_gap_heap = _build_free_gap_heap(
        ovens=ovens,
        shifts=shifts,
        blocked=blocked,
        start_from=start_from,
        horizon_days=horizon_days,
        min_required_minutes=min_required_minutes,
    )

    heap_sequence = count(1_000_000)

    production_slots: list[ScheduleSlotPreview] = []
    all_slots: list[ScheduleSlotPreview] = []

    total_quantity = 0
    total_curing_minutes = 0
    total_break_minutes = 0
    completion_datetime = start_from

    for line in valid_lines:
        tire = tires.get(line.tire_type_id)

        if tire is None:
            raise ValueError(f"Invalid tire type id: {line.tire_type_id}")

        curing_minutes = int(tire.curing_minutes)
        block_minutes = curing_minutes + break_minutes

        for _ in range(line.quantity):
            candidate = _take_earliest_gap_that_fits(
                heap=free_gap_heap,
                sequence=heap_sequence,
                required_minutes=block_minutes,
                min_required_minutes=min_required_minutes,
            )

            if candidate is None:
                raise ValueError(
                    "No available oven capacity found inside the planning horizon. "
                    f"The system searched {horizon_days} days. "
                    "Try increasing MAX_PLANNING_HORIZON_DAYS or check active ovens and shifts."
                )

            prod_start = candidate.start_datetime
            prod_end = prod_start + timedelta(minutes=curing_minutes)
            break_end = prod_end + timedelta(minutes=break_minutes)

            prod_slot = ScheduleSlotPreview(
                schedule_date=candidate.window_date,
                shift_id=candidate.shift.id,
                shift_name=candidate.shift.shift_name,
                oven_id=candidate.oven.id,
                oven_code=candidate.oven.oven_code,
                tire_type_id=tire.id,
                tire_name=tire.tire_name,
                slot_type="PRODUCTION",
                start_datetime=prod_start,
                end_datetime=prod_end,
                duration_minutes=curing_minutes,
            )

            production_slots.append(prod_slot)
            all_slots.append(prod_slot)

            if break_minutes > 0:
                break_slot = ScheduleSlotPreview(
                    schedule_date=candidate.window_date,
                    shift_id=candidate.shift.id,
                    shift_name=candidate.shift.shift_name,
                    oven_id=candidate.oven.id,
                    oven_code=candidate.oven.oven_code,
                    tire_type_id=None,
                    tire_name=None,
                    slot_type="BREAK",
                    start_datetime=prod_end,
                    end_datetime=break_end,
                    duration_minutes=break_minutes,
                )

                all_slots.append(break_slot)

            remaining_gap = _FreeGap(
                start_datetime=break_end,
                end_datetime=candidate.end_datetime,
                window_date=candidate.window_date,
                shift=candidate.shift,
                oven=candidate.oven,
            )

            _push_gap_if_useful(
                free_gap_heap,
                heap_sequence,
                remaining_gap,
                min_required_minutes,
            )

            total_quantity += 1
            total_curing_minutes += curing_minutes
            total_break_minutes += break_minutes
            completion_datetime = max(completion_datetime, prod_end)

    return SchedulePreviewResult(
        can_receive_datetime=completion_datetime,
        production_slots=production_slots,
        all_slots=all_slots,
        total_order_quantity=total_quantity,
        total_curing_minutes=total_curing_minutes,
        total_break_minutes=total_break_minutes,
    )