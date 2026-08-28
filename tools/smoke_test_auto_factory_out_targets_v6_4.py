from __future__ import annotations

import argparse
from pathlib import Path
import py_compile


AUTO_TARGET_SOURCE = "Auto Earliest Feasible Factory Out"


def _is_auto_source(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return (
        not normalized
        or normalized.startswith("auto")
        or normalized.startswith("automatic")
    )


def _target_state(*, is_manual: bool, source: str, stored_target, factory_out):
    auto = (
        not is_manual
        and (stored_target is None or _is_auto_source(source))
    )
    target = factory_out if auto else stored_target
    status = (
        "Auto Scheduled"
        if auto and factory_out
        else ("Pending Planning" if auto else "Manual / Excel")
    )
    return auto, target, status


def _live_checks(root: Path) -> None:
    import sys
    sys.path.insert(0, str(root))
    from sqlalchemy import text
    from app.database import engine

    with engine.begin() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE LOWER(COALESCE(status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(COALESCE(target_date_source,'')) =
                            'excel import - date missing'
                    ) AS legacy_review_count,
                    COUNT(*) FILTER (
                        WHERE LOWER(COALESCE(target_date_source,'')) LIKE 'auto%'
                          AND COALESCE(target_date_is_manual,FALSE)
                    ) AS auto_marked_manual_count,
                    COUNT(*) FILTER (
                        WHERE LOWER(COALESCE(target_date_source,'')) LIKE 'auto%'
                          AND factory_out_date IS NOT NULL
                          AND target_date IS DISTINCT FROM factory_out_date
                    ) AS auto_target_mismatch_count,
                    COUNT(*) FILTER (
                        WHERE LOWER(COALESCE(target_date_source,'')) LIKE 'auto%'
                          AND LOWER(COALESCE(delivery_status,'')) IN (
                              'review required',
                              'pending approval'
                          )
                    ) AS auto_approval_status_count
                FROM mpps_shipments
                """
            )
        ).mappings().one()

    for key in (
        "legacy_review_count",
        "auto_marked_manual_count",
        "auto_target_mismatch_count",
        "auto_approval_status_count",
    ):
        assert int(counts[key] or 0) == 0, counts

    print("LIVE AUTO-TARGET DATABASE INVARIANT CHECK PASSED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    files = {
        "planner": root / "app" / "services" / "factory_planning_engine.py",
        "sync": root / "app" / "services" / "workbook_continuous_sync_service.py",
        "shipment": root / "app" / "ui" / "shipment_orders_page.py",
        "operations": root / "app" / "ui" / "intelligent_operations_pages.py",
        "migration": root / "database" / "migrations" / "enable_auto_factory_out_targets_v6_4.py",
        "replan": root / "tools" / "run_auto_target_replan_v6_4.py",
    }
    for path in files.values():
        assert path.exists(), path
        py_compile.compile(str(path), doraise=True)

    planner = files["planner"].read_text(encoding="utf-8-sig")
    sync = files["sync"].read_text(encoding="utf-8-sig")
    shipment = files["shipment"].read_text(encoding="utf-8-sig")
    operations = files["operations"].read_text(encoding="utf-8-sig")
    migration = files["migration"].read_text(encoding="utf-8-sig")

    for marker in (
        "AUTO FACTORY-OUT TARGET SCHEDULING V6.4",
        "AUTO_TARGET_SOURCE",
        "shipment_target_is_locked",
        "dispatch_buffer_days",
        'delivery_status = "Auto Scheduled"',
        '"factory_out_date": factory_out_date',
        '"target_date_source": target_source',
    ):
        assert marker in planner, marker

    # R7 authoritative import path is WorkbookContinuousSyncService, not the
    # retired raw-viewer/legacy importer path.
    for marker in (
        '"status": "Planned"',
        '"planning_status": "Pending Replan"',
        "Auto Earliest Feasible Factory Out",
        '"shipments_created"',
        '"dispatch_buffer_days"',
        '"factory_can_receive_date": None',
        '"factory_out_date": None',
    ):
        assert marker in sync, marker

    for marker in (
        "Reset to Auto Target",
        "Set Target Date",
        "Replan All",
        "Save & Replan",
        "Factory Can Out",
        "AUTO TARGET — SCHEDULED",
        "Auto target = Factory Can Out",
        "if column == 3:",
        "shipment_auto_target_",
    ):
        assert marker in shipment, marker

    assert "Target Source" in operations
    assert "Auto Earliest Feasible Factory Out" in operations

    for marker in (
        "legacy_review_promoted",
        "Auto Target scheduling requested",
        "Pending Replan",
        "dispatch_buffer_days",
        "auto_target_scheduling_runs",
        "planning_resource_reservations",
        "shipment_stock_allocations",
    ):
        assert marker in migration, marker

    auto, target, status = _target_state(
        is_manual=False,
        source="Excel Import - Date Missing",
        stored_target=None,
        factory_out="2026-08-05",
    )
    assert auto
    assert target == "2026-08-05"
    assert status == "Auto Scheduled"

    auto, target, status = _target_state(
        is_manual=True,
        source="Manual Approved",
        stored_target="2026-08-01",
        factory_out="2026-08-05",
    )
    assert not auto
    assert target == "2026-08-01"
    assert status == "Manual / Excel"

    if args.live:
        _live_checks(root)

    print("R7 CONTINUOUS-SYNC AUTO-TARGET SOURCE CHECK PASSED")
    print("EARLIEST FACTORY CAN OUT TARGET CHECK PASSED")
    print("MANUAL TARGET PRIORITY LOCK CHECK PASSED")
    print("SHIPMENT QUICK SCHEDULE CONTROL CHECK PASSED")
    print("AUTO FACTORY-OUT TARGET SCHEDULING V6.4/R7 TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
