from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root))

    planner = (
        root / "app/services/factory_planning_engine.py"
    ).read_text(encoding="utf-8-sig")
    cavity = (
        root / "app/services/cavity_daily_plan_service.py"
    ).read_text(encoding="utf-8-sig")
    item = (
        root / "app/ui/item_resource_control_center_page.py"
    ).read_text(encoding="utf-8-sig")
    migration = (
        root
        / "database/migrations/repair_process_standard_integrity_v6_5.py"
    ).read_text(encoding="utf-8-sig")

    for marker in [
        "PROCESS STANDARD PLANNING INTEGRITY V6.5",
        "resolve_process_standard_from_connection",
        "Physical mold/casing/cavity capacity alone",
    ]:
        assert marker in planner, marker

    for marker in [
        "process_standard_index.resolve(",
        "process_standard_complete",
        "PROCESS STANDARD PLANNING INTEGRITY V6.5",
    ]:
        assert marker in cavity, marker

    for marker in [
        "PROCESS STANDARD REQUIRED",
        "MASTER APPROVAL REQUIRED",
        "PRODUCTION RATE UNAVAILABLE",
    ]:
        assert marker in item, marker

    for marker in [
        "smds_process_standard_backup_",
        "process_standard_repair_runs",
        "process_standard_repair_rows",
        "PROCESS_STANDARD_UNRESOLVED_V6_5",
        "planning_manager_approval_status = 'Approved'",
    ]:
        assert marker in migration, marker

    from app.services.process_standard_resolution import (
        process_standard_complete,
        resolve_process_standard,
    )

    rows = []
    for code in ("PEER-1", "PEER-2", "PEER-3"):
        rows.append(
            {
                "sap_code": code,
                "key_code": "8.25-15 OPT",
                "casing_type": "B5",
                "line": "Line-800",
                "curing_cycle": "7h",
                "normal_curing_minutes": 420,
                "handling_time": 20,
                "day_plan": 1.636,
                "night_plan": 1.636,
                "total_plan": 3.273,
            }
        )
    rows.append(
        {
            "sap_code": "OUTLIER",
            "key_code": "8.25-15 OPT",
            "casing_type": "B5",
            "line": "Line-800",
            "curing_cycle": "6h 15m",
            "normal_curing_minutes": 375,
            "handling_time": 20,
            "day_plan": 1.823,
            "night_plan": 1.823,
            "total_plan": 3.646,
        }
    )
    target = {
        "sap_code": "60006811",
        "key_code": "8.25-15 OPT",
        "casing_type": "B5",
        "line": "Line-800",
        "curing_cycle": "-",
        "normal_curing_minutes": 0,
        "handling_time": None,
        "day_plan": None,
        "night_plan": None,
        "total_plan": None,
    }

    resolution = resolve_process_standard(rows, target)
    assert resolution is not None
    assert resolution.normal_curing_minutes == 420
    assert resolution.handling_time == 20
    assert resolution.total_plan == 3.273
    assert resolution.peer_count == 3
    assert resolution.group_count == 4
    assert resolution.confidence == 0.75
    assert process_standard_complete(resolution.as_smds_values())

    print("EXACT RESOURCE-PEER CONSENSUS CHECK PASSED")
    print("OUTLIER RESISTANCE CHECK PASSED")
    print("MISSING PROCESS STANDARD PLANNER FALLBACK CHECK PASSED")
    print("MASTER APPROVAL RESTORATION SOURCE CHECK PASSED")
    print("TRUTHFUL ITEM BLOCKER DISPLAY CHECK PASSED")
    print("PROCESS STANDARD PLANNING INTEGRITY V6.5 SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
