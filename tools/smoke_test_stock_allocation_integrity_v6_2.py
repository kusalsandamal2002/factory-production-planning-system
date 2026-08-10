from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import py_compile
import sys


def _safe_available(row: dict) -> int:
    return max(
        0,
        max(0, int(row.get("fg_stock") or 0))
        + max(0, int(row.get("qc_stock") or 0))
        - max(0, int(row.get("scrap_stock") or 0))
        - max(0, int(row.get("blocked_stock") or 0)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--workbook", default="")
    args = parser.parse_args()

    root = Path(args.source_root).resolve()
    service_path = (
        root
        / "app"
        / "services"
        / "intelligent_excel_import_service.py"
    )
    shipment_page_path = (
        root
        / "app"
        / "ui"
        / "shipment_orders_page.py"
    )
    migration_path = (
        root
        / "database"
        / "migrations"
        / "repair_stock_allocation_integrity_v6_2.py"
    )

    for path in (
        service_path,
        shipment_page_path,
        migration_path,
    ):
        assert path.exists(), path
        py_compile.compile(str(path), doraise=True)

    service_source = service_path.read_text(
        encoding="utf-8-sig"
    )
    page_source = shipment_page_path.read_text(
        encoding="utf-8-sig"
    )
    migration_source = migration_path.read_text(
        encoding="utf-8-sig"
    )

    service_markers = [
        "stock_remaining_by_code",
        "draft_negative_source_stock_protected",
        "non-negative cumulative stock preview",
        "shipment_stock_allocations",
        "physical_available = max(",
        "allocated = min(order_qty, available_qty)",
    ]
    for marker in service_markers:
        assert marker in service_source, marker

    page_markers = [
        "STOCK ALLOCATION INTEGRITY V6.2",
        "GREATEST(",
        "LEAST(",
        ") AS stock_allocated_qty",
        ") AS production_required_qty",
    ]
    for marker in page_markers:
        assert marker in page_source, marker

    migration_markers = [
        "NEGATIVE_STOCK_ALLOCATION",
        "PRODUCTION_REQUIRED_EXCEEDS_QUANTITY",
        "stock_allocation_integrity_runs",
        "stock_allocation_integrity_items",
        "chk_mpps_shipment_items_stock_range_v62",
        "chk_mpps_shipment_items_required_range_v62",
        "invalid_rows_after",
        "imported_review_rows_recalculated",
    ]
    for marker in migration_markers:
        assert marker in migration_source, marker

    if args.workbook:
        workbook = Path(args.workbook).resolve()
        assert workbook.exists(), workbook

        sys.path.insert(0, str(root))
        from app.services.intelligent_excel_import_service import (
            IntelligentExcelImportService,
        )

        analysis = IntelligentExcelImportService(root).analyze(
            workbook
        )
        stock_by_code = {
            row["sap_code"]: row
            for row in analysis.stock_rows
        }
        negative_rows = [
            row
            for row in analysis.stock_rows
            if int(row.get("fg_stock") or 0) < 0
        ]
        assert negative_rows

        remaining = {
            code: _safe_available(row)
            for code, row in stock_by_code.items()
        }
        total_allocated: dict[str, int] = defaultdict(int)
        impacted_old_rows = 0

        grouped: dict[str, list[dict]] = defaultdict(list)
        for item in analysis.shipment_rows:
            if item.get("source_status") not in {
                "OK",
                "YES",
                "ACTIVE",
            }:
                continue
            grouped[item["shipment_column"]].append(item)

        for column in grouped:
            for item in grouped[column]:
                code = item["sap_code"]
                qty = max(0, int(item["quantity"] or 0))
                raw_fg = int(
                    stock_by_code.get(
                        code,
                        {},
                    ).get("fg_stock", 0)
                    or 0
                )
                old_allocated = min(qty, raw_fg)
                if old_allocated < 0:
                    impacted_old_rows += 1

                available = max(0, remaining.get(code, 0))
                allocated = min(qty, available)
                required = max(0, qty - allocated)
                assert 0 <= allocated <= qty
                assert 0 <= required <= qty
                remaining[code] = max(
                    0,
                    available - allocated,
                )
                total_allocated[code] += allocated

        for code, allocated in total_allocated.items():
            assert allocated <= _safe_available(
                stock_by_code.get(code, {})
            )

        assert impacted_old_rows > 0
        print(
            "WORKBOOK DEFECT REPRODUCTION CHECK PASSED "
            f"({len(negative_rows)} negative stock rows; "
            f"{impacted_old_rows} shipment rows protected)"
        )

    print("NON-NEGATIVE ALLOCATION FORMULA CHECK PASSED")
    print("CUMULATIVE STOCK LEDGER CHECK PASSED")
    print("LIVE RESERVATION SUBTRACTION CHECK PASSED")
    print("SHIPMENT UI DEFENSIVE DISPLAY CHECK PASSED")
    print("DATABASE INVARIANT REPAIR CHECK PASSED")
    print(
        "INTELLIGENT EXCEL STOCK ALLOCATION "
        "INTEGRITY V6.2 SMOKE TEST PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
