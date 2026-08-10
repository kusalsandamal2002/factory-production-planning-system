from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import engine


REVIEW_STATUS_VALUES = (
    "imported review",
    "review required",
    "draft import",
    "excel review hold",
)


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _review_sql(alias: str = "shipment") -> str:
    return f"""
        (
            LOWER(COALESCE({alias}.status, '')) IN (
                'imported review',
                'review required',
                'draft import',
                'excel review hold'
            )
            OR LOWER(COALESCE({alias}.planning_status, ''))
                = 'review required'
            OR LOWER(COALESCE({alias}.target_date_source, ''))
                = 'excel import - date missing'
        )
    """


def _fetch_snapshot(connection) -> list[dict[str, Any]]:
    review_sql = _review_sql("shipment")
    rows = connection.execute(
        text(
            f"""
            WITH item_rollup AS (
                SELECT
                    shipment_id,
                    COUNT(*) AS item_count,
                    COALESCE(SUM(quantity), 0) AS total_qty,
                    COALESCE(SUM(stock_allocated_qty), 0)
                        AS stock_allocated_qty,
                    COALESCE(SUM(production_required_qty), 0)
                        AS production_required_qty,
                    COALESCE(SUM(produced_qty), 0)
                        AS produced_qty,
                    COALESCE(SUM(completed_qty), 0)
                        AS completed_qty,
                    COALESCE(SUM(remaining_qty), 0)
                        AS remaining_qty,
                    COUNT(*) FILTER (
                        WHERE COALESCE(quantity, 0) > 0
                          AND COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                              ) IS NULL
                    ) AS missing_receive_count,
                    MIN(
                        COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date,
                            start_date
                        )
                    ) AS first_receive_date,
                    MAX(
                        COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date,
                            start_date
                        )
                    ) AS latest_receive_date
                FROM mpps_shipment_items
                GROUP BY shipment_id
            )
            SELECT
                shipment.id,
                shipment.shipment_no,
                shipment.shipment_name,
                shipment.status,
                shipment.planning_status,
                shipment.target_date,
                shipment.plan_date,
                shipment.manager_order_date,
                shipment.shipment_date,
                shipment.target_date_is_manual,
                shipment.target_date_source,
                shipment.factory_can_receive_date,
                shipment.factory_out_date,
                shipment.delivery_status,
                shipment.delay_days,
                shipment.early_days,
                shipment.total_qty AS header_total_qty,
                shipment.completed_qty AS header_completed_qty,
                shipment.progress_pct AS header_progress_pct,
                shipment.last_replanned_at,
                {review_sql} AS review_required,
                COALESCE(item_rollup.item_count, 0)
                    AS item_count,
                COALESCE(item_rollup.total_qty, 0)
                    AS item_total_qty,
                COALESCE(item_rollup.stock_allocated_qty, 0)
                    AS item_stock_allocated_qty,
                COALESCE(item_rollup.production_required_qty, 0)
                    AS item_production_required_qty,
                COALESCE(item_rollup.produced_qty, 0)
                    AS item_produced_qty,
                COALESCE(item_rollup.completed_qty, 0)
                    AS item_completed_qty,
                COALESCE(item_rollup.remaining_qty, 0)
                    AS item_remaining_qty,
                COALESCE(item_rollup.missing_receive_count, 0)
                    AS missing_receive_count,
                item_rollup.first_receive_date,
                item_rollup.latest_receive_date
            FROM mpps_shipments shipment
            LEFT JOIN item_rollup
              ON item_rollup.shipment_id = shipment.id
            ORDER BY shipment.id
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _table_exists(connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{table_name}"},
        ).scalar_one()
    )


def _create_schema(connection) -> None:
    for statement in [
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS target_date DATE",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS plan_date DATE",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS manager_order_date DATE",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS target_date_is_manual BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS target_date_source VARCHAR(80) NOT NULL DEFAULT 'Automatic Factory Receive'",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_can_receive_date DATE",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_date DATE",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(80) NOT NULL DEFAULT ''",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS delay_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS early_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS total_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS completed_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS progress_pct NUMERIC(8,2) NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS planning_status VARCHAR(80) NOT NULL DEFAULT ''",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS planning_note TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS last_replanned_at TIMESTAMP",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS stock_allocated_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_required_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS produced_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS completed_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS remaining_qty INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS progress_pct NUMERIC(8,2) NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS allocated_cavity_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS allocated_cavities INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS daily_capacity INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS receive_date DATE",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS item_receive_date DATE",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS planning_note TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS schedule_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS factory_out_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS planning_version BIGINT NOT NULL DEFAULT 0",
    ]:
        connection.execute(text(statement))

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS delivery_date_integrity_runs (
                id BIGSERIAL PRIMARY KEY,
                started_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
                shipments_audited INTEGER NOT NULL DEFAULT 0,
                false_on_time_before INTEGER NOT NULL DEFAULT 0,
                unresolved_review_repaired INTEGER NOT NULL DEFAULT 0,
                prior_manual_approvals_promoted INTEGER NOT NULL DEFAULT 0,
                headers_pending_after INTEGER NOT NULL DEFAULT 0,
                summary_json JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS delivery_date_integrity_rows (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL
                    REFERENCES delivery_date_integrity_runs(id)
                    ON DELETE CASCADE,
                shipment_id INTEGER NOT NULL,
                shipment_no TEXT NOT NULL DEFAULT '',
                issue_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (run_id, shipment_id)
            )
            """
        )
    )


def _add_delivery_constraints(connection) -> None:
    statements = [
        (
            "ck_mpps_shipments_delay_days_v63",
            "COALESCE(delay_days, 0) >= 0",
        ),
        (
            "ck_mpps_shipments_early_days_v63",
            "COALESCE(early_days, 0) >= 0",
        ),
        (
            "ck_mpps_shipments_progress_v63",
            "COALESCE(progress_pct, 0) >= 0 "
            "AND COALESCE(progress_pct, 0) <= 100",
        ),
        (
            "ck_mpps_shipments_on_time_dates_v63",
            "LOWER(COALESCE(delivery_status, '')) <> 'on time' "
            "OR (target_date IS NOT NULL "
            "AND factory_can_receive_date IS NOT NULL "
            "AND factory_can_receive_date = target_date)",
        ),
        (
            "ck_mpps_shipments_early_dates_v63",
            "LOWER(COALESCE(delivery_status, '')) "
            "<> 'can deliver early' "
            "OR (target_date IS NOT NULL "
            "AND factory_can_receive_date IS NOT NULL "
            "AND factory_can_receive_date < target_date)",
        ),
        (
            "ck_mpps_shipments_delayed_dates_v63",
            "LOWER(COALESCE(delivery_status, '')) <> 'delayed' "
            "OR (target_date IS NOT NULL "
            "AND factory_can_receive_date IS NOT NULL "
            "AND factory_can_receive_date > target_date)",
        ),
    ]
    for name, expression in statements:
        connection.execute(
            text(
                f"""
                DO $$
                BEGIN
                    ALTER TABLE mpps_shipments
                    ADD CONSTRAINT {name}
                    CHECK ({expression});
                EXCEPTION
                    WHEN duplicate_object THEN NULL;
                END
                $$;
                """
            )
        )


def _issue_codes(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    review = bool(row.get("review_required"))
    target = row.get("target_date")
    factory = row.get("factory_can_receive_date")
    delivery = str(row.get("delivery_status") or "").strip().lower()
    missing = int(row.get("missing_receive_count") or 0)

    if review and target is not None:
        issues.append("UNAPPROVED_TARGET_PRESENT")
    if review and factory is not None:
        issues.append("UNAPPROVED_FACTORY_RECEIVE_PRESENT")
    if review and delivery in {
        "on time",
        "can deliver early",
        "delayed",
    }:
        issues.append("FALSE_DELIVERY_PROMISE_DURING_REVIEW")
    if missing > 0 and factory is not None:
        issues.append("HEADER_RECEIVE_WITH_MISSING_ITEM_DATES")
    if target is not None and factory is not None and delivery == "on time":
        if missing > 0 or review:
            issues.append("FALSE_ON_TIME")
    if row.get("plan_date") == row.get("target_date") and review:
        issues.append("WORKBOOK_DATE_PROMOTED_TO_TARGET")
    if (
        int(row.get("header_total_qty") or 0)
        != int(row.get("item_total_qty") or 0)
    ):
        issues.append("HEADER_TOTAL_MISMATCH")
    if (
        int(row.get("header_completed_qty") or 0)
        != int(row.get("item_completed_qty") or 0)
    ):
        issues.append("HEADER_COMPLETED_MISMATCH")
    return issues


def _write_report(
    report_dir: Path,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    after_by_id = {int(row["id"]): row for row in after}

    fieldnames = [
        "shipment_id",
        "shipment_no",
        "issue_codes",
        "before_status",
        "before_planning_status",
        "before_target_date",
        "before_factory_receive",
        "before_delivery_status",
        "before_missing_item_dates",
        "after_status",
        "after_planning_status",
        "after_target_date",
        "after_factory_receive",
        "after_delivery_status",
        "after_missing_item_dates",
    ]
    with (report_dir / "delivery_date_audit.csv").open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for old in before:
            new = after_by_id[int(old["id"])]
            issues = _issue_codes(old)
            writer.writerow(
                {
                    "shipment_id": old["id"],
                    "shipment_no": old["shipment_no"],
                    "issue_codes": ";".join(issues),
                    "before_status": old["status"],
                    "before_planning_status": old["planning_status"],
                    "before_target_date": old["target_date"],
                    "before_factory_receive": old[
                        "factory_can_receive_date"
                    ],
                    "before_delivery_status": old["delivery_status"],
                    "before_missing_item_dates": old[
                        "missing_receive_count"
                    ],
                    "after_status": new["status"],
                    "after_planning_status": new["planning_status"],
                    "after_target_date": new["target_date"],
                    "after_factory_receive": new[
                        "factory_can_receive_date"
                    ],
                    "after_delivery_status": new["delivery_status"],
                    "after_missing_item_dates": new[
                        "missing_receive_count"
                    ],
                }
            )

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    (report_dir / "README.txt").write_text(
        "MPPS Delivery Date Integrity V6.3\n"
        "=================================\n\n"
        "The report compares shipment header delivery values before and "
        "after repair. Workbook snapshot dates are not customer target "
        "dates. REVIEW REQUIRED shipments remain pending until a manual "
        "target date is approved. A shipment-level receive date is shown "
        "only when every positive-quantity item has a receive date.\n",
        encoding="utf-8",
    )


def repair(project_root: Path) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (
        project_root
        / "reports"
        / f"delivery_date_integrity_v6_3_{timestamp}"
    )

    with engine.begin() as connection:
        _create_schema(connection)
        run_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO delivery_date_integrity_runs(status)
                    VALUES ('RUNNING')
                    RETURNING id
                    """
                )
            ).scalar_one()
        )

        before = _fetch_snapshot(connection)
        issue_map = {
            int(row["id"]): _issue_codes(row)
            for row in before
        }
        false_on_time_before = sum(
            "FALSE_ON_TIME" in issues
            or "FALSE_DELIVERY_PROMISE_DURING_REVIEW" in issues
            for issues in issue_map.values()
        )

        for row in before:
            connection.execute(
                text(
                    """
                    INSERT INTO delivery_date_integrity_rows (
                        run_id,
                        shipment_id,
                        shipment_no,
                        issue_codes,
                        before_json
                    )
                    VALUES (
                        :run_id,
                        :shipment_id,
                        :shipment_no,
                        :issue_codes,
                        CAST(:before_json AS JSONB)
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "shipment_id": int(row["id"]),
                    "shipment_no": str(row.get("shipment_no") or ""),
                    "issue_codes": issue_map[int(row["id"])],
                    "before_json": _json(row),
                },
            )

        # Repair item arithmetic invariants. Production required means the
        # physical quantity still requiring production after valid stock and
        # already-produced quantity are considered.
        connection.execute(
            text(
                """
                UPDATE mpps_shipment_items
                SET
                    quantity = GREATEST(0, COALESCE(quantity, 0)),
                    stock_allocated_qty = GREATEST(
                        0,
                        LEAST(
                            GREATEST(0, COALESCE(quantity, 0)),
                            COALESCE(stock_allocated_qty, 0)
                        )
                    ),
                    produced_qty = GREATEST(
                        0,
                        LEAST(
                            GREATEST(0, COALESCE(quantity, 0)),
                            COALESCE(produced_qty, 0)
                        )
                    ),
                    completed_qty = GREATEST(
                        0,
                        LEAST(
                            GREATEST(0, COALESCE(quantity, 0)),
                            GREATEST(
                                0,
                                LEAST(
                                    GREATEST(0, COALESCE(quantity, 0)),
                                    COALESCE(stock_allocated_qty, 0)
                                )
                            )
                            + GREATEST(
                                0,
                                LEAST(
                                    GREATEST(0, COALESCE(quantity, 0)),
                                    COALESCE(produced_qty, 0)
                                )
                            )
                        )
                    ),
                    production_required_qty = GREATEST(
                        0,
                        GREATEST(0, COALESCE(quantity, 0))
                        - GREATEST(
                            0,
                            LEAST(
                                GREATEST(0, COALESCE(quantity, 0)),
                                COALESCE(stock_allocated_qty, 0)
                            )
                        )
                        - GREATEST(
                            0,
                            LEAST(
                                GREATEST(0, COALESCE(quantity, 0)),
                                COALESCE(produced_qty, 0)
                            )
                        )
                    ),
                    remaining_qty = GREATEST(
                        0,
                        GREATEST(0, COALESCE(quantity, 0))
                        - GREATEST(
                            0,
                            LEAST(
                                GREATEST(0, COALESCE(quantity, 0)),
                                GREATEST(
                                    0,
                                    LEAST(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        ),
                                        COALESCE(
                                            stock_allocated_qty,
                                            0
                                        )
                                    )
                                )
                                + GREATEST(
                                    0,
                                    LEAST(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        ),
                                        COALESCE(produced_qty, 0)
                                    )
                                )
                            )
                        )
                    ),
                    progress_pct = CASE
                        WHEN GREATEST(0, COALESCE(quantity, 0)) > 0
                        THEN ROUND(
                            (
                                GREATEST(
                                    0,
                                    LEAST(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        ),
                                        GREATEST(
                                            0,
                                            COALESCE(
                                                stock_allocated_qty,
                                                0
                                            )
                                        )
                                        + GREATEST(
                                            0,
                                            COALESCE(produced_qty, 0)
                                        )
                                    )
                                )::NUMERIC
                                / GREATEST(
                                    0,
                                    COALESCE(quantity, 0)
                                )
                            ) * 100,
                            2
                        )
                        ELSE 0
                    END,
                    updated_at = CURRENT_TIMESTAMP
                """
            )
        )

        # Old versions saved a manual date but failed to move the imported
        # shipment out of REVIEW REQUIRED. Treat a real manual target as the
        # user's approval and place the shipment into the planner queue.
        promoted_rows = connection.execute(
            text(
                f"""
                WITH candidates AS (
                    SELECT id
                    FROM mpps_shipments shipment
                    WHERE {_review_sql("shipment")}
                      AND COALESCE(
                            shipment.target_date_is_manual,
                            FALSE
                          ) = TRUE
                      AND shipment.target_date IS NOT NULL
                      AND LOWER(
                            COALESCE(
                                shipment.target_date_source,
                                ''
                            )
                          ) LIKE 'manual%'
                )
                UPDATE mpps_shipments shipment
                SET
                    status = 'Planned',
                    planning_status = 'Pending Replan',
                    planning_note =
                        'Previously entered manual target date '
                        'recognized as imported-shipment approval.',
                    plan_date = shipment.target_date,
                    factory_can_receive_date = NULL,
                    factory_out_date = NULL,
                    delivery_status = 'Pending Planning',
                    delay_days = 0,
                    early_days = 0,
                    last_replanned_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                FROM candidates
                WHERE shipment.id = candidates.id
                RETURNING shipment.id
                """
            )
        ).scalars().all()
        promoted = len(promoted_rows)

        if promoted:
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipment_items item
                    SET
                        start_date = NULL,
                        end_date = NULL,
                        item_status = 'Pending',
                        allocated_cavity_count = 0,
                        allocated_cavities = 0,
                        daily_capacity = 0,
                        production_days = 0,
                        receive_date = NULL,
                        item_receive_date = NULL,
                        planning_note =
                            'Target approved; waiting for cumulative '
                            'resource planning.',
                        schedule_reason =
                            'Target approved; waiting for cumulative '
                            'resource planning.',
                        factory_out_reason = '',
                        planning_version = 0,
                        updated_at = CURRENT_TIMESTAMP
                    FROM mpps_shipments shipment
                    WHERE item.shipment_id = shipment.id
                      AND shipment.status = 'Planned'
                      AND shipment.planning_status = 'Pending Replan'
                      AND shipment.planning_note LIKE
                            'Previously entered manual target date%'
                    """
                )
            )

        review_sql = _review_sql("shipment")
        unresolved_review_count = int(
            connection.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM mpps_shipments shipment
                    WHERE {review_sql}
                    """
                )
            ).scalar_one()
            or 0
        )

        # Restore unresolved Excel imports to their correct semantic state.
        connection.execute(
            text(
                f"""
                UPDATE mpps_shipments shipment
                SET
                    status = 'Imported Review',
                    target_date = NULL,
                    plan_date = shipment.shipment_date,
                    manager_order_date = NULL,
                    target_date_is_manual = FALSE,
                    target_date_source =
                        'Excel Import - Date Missing',
                    factory_can_receive_date = NULL,
                    factory_out_date = NULL,
                    delivery_status = 'Review Required',
                    delay_days = 0,
                    early_days = 0,
                    planning_status = 'REVIEW REQUIRED',
                    planning_note =
                        'Imported shipment snapshot; a manual target '
                        'date must be approved before live planning.',
                    last_replanned_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE {review_sql}
                """
            )
        )
        connection.execute(
            text(
                f"""
                UPDATE mpps_shipment_items item
                SET
                    start_date = NULL,
                    end_date = NULL,
                    item_status = 'Imported Review',
                    allocated_cavity_count = 0,
                    allocated_cavities = 0,
                    daily_capacity = 0,
                    production_days = 0,
                    receive_date = NULL,
                    item_receive_date = NULL,
                    planning_note =
                        'Target date approval required before live planning.',
                    schedule_reason =
                        'Target date approval required before live planning.',
                    factory_out_reason =
                        'Target date approval required before live planning.',
                    planning_version = 0,
                    updated_at = CURRENT_TIMESTAMP
                FROM mpps_shipments shipment
                WHERE item.shipment_id = shipment.id
                  AND {review_sql}
                """
            )
        )

        resource_reservations_removed = 0
        review_stock_reservations_removed = 0
        review_cavity_rows_removed = 0

        if _table_exists(
            connection,
            "planning_resource_reservations",
        ):
            result = connection.execute(
                text(
                    f"""
                    DELETE FROM planning_resource_reservations reservation
                    USING mpps_shipment_items item,
                          mpps_shipments shipment
                    WHERE reservation.shipment_item_id = item.id
                      AND item.shipment_id = shipment.id
                      AND (
                            {_review_sql("shipment")}
                            OR (
                                LOWER(
                                    COALESCE(item.item_status, '')
                                ) IN (
                                    'blocked',
                                    'unplanned',
                                    'failed',
                                    'error'
                                )
                                AND COALESCE(
                                    item.item_receive_date,
                                    item.receive_date,
                                    item.end_date,
                                    item.start_date
                                ) IS NULL
                            )
                          )
                    """
                )
            )
            resource_reservations_removed = max(
                0,
                int(result.rowcount or 0),
            )

        if _table_exists(
            connection,
            "shipment_stock_allocations",
        ):
            result = connection.execute(
                text(
                    f"""
                    DELETE FROM shipment_stock_allocations allocation
                    USING mpps_shipments shipment
                    WHERE allocation.shipment_id = shipment.id
                      AND {_review_sql("shipment")}
                    """
                )
            )
            review_stock_reservations_removed = max(
                0,
                int(result.rowcount or 0),
            )

        if _table_exists(
            connection,
            "mpps_cavity_plan_rows",
        ):
            result = connection.execute(
                text(
                    f"""
                    DELETE FROM mpps_cavity_plan_rows plan_row
                    USING mpps_shipments shipment
                    WHERE plan_row.shipment_id = shipment.id
                      AND {_review_sql("shipment")}
                    """
                )
            )
            review_cavity_rows_removed = max(
                0,
                int(result.rowcount or 0),
            )

        # Synchronize shipment totals and derive a header receive date only
        # when every positive-quantity item has a verified date.
        connection.execute(
            text(
                f"""
                WITH item_rollup AS (
                    SELECT
                        shipment_id,
                        COUNT(*) FILTER (
                            WHERE COALESCE(quantity, 0) > 0
                        ) AS positive_item_count,
                        COUNT(*) FILTER (
                            WHERE COALESCE(quantity, 0) > 0
                              AND COALESCE(
                                    item_receive_date,
                                    receive_date,
                                    end_date,
                                    start_date
                                  ) IS NULL
                        ) AS missing_receive_count,
                        COALESCE(SUM(quantity), 0) AS total_qty,
                        COALESCE(SUM(completed_qty), 0)
                            AS completed_qty,
                        MAX(
                            COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                            )
                        ) AS latest_receive_date
                    FROM mpps_shipment_items
                    GROUP BY shipment_id
                ),
                calculated AS (
                    SELECT
                        shipment.id,
                        {review_sql} AS review_required,
                        shipment.target_date,
                        COALESCE(item_rollup.total_qty, 0)
                            AS total_qty,
                        COALESCE(item_rollup.completed_qty, 0)
                            AS completed_qty,
                        CASE
                            WHEN COALESCE(item_rollup.total_qty, 0) > 0
                            THEN ROUND(
                                (
                                    COALESCE(
                                        item_rollup.completed_qty,
                                        0
                                    )::NUMERIC
                                    / item_rollup.total_qty
                                ) * 100,
                                2
                            )
                            ELSE 0
                        END AS progress_pct,
                        CASE
                            WHEN {review_sql}
                            THEN NULL
                            WHEN COALESCE(
                                item_rollup.positive_item_count,
                                0
                            ) <= 0
                            THEN NULL
                            WHEN COALESCE(
                                item_rollup.missing_receive_count,
                                0
                            ) > 0
                            THEN NULL
                            ELSE item_rollup.latest_receive_date
                        END AS verified_receive
                    FROM mpps_shipments shipment
                    LEFT JOIN item_rollup
                      ON item_rollup.shipment_id = shipment.id
                )
                UPDATE mpps_shipments shipment
                SET
                    total_qty = calculated.total_qty,
                    completed_qty = calculated.completed_qty,
                    progress_pct = calculated.progress_pct,
                    factory_can_receive_date =
                        calculated.verified_receive,
                    factory_out_date =
                        calculated.verified_receive,
                    delivery_status = CASE
                        WHEN calculated.review_required
                        THEN 'Review Required'
                        WHEN calculated.target_date IS NULL
                        THEN 'Pending Target'
                        WHEN calculated.verified_receive IS NULL
                        THEN 'Pending Planning'
                        WHEN calculated.verified_receive
                            < calculated.target_date
                        THEN 'Can Deliver Early'
                        WHEN calculated.verified_receive
                            = calculated.target_date
                        THEN 'On Time'
                        ELSE 'Delayed'
                    END,
                    delay_days = CASE
                        WHEN calculated.target_date IS NOT NULL
                         AND calculated.verified_receive
                                > calculated.target_date
                        THEN (
                            calculated.verified_receive
                            - calculated.target_date
                        )
                        ELSE 0
                    END,
                    early_days = CASE
                        WHEN calculated.target_date IS NOT NULL
                         AND calculated.verified_receive
                                < calculated.target_date
                        THEN (
                            calculated.target_date
                            - calculated.verified_receive
                        )
                        ELSE 0
                    END,
                    updated_at = CURRENT_TIMESTAMP
                FROM calculated
                WHERE shipment.id = calculated.id
                """
            )
        )

        _add_delivery_constraints(connection)

        after = _fetch_snapshot(connection)
        after_by_id = {int(row["id"]): row for row in after}
        for old in before:
            new = after_by_id[int(old["id"])]
            connection.execute(
                text(
                    """
                    UPDATE delivery_date_integrity_rows
                    SET after_json = CAST(:after_json AS JSONB)
                    WHERE run_id = :run_id
                      AND shipment_id = :shipment_id
                    """
                ),
                {
                    "run_id": run_id,
                    "shipment_id": int(old["id"]),
                    "after_json": _json(new),
                },
            )

        pending_after = sum(
            str(row.get("delivery_status") or "").lower()
            in {
                "review required",
                "pending target",
                "pending planning",
            }
            for row in after
        )
        false_after = sum(
            "FALSE_ON_TIME" in _issue_codes(row)
            or "FALSE_DELIVERY_PROMISE_DURING_REVIEW"
                in _issue_codes(row)
            for row in after
        )
        summary = {
            "run_id": run_id,
            "shipments_audited": len(before),
            "false_on_time_before": false_on_time_before,
            "false_on_time_after": false_after,
            "unresolved_review_repaired": unresolved_review_count,
            "prior_manual_approvals_promoted": promoted,
            "headers_pending_after": pending_after,
            "resource_reservations_removed":
                resource_reservations_removed,
            "review_stock_reservations_removed":
                review_stock_reservations_removed,
            "review_cavity_rows_removed":
                review_cavity_rows_removed,
            "report_directory": str(report_dir),
        }
        if false_after:
            raise RuntimeError(
                f"Delivery integrity repair left {false_after} false "
                "delivery promises."
            )

        connection.execute(
            text(
                """
                UPDATE delivery_date_integrity_runs
                SET
                    completed_at = CURRENT_TIMESTAMP,
                    status = 'COMPLETED',
                    shipments_audited = :shipments_audited,
                    false_on_time_before = :false_on_time_before,
                    unresolved_review_repaired =
                        :unresolved_review_repaired,
                    prior_manual_approvals_promoted =
                        :prior_manual_approvals_promoted,
                    headers_pending_after =
                        :headers_pending_after,
                    summary_json = CAST(:summary_json AS JSONB)
                WHERE id = :run_id
                """
            ),
            {
                **summary,
                "summary_json": _json(summary),
            },
        )

    _write_report(report_dir, before, after, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
    )
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    summary = repair(project_root)
    print("DELIVERY DATE INTEGRITY V6.3 REPAIR COMPLETED")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
