from __future__ import annotations

from datetime import date

from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)


def main() -> int:
    result = FactoryPlanningEngine(
        start_date=date.today()
    ).replan_all_open_shipments(
        trigger_reason="process_standard_integrity_v6_5",
        created_by="process_standard_v6_5_installer",
    )

    blocked_count = sum(
        "blocked" in (
            shipment.planning_status or ""
        ).lower()
        for shipment in result.shipments
    )
    scheduled_count = sum(
        shipment.factory_can_receive_date is not None
        for shipment in result.shipments
    )

    print("PROCESS STANDARD V6.5 CUMULATIVE REPLAN COMPLETED")
    print(f"planning_run_id: {result.planning_run_id}")
    print(f"active_shipments_planned: {len(result.shipments)}")
    print(f"shipments_with_receive_date: {scheduled_count}")
    print(f"blocked_or_partially_blocked: {blocked_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
