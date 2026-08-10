from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.master_data_normalization import normalize_sap_code


REVIEW_STATUSES = {
    "draft",
    "draft import",
    "imported review",
    "review required",
    "on hold",
    "hold",
    "excel review hold",
}

CLOSED_STATUSES = {
    "cancelled",
    "canceled",
    "closed",
    "complete",
    "completed",
    "shipped",
    "done",
}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_imported_review(row: dict[str, Any]) -> bool:
    shipment_no = str(row.get("shipment_no") or "").strip().upper()
    status = _norm(row.get("shipment_status"))
    planning_status = _norm(row.get("shipment_planning_status"))
    shipment_note = _norm(row.get("shipment_note"))
    return (
        shipment_no.startswith("XLS-")
        or status in REVIEW_STATUSES
        or planning_status == "review required"
        or "imported from" in shipment_note
        or "intelligent import" in shipment_note
    )


def _invalid_reasons(row: dict[str, Any]) -> list[str]:
    qty = _int(row.get("quantity"))
    stock = _int(row.get("stock_allocated_qty"))
    required = _int(row.get("production_required_qty"))
    produced = _int(row.get("produced_qty"))
    remaining = _int(row.get("remaining_qty"))

    reasons: list[str] = []
    if qty < 0:
        reasons.append("NEGATIVE_QUANTITY")
    if stock < 0:
        reasons.append("NEGATIVE_STOCK_ALLOCATION")
    if stock > max(0, qty):
        reasons.append("STOCK_ALLOCATION_EXCEEDS_QUANTITY")
    if required < 0:
        reasons.append("NEGATIVE_PRODUCTION_REQUIRED")
    if required > max(0, qty):
        reasons.append("PRODUCTION_REQUIRED_EXCEEDS_QUANTITY")
    if produced < 0:
        reasons.append("NEGATIVE_PRODUCED")
    if remaining < 0:
        reasons.append("NEGATIVE_REMAINING")
    if stock + required + max(0, produced) > max(0, qty):
        reasons.append("ALLOCATION_COMPONENTS_EXCEED_QUANTITY")
    return reasons


def _table_exists(connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{table_name}"},
        ).scalar_one()
    )


def _available_stock_map(connection) -> dict[str, int]:
    result: dict[str, int] = {}

    if _table_exists(connection, "mpps_stock_items"):
        rows = connection.execute(
            text(
                """
                SELECT
                    material_code AS sap_code,
                    GREATEST(
                        0,
                        COALESCE(fg_stock, 0)
                        + COALESCE(qc_stock, 0)
                        - COALESCE(scrap_stock, 0)
                        - COALESCE(blocked_stock, 0)
                    ) AS available_qty
                FROM mpps_stock_items
                WHERE COALESCE(is_active, TRUE) = TRUE
                """
            )
        ).mappings()
        for row in rows:
            code = normalize_sap_code(row["sap_code"])
            if code:
                result[code] = max(
                    result.get(code, 0),
                    _int(row["available_qty"]),
                )

    if _table_exists(connection, "mpps_sap_stock_items"):
        rows = connection.execute(
            text(
                """
                SELECT
                    sap_code,
                    GREATEST(
                        0,
                        COALESCE(fg_stock, 0)
                        + COALESCE(qc_stock, 0)
                        - COALESCE(scrap_stock, 0)
                        - COALESCE(blocked_stock, 0)
                    ) AS available_qty
                FROM mpps_sap_stock_items
                WHERE COALESCE(is_active, TRUE) = TRUE
                """
            )
        ).mappings()
        for row in rows:
            code = normalize_sap_code(row["sap_code"])
            if code:
                # SAP stock master is the canonical live source.
                result[code] = _int(row["available_qty"])

    return {code: max(0, qty) for code, qty in result.items()}


def _live_reserved_stock_map(connection) -> dict[str, int]:
    reserved: dict[str, int] = defaultdict(int)

    if _table_exists(connection, "shipment_stock_allocations"):
        rows = connection.execute(
            text(
                """
                SELECT
                    allocation.sap_code,
                    COALESCE(
                        SUM(
                            GREATEST(
                                0,
                                allocation.allocated_stock_qty
                            )
                        ),
                        0
                    ) AS allocated_qty
                FROM shipment_stock_allocations allocation
                JOIN mpps_shipments shipment
                  ON shipment.id = allocation.shipment_id
                WHERE COALESCE(
                    LOWER(shipment.status),
                    'planned'
                ) NOT IN (
                    'cancelled',
                    'canceled',
                    'closed',
                    'complete',
                    'completed',
                    'shipped',
                    'done',
                    'draft',
                    'draft import',
                    'imported review',
                    'review required',
                    'on hold',
                    'hold',
                    'excel review hold'
                )
                GROUP BY allocation.sap_code
                """
            )
        ).mappings()
        for row in rows:
            code = normalize_sap_code(row["sap_code"])
            reserved[code] = max(
                reserved.get(code, 0),
                max(0, _int(row["allocated_qty"])),
            )

    # The item table is a second source for installations whose planner
    # allocation table is stale or only partly populated. MAX avoids
    # double-counting the same reservation.
    rows = connection.execute(
        text(
            """
            SELECT
                item.sap_code,
                COALESCE(
                    SUM(
                        GREATEST(
                            0,
                            LEAST(
                                COALESCE(item.quantity, 0),
                                COALESCE(
                                    item.stock_allocated_qty,
                                    0
                                )
                            )
                        )
                    ),
                    0
                ) AS allocated_qty
            FROM mpps_shipment_items item
            JOIN mpps_shipments shipment
              ON shipment.id = item.shipment_id
            WHERE COALESCE(
                LOWER(shipment.status),
                'planned'
            ) NOT IN (
                'cancelled',
                'canceled',
                'closed',
                'complete',
                'completed',
                'shipped',
                'done',
                'draft',
                'draft import',
                'imported review',
                'review required',
                'on hold',
                'hold',
                'excel review hold'
            )
            GROUP BY item.sap_code
            """
        )
    ).mappings()
    for row in rows:
        code = normalize_sap_code(row["sap_code"])
        reserved[code] = max(
            reserved.get(code, 0),
            max(0, _int(row["allocated_qty"])),
        )
    return dict(reserved)


def _fetch_items(connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            """
            SELECT
                item.id,
                item.shipment_id,
                item.sap_code,
                item.item_description,
                item.quantity,
                item.stock_allocated_qty,
                item.production_required_qty,
                item.produced_qty,
                item.completed_qty,
                item.remaining_qty,
                item.progress_pct,
                item.item_status,
                item.note AS item_note,
                item.planning_note,
                shipment.shipment_no,
                shipment.shipment_name,
                shipment.status AS shipment_status,
                shipment.planning_status
                    AS shipment_planning_status,
                shipment.note AS shipment_note,
                shipment.target_date,
                shipment.plan_date,
                shipment.shipment_date,
                shipment.created_at AS shipment_created_at
            FROM mpps_shipment_items item
            JOIN mpps_shipments shipment
              ON shipment.id = item.shipment_id
            ORDER BY
                COALESCE(
                    shipment.plan_date,
                    shipment.shipment_date,
                    DATE '9999-12-31'
                ),
                shipment.created_at,
                shipment.id,
                item.id
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _create_audit_schema(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS
                stock_allocation_integrity_runs (
                    id BIGSERIAL PRIMARY KEY,
                    started_at TIMESTAMP NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status VARCHAR(30) NOT NULL
                        DEFAULT 'RUNNING',
                    invalid_before INTEGER NOT NULL DEFAULT 0,
                    imported_review_recalculated INTEGER
                        NOT NULL DEFAULT 0,
                    non_review_repaired INTEGER
                        NOT NULL DEFAULT 0,
                    negative_stock_fixed INTEGER
                        NOT NULL DEFAULT 0,
                    over_required_fixed INTEGER
                        NOT NULL DEFAULT 0,
                    summary_json JSONB NOT NULL
                        DEFAULT '{}'::jsonb
                )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS
                stock_allocation_integrity_items (
                    id BIGSERIAL PRIMARY KEY,
                    run_id BIGINT NOT NULL
                        REFERENCES stock_allocation_integrity_runs(id)
                        ON DELETE CASCADE,
                    shipment_item_id BIGINT NOT NULL,
                    shipment_id BIGINT NOT NULL,
                    shipment_no TEXT NOT NULL DEFAULT '',
                    sap_code TEXT NOT NULL DEFAULT '',
                    repair_scope VARCHAR(30) NOT NULL,
                    reasons TEXT NOT NULL DEFAULT '',
                    quantity_before INTEGER NOT NULL DEFAULT 0,
                    stock_before INTEGER NOT NULL DEFAULT 0,
                    required_before INTEGER NOT NULL DEFAULT 0,
                    produced_before INTEGER NOT NULL DEFAULT 0,
                    remaining_before INTEGER NOT NULL DEFAULT 0,
                    quantity_after INTEGER NOT NULL DEFAULT 0,
                    stock_after INTEGER NOT NULL DEFAULT 0,
                    required_after INTEGER NOT NULL DEFAULT 0,
                    produced_after INTEGER NOT NULL DEFAULT 0,
                    remaining_after INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(run_id, shipment_item_id)
                )
            """
        )
    )


def _add_integrity_constraints(connection) -> None:
    constraints = [
        (
            "chk_mpps_shipment_items_quantity_nonnegative_v62",
            "quantity >= 0",
        ),
        (
            "chk_mpps_shipment_items_stock_range_v62",
            "stock_allocated_qty >= 0 "
            "AND stock_allocated_qty <= quantity",
        ),
        (
            "chk_mpps_shipment_items_required_range_v62",
            "production_required_qty >= 0 "
            "AND production_required_qty <= quantity",
        ),
    ]
    for name, expression in constraints:
        connection.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = '{name}'
                    ) THEN
                        ALTER TABLE mpps_shipment_items
                        ADD CONSTRAINT {name}
                        CHECK ({expression});
                    END IF;
                END
                $$;
                """
            )
        )


def _write_reports(
    project_root: Path,
    run_id: int,
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_root = (
        project_root
        / "reports"
        / f"stock_allocation_integrity_v6_2_{stamp}"
    )
    report_root.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "shipment_item_id",
        "shipment_id",
        "shipment_no",
        "shipment_name",
        "shipment_status",
        "shipment_planning_status",
        "sap_code",
        "quantity",
        "stock_allocated_qty",
        "production_required_qty",
        "produced_qty",
        "completed_qty",
        "remaining_qty",
        "progress_pct",
        "invalid_reasons",
        "imported_review",
    ]

    for filename, rows in (
        ("before.csv", before_rows),
        ("after.csv", after_rows),
    ):
        with (report_root / filename).open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)

    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        **summary,
    }
    (report_root / "summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

    lines = [
        "MPPS STOCK ALLOCATION INTEGRITY AUDIT V6.2",
        "=" * 45,
        "",
        f"Repair run: {run_id}",
    ]
    for key, value in summary.items():
        lines.append(f"{key}: {value}")
    lines.extend(
        [
            "",
            "Core invariant:",
            "0 <= stock_allocated_qty <= quantity",
            "0 <= production_required_qty <= quantity",
            "",
            "Imported-review shipments were recalculated cumulatively.",
            "Negative source stock was treated as zero physical stock.",
            "Approved/live reservations were subtracted before preview allocation.",
        ]
    )
    (report_root / "README.txt").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return report_root


def run_repair(project_root: Path) -> tuple[int, Path, dict[str, Any]]:
    before_report_rows: list[dict[str, Any]] = []
    after_report_rows: list[dict[str, Any]] = []

    with engine.begin() as connection:
        _create_audit_schema(connection)
        run_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO stock_allocation_integrity_runs
                        (status)
                    VALUES ('RUNNING')
                    RETURNING id
                    """
                )
            ).scalar_one()
        )

        items = _fetch_items(connection)
        available = _available_stock_map(connection)
        live_reserved = _live_reserved_stock_map(connection)
        stock_remaining = {
            code: max(0, qty - live_reserved.get(code, 0))
            for code, qty in available.items()
        }

        invalid_before = 0
        imported_recalculated = 0
        non_review_repaired = 0
        negative_stock_fixed = 0
        over_required_fixed = 0
        touched_ids: list[int] = []

        for original in items:
            row = dict(original)
            reasons = _invalid_reasons(row)
            imported_review = _is_imported_review(row)

            report_row = {
                "shipment_item_id": row["id"],
                "shipment_id": row["shipment_id"],
                "shipment_no": row["shipment_no"],
                "shipment_name": row["shipment_name"],
                "shipment_status": row["shipment_status"],
                "shipment_planning_status": (
                    row["shipment_planning_status"]
                ),
                "sap_code": row["sap_code"],
                "quantity": row["quantity"],
                "stock_allocated_qty": row[
                    "stock_allocated_qty"
                ],
                "production_required_qty": row[
                    "production_required_qty"
                ],
                "produced_qty": row["produced_qty"],
                "completed_qty": row["completed_qty"],
                "remaining_qty": row["remaining_qty"],
                "progress_pct": row["progress_pct"],
                "invalid_reasons": "|".join(reasons),
                "imported_review": imported_review,
            }

            if reasons:
                invalid_before += 1

            if reasons or imported_review:
                before_report_rows.append(report_row)

            if not imported_review and not reasons:
                continue

            qty = max(0, _int(row["quantity"]))
            produced = min(
                qty,
                max(0, _int(row["produced_qty"])),
            )
            code = normalize_sap_code(row["sap_code"])
            old_stock = _int(row["stock_allocated_qty"])
            old_required = _int(
                row["production_required_qty"]
            )

            if imported_review:
                need = max(0, qty - produced)
                available_qty = max(
                    0,
                    stock_remaining.get(code, 0),
                )
                new_stock = min(need, available_qty)
                stock_remaining[code] = max(
                    0,
                    available_qty - new_stock,
                )
                new_required = max(
                    0,
                    qty - produced - new_stock,
                )
                # Review-required shipment values are previews only.
                new_completed = min(
                    qty,
                    max(0, _int(row["completed_qty"])),
                )
                new_remaining = max(
                    0,
                    qty - new_completed,
                )
                new_progress = round(
                    (
                        new_completed
                        / qty
                        * 100
                    )
                    if qty
                    else 0.0,
                    2,
                )
                new_status = (
                    row["item_status"]
                    or "Imported Review"
                )
                new_planning_note = (
                    "Target date approval required before live "
                    "planning. Stock preview recalculated "
                    "cumulatively by integrity repair V6.2; "
                    "negative source stock is excluded."
                )
                repair_scope = "IMPORTED_REVIEW"
                imported_recalculated += 1
            else:
                need = max(0, qty - produced)
                new_stock = min(
                    need,
                    max(0, old_stock),
                )
                new_required = max(
                    0,
                    qty - produced - new_stock,
                )
                new_completed = min(
                    qty,
                    max(
                        max(
                            0,
                            _int(row["completed_qty"]),
                        ),
                        produced + new_stock,
                    ),
                )
                new_remaining = max(
                    0,
                    qty - new_completed,
                )
                new_progress = round(
                    (
                        new_completed
                        / qty
                        * 100
                    )
                    if qty
                    else 0.0,
                    2,
                )
                new_status = row["item_status"]
                new_planning_note = (
                    str(row.get("planning_note") or "")
                    + " Stock allocation invariant repaired "
                    "by V6.2."
                ).strip()
                repair_scope = "INVALID_NON_REVIEW"
                non_review_repaired += 1

            if old_stock < 0:
                negative_stock_fixed += 1
            if old_required > max(0, qty):
                over_required_fixed += 1

            connection.execute(
                text(
                    """
                    INSERT INTO
                        stock_allocation_integrity_items (
                            run_id,
                            shipment_item_id,
                            shipment_id,
                            shipment_no,
                            sap_code,
                            repair_scope,
                            reasons,
                            quantity_before,
                            stock_before,
                            required_before,
                            produced_before,
                            remaining_before,
                            quantity_after,
                            stock_after,
                            required_after,
                            produced_after,
                            remaining_after
                        )
                    VALUES (
                        :run_id,
                        :shipment_item_id,
                        :shipment_id,
                        :shipment_no,
                        :sap_code,
                        :repair_scope,
                        :reasons,
                        :quantity_before,
                        :stock_before,
                        :required_before,
                        :produced_before,
                        :remaining_before,
                        :quantity_after,
                        :stock_after,
                        :required_after,
                        :produced_after,
                        :remaining_after
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "shipment_item_id": row["id"],
                    "shipment_id": row["shipment_id"],
                    "shipment_no": row["shipment_no"],
                    "sap_code": code,
                    "repair_scope": repair_scope,
                    "reasons": "|".join(reasons),
                    "quantity_before": _int(row["quantity"]),
                    "stock_before": old_stock,
                    "required_before": old_required,
                    "produced_before": _int(
                        row["produced_qty"]
                    ),
                    "remaining_before": _int(
                        row["remaining_qty"]
                    ),
                    "quantity_after": qty,
                    "stock_after": new_stock,
                    "required_after": new_required,
                    "produced_after": produced,
                    "remaining_after": new_remaining,
                },
            )

            connection.execute(
                text(
                    """
                    UPDATE mpps_shipment_items
                    SET
                        quantity = :quantity,
                        stock_allocated_qty = :stock,
                        production_required_qty = :required,
                        produced_qty = :produced,
                        completed_qty = :completed,
                        remaining_qty = :remaining,
                        progress_pct = :progress,
                        item_status = :item_status,
                        planning_note = :planning_note,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :item_id
                    """
                ),
                {
                    "quantity": qty,
                    "stock": new_stock,
                    "required": new_required,
                    "produced": produced,
                    "completed": new_completed,
                    "remaining": new_remaining,
                    "progress": new_progress,
                    "item_status": new_status,
                    "planning_note": new_planning_note,
                    "item_id": row["id"],
                },
            )
            touched_ids.append(int(row["id"]))

        # Keep shipment header metrics consistent with their item rows.
        connection.execute(
            text(
                """
                UPDATE mpps_shipments shipment
                SET
                    total_qty = summary.total_qty,
                    completed_qty = summary.completed_qty,
                    progress_pct = summary.progress_pct,
                    updated_at = CURRENT_TIMESTAMP
                FROM (
                    SELECT
                        shipment_id,
                        COALESCE(
                            SUM(GREATEST(0, quantity)),
                            0
                        ) AS total_qty,
                        COALESCE(
                            SUM(
                                GREATEST(
                                    0,
                                    LEAST(
                                        quantity,
                                        completed_qty
                                    )
                                )
                            ),
                            0
                        ) AS completed_qty,
                        ROUND(
                            CASE
                                WHEN COALESCE(
                                    SUM(
                                        GREATEST(
                                            0,
                                            quantity
                                        )
                                    ),
                                    0
                                ) > 0
                                THEN (
                                    COALESCE(
                                        SUM(
                                            GREATEST(
                                                0,
                                                LEAST(
                                                    quantity,
                                                    completed_qty
                                                )
                                            )
                                        ),
                                        0
                                    )::NUMERIC
                                    /
                                    SUM(
                                        GREATEST(
                                            0,
                                            quantity
                                        )
                                    )
                                    * 100
                                )
                                ELSE 0
                            END,
                            2
                        ) AS progress_pct
                    FROM mpps_shipment_items
                    GROUP BY shipment_id
                ) summary
                WHERE shipment.id = summary.shipment_id
                """
            )
        )

        _add_integrity_constraints(connection)

        after_items = _fetch_items(connection)
        after_by_id = {
            int(row["id"]): row
            for row in after_items
        }
        for item_id in touched_ids:
            row = after_by_id[item_id]
            reasons = _invalid_reasons(row)
            after_report_rows.append(
                {
                    "shipment_item_id": row["id"],
                    "shipment_id": row["shipment_id"],
                    "shipment_no": row["shipment_no"],
                    "shipment_name": row["shipment_name"],
                    "shipment_status": row["shipment_status"],
                    "shipment_planning_status": (
                        row["shipment_planning_status"]
                    ),
                    "sap_code": row["sap_code"],
                    "quantity": row["quantity"],
                    "stock_allocated_qty": row[
                        "stock_allocated_qty"
                    ],
                    "production_required_qty": row[
                        "production_required_qty"
                    ],
                    "produced_qty": row["produced_qty"],
                    "completed_qty": row["completed_qty"],
                    "remaining_qty": row["remaining_qty"],
                    "progress_pct": row["progress_pct"],
                    "invalid_reasons": "|".join(reasons),
                    "imported_review": _is_imported_review(row),
                }
            )

        invalid_after = sum(
            bool(_invalid_reasons(row))
            for row in after_items
        )
        if invalid_after:
            raise RuntimeError(
                "Stock-allocation repair left "
                f"{invalid_after} invalid shipment item rows."
            )

        summary = {
            "total_shipment_items_audited": len(items),
            "invalid_rows_before": invalid_before,
            "invalid_rows_after": invalid_after,
            "imported_review_rows_recalculated": (
                imported_recalculated
            ),
            "non_review_invalid_rows_repaired": (
                non_review_repaired
            ),
            "negative_stock_allocations_fixed": (
                negative_stock_fixed
            ),
            "production_required_over_quantity_fixed": (
                over_required_fixed
            ),
            "live_reserved_sap_codes": len(live_reserved),
            "stock_master_sap_codes": len(available),
        }

        connection.execute(
            text(
                """
                UPDATE stock_allocation_integrity_runs
                SET
                    completed_at = CURRENT_TIMESTAMP,
                    status = 'COMPLETED',
                    invalid_before = :invalid_before,
                    imported_review_recalculated =
                        :imported_recalculated,
                    non_review_repaired =
                        :non_review_repaired,
                    negative_stock_fixed =
                        :negative_stock_fixed,
                    over_required_fixed =
                        :over_required_fixed,
                    summary_json =
                        CAST(:summary_json AS JSONB)
                WHERE id = :run_id
                """
            ),
            {
                "invalid_before": invalid_before,
                "imported_recalculated": imported_recalculated,
                "non_review_repaired": non_review_repaired,
                "negative_stock_fixed": negative_stock_fixed,
                "over_required_fixed": over_required_fixed,
                "summary_json": json.dumps(summary),
                "run_id": run_id,
            },
        )

    report_path = _write_reports(
        project_root,
        run_id,
        before_report_rows,
        after_report_rows,
        summary,
    )
    return run_id, report_path, summary


def main() -> int:
    project_root = Path.cwd().resolve()
    run_id, report_path, summary = run_repair(project_root)

    print("STOCK ALLOCATION INTEGRITY V6.2 REPAIR COMPLETED")
    print("REPAIR RUN:", run_id)
    for key, value in summary.items():
        print(f"{key}: {value}")
    print("AUDIT REPORT:", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
