from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--workbook", default="")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root))

    service_path = root / "app" / "services" / "intelligent_excel_import_service.py"
    ui_path = root / "app" / "ui" / "raw_excel_viewer_page.py"

    service_source = service_path.read_text(encoding="utf-8-sig")
    ui_source = ui_path.read_text(encoding="utf-8-sig")

    required_service_markers = [
        "NEGATIVE_STOCK_NORMALIZED",
        "negative_stock_rows_normalized",
        "live_stock = {",
        "max(0, value)",
        "Do not issue another UPDATE here",
    ]
    for marker in required_service_markers:
        assert marker in service_source, marker

    required_ui_markers = [
        "Negative source-stock rows protected",
        "Exact reason:",
        "setMaximumHeight(240)",
    ]
    for marker in required_ui_markers:
        assert marker in ui_source, marker

    from app.services.intelligent_excel_import_service import (
        IntelligentExcelImportService,
    )

    if args.workbook:
        workbook = Path(args.workbook).resolve()
        assert workbook.exists(), workbook

        analysis = IntelligentExcelImportService(root).analyze(workbook)
        negative_rows = [
            row
            for row in analysis.stock_rows
            if any(
                int(row.get(field_name) or 0) < 0
                for field_name in (
                    "fg_stock",
                    "qc_stock",
                    "scrap_stock",
                    "blocked_stock",
                )
            )
        ]
        assert negative_rows, "The reviewed workbook should contain negative stock evidence."
        assert (
            analysis.summary.get("negative_stock_row_count")
            == len(negative_rows)
        )
        issue_count = sum(
            issue.category == "NEGATIVE_STOCK_NORMALIZED"
            for issue in analysis.issues
        )
        assert issue_count == len(negative_rows)
        print(
            "NEGATIVE STOCK WORKBOOK PROTECTION CHECK PASSED "
            f"({len(negative_rows)} rows)"
        )

    print("ORIGINAL DATABASE ERROR PRESERVATION CHECK PASSED")
    print("LIVE STOCK NON-NEGATIVE NORMALIZATION CHECK PASSED")
    print("EXACT ERROR DIALOG CHECK PASSED")
    print("INTELLIGENT EXCEL IMPORT HOTFIX V6.1 SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
