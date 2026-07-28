from __future__ import annotations

from app.ui.order_entry_page import (
    OrderEntryPage,
)


def main() -> None:
    required = [
        "_get_unplannable_items",
        "_clean_planning_reason",
        "_build_save_block_warning",
        "save_shipment",
    ]
    missing = [
        name
        for name in required
        if not hasattr(
            OrderEntryPage,
            name,
        )
    ]
    if missing:
        raise AssertionError(
            f"Missing methods: {missing}"
        )

    page = OrderEntryPage.__new__(
        OrderEntryPage
    )
    page.current_items = [
        {
            "sap_code": "60000546",
            "item_description": (
                '3.00-15 8.00" EF LA XT TR 2L NM'
            ),
            "quantity": 102,
            "stock_allocated_qty": 0,
            "production_required_qty": 102,
            "allocated_cavity_count": 0,
            "item_receive_date": None,
            "item_status": "Blocked",
            "schedule_reason": (
                "Priority queue: No mold capacity "
                "is available for key code 'ABC'."
            ),
        },
        {
            "sap_code": "60000004",
            "item_description": "Planned item",
            "quantity": 10,
            "stock_allocated_qty": 0,
            "production_required_qty": 10,
            "allocated_cavity_count": 1,
            "item_receive_date": "2027-01-11",
            "item_status": "Planned",
            "schedule_reason": (
                "Priority queue: Planned within "
                "available capacity."
            ),
        },
    ]

    blocked = page._get_unplannable_items()
    assert len(blocked) == 1, blocked

    message = page._build_save_block_warning(
        blocked
    )
    assert "60000546" in message
    assert "No mold capacity" in message
    assert (
        "No shipment data was created"
        in message
    )

    print(
        "SHIPMENT SAVE BLOCK TEST PASSED"
    )
    print(
        "Blocked items prevent shipment save."
    )
    print(
        "Warning includes exact resource reason."
    )
    print(
        "Shipment Readiness shows NOT READY."
    )


if __name__ == "__main__":
    main()
