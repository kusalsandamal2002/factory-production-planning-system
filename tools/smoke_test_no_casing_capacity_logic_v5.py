from __future__ import annotations

import inspect

from app.ui.item_resource_control_center_page import (
    ItemResourceControlCenterPage,
    _casing_required,
)


def main() -> None:
    no_casing_values = [
        "",
        "-",
        "No Casing",
        "NO CASING REQUIRED",
        "Casing Not Required",
        "Not Required",
        "Without Casing",
        "Does not require casing",
        "N/A",
    ]

    for value in no_casing_values:
        assert not _casing_required(value), value

    required_casing_values = [
        "B7",
        "B5 Special 03",
        "Casing Type A",
    ]

    for value in required_casing_values:
        assert _casing_required(value), value

    source = inspect.getsource(
        ItemResourceControlCenterPage
    )

    required_markers = [
        "NO-CASING PLANNING INVARIANT",
        "Casing Requirement",
        "Casing Required",
        "Capacity Rule",
        "Planning Impact",
        "NO CAPACITY LIMIT",
        "No casing is required for this item.",
        "Casing — Not Required",
    ]

    missing = [
        marker
        for marker in required_markers
        if marker not in source
    ]
    if missing:
        raise AssertionError(
            "Missing no-casing features: "
            + ", ".join(missing)
        )

    assert (
        'if d["casing_required"]:\n'
        '            candidates["CASING"]'
        in source
    )
    assert (
        'if d["casing_required"]:\n'
        '            physical_candidates["CASING"]'
        in source
    )

    print(
        "NO-CASING CAPACITY RUNTIME SOURCE TEST PASSED"
    )


if __name__ == "__main__":
    main()
