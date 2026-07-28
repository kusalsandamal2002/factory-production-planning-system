from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.services.cavity_daily_plan_service import (
    CavityPlanSettings,
    _Cavity,
    _Demand,
    _format_minute,
    _schedule_day,
)


def make_cavities():
    return [
        _Cavity(
            cavity_id=index,
            line_name="Line-800",
            cavity_no=index,
            oven_no=f"T800-{index:03}",
            database_status="Active",
            assigned_tyre_item="",
            remarks="",
            is_active=True,
        )
        for index in range(1, 7)
    ]


def make_demand():
    return _Demand(
        sap_code="60000004",
        description="Synthetic fixed-shift test tyre",
        due_date=None,
        required_qty=105,
        remaining_qty=105,
        shipment_id=1,
        shipment_item_id=1,
        approval_status="Approved",
        line_names={"Line-800"},
        mold_type="M1",
        casing_type="B7",
        effective_cycle_minutes=500,
        weight_per_tyre_kg=0.0,
        heel="-",
        soft="-",
        tred="-",
        remark="-",
        core="-",
    )


def allocate(day_minutes, night_minutes):
    return _schedule_day(
        cavities=make_cavities(),
        demands=[make_demand()],
        settings=CavityPlanSettings(
            planning_date=date.today(),
            day_shift_minutes=day_minutes,
            night_shift_minutes=night_minutes,
            changeover_minutes=0,
        ),
        mold_capacity={"m1": 2},
        casing_capacity={"b7": 2},
    )


def main():
    all_allocations = allocate(720, 720)
    day_allocations = allocate(720, 0)
    night_allocations = allocate(0, 720)

    assert len(all_allocations) == 4, len(all_allocations)
    assert len(day_allocations) == 2, len(day_allocations)
    assert len(night_allocations) == 2, len(night_allocations)

    by_cavity = defaultdict(list)
    for item in all_allocations:
        by_cavity[item.cavity_id].append(item.shift_name)
    assert len(by_cavity) == 2, len(by_cavity)
    for shifts in by_cavity.values():
        assert sorted(shifts) == ["DAY", "NIGHT"], shifts

    for item in day_allocations:
        assert item.shift_name == "DAY"
        assert 0 <= item.start_minute < item.end_minute <= 720

    for item in night_allocations:
        assert item.shift_name == "NIGHT"
        assert 720 <= item.start_minute < item.end_minute <= 1440

    assert _format_minute(0) == "07:00"
    assert _format_minute(720) == "19:00"
    assert _format_minute(1440) == "07:00"

    print("FIXED SHIFT SELECTOR TEST PASSED")
    print("ALL SHIFTS: 4 units on 2 ovens")
    print("DAY SHIFT: 2 units between 07:00 and 19:00")
    print("NIGHT SHIFT: 2 units between 19:00 and 07:00")


if __name__ == "__main__":
    main()
