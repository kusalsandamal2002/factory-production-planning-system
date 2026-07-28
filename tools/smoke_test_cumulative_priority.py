from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.database import engine
from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)
from app.ui.order_entry_page import OrderEntryPage


def main() -> None:
    required_engine_methods = [
        "calculate_cart_items",
        "_shipment_priority_sort_key",
        "replan_all_open_shipments",
    ]
    required_page_methods = [
        "recalculate_current_cart",
        "_manual_preview_target_date",
        "save_shipment",
    ]

    missing = [
        name
        for name in required_engine_methods
        if not hasattr(FactoryPlanningEngine, name)
    ]
    missing += [
        name
        for name in required_page_methods
        if not hasattr(OrderEntryPage, name)
    ]
    if missing:
        raise AssertionError(
            f"Missing cumulative planner methods: {missing}"
        )

    planner = FactoryPlanningEngine(
        start_date=date.today()
    )

    with engine.begin() as connection:
        before_count = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM planning_resource_reservations
                    """
                )
            ).scalar_one()
        )

        sample = connection.execute(
            text(
                """
                SELECT
                    item.sap_code,
                    item.item_description,
                    GREATEST(item.quantity, 1)
                        AS quantity,
                    shipment.id AS shipment_id,
                    shipment.target_date,
                    shipment.factory_can_receive_date
                FROM mpps_shipment_items item
                JOIN mpps_shipments shipment
                  ON shipment.id = item.shipment_id
                JOIN smds
                  ON TRIM(smds.sap_code)
                    = TRIM(item.sap_code)
                WHERE LOWER(
                    COALESCE(
                        smds.planning_manager_approval_status,
                        ''
                    )
                ) = 'approved'
                  AND LOWER(
                    COALESCE(
                        shipment.status,
                        'planned'
                    )
                  ) NOT IN (
                    'cancelled',
                    'canceled',
                    'completed',
                    'shipped'
                  )
                ORDER BY
                    CASE
                        WHEN COALESCE(
                            shipment.target_date_is_manual,
                            FALSE
                        )
                        THEN 0
                        ELSE 1
                    END,
                    shipment.target_date NULLS LAST,
                    shipment.created_at,
                    shipment.id,
                    item.id
                LIMIT 1
                """
            )
        ).mappings().first()

    if sample is None:
        print(
            "CUMULATIVE PRIORITY SMOKE TEST PASSED"
        )
        print(
            "Preview sample skipped: no active "
            "approved shipment item."
        )
        return

    preview = planner.calculate_cart_items(
        [
            {
                "sap_code": sample["sap_code"],
                "item_description": (
                    sample["item_description"]
                ),
                "quantity": int(
                    sample["quantity"]
                ),
            }
        ],
        target_date=None,
        target_date_is_manual=False,
    )

    with engine.begin() as connection:
        after_count = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM planning_resource_reservations
                    """
                )
            ).scalar_one()
        )

    assert before_count == after_count, (
        before_count,
        after_count,
    )
    assert len(preview) == 1, preview

    result = preview[0]

    print(
        "CUMULATIVE PRIORITY SMOKE TEST PASSED"
    )
    print(
        f"Existing shipment ID: "
        f"{sample['shipment_id']}"
    )
    print(
        f"Existing target: "
        f"{sample['target_date']}"
    )
    print(
        f"Existing receive: "
        f"{sample['factory_can_receive_date']}"
    )
    print(
        f"New draft preview receive: "
        f"{result.get('item_receive_date')}"
    )
    print(
        f"New draft status: "
        f"{result.get('item_status')}"
    )
    print(
        "Preview did not change saved reservation "
        f"count: {before_count}"
    )


if __name__ == "__main__":
    main()
