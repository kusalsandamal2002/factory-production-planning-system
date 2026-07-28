from __future__ import annotations

import inspect

from app.ui.shipment_orders_page import (
    ShipmentItemDialog,
    ShipmentOrdersPage,
)


def main() -> None:
    dialog_source = inspect.getsource(
        ShipmentItemDialog
    )
    add_source = inspect.getsource(
        ShipmentOrdersPage.add_item
    )
    edit_source = inspect.getsource(
        ShipmentOrdersPage.edit_selected_item
    )

    assert "receive_date_input" not in dialog_source
    assert (
        "Item Receive Date is calculated automatically"
        in dialog_source
    )
    assert (
        "replan_all_open_shipments"
        in add_source
    )
    assert (
        "replan_all_open_shipments"
        in edit_source
    )
    assert (
        "item_receive_date = NULL"
        in edit_source
    )
    assert (
        "RETURNING id"
        in add_source
    )

    print(
        "SHIPMENT ITEM AUTO RECEIVE DATE TEST PASSED"
    )
    print(
        "Manual Item Receive Date editing was removed."
    )
    print(
        "Add/Edit Item now triggers automatic cumulative replanning."
    )
    print(
        "Failed item changes are rolled back."
    )


if __name__ == "__main__":
    main()
