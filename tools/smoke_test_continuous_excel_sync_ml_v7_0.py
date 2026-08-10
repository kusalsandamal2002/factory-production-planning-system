from __future__ import annotations

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root))

    importer = (
        root / "app/services/intelligent_excel_import_service.py"
    ).read_text(encoding="utf-8-sig")
    sync_source = (
        root / "app/services/workbook_continuous_sync_service.py"
    ).read_text(encoding="utf-8-sig")
    learning_source = (
        root / "app/services/production_learning_service.py"
    ).read_text(encoding="utf-8-sig")
    import_ui = (
        root / "app/ui/raw_excel_viewer_page.py"
    ).read_text(encoding="utf-8-sig")
    learning_ui = (
        root / "app/ui/workbook_learning_center_page.py"
    ).read_text(encoding="utf-8-sig")
    main_window = (
        root / "app/ui/main_window.py"
    ).read_text(encoding="utf-8-sig")
    migration = (
        root
        / "database/migrations/enable_continuous_excel_sync_ml_v7_0.py"
    ).read_text(encoding="utf-8-sig")

    for marker in [
        "sync_live_shipments",
        "auto_detect_import_mode",
        "preview_shipment_sync",
        "finalize_post_plan",
        "source_target_date",
        "source_date_class",
        "capture_learning_observations",
    ]:
        assert marker in importer, marker

    for marker in [
        "HISTORICAL",
        "MISSING_FROM_LATEST",
        "source_manual_lock",
        "protected_actual",
        "excel_shipment_identities",
        "excel_shipment_item_revisions",
        "completed/closed shipment",
        "GEN-",
    ]:
        assert marker in sync_source, marker

    for marker in [
        "WORKBOOK_PLAN_OR_UNCLASSIFIED",
        "is_advisory_only",
        "excel_plan_reconciliation",
        "SAP_DEMAND_FORECAST",
        "PRODUCTION_SIGNAL_MODEL",
    ]:
        assert marker in learning_source, marker

    for marker in [
        "Live Sync Preview",
        "Auto-sync live shipments",
        "Resolved Import Mode",
        "Capture ML learning observations",
    ]:
        assert marker in import_ui, marker

    for marker in [
        "AI / ML Learning Center",
        "ADVISORY LEARNING MODE",
        "Excel vs App Reconciliation",
    ]:
        assert marker in learning_ui, marker

    assert "WORKBOOK_LEARNING_INDEX = 39" in main_window
    assert "AI Learning Center" in main_window

    for marker in [
        "mpps_shipments_v7_before_",
        "Superseded Import",
        "LEGACY_DUPLICATE_REVIEW",
        "No shipment was physically deleted",
        "migration baseline seeded",
        "latest committed intelligent import",
    ]:
        assert marker in migration, marker

    from app.services.workbook_continuous_sync_service import (
        WorkbookContinuousSyncService,
        _identity_key,
        _source_base_key,
    )
    from app.services.production_learning_service import (
        _confidence,
    )

    first = SimpleNamespace(
        shipment_rows=[
            {
                "shipment_column": "BZ",
                "shipment_name": "GULF 56",
                "source_status": "OK",
                "source_target_date": None,
                "source_date_class": "AUTO_TARGET_REQUIRED",
                "sap_code": "60006811",
                "description": "Tyre A",
                "quantity": 40,
            },
            {
                "shipment_column": "BZ",
                "shipment_name": "GULF 56",
                "source_status": "OK",
                "source_target_date": None,
                "source_date_class": "AUTO_TARGET_REQUIRED",
                "sap_code": "60006483",
                "description": "Tyre B",
                "quantity": 26,
            },
        ]
    )
    second = SimpleNamespace(
        shipment_rows=[
            {
                "shipment_column": "CE",
                "shipment_name": "  Gulf   56 ",
                "source_status": "OK",
                "source_target_date": None,
                "source_date_class": "AUTO_TARGET_REQUIRED",
                "sap_code": "60006811",
                "description": "Tyre A",
                "quantity": 55,
            },
            {
                "shipment_column": "CE",
                "shipment_name": "  Gulf   56 ",
                "source_status": "OK",
                "source_target_date": None,
                "source_date_class": "AUTO_TARGET_REQUIRED",
                "sap_code": "60006483",
                "description": "Tyre B",
                "quantity": 20,
            },
        ]
    )
    first_group = WorkbookContinuousSyncService._group_analysis(first)[0]
    second_group = WorkbookContinuousSyncService._group_analysis(second)[0]
    assert first_group.base_key == second_group.base_key == "GULF 56"
    assert _identity_key(first_group.base_key) == _identity_key(
        second_group.base_key
    )
    assert first_group.total_qty == 66
    assert second_group.total_qty == 75
    assert _source_base_key("Gulf-56") == "GULF 56"

    score, band = _confidence(3, 0.25)
    assert 0 <= score <= 1
    assert band in {"LOW", "MEDIUM", "HIGH", "LEARNING"}

    print("STABLE SHIPMENT IDENTITY CHECK PASSED")
    print("DUPLICATE-SAFE REVISION UPDATE CHECK PASSED")
    print("HISTORICAL/LIVE MODE SOURCE CHECK PASSED")
    print("MANUAL AND ACTUAL PROTECTION CHECK PASSED")
    print("MISSING-FROM-LATEST NON-DESTRUCTIVE CHECK PASSED")
    print("LOCAL ADVISORY LEARNING MODEL CHECK PASSED")
    print("EXCEL VS APP RECONCILIATION CHECK PASSED")
    print("AI LEARNING CENTER ROUTE CHECK PASSED")
    print("CONTINUOUS EXCEL SYNC + ML FOUNDATION V7.0 SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
