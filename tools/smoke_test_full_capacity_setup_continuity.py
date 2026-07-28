from __future__ import annotations

from datetime import date
import inspect

from app.services.cavity_daily_plan_service import (
    CavityPlanSettings,
    _Cavity,
    _Demand,
    _schedule_day,
    _setup_reuse_rank,
)
from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)


def make_cavity(
    cavity_id: int,
) -> _Cavity:
    return _Cavity(
        cavity_id=cavity_id,
        line_name="Line-800",
        cavity_no=cavity_id,
        oven_no=f"OVEN-{cavity_id}",
        database_status="Active",
        assigned_tyre_item="",
        remarks="",
        is_active=True,
    )


def make_demand(
    *,
    sap: str,
    qty: int,
    mold: str,
    casing: str,
) -> _Demand:
    return _Demand(
        sap_code=sap,
        description=sap,
        due_date=date(2026, 7, 30),
        required_qty=qty,
        remaining_qty=qty,
        shipment_id=1,
        shipment_item_id=1,
        approval_status="Approved",
        line_names={"Line-800"},
        mold_type=mold,
        casing_type=casing,
        effective_cycle_minutes=720,
        weight_per_tyre_kg=0.0,
        heel="-",
        soft="-",
        tred="-",
        remark="-",
        core="-",
        source={"test": True},
    )


def main() -> None:
    settings = CavityPlanSettings(
        planning_date=date(2026, 7, 27),
        day_shift_minutes=720,
        night_shift_minutes=0,
        changeover_minutes=20,
    )

    full_allocations = _schedule_day(
        cavities=[
            make_cavity(1),
            make_cavity(2),
            make_cavity(3),
            make_cavity(4),
        ],
        demands=[
            make_demand(
                sap="FULL",
                qty=4,
                mold="M1",
                casing="C1",
            )
        ],
        settings=settings,
        mold_capacity={"m1": 4},
        casing_capacity={"c1": 4},
    )

    assert len(full_allocations) == 4
    assert len({
        item.cavity_id
        for item in full_allocations
    }) == 4

    same_setup_allocations = _schedule_day(
        cavities=[
            make_cavity(1),
            make_cavity(2),
        ],
        demands=[
            make_demand(
                sap="NEW-SAP",
                qty=1,
                mold="M1",
                casing="C1",
            )
        ],
        settings=settings,
        mold_capacity={"m1": 2},
        casing_capacity={"c1": 2},
        initial_setups={
            1: ("OLD-SAP", "m1", "c1"),
        },
    )
    assert (
        same_setup_allocations[0].cavity_id
        == 1
    )

    empty_first_allocations = _schedule_day(
        cavities=[
            make_cavity(1),
            make_cavity(2),
        ],
        demands=[
            make_demand(
                sap="OTHER",
                qty=1,
                mold="M2",
                casing="C2",
            )
        ],
        settings=settings,
        mold_capacity={"m2": 1},
        casing_capacity={"c2": 1},
        initial_setups={
            1: ("OLD-SAP", "m1", "c1"),
        },
    )
    assert (
        empty_first_allocations[0].cavity_id
        == 2
    )

    reused = make_cavity(1)
    reused.last_sap_code = "OLD"
    reused.last_mold_type = "M1"
    reused.last_casing_type = "C1"

    assert _setup_reuse_rank(
        reused,
        make_demand(
            sap="NEW",
            qty=1,
            mold="M1",
            casing="C1",
        ),
    ) == 1

    source = inspect.getsource(
        FactoryPlanningEngine
    )
    assert (
        "Maximum useful compatible "
        "capacity used."
        in source
    )
    assert (
        "Physical mold and casing counts "
        "remain hard simultaneous-capacity limits."
        in source
    )

    print(
        "FULL CAPACITY SYNTHETIC TEST PASSED"
    )
    print(
        "SAME SETUP REUSE TEST PASSED"
    )
    print(
        "EMPTY CAVITY BEFORE CHANGEOVER TEST PASSED"
    )
    print(
        "RESOURCE BOTTLENECK EXPLANATION TEST PASSED"
    )


if __name__ == "__main__":
    main()
