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
        "Mold Capacity",
        "Casing Capacity",
        "Cavity Capacity",
        "Production Line Capacity",
        "Total Compatible",
        "Available Free",
        "Assigned This Item",
        "mold_assigned_item",
        "casing_assigned_item",
        "cavity_assigned_item",
        "available_line_total",
        "assigned_line_count",
        "Daily Output Capacity",
        "Resource position —",
    ]

    missing = [
        value
        for value in required
        if value not in source
    ]

    if missing:
        raise AssertionError(
            "Missing V4 features: "
            + ", ".join(missing)
        )

    assert (
        source.index("Mold Capacity")
        < source.index(
            "Maximum Physical Capacity"
        )
    )
    assert (
        "mold_now"
        in source
        and "mold_assigned_item"
        in source
    )
    assert (
        "casing_now"
        in source
        and "casing_assigned_item"
        in source
    )
    assert (
        "cavity_now"
        in source
        and "cavity_assigned_item"
        in source
    )

    print(
        "ITEM RESOURCE CAPACITY CARDS "
        "RUNTIME SOURCE TEST PASSED"
    )


if __name__ == "__main__":
    main()
