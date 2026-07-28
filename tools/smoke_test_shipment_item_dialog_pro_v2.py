from __future__ import annotations

import inspect

from app.ui.shipment_orders_page import (
    ShipmentItemDialog,
)


def main() -> None:
    source = inspect.getsource(
        ShipmentItemDialog
    )

    required = [
        "Approved Tyre Item",
        "Order Requirement",
        "Automatic Planning Controls",
        "Add Item & Replan",
        "Save Changes & Replan",
        "_validate_and_accept",
        "PLANNER CONTROLLED",
        "Typed free-text items cannot be added",
    ]

    missing = [
        value
        for value in required
        if value not in source
    ]

    if missing:
        raise AssertionError(
            f"Missing professional dialog features: {missing}"
        )

    forbidden = [
        "receive_date_input",
        "self.status_input = QComboBox",
    ]

    present = [
        value
        for value in forbidden
        if value in source
    ]

    if present:
        raise AssertionError(
            f"Manual planner fields still exist: {present}"
        )

    print(
        "SHIPMENT ITEM DIALOG PRO V2 TEST PASSED"
    )
    print(
        "Approved-item selection, quantity, planning "
        "controls and professional layout are present."
    )
    print(
        "Manual receive-date and editable-status controls "
        "are not present."
    )


if __name__ == "__main__":
    main()
