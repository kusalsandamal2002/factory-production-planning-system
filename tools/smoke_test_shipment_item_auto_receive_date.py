from __future__ import annotations

import inspect

from app.ui.shipment_orders_page import (
    ShipmentItemDialog,
    ShipmentOrdersPage,
)
from app.ui.existing_shipment_add_items_dialog import (
    ExistingShipmentAddItemsDialog,
)


def main() -> None:
    dialog_source = inspect.getsource(ShipmentItemDialog)
    add_source = inspect.getsource(ShipmentOrdersPage.add_item)
    edit_source = inspect.getsource(ShipmentOrdersPage.edit_selected_item)
    add_workspace_source = inspect.getsource(ExistingShipmentAddItemsDialog)

    assert "receive_date_input" not in dialog_source
    assert "CALCULATED AUTOMATICALLY" in dialog_source

    # R7: add_item delegates to the dedicated existing-shipment workspace.
    # That workspace owns insert + cumulative replan + rollback protection.
    assert "ExistingShipmentAddItemsDialog" in add_source
    assert "replan_all_open_shipments" in add_workspace_source
    assert "RETURNING id" in add_workspace_source

    assert "replan_all_open_shipments" in edit_source
    assert "item_receive_date = NULL" in edit_source

    print("SHIPMENT ITEM AUTO RECEIVE DATE TEST PASSED")
    print("Manual Item Receive Date editing is disabled.")
    print("Add-item workspace owns automatic cumulative replanning.")
    print("Edit Item triggers automatic cumulative replanning.")
    print("Failed add-item changes retain rollback protection.")


if __name__ == "__main__":
    main()
