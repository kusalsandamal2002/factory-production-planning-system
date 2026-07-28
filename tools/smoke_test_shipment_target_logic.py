from __future__ import annotations

from datetime import date

from app.ui.order_entry_page import OrderEntryPage


def main() -> None:
    required_methods = [
        "_resolved_target_date",
        "_delivery_promise",
        "_apply_promise_style",
        "save_shipment",
        "clear_form",
        "load_shipment",
    ]

    missing = [
        name
        for name in required_methods
        if not hasattr(OrderEntryPage, name)
    ]

    if missing:
        raise AssertionError(
            f"Missing OrderEntryPage methods: {missing}"
        )

    equal_result = OrderEntryPage._delivery_promise(
        None,
        date(2026, 7, 10),
        date(2026, 7, 10),
    )
    early_result = OrderEntryPage._delivery_promise(
        None,
        date(2026, 7, 10),
        date(2026, 7, 5),
    )
    late_result = OrderEntryPage._delivery_promise(
        None,
        date(2026, 7, 5),
        date(2026, 7, 10),
    )
    pending_result = OrderEntryPage._delivery_promise(
        None,
        None,
        date(2026, 7, 10),
    )

    assert equal_result[0] == "on_time", equal_result
    assert equal_result[1] == (
        "CAN DELIVER ON TARGET"
    ), equal_result

    assert early_result[0] == "early", early_result
    assert early_result[1] == (
        "CAN DELIVER +5 DAYS EARLY"
    ), early_result

    assert late_result[0] == "late", late_result
    assert late_result[1] == (
        "CANNOT DELIVER -5 DAYS LATE"
    ), late_result

    assert pending_result[0] == "pending", pending_result

    print(
        "SHIPMENT ENTRY TARGET-DATE TEST PASSED"
    )
    print(
        "Automatic target: Factory Can Receive Date"
    )
    print(
        "Manual target: optional manager-selected date"
    )
    print(
        "Delivery promise: early, on target, late, pending"
    )


if __name__ == "__main__":
    main()
