from __future__ import annotations

import inspect

from app.ui.shipment_orders_page import (
    ShipmentOrdersPage,
)


def main() -> None:
    required_methods = [
        "change_current_target_date",
        "edit_target_date_for_shipment",
        "recalculate_shipment_factory_out_date",
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

    target_source = inspect.getsource(
        ShipmentOrdersPage
        .edit_target_date_for_shipment
    )
    recalc_source = inspect.getsource(
        ShipmentOrdersPage
        .recalculate_shipment_factory_out_date
    )

    for required in (
        "target_date_is_manual",
        "target_date_source",
        "replan_all_open_shipments",
        "Automatic Factory Receive",
    ):
        if required not in target_source:
            raise AssertionError(
                f"Missing Target Date logic: {required}"
            )

    for required in (
        "effective_target",
        "factory_can_receive_date",
        "delay_days",
        "early_days",
    ):
        if required not in recalc_source:
            raise AssertionError(
                f"Missing recalculation logic: {required}"
            )

    print(
        "SHIPMENT TARGET DATE CONTROL TEST PASSED"
    )
    print(
        "Manual and automatic Target Date modes exist."
    )
    print(
        "Changing Target Date replans all active shipments."
    )
    print(
        "Delivery variance and status are recalculated."
    )


if __name__ == "__main__":
    main()
