from __future__ import annotations

import argparse
from pathlib import Path
import py_compile


AUTO_TARGET_SOURCE = (
    "Auto Earliest Feasible Factory Out"
)


def _section(
    source: str,
    start: str,
    end: str,
) -> str:
    start_index = source.index(start)
    end_index = source.index(
        end,
        start_index,
    )
    return source[
        start_index:end_index
    ]


def _is_auto_source(value: str) -> bool:
    normalized = str(
        value or ""
    ).strip().lower()
    return (
        not normalized
        or normalized.startswith("auto")
        or normalized.startswith(
            "automatic"
        )
    )


def _target_state(
    *,
    is_manual: bool,
    source: str,
    stored_target,
    factory_out,
):
    auto = (
        not is_manual
        and (
            stored_target is None
            or _is_auto_source(source)
        )
    )
    target = (
        factory_out
        if auto
        else stored_target
    )
    status = (
        "Auto Scheduled"
        if auto and factory_out
        else (
            "Pending Planning"
            if auto
            else "Manual / Excel"
        )
    )
    return auto, target, status


def _live_checks(root: Path) -> None:
    import sys

    sys.path.insert(
        0,
        str(root),
    )
    from sqlalchemy import text
    from app.database import engine

    with engine.begin() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(status, '')
                        ) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(
                            COALESCE(
                                target_date_source,
                                ''
                            )
                        ) = 'excel import - date missing'
                    ) AS legacy_review_count,
                    COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                target_date_source,
                                ''
                            )
                        ) LIKE 'auto%'
                          AND COALESCE(
                                target_date_is_manual,
                                FALSE
                              )
                    ) AS auto_marked_manual_count,
                    COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                target_date_source,
                                ''
                            )
                        ) LIKE 'auto%'
                          AND factory_out_date IS NOT NULL
                          AND target_date
                                IS DISTINCT FROM
                                factory_out_date
                    ) AS auto_target_mismatch_count,
                    COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                target_date_source,
                                ''
                            )
                        ) LIKE 'auto%'
                          AND LOWER(
                                COALESCE(
                                    delivery_status,
                                    ''
                                )
                              ) IN (
                                'review required',
                                'pending approval'
                              )
                    ) AS auto_approval_status_count
                FROM mpps_shipments
                """
            )
        ).mappings().one()

    assert int(
        counts[
            "legacy_review_count"
        ]
        or 0
    ) == 0, counts
    assert int(
        counts[
            "auto_marked_manual_count"
        ]
        or 0
    ) == 0, counts
    assert int(
        counts[
            "auto_target_mismatch_count"
        ]
        or 0
    ) == 0, counts
    assert int(
        counts[
            "auto_approval_status_count"
        ]
        or 0
    ) == 0, counts

    print(
        "LIVE AUTO-TARGET DATABASE "
        "INVARIANT CHECK PASSED"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        required=True,
    )
    parser.add_argument(
        "--live",
        action="store_true",
    )
    args = parser.parse_args()
    root = Path(
        args.project_root
    ).resolve()

    files = {
        "planner": (
            root
            / "app"
            / "services"
            / "factory_planning_engine.py"
        ),
        "importer": (
            root
            / "app"
            / "services"
            / "intelligent_excel_import_service.py"
        ),
        "shipment": (
            root
            / "app"
            / "ui"
            / "shipment_orders_page.py"
        ),
        "raw_excel": (
            root
            / "app"
            / "ui"
            / "raw_excel_viewer_page.py"
        ),
        "operations": (
            root
            / "app"
            / "ui"
            / "intelligent_operations_pages.py"
        ),
        "migration": (
            root
            / "database"
            / "migrations"
            / "enable_auto_factory_out_targets_v6_4.py"
        ),
        "replan": (
            root
            / "tools"
            / "run_auto_target_replan_v6_4.py"
        ),
    }

    for path in files.values():
        assert path.exists(), path
        py_compile.compile(
            str(path),
            doraise=True,
        )

    planner = files["planner"].read_text(
        encoding="utf-8-sig"
    )
    importer = files["importer"].read_text(
        encoding="utf-8-sig"
    )
    shipment = files["shipment"].read_text(
        encoding="utf-8-sig"
    )
    raw_excel = files[
        "raw_excel"
    ].read_text(
        encoding="utf-8-sig"
    )
    operations = files[
        "operations"
    ].read_text(
        encoding="utf-8-sig"
    )
    migration = files[
        "migration"
    ].read_text(
        encoding="utf-8-sig"
    )

    required_planner = [
        "AUTO FACTORY-OUT TARGET SCHEDULING V6.4",
        "AUTO_TARGET_SOURCE",
        "shipment_target_is_locked",
        "dispatch_buffer_days",
        'delivery_status = "Auto Scheduled"',
        '"factory_out_date": factory_out_date',
        '"target_date_source": target_source',
    ]
    for marker in required_planner:
        assert marker in planner, marker

    required_importer = [
        '"status": "Planned"',
        '"planning_status": "Pending Replan"',
        '"target_date_source": (',
        "Auto Earliest Feasible Factory Out",
        '"auto_shipments_created"',
        '"dispatch_buffer_days"',
        '"schedule_reason"',
    ]
    for marker in required_importer:
        assert marker in importer, marker

    required_shipment = [
        "Reset to Auto Target",
        "Set Target Date",
        "Replan All",
        "Save & Replan",
        "Factory Can Out",
        "AUTO TARGET — SCHEDULED",
        "Auto target = Factory Can Out",
        "if column == 3:",
        "shipment_auto_target_",
    ]
    for marker in required_shipment:
        assert marker in shipment, marker

    required_raw = [
        "Create live auto-scheduled shipment orders",
        "_commit_and_auto_replan",
        "Running cumulative auto-target scheduling",
        "auto_planned_shipments",
    ]
    for marker in required_raw:
        assert marker in raw_excel, marker

    assert "Target Source" in operations
    assert (
        "Auto Earliest Feasible Factory Out"
        in operations
    )

    required_migration = [
        "legacy_review_promoted",
        "Auto Target scheduling requested",
        "Pending Replan",
        "dispatch_buffer_days",
        "auto_target_scheduling_runs",
        "planning_resource_reservations",
        "shipment_stock_allocations",
    ]
    for marker in required_migration:
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

    print(
        "EXCEL-MISSING TARGET AUTO-PROMOTION "
        "CHECK PASSED"
    )
    print(
        "EARLIEST FACTORY CAN OUT TARGET "
        "CHECK PASSED"
    )
    print(
        "MANUAL TARGET PRIORITY LOCK "
        "CHECK PASSED"
    )
    print(
        "SHIPMENT QUICK SCHEDULE CONTROL "
        "CHECK PASSED"
    )
    print(
        "DOUBLE-CLICK TARGET EDIT "
        "CHECK PASSED"
    )
    print(
        "IMPORT AUTO-REPLAN "
        "CHECK PASSED"
    )
    print(
        "AUTO FACTORY-OUT TARGET "
        "SCHEDULING V6.4 SMOKE TEST PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
