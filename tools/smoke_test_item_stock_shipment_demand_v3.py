from __future__ import annotations

import inspect

from app.ui.item_resource_control_center_page import (
    ItemResourceControlCenterPage,
)


def main() -> None:
    source = inspect.getsource(
        ItemResourceControlCenterPage
    )

    required = [
        "CURRENT STOCK POSITION",
        "CURRENT ITEM PRODUCTION & DEMAND STATUS",
        "Shipment-wise Demand and Main-Rule Production Plan",
        "Current Physical Stock",
        "Unallocated Stock",
        "Total Shipment Quantity",
        "Stock Allocated",
        "Production Required",
        "Fulfilment Progress",
        "physical_available_stock",
        "stock_allocated + completed",
        "earliest Target Date receives priority first",
        "Planned Start",
        "Planned Finish",
        "Plan Status",
    ]

    missing = [
        value
        for value in required
        if value not in source
    ]

    if missing:
        raise AssertionError(
            "Missing features: "
            + ", ".join(missing)
        )

    assert (
        source.index(
            "Current Physical Stock"
        )
        < source.index(
            "Shipment-wise Demand and Main-Rule Production Plan"
        )
    )

    print(
        "ITEM STOCK & SHIPMENT DEMAND "
        "RUNTIME SOURCE TEST PASSED"
    )


if __name__ == "__main__":
    main()
