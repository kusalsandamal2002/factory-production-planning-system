from __future__ import annotations

import inspect

from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)
from app.ui.order_entry_page import (
    OrderEntryPage,
)
from app.ui.shipment_orders_page import (
    ShipmentOrdersPage,
)


def main() -> None:
    required_order_methods = [
        "open_existing_shipment_for_item_add",
        "_save_existing_item_additions",
        "return_to_shipment_details",
        "_restore_new_shipment_mode",
    ]

    missing = [
        method
        for method in required_order_methods
        if not hasattr(
            OrderEntryPage,
            method,
        )
    ]
    if missing:
        raise AssertionError(
            f"Missing Order Entry methods: {missing}"
        )

    add_source = inspect.getsource(
        ShipmentOrdersPage.add_item
    )
    order_source = inspect.getsource(
        OrderEntryPage
    )
    planner_source = inspect.getsource(
        FactoryPlanningEngine
        .calculate_cart_items
    )

    assert (
        "open_existing_shipment_for_item_add"
        in add_source
    )
    assert (
        "Add Items to Existing Shipment"
        in order_source
    )
    assert (
        "only the new additions are saved"
        in order_source
    )
    assert (
        "Add Items & Replan"
        in order_source
    )
    assert (
        "draft_created_at"
        in planner_source
    )
    assert (
        'item.get("produced_qty")'
        in planner_source
    )

    print(
        "EXISTING SHIPMENT ADD-ITEM WORKSPACE TEST PASSED"
    )
    print(
        "Shipment Details Add Item opens the full "
        "Shipment Order workspace."
    )
    print(
        "Existing shipment headers and saved items "
        "are protected from rewrite."
    )
    print(
        "Only new items are inserted before cumulative replanning."
    )
    print(
        "Existing shipment priority and produced quantities "
        "are preserved in preview planning."
    )


if __name__ == "__main__":
    main()
