from __future__ import annotations

import argparse
from datetime import date

from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--created-by",
        default="auto_target_v6_4_installer",
    )
    args = parser.parse_args()

    result = FactoryPlanningEngine(
        start_date=date.today()
    ).replan_all_open_shipments(
        trigger_reason=(
            "auto_factory_out_target_v6_4"
        ),
        created_by=args.created_by,
    )

    auto_count = sum(
        shipment.delivery_status
        == "Auto Scheduled"
        for shipment in result.shipments
    )
    blocked_count = sum(
        "blocked" in shipment.planning_status.lower()
        for shipment in result.shipments
    )

    print(
        "AUTO FACTORY-OUT CUMULATIVE REPLAN COMPLETED"
    )
    print(
        f"planning_run_id: "
        f"{result.planning_run_id}"
    )
    print(
        f"active_shipments_planned: "
        f"{len(result.shipments)}"
    )
    print(
        f"auto_scheduled_shipments: "
        f"{auto_count}"
    )
    print(
        f"blocked_or_partially_blocked: "
        f"{blocked_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
