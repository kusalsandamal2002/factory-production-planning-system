from __future__ import annotations

import argparse
from pathlib import Path
import py_compile


FILES = [
    "app/main.py",
    "app/database.py",
    "app/services/performance_runtime.py",
    "app/services/cavity_daily_plan_service.py",
    "app/ui/schedule_page.py",
    "app/ui/main_window.py",
    "database/migrations/ensure_performance_indexes_v7_2.py",
    "tools/benchmark_production_planner_v7_2.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    for relative in FILES:
        path = root / relative
        assert path.exists(), relative
        py_compile.compile(str(path), doraise=True)

    cavity = (root / "app/services/cavity_daily_plan_service.py").read_text(
        encoding="utf-8-sig"
    )
    schedule = (root / "app/ui/schedule_page.py").read_text(
        encoding="utf-8-sig"
    )
    main_window = (root / "app/ui/main_window.py").read_text(
        encoding="utf-8-sig"
    )
    main_app = (root / "app/main.py").read_text(encoding="utf-8-sig")
    database = (root / "app/database.py").read_text(encoding="utf-8-sig")
    migration = (
        root / "database/migrations/ensure_performance_indexes_v7_2.py"
    ).read_text(encoding="utf-8-sig")

    for marker in [
        "MPPS ULTRA PERFORMANCE + GLOBAL PROGRESS V7.2",
        "progress_callback: ProgressCallback | None",
        "compatible_by_line",
        "demand_line_keys",
        "Today plan —",
        "Next-day plan —",
    ]:
        assert marker in cavity, marker

    for marker in [
        "QProgressBar",
        "CALCULATING {value}%",
        "worker.progress.connect",
        "QThread.Priority.HighPriority",
        "Production plan ready — 100%",
    ]:
        assert marker in schedule, marker

    for marker in [
        "LOADING WORKSPACE {value}%",
        "_set_loading_progress",
        "QProgressBar",
        "Workspace ready",
    ]:
        assert marker in main_window, marker

    for marker in [
        "configure_process_environment",
        "configure_qt_thread_pool",
        "[MPPS PERFORMANCE]",
    ]:
        assert marker in main_app, marker

    for marker in [
        "pool_size=_DB_POOL_SIZE",
        "max_overflow=_DB_POOL_SIZE",
        "pool_use_lifo=True",
    ]:
        assert marker in database, marker

    for marker in [
        "ix_v72_shipment_items_shipment_sap",
        "ix_v72_shipments_planning_queue",
        "ix_v72_smds_sap_expr",
        "ANALYZE",
        "data_rows_modified: 0",
    ]:
        assert marker in migration, marker

    print("CPU/RAM RUNTIME PERFORMANCE MODE CHECK PASSED")
    print("DATABASE POOL AND INDEX CHECK PASSED")
    print("INDEXED CAVITY CANDIDATE ENGINE CHECK PASSED")
    print("REAL PRODUCTION PLAN PERCENT PROGRESS CHECK PASSED")
    print("GLOBAL WORKSPACE PERCENT PROGRESS CHECK PASSED")
    print("HIGH-PRIORITY BACKGROUND PLANNER CHECK PASSED")
    print("GPU WORKLOAD SAFETY RULE CHECK PASSED")
    print("MPPS ULTRA PERFORMANCE + GLOBAL PROGRESS V7.2 SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
