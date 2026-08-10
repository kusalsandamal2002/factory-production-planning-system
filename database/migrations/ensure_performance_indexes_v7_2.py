from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import text

from app.database import engine


VERSION = "7.2.0"


INDEX_STATEMENTS = [
    (
        "ix_v72_shipment_items_shipment_sap",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_shipment_items_shipment_sap
        ON mpps_shipment_items (shipment_id, sap_code)
        """,
    ),
    (
        "ix_v72_shipment_items_active_sap_expr",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_shipment_items_active_sap_expr
        ON mpps_shipment_items ((TRIM(sap_code)))
        WHERE COALESCE(quantity, 0) > 0
        """,
    ),
    (
        "ix_v72_shipments_planning_queue",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_shipments_planning_queue
        ON mpps_shipments (
            status,
            target_date_is_manual,
            target_date,
            created_at,
            id
        )
        """,
    ),
    (
        "ix_v72_stock_sap_expr",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_stock_sap_expr
        ON mpps_sap_stock_items ((TRIM(sap_code)))
        """,
    ),
    (
        "ix_v72_smds_sap_expr",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_smds_sap_expr
        ON smds ((TRIM(sap_code)))
        """,
    ),
    (
        "ix_v72_cavities_live_line",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_cavities_live_line
        ON production_line_cavities (
            is_active,
            status,
            line_name,
            cavity_no
        )
        """,
    ),
    (
        "ix_v72_mold_key_status",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_mold_key_status
        ON mold_master (mold_key_code, is_active, status)
        """,
    ),
    (
        "ix_v72_casing_units_live",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_casing_units_live
        ON casing_units (
            casing_type,
            condition_status,
            stock_status
        )
        """,
    ),
    (
        "ix_v72_casing_master_type",
        """
        CREATE INDEX IF NOT EXISTS ix_v72_casing_master_type
        ON casing_master (casing_type, is_active, status)
        """,
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    report_dir = (
        project_root
        / "reports"
        / (
            "performance_v7_2_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
        )
    )
    report_dir.mkdir(parents=True, exist_ok=True)

    created = []
    analyzed = []
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        conn.execute(text("SET LOCAL statement_timeout = '120s'"))

        for name, statement in INDEX_STATEMENTS:
            conn.execute(text(statement))
            created.append(name)
            print("INDEX READY:", name)

        for table_name in [
            "mpps_shipments",
            "mpps_shipment_items",
            "mpps_sap_stock_items",
            "smds",
            "production_line_cavities",
            "mold_master",
            "casing_units",
            "casing_master",
        ]:
            conn.execute(text(f"ANALYZE {table_name}"))
            analyzed.append(table_name)
            print("ANALYZED:", table_name)

    summary = {
        "version": VERSION,
        "indexes_ready": created,
        "tables_analyzed": analyzed,
        "data_rows_modified": 0,
        "note": (
            "Performance-only migration. No shipment, stock, plan or master "
            "data values were changed."
        ),
    }
    (report_dir / "performance_index_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("PERFORMANCE INDEX MIGRATION V7.2 COMPLETED")
    print("indexes_ready:", len(created))
    print("tables_analyzed:", len(analyzed))
    print("data_rows_modified: 0")
    print("report_directory:", report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
