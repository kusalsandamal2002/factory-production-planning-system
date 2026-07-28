from __future__ import annotations

import inspect

from app.ui.item_resource_control_center_page import (
    ItemResourceControlCenterPage,
    _casing_required,
)


def main() -> None:
    no_casing_values = [
        None,
        "",
        "-",
        "N/A",
        "n/a",
        "NA",
        "None",
        "No",
        "No Casing",
        "NO CASING REQUIRED",
        "Casing Not Required",
        "Casing is not required",
        "Not Required",
        "Not Applicable",
        "Without Casing",
        "Without Any Casing",
        "Does not require casing",
    ]

    for value in no_casing_values:
        assert not _casing_required(value), (
            f"Expected no-casing value: {value!r}"
        )

    required_casing_values = [
        "B7",
        "B5 Special 03",
        "Casing Type A",
    ]

    for value in required_casing_values:
        assert _casing_required(value), (
            f"Expected required-casing value: {value!r}"
        )

    source = inspect.getsource(
        ItemResourceControlCenterPage
    )

    required_markers = [
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
            "Missing no-casing UI features: "
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
        "NO-CASING V5.1 RUNTIME TEST PASSED"
    )


if __name__ == "__main__":
    main()
