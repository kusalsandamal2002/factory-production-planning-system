from __future__ import annotations

from PySide6.QtWidgets import QApplication
from sqlalchemy import text

from app.database import engine
from app.ui.item_resource_control_center_page import (
    ItemResourceControlCenterPage,
)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    page = ItemResourceControlCenterPage()

    with engine.connect() as connection:
        event_table = connection.execute(
            text(
                """
                SELECT to_regclass(
                    'public.item_operational_events'
                )
                """
            )
        ).scalar_one()

        sample_sap = connection.execute(
            text(
                """
                SELECT sap_code
                FROM smds
                WHERE TRIM(COALESCE(sap_code, '')) <> ''
                ORDER BY
                    CASE
                        WHEN planning_manager_approval_status = 'Approved'
                        THEN 0
                        ELSE 1
                    END,
                    id
                LIMIT 1
                """
            )
        ).scalar()

    assert event_table is not None
    assert hasattr(page, "lifecycle_status")
    assert hasattr(page, "lifecycle_shipment_table")
    assert hasattr(page, "current_production_table")
    assert hasattr(page, "event_table")
    assert hasattr(page, "_place_hold")
    assert hasattr(page, "_release_hold")

    if sample_sap:
        page.sap_code = str(sample_sap)
        page._load_data()
        page._calculate_capacity()

        assert "physical_capacity" in page.data
        assert "committed_capacity" in page.data
        assert "daily_max" in page.data
        assert "status" in page.lifecycle
        assert "shipment_schedules" in page.lifecycle

        print(
            "Sample SAP:",
            sample_sap,
        )
        print(
            "Lifecycle status:",
            page.lifecycle.get("status"),
        )
        print(
            "Physical / committed / additional free:",
            page.data.get("physical_capacity"),
            page.data.get("committed_capacity"),
            page.data.get("simultaneous"),
        )

    page.close()
    app.quit()

    print(
        "ITEM LIFECYCLE CONTROL CENTER RUNTIME TEST PASSED"
    )


if __name__ == "__main__":
    main()
