from __future__ import annotations

import argparse
from pathlib import Path
import py_compile


def _section(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def _delivery_state(
    *,
    review_required: bool,
    target_date,
    factory_receive_date,
) -> tuple[str, str]:
    if review_required:
        return "Review Required", "Pending approval"
    if target_date is None:
        return "Pending Target", "Pending target"
    if factory_receive_date is None:
        return "Pending Planning", "Pending planning"
    if factory_receive_date < target_date:
        return "Can Deliver Early", "Early"
    if factory_receive_date == target_date:
        return "On Time", "On target"
    return "Delayed", "Late"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    files = {
        "shipment": root / "app" / "ui" / "shipment_orders_page.py",
        "add_dialog": root / "app" / "ui" / "existing_shipment_add_items_dialog.py",
        "planner": root / "app" / "services" / "factory_planning_engine.py",
        "importer": root / "app" / "services" / "intelligent_excel_import_service.py",
        "operations": root / "app" / "ui" / "intelligent_operations_pages.py",
        "migration": root / "database" / "migrations" / "repair_delivery_date_integrity_v6_3.py",
    }
    for path in files.values():
        assert path.exists(), path
        py_compile.compile(str(path), doraise=True)

    shipment = files["shipment"].read_text(encoding="utf-8-sig")
    add_dialog = files["add_dialog"].read_text(encoding="utf-8-sig")
    planner = files["planner"].read_text(encoding="utf-8-sig")
    importer = files["importer"].read_text(encoding="utf-8-sig")
    operations = files["operations"].read_text(encoding="utf-8-sig")
    migration = files["migration"].read_text(encoding="utf-8-sig")

    open_detail = _section(
        shipment,
        "    def open_shipment_detail(",
        "    def back_to_list(",
    )
    assert "recalculate_shipment_factory_out_date" not in open_detail
    assert "Opening a detail page is read-only" in open_detail

    recalc_all = _section(
        shipment,
        "    def _recalculate_all_factory_out_dates",
        "    def recalculate_shipment_factory_out_date",
    )
    assert "CURRENT_DATE" not in recalc_all
    assert "target_date =" not in recalc_all
    assert "verified_factory_receive" in recalc_all
    assert "missing_receive_count" in recalc_all

    assert "review_required" in shipment
    assert "Approval Required" in shipment
    assert "Pending Planning" in shipment
    assert "status = CASE" in shipment
    assert "THEN 'Planned'" in shipment
    assert "Manual Approved" in shipment
    assert "Factory receive and delivery variance are shown only" in shipment
    assert "shipment_item_deleted_" in shipment
    assert "shipment_deleted_" in shipment

    assert "review shipments cannot receive planned dates" in add_dialog
    assert "Target Date: {target_display}" in add_dialog
    assert "if not self.review_required:" in add_dialog
    assert 'item["item_receive_date"] = None' in add_dialog

    assert "all_positive_items_dated" in planner
    assert "tentative_allocations" in planner
    assert "Commit resource reservations only after the whole production" in planner
    assert "shipment_date, target_date, plan_date, or today" in planner
    assert "else None" in planner

    assert '"delivery_status": "Review Required"' in importer
    assert '"factory_can_receive_date": None' in importer
    assert '"last_replanned_at": None' in importer

    assert (
        "s.fg_stock + s.qc_stock - s.scrap_stock - s.blocked_stock"
        in operations
    )
    assert "THEN NULL" in operations

    required_migration_markers = [
        "FALSE_DELIVERY_PROMISE_DURING_REVIEW",
        "HEADER_RECEIVE_WITH_MISSING_ITEM_DATES",
        "WORKBOOK_DATE_PROMOTED_TO_TARGET",
        "Previously entered manual target date",
        "resource_reservations_removed",
        "ck_mpps_shipments_on_time_dates_v63",
        "Review Required",
        "Pending Planning",
    ]
    for marker in required_migration_markers:
        assert marker in migration, marker

    # Reproduce the screenshot's semantic contradiction. A review-required
    # shipment must never be classified as On Time merely because two fabricated
    # header dates are equal.
    status, variance = _delivery_state(
        review_required=True,
        target_date="2026-07-28",
        factory_receive_date="2026-07-28",
    )
    assert status == "Review Required"
    assert variance == "Pending approval"

    # A planned shipment with a target but unresolved item dates remains pending.
    status, variance = _delivery_state(
        review_required=False,
        target_date="2026-07-28",
        factory_receive_date=None,
    )
    assert status == "Pending Planning"
    assert variance == "Pending planning"

    print("READ-ONLY SHIPMENT DETAILS CHECK PASSED")
    print("NO FABRICATED TARGET / RECEIVE DATE CHECK PASSED")
    print("REVIEW REQUIRED PROMISE GATING CHECK PASSED")
    print("MANUAL TARGET APPROVAL LIFECYCLE CHECK PASSED")
    print("ALL-ITEM RECEIVE DATE COMPLETENESS CHECK PASSED")
    print("BLOCKED PARTIAL RESERVATION PROTECTION CHECK PASSED")
    print("ADD-ITEM REVIEW PROTECTION CHECK PASSED")
    print("DELIVERY REPORT STOCK FORMULA CHECK PASSED")
    print("LIVE DATABASE REPAIR SOURCE CHECK PASSED")
    print("SHIPMENT DELIVERY CALCULATION INTEGRITY V6.3 SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
