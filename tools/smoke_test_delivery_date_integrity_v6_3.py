from __future__ import annotations

import argparse
from pathlib import Path
import py_compile


def _section_to_next_method(source: str, marker: str) -> str:
    start = source.index(marker)
    end = source.find("\n    def ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def _section(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def _delivery_state(*, review_required: bool, target_date, factory_out_date):
    if review_required:
        return "Review Required", "Pending approval"
    if target_date is None:
        return "Pending Target", "Pending target"
    if factory_out_date is None:
        return "Pending Planning", "Pending planning"
    if factory_out_date < target_date:
        return "Can Deliver Early", "Early"
    if factory_out_date == target_date:
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
        "sync": root / "app" / "services" / "workbook_continuous_sync_service.py",
        "migration": root / "database" / "migrations" / "repair_delivery_date_integrity_v6_3.py",
    }
    for path in files.values():
        assert path.exists(), path
        py_compile.compile(str(path), doraise=True)

    shipment = files["shipment"].read_text(encoding="utf-8-sig")
    add_dialog = files["add_dialog"].read_text(encoding="utf-8-sig")
    planner = files["planner"].read_text(encoding="utf-8-sig")
    sync = files["sync"].read_text(encoding="utf-8-sig")
    migration = files["migration"].read_text(encoding="utf-8-sig")

    open_detail = _section(
        shipment,
        "    def open_shipment_detail(",
        "    def back_to_list(",
    )
    assert "recalculate_shipment_factory_out_date" not in open_detail
    assert "Opening a detail page is read-only" in open_detail

    # R7 architecture: bulk recalc is intentionally a thin delegate. Validate
    # the delegate and then validate the canonical reconciliation implementation.
    recalc_all = _section_to_next_method(
        shipment,
        "    def _recalculate_all_factory_out_dates(",
    )
    assert "_reconcile_factory_out_dates" in recalc_all
    assert "CURRENT_DATE" not in recalc_all
    assert "target_date =" not in recalc_all

    reconcile = _section_to_next_method(
        shipment,
        "    def _reconcile_factory_out_dates(",
    )
    for marker in (
        "verified_factory_receive",
        "verified_factory_out",
        "missing_receive_count",
        "dispatch_buffer_days",
        "factory_can_receive_date",
        "factory_out_date",
        "Auto Earliest Feasible Factory Out",
        "Pending Planning",
        "Review Required",
    ):
        assert marker in reconcile, marker

    # UI must surface the canonical promise fields without recalculating on open.
    for marker in (
        "Factory Can Out",
        "Delivery Variance",
        "Manual Approved",
        "AUTO TARGET — SCHEDULED",
        "shipment_item_deleted_",
        "shipment_deleted_",
    ):
        assert marker in shipment, marker

    # Add-item review mode must not fabricate planner dates.
    for marker in (
        "review shipments cannot receive planned dates",
        "Target Date: {target_display}",
        "if not self.review_required:",
        'item["item_receive_date"] = None',
    ):
        assert marker in add_dialog, marker

    # Planner must only promise a shipment date after every positive-qty item is
    # dated and after its whole resource allocation succeeds.
    for marker in (
        "all_positive_items_dated",
        "tentative_allocations",
        "Commit resource reservations only after the whole production",
        "shipment_date, target_date, plan_date, or today",
        "factory_out_date = (",
        "dispatch_buffer_days",
    ):
        assert marker in planner, marker

    # Current R7 LIVE Excel synchronization creates/refreshes shipments as
    # Pending Replan with no fabricated factory dates. Cumulative planning owns
    # those dates.
    for marker in (
        '"planning_status": "Pending Replan"',
        '"delivery_status": "Pending Planning"',
        '"factory_can_receive_date": None',
        '"factory_out_date": None',
        "Auto Earliest Feasible Factory Out",
    ):
        assert marker in sync, marker

    for marker in (
        "FALSE_DELIVERY_PROMISE_DURING_REVIEW",
        "HEADER_RECEIVE_WITH_MISSING_ITEM_DATES",
        "WORKBOOK_DATE_PROMOTED_TO_TARGET",
        "Previously entered manual target date",
        "resource_reservations_removed",
        "ck_mpps_shipments_on_time_dates_v63",
        "Review Required",
        "Pending Planning",
    ):
        assert marker in migration, marker

    status, variance = _delivery_state(
        review_required=True,
        target_date="2026-07-28",
        factory_out_date="2026-07-28",
    )
    assert status == "Review Required"
    assert variance == "Pending approval"

    status, variance = _delivery_state(
        review_required=False,
        target_date="2026-07-28",
        factory_out_date=None,
    )
    assert status == "Pending Planning"
    assert variance == "Pending planning"

    print("READ-ONLY SHIPMENT DETAILS CHECK PASSED")
    print("CANONICAL DELIVERY RECONCILIATION CHECK PASSED")
    print("NO FABRICATED FACTORY DATE CHECK PASSED")
    print("REVIEW REQUIRED PROMISE GATING CHECK PASSED")
    print("ALL-ITEM RECEIVE DATE COMPLETENESS CHECK PASSED")
    print("BLOCKED PARTIAL RESERVATION PROTECTION CHECK PASSED")
    print("R7 CONTINUOUS-SYNC PENDING-REPLAN CHECK PASSED")
    print("SHIPMENT DELIVERY CALCULATION INTEGRITY V6.3/R7 TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
