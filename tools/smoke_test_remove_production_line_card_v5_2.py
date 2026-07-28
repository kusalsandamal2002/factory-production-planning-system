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
        "Three operational resource cards fill the full row.",
        "column * 4",
        "column * 3",
        "for grid_column in range(12)",
        "Lines & Cavities",
        "compatible_line_total",
        "available_line_total",
        "assigned_line_count",
    ]

    forbidden = [
        '"line",\n                "Production Line Capacity"',
        'resource_values["line"]["total"]',
        'resource_values["line"]["available"]',
        'resource_values["line"]["assigned"]',
    ]

    missing = [
        marker
        for marker in required
        if marker not in source
    ]
    present_forbidden = [
        marker
        for marker in forbidden
        if marker in source
    ]

    if missing:
        raise AssertionError(
            "Missing V5.2 features: "
            + ", ".join(missing)
        )

    if present_forbidden:
        raise AssertionError(
            "Production Line card code still exists: "
            + ", ".join(present_forbidden)
        )

    print(
        "PRODUCTION LINE CARD REMOVAL "
        "RUNTIME SOURCE TEST PASSED"
    )


if __name__ == "__main__":
    main()
