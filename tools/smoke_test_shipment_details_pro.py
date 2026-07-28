from __future__ import annotations

import inspect

from app.ui.shipment_orders_page import (
    ShipmentOrdersPage,
)


def main() -> None:
    required_methods = [
        "_build_detail_page",
        "_setup_detail_table",
        "open_shipment_detail",
        "on_detail_selection_changed",
    ]

    missing = [
        name
        for name in required_methods
        if not hasattr(
            ShipmentOrdersPage,
            name,
        )
    ]
    if missing:
        raise AssertionError(
            f"Missing methods: {missing}"
        )

    source = inspect.getsource(
        ShipmentOrdersPage.open_shipment_detail
    )

    required_fields = [
        "production_required_qty",
        "produced_qty",
        "completed_qty",
        "remaining_qty",
        "daily_capacity",
        "progress_pct",
        "factory_can_receive_date",
        "target_date_source",
    ]

    absent = [
        field
        for field in required_fields
        if field not in source
    ]
    if absent:
        raise AssertionError(
            f"Missing detail mappings: {absent}"
        )

    print(
        "SHIPMENT DETAILS PRO SMOKE TEST PASSED"
    )
    print(
        "Production, completion, remaining, "
        "capacity, date and status mappings exist."
    )


if __name__ == "__main__":
    main()
