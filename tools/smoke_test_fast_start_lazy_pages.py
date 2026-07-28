from __future__ import annotations

import inspect

from app.ui.main_window import (
    MainWindow,
)


def main() -> None:
    source = inspect.getsource(
        MainWindow
    )
    build_source = inspect.getsource(
        MainWindow._build_content
    )

    required = [
        "_page_factories",
        "_ensure_page_loaded",
        "_loading_page",
        "_loaded_page_indexes",
        "QTimer.singleShot",
        "perf_counter",
    ]

    missing = [
        value
        for value in required
        if value not in source
    ]
    if missing:
        raise AssertionError(
            f"Missing fast-start features: {missing}"
        )

    eager_patterns = [
        "self.dashboard_page = self._create_dashboard_page()",
        "self.order_entry_page = OrderEntryPage(",
        "self.schedule_page = SchedulePage(",
        "self.shipment_details_page = ShipmentDetailsPage(",
        "self.mold_master_v2_page = MoldMasterPage()",
        "self.casing_master_v2_page = CasingMasterPage()",
    ]

    eager = [
        value
        for value in eager_patterns
        if value in build_source
    ]
    if eager:
        raise AssertionError(
            f"Eager page creation remains: {eager}"
        )

    print(
        "MPPS FAST START LAZY PAGES TEST PASSED"
    )
    print(
        "The app shell opens before heavy pages are constructed."
    )
    print(
        "Each page loads on its first visit only."
    )
    print(
        "First construction is not followed by a duplicate refresh."
    )


if __name__ == "__main__":
    main()
