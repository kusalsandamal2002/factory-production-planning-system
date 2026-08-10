from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.production_learning_service import (
    ProductionLearningService,
)
from app.services.workbook_continuous_sync_service import (
    WorkbookContinuousSyncService,
    _identity_key,
    _source_base_key,
)


VERSION = "7.0.0"


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except Exception:
            return None
    return None


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except Exception:
        return 0


def _shipment_sort_key(
    row: dict[str, Any],
) -> tuple[int, int, int, date, datetime, int]:
    actual = (
        _safe_int(row.get("produced_qty"))
        + _safe_int(row.get("completed_qty"))
    )
    manual = 1 if bool(
        row.get("target_date_is_manual")
    ) else 0
    status = str(row.get("status") or "").strip().lower()
    open_live = 0 if status in {
        "cancelled",
        "canceled",
        "closed",
        "complete",
        "completed",
        "shipped",
        "done",
        "on hold",
        "hold",
        "superseded import",
    } else 1
    plan_date = (
        _as_date(row.get("source_latest_plan_date"))
        or _as_date(row.get("plan_date"))
        or _as_date(row.get("shipment_date"))
        or date.min
    )
    updated = row.get("updated_at")
    if not isinstance(updated, datetime):
        updated = datetime.min
    return (
        open_live,
        1 if actual > 0 else 0,
        manual,
        plan_date,
        updated,
        int(row["id"]),
    )


def _ensure_migration_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS database_migrations (
                id BIGSERIAL PRIMARY KEY,
                version VARCHAR(32) UNIQUE NOT NULL,
                description TEXT NOT NULL,
                source_database VARCHAR(128),
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    report_root = project_root / "reports"
    report_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = report_root / f"continuous_excel_sync_v7_0_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    shipment_backup = f"mpps_shipments_v7_before_{stamp}"
    item_backup = f"mpps_shipment_items_v7_before_{stamp}"
    report_rows: list[dict[str, Any]] = []

    summary = {
        "version": VERSION,
        "shipment_backup": shipment_backup,
        "item_backup": item_backup,
        "legacy_excel_shipments": 0,
        "identity_groups": 0,
        "canonical_shipments": 0,
        "superseded_duplicates": 0,
        "protected_duplicate_reviews": 0,
        "reservations_released": 0,
        "stock_allocations_released": 0,
    }

    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text("SET LOCAL statement_timeout = '120s'"))
        WorkbookContinuousSyncService.ensure_schema(conn)
        ProductionLearningService.ensure_schema(conn)
        _ensure_migration_table(conn)

        conn.execute(
            text(
                f'CREATE TABLE "{shipment_backup}" AS '
                "SELECT * FROM mpps_shipments"
            )
        )
        conn.execute(
            text(
                f'CREATE TABLE "{item_backup}" AS '
                "SELECT * FROM mpps_shipment_items"
            )
        )

        rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT
                        shipment.*,
                        COALESCE(SUM(GREATEST(0, item.produced_qty)), 0) AS produced_qty,
                        COALESCE(SUM(GREATEST(0, item.completed_qty)), 0) AS completed_qty,
                        COALESCE(SUM(GREATEST(0, item.quantity)), 0) AS item_total_qty,
                        COUNT(item.id) AS item_count
                    FROM mpps_shipments shipment
                    LEFT JOIN mpps_shipment_items item
                      ON item.shipment_id = shipment.id
                    WHERE shipment.shipment_no ILIKE 'XLS-%'
                       OR shipment.source_family = 'OVEN_SHEET'
                    GROUP BY shipment.id
                    ORDER BY shipment.id
                    """
                )
            ).mappings().all()
        ]
        summary["legacy_excel_shipments"] = len(rows)

        latest_import = conn.execute(
            text(
                """
                SELECT
                    id,
                    workbook_hash,
                    workbook_name,
                    plan_date
                FROM excel_import_runs
                WHERE status IN (
                    'COMMITTED',
                    'COMMITTED WITH WARNINGS'
                )
                  AND rollback_at IS NULL
                  AND plan_date IS NOT NULL
                ORDER BY plan_date DESC, id DESC
                LIMIT 1
                """
            )
        ).mappings().first()
        if latest_import:
            existing_baseline = conn.execute(
                text(
                    """
                    SELECT id
                    FROM excel_shipment_sync_runs
                    WHERE sync_mode = 'LIVE'
                      AND status = 'COMMITTED'
                      AND rollback_at IS NULL
                    LIMIT 1
                    """
                )
            ).scalar()
            if not existing_baseline:
                conn.execute(
                    text(
                        """
                        INSERT INTO excel_shipment_sync_runs (
                            import_run_id,
                            workbook_hash,
                            workbook_name,
                            plan_date,
                            sync_mode,
                            status,
                            reason,
                            details_json,
                            started_at,
                            completed_at
                        )
                        VALUES (
                            :import_run_id,
                            :workbook_hash,
                            :workbook_name,
                            :plan_date,
                            'LIVE',
                            'COMMITTED',
                            :reason,
                            CAST(:details_json AS JSONB),
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "import_run_id": latest_import["id"],
                        "workbook_hash": (
                            latest_import.get("workbook_hash")
                            or ""
                        ),
                        "workbook_name": (
                            latest_import.get("workbook_name")
                            or "Legacy latest committed import"
                        ),
                        "plan_date": latest_import["plan_date"],
                        "reason": (
                            "V7.0 migration baseline seeded from the "
                            "latest committed intelligent import. Older "
                            "workbooks will be historical snapshots."
                        ),
                        "details_json": json.dumps(
                            {
                                "migration_baseline": True,
                                "source_import_run_id": latest_import["id"],
                            }
                        ),
                    },
                )
                summary["live_baseline_plan_date"] = str(
                    latest_import["plan_date"]
                )

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            base = _source_base_key(
                str(row.get("shipment_name") or row.get("customer_name") or row.get("shipment_no") or "")
            )
            grouped.setdefault(base, []).append(row)
        summary["identity_groups"] = len(grouped)

        for base_key, group in sorted(grouped.items()):
            group.sort(key=_shipment_sort_key, reverse=True)
            canonical = group[0]
            canonical_id = int(canonical["id"])
            identity_key = _identity_key(base_key)
            latest_plan_date = (
                _as_date(canonical.get("source_latest_plan_date"))
                or _as_date(canonical.get("plan_date"))
                or _as_date(canonical.get("shipment_date"))
            )

            conn.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET
                        source_family = 'OVEN_SHEET',
                        source_identity_key = :identity_key,
                        source_latest_plan_date = COALESCE(source_latest_plan_date, :plan_date),
                        source_latest_workbook = CASE
                            WHEN source_latest_workbook = '' THEN 'Legacy Excel import'
                            ELSE source_latest_workbook
                        END,
                        source_missing_from_latest = FALSE,
                        source_sync_status = 'CANONICAL_V7',
                        source_sync_note = :note,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :shipment_id
                    """
                ),
                {
                    "identity_key": identity_key,
                    "plan_date": latest_plan_date,
                    "note": (
                        "Selected as the stable canonical shipment during V7.0 "
                        "duplicate-safe identity migration."
                    ),
                    "shipment_id": canonical_id,
                },
            )

            conn.execute(
                text(
                    """
                    INSERT INTO excel_shipment_identities (
                        source_family,
                        identity_key,
                        base_key,
                        display_name,
                        canonical_shipment_id,
                        first_seen_plan_date,
                        last_seen_plan_date,
                        latest_workbook_name,
                        latest_total_qty,
                        latest_item_count,
                        is_active,
                        updated_at
                    )
                    VALUES (
                        'OVEN_SHEET',
                        :identity_key,
                        :base_key,
                        :display_name,
                        :canonical_shipment_id,
                        :plan_date,
                        :plan_date,
                        'Legacy Excel import',
                        :total_qty,
                        :item_count,
                        TRUE,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (source_family, identity_key)
                    DO UPDATE SET
                        base_key = EXCLUDED.base_key,
                        display_name = EXCLUDED.display_name,
                        canonical_shipment_id = EXCLUDED.canonical_shipment_id,
                        first_seen_plan_date = COALESCE(
                            excel_shipment_identities.first_seen_plan_date,
                            EXCLUDED.first_seen_plan_date
                        ),
                        last_seen_plan_date = GREATEST(
                            COALESCE(
                                excel_shipment_identities.last_seen_plan_date,
                                EXCLUDED.last_seen_plan_date
                            ),
                            COALESCE(
                                EXCLUDED.last_seen_plan_date,
                                excel_shipment_identities.last_seen_plan_date
                            )
                        ),
                        latest_total_qty = EXCLUDED.latest_total_qty,
                        latest_item_count = EXCLUDED.latest_item_count,
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "identity_key": identity_key,
                    "base_key": base_key,
                    "display_name": str(
                        canonical.get("shipment_name")
                        or canonical.get("customer_name")
                        or canonical.get("shipment_no")
                    ),
                    "canonical_shipment_id": canonical_id,
                    "plan_date": latest_plan_date,
                    "total_qty": _safe_int(canonical.get("item_total_qty")),
                    "item_count": _safe_int(canonical.get("item_count")),
                },
            )
            summary["canonical_shipments"] += 1
            report_rows.append(
                {
                    "base_key": base_key,
                    "shipment_id": canonical_id,
                    "shipment_no": canonical.get("shipment_no"),
                    "shipment_name": canonical.get("shipment_name"),
                    "action": "CANONICAL",
                    "actual_qty": _safe_int(canonical.get("produced_qty"))
                    + _safe_int(canonical.get("completed_qty")),
                    "manual_target": bool(canonical.get("target_date_is_manual")),
                    "note": "Stable identity selected.",
                }
            )

            for duplicate in group[1:]:
                duplicate_id = int(duplicate["id"])
                actual_qty = _safe_int(duplicate.get("produced_qty")) + _safe_int(
                    duplicate.get("completed_qty")
                )
                protected = actual_qty > 0 or bool(duplicate.get("target_date_is_manual"))
                legacy_key = _identity_key(base_key, f"LEGACY-{duplicate_id}")
                if protected:
                    action = "LEGACY_DUPLICATE_REVIEW"
                    summary["protected_duplicate_reviews"] += 1
                    conn.execute(
                        text(
                            """
                            UPDATE mpps_shipments
                            SET
                                source_family = 'OVEN_SHEET',
                                source_identity_key = :legacy_key,
                                source_sync_status = 'LEGACY_DUPLICATE_REVIEW',
                                source_sync_note = :note,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :shipment_id
                            """
                        ),
                        {
                            "legacy_key": legacy_key,
                            "note": (
                                "Legacy duplicate retained for manual review because "
                                "actual production/completion or a manual target exists."
                            ),
                            "shipment_id": duplicate_id,
                        },
                    )
                else:
                    action = "SUPERSEDED_IMPORT"
                    summary["superseded_duplicates"] += 1
                    conn.execute(
                        text(
                            """
                            UPDATE mpps_shipments
                            SET
                                source_family = 'OVEN_SHEET',
                                source_identity_key = :legacy_key,
                                status = 'Superseded Import',
                                planning_status = 'Superseded',
                                delivery_status = 'Superseded',
                                source_missing_from_latest = TRUE,
                                source_sync_status = 'SUPERSEDED_V7',
                                source_sync_note = :note,
                                planning_note = :note,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :shipment_id
                            """
                        ),
                        {
                            "legacy_key": legacy_key,
                            "note": (
                                "Older duplicate Excel import superseded by stable "
                                "continuous-sync identity; row retained for audit."
                            ),
                            "shipment_id": duplicate_id,
                        },
                    )
                    released = conn.execute(
                        text(
                            "DELETE FROM planning_resource_reservations "
                            "WHERE shipment_id = :shipment_id"
                        ),
                        {"shipment_id": duplicate_id},
                    )
                    summary["reservations_released"] += int(released.rowcount or 0)
                    released = conn.execute(
                        text(
                            "DELETE FROM shipment_stock_allocations "
                            "WHERE shipment_id = :shipment_id"
                        ),
                        {"shipment_id": duplicate_id},
                    )
                    summary["stock_allocations_released"] += int(released.rowcount or 0)

                report_rows.append(
                    {
                        "base_key": base_key,
                        "shipment_id": duplicate_id,
                        "shipment_no": duplicate.get("shipment_no"),
                        "shipment_name": duplicate.get("shipment_name"),
                        "action": action,
                        "actual_qty": actual_qty,
                        "manual_target": bool(duplicate.get("target_date_is_manual")),
                        "note": (
                            "Protected review retained."
                            if protected
                            else "Safely superseded; not deleted."
                        ),
                    }
                )

        conn.execute(
            text(
                """
                INSERT INTO database_migrations (
                    version,
                    description,
                    source_database
                )
                VALUES (
                    :version,
                    :description,
                    current_database()
                )
                ON CONFLICT (version)
                DO UPDATE SET
                    description = EXCLUDED.description,
                    source_database = EXCLUDED.source_database,
                    applied_at = NOW()
                """
            ),
            {
                "version": VERSION,
                "description": (
                    "Added duplicate-safe continuous Excel shipment revision sync, "
                    "historical/live import protection, reconciliation and advisory "
                    "learning foundation"
                ),
            },
        )

    report_csv = report_dir / "legacy_excel_shipment_identity_audit.csv"
    fieldnames = [
        "base_key",
        "shipment_id",
        "shipment_no",
        "shipment_name",
        "action",
        "actual_qty",
        "manual_target",
        "note",
    ]
    with report_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    (report_dir / "README.txt").write_text(
        "\n".join(
            [
                "CONTINUOUS EXCEL SYNC V7.0 MIGRATION AUDIT",
                "============================================",
                "",
                "No shipment was physically deleted.",
                "Unprotected old duplicates were marked Superseded Import.",
                "Shipments with actual production/completion or manual targets were retained for review.",
                f"Shipment backup table: {shipment_backup}",
                f"Shipment-item backup table: {item_backup}",
            ]
        ),
        encoding="utf-8",
    )

    print("CONTINUOUS EXCEL SYNC + LEARNING V7.0 MIGRATION COMPLETED")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"report_directory: {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
