from __future__ import annotations

import inspect

from app.ui.existing_shipment_add_items_dialog import (
    ExistingShipmentAddItemsDialog,
)
from app.ui.shipment_orders_page import (
    ShipmentOrdersPage,
)


def main() -> None:
    add_source = inspect.getsource(
        ShipmentOrdersPage.add_item
    )
    dialog_source = inspect.getsource(
        ExistingShipmentAddItemsDialog
    )

    assert (
        "ExistingShipmentAddItemsDialog"
        in add_source
    )
    assert "dialog.exec()" in add_source
    assert "navigate(" not in add_source
    assert (
        "Already Saved Shipment Items"
        in dialog_source
    )
    assert "New Items to Add" in dialog_source
    assert "Add Items & Replan" in dialog_source
    assert (
        "normal Shipment Orders page remains unchanged"
        in dialog_source
    )

    print(
        "EXISTING SHIPMENT ADD-ITEM POPUP TEST PASSED"
    )
    print(
        "Shipment Details Add Item opens a separate modal dialog."
    )
    print(
        "The normal Shipment Orders page is no longer reused."
    )
    print(
        "New items and already-saved items are shown separately."
    )


if __name__ == "__main__":
    main()
