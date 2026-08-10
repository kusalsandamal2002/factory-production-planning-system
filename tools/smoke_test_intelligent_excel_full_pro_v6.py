from __future__ import annotations

import argparse
from pathlib import Path

from app.services.intelligent_excel_import_service import IntelligentExcelImportService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--workbook", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    paths = {
        "main": project_root / "app" / "ui" / "main_window.py",
        "import_ui": project_root / "app" / "ui" / "raw_excel_viewer_page.py",
        "ops_ui": project_root / "app" / "ui" / "intelligent_operations_pages.py",
        "service": project_root / "app" / "services" / "intelligent_excel_import_service.py",
        "migration": project_root / "database" / "migrations" / "ensure_intelligent_excel_import_schema.py",
        "cavity_planner": project_root / "app" / "services" / "cavity_daily_plan_service.py",
        "factory_planner": project_root / "app" / "services" / "factory_planning_engine.py",
    }
    for name, path in paths.items():
        if not path.exists():
            raise AssertionError(f"Missing V6 file {name}: {path}")

    source = {name: path.read_text(encoding="utf-8-sig") for name, path in paths.items()}
    joined = "\n".join(source.values())
    required_markers = [
        "Intelligent Excel Import",
        "IntelligentExcelImportService",
        "DeliveryDateControlPage",
        "DailyProductionPlanPage",
        "ShiftPlanPage",
        "OperationsReportsPage",
        "excel_import_runs",
        "excel_import_changes",
        "excel_import_shipment_snapshots",
        "excel_import_material_plans",
        "def rollback(",
        "Archive exact source workbook",
        "Commit Safe Full Update",
        "imported review",
        "excel review hold",
    ]
    missing = [marker for marker in required_markers if marker not in joined]
    if missing:
        raise AssertionError("Missing V6 markers: " + ", ".join(missing))

    placeholder_fragments = [
        'lambda: PlaceholderPage(\n                    "Delivery Date Calculation"',
        'lambda: PlaceholderPage(\n                    "Daily Production Plan"',
        'lambda: PlaceholderPage(\n                    "Day / Night Shift Plan"',
        'lambda: PlaceholderPage(\n                    "Reports"',
    ]
    remaining = [fragment for fragment in placeholder_fragments if fragment in source["main"]]
    if remaining:
        raise AssertionError("Operational placeholders remain in main_window.py")

    print("INTELLIGENT EXCEL UI AND OPERATIONS PAGE CHECK PASSED")
    print("PLACEHOLDER REPLACEMENT CHECK PASSED")
    print("TRANSACTIONAL IMPORT AND ROLLBACK SOURCE CHECK PASSED")

    workbook_text = args.workbook.strip()
    if workbook_text:
        workbook = Path(workbook_text).resolve()
        if not workbook.exists():
            raise FileNotFoundError(workbook)
        service = IntelligentExcelImportService(project_root)
        analysis = service.analyze(workbook)
        summary = analysis.summary
        checks = {
            "sheet_count": summary.get("sheet_count", 0) >= 12,
            "mapped_sheet_count": summary.get("mapped_sheet_count", 0) >= 12,
            "confidence": analysis.confidence_score >= 0.90,
            "stock_items": summary.get("stock_item_count", 0) >= 3000,
            "shipments": summary.get("shipment_count", 0) >= 100,
            "production_required": summary.get("production_required_qty", 0) > 25000,
            "day_plan": summary.get("day_plan_qty", 0) == 376,
            "night_plan": summary.get("night_plan_qty", 0) == 374,
            "next_day_plan": summary.get("next_day_plan_qty", 0) == 742,
            "compound_bom": summary.get("compound_bom_rows", 0) >= 13000,
            "formula_errors": summary.get("cached_error_cell_count", 0) >= 3000,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise AssertionError("Workbook analysis checks failed: " + ", ".join(failed))
        print("JUNE 2026 WORKBOOK SEMANTIC ANALYSIS CHECK PASSED")
        print(
            "WORKBOOK SUMMARY: "
            f"confidence={analysis.confidence_score:.4f}; "
            f"stock={summary['stock_item_count']}; "
            f"shipments={summary['shipment_count']}; "
            f"day={summary['day_plan_qty']}; "
            f"night={summary['night_plan_qty']}; "
            f"next={summary['next_day_plan_qty']}; "
            f"compound={summary['compound_bom_rows']}"
        )
    else:
        print("WORKBOOK ANALYSIS CHECK SKIPPED — no --workbook path supplied")

    print("INTELLIGENT EXCEL FULL PRO UPGRADE V6 SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
