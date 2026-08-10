from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import engine


AUTO_TARGET_SOURCE = "Auto Earliest Feasible Factory Out"


def _json(value: Any) -> str:
    return json.dumps(
        value,
        default=str,
        ensure_ascii=False,
    )


def _table_exists(connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT to_regclass(:table_name) IS NOT NULL"
            ),
            {
                "table_name": (
                    f"public.{table_name}"
                )
            },
        ).scalar_one()
    )


def _legacy_review_sql(alias: str = "shipment") -> str:
    return f"""
        (
            LOWER(COALESCE({alias}.status, '')) IN (
                'imported review',
                'review required',
                'draft import',
                'excel review hold'
            )
            OR LOWER(
                COALESCE(
                    {alias}.planning_status,
                    ''
                )
            ) = 'review required'
            OR LOWER(
                COALESCE(
                    {alias}.target_date_source,
                    ''
                )
            ) = 'excel import - date missing'
        )
    """


def _ensure_schema(connection) -> None:
    for statement in [
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS target_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS plan_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS manager_order_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS target_date_is_manual "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS target_date_source "
            "VARCHAR(120) NOT NULL DEFAULT "
            "'Auto Earliest Feasible Factory Out'"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS "
            "factory_can_receive_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS factory_out_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS dispatch_buffer_days "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS delivery_status "
            "VARCHAR(80) NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS delay_days "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS early_days "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS planning_status "
            "VARCHAR(80) NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS planning_note "
            "TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipments "
            "ADD COLUMN IF NOT EXISTS last_replanned_at "
            "TIMESTAMP"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS item_status "
            "VARCHAR(80) NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS "
            "allocated_cavity_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS allocated_cavities "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS daily_capacity "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS production_days "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS receive_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS item_receive_date DATE"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS planning_note "
            "TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS schedule_reason "
            "TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS factory_out_reason "
            "TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE mpps_shipment_items "
            "ADD COLUMN IF NOT EXISTS planning_version "
            "BIGINT NOT NULL DEFAULT 0"
        ),
    ]:
        connection.execute(text(statement))

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS
            auto_target_scheduling_runs (
                id BIGSERIAL PRIMARY KEY,
                started_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status VARCHAR(30) NOT NULL
                    DEFAULT 'RUNNING',
                shipments_audited INTEGER NOT NULL
                    DEFAULT 0,
                legacy_review_promoted INTEGER NOT NULL
                    DEFAULT 0,
                automatic_sources_normalized INTEGER NOT NULL
                    DEFAULT 0,
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
            auto_target_scheduling_rows (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL
                    REFERENCES auto_target_scheduling_runs(id)
                    ON DELETE CASCADE,
                shipment_id INTEGER NOT NULL,
                shipment_no TEXT NOT NULL DEFAULT '',
                before_json JSONB NOT NULL
                    DEFAULT '{}'::jsonb,
                after_json JSONB NOT NULL
                    DEFAULT '{}'::jsonb,
                action_text TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    connection.execute(
        text(
            """
            UPDATE mpps_shipments
            SET dispatch_buffer_days = GREATEST(
                0,
                COALESCE(dispatch_buffer_days, 0)
            )
            """
        )
    )

    connection.execute(
        text(
            """
            ALTER TABLE mpps_shipments
            DROP CONSTRAINT IF EXISTS
            ck_mpps_shipments_dispatch_buffer_nonnegative
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE mpps_shipments
            ADD CONSTRAINT
            ck_mpps_shipments_dispatch_buffer_nonnegative
            CHECK (dispatch_buffer_days >= 0)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS
            ix_mpps_shipments_target_source
            ON mpps_shipments(target_date_source)
            """
        )
    )


def _fetch_shipments(
    connection,
    shipment_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    where_sql = ""
    params: dict[str, Any] = {}
    if shipment_ids is not None:
        if not shipment_ids:
            return []
        where_sql = "WHERE shipment.id = ANY(:shipment_ids)"
        params["shipment_ids"] = shipment_ids

    rows = connection.execute(
        text(
            f"""
            WITH item_rollup AS (
                SELECT
                    shipment_id,
                    COUNT(*) AS item_count,
                    COALESCE(
                        SUM(
                            GREATEST(
                                0,
                                COALESCE(quantity, 0)
                            )
                        ),
                        0
                    ) AS total_qty,
                    COUNT(*) FILTER (
                        WHERE COALESCE(quantity, 0) > 0
                          AND COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                              ) IS NULL
                    ) AS missing_receive_count,
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
                shipment.shipment_date,
                shipment.target_date_is_manual,
                shipment.target_date_source,
                shipment.dispatch_buffer_days,
                shipment.factory_can_receive_date,
                shipment.factory_out_date,
                shipment.delivery_status,
                shipment.delay_days,
                shipment.early_days,
                shipment.planning_note,
                shipment.last_replanned_at,
                COALESCE(
                    item_rollup.item_count,
                    0
                ) AS item_count,
                COALESCE(
                    item_rollup.total_qty,
                    0
                ) AS item_total_qty,
                COALESCE(
                    item_rollup.missing_receive_count,
                    0
                ) AS missing_receive_count,
                item_rollup.latest_receive_date
            FROM mpps_shipments shipment
            LEFT JOIN item_rollup
              ON item_rollup.shipment_id = shipment.id
            {where_sql}
            ORDER BY shipment.id
            """
        ),
        params,
    ).mappings().all()
    return [
        dict(row)
        for row in rows
    ]


def _write_report(
    project_root: Path,
    run_id: int,
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> Path:
    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_root = (
        project_root
        / "reports"
        / f"auto_target_scheduling_v6_4_{stamp}"
    )
    report_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    after_by_id = {
        int(row["id"]): row
        for row in after_rows
    }
    csv_path = (
        report_root
        / "auto_target_migration.csv"
    )
    fieldnames = [
        "shipment_id",
        "shipment_no",
        "before_status",
        "after_status",
        "before_planning_status",
        "after_planning_status",
        "before_target_date",
        "after_target_date",
        "before_target_source",
        "after_target_source",
        "before_factory_out",
        "after_factory_out",
    ]
    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        for before in before_rows:
            after = after_by_id.get(
                int(before["id"]),
                {},
            )
            writer.writerow(
                {
                    "shipment_id": before["id"],
                    "shipment_no": before.get(
                        "shipment_no"
                    ),
                    "before_status": before.get(
                        "status"
                    ),
                    "after_status": after.get(
                        "status"
                    ),
                    "before_planning_status": (
                        before.get(
                            "planning_status"
                        )
                    ),
                    "after_planning_status": (
                        after.get(
                            "planning_status"
                        )
                    ),
                    "before_target_date": before.get(
                        "target_date"
                    ),
                    "after_target_date": after.get(
                        "target_date"
                    ),
                    "before_target_source": (
                        before.get(
                            "target_date_source"
                        )
                    ),
                    "after_target_source": (
                        after.get(
                            "target_date_source"
                        )
                    ),
                    "before_factory_out": before.get(
                        "factory_out_date"
                    ),
                    "after_factory_out": after.get(
                        "factory_out_date"
                    ),
                }
            )

    (
        report_root
        / "summary.json"
    ).write_text(
        json.dumps(
            {
                "run_id": run_id,
                **summary,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    (
        report_root
        / "README.txt"
    ).write_text(
        (
            "AUTO FACTORY-OUT TARGET SCHEDULING V6.4\n"
            "=======================================\n\n"
            "Legacy Excel review shipments without a target date were "
            "promoted to the active planning queue. The global planner "
            "will calculate the earliest feasible Factory Can Out date "
            "and save it as an editable Auto Target.\n\n"
            "Manual and approved Excel targets remain locked and keep "
            "priority over auto-target shipments.\n"
        ),
        encoding="utf-8",
    )
    return report_root


def run(project_root: Path) -> dict[str, Any]:
    legacy_review_sql = _legacy_review_sql(
        "shipment"
    )
    with engine.begin() as connection:
        connection.execute(
            text("SET LOCAL lock_timeout = '10s'")
        )
        connection.execute(
            text(
                "SET LOCAL statement_timeout = '120s'"
            )
        )
        _ensure_schema(connection)

        all_before = _fetch_shipments(
            connection
        )
        run_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO auto_target_scheduling_runs (
                        shipments_audited
                    )
                    VALUES (:shipments_audited)
                    RETURNING id
                    """
                ),
                {
                    "shipments_audited": len(
                        all_before
                    )
                },
            ).scalar_one()
        )

        legacy_rows = connection.execute(
            text(
                f"""
                SELECT shipment.id
                FROM mpps_shipments shipment
                WHERE {legacy_review_sql}
                ORDER BY shipment.id
                """
            )
        ).scalars().all()
        legacy_ids = [
            int(value)
            for value in legacy_rows
        ]
        legacy_before = _fetch_shipments(
            connection,
            legacy_ids,
        )
        auto_review_ids = [
            int(row["id"])
            for row in legacy_before
            if (
                not bool(
                    row.get(
                        "target_date_is_manual"
                    )
                )
                or row.get("target_date")
                is None
            )
        ]
        manual_review_ids = [
            int(row["id"])
            for row in legacy_before
            if (
                bool(
                    row.get(
                        "target_date_is_manual"
                    )
                )
                and row.get("target_date")
                is not None
            )
        ]

        if legacy_ids:
            if _table_exists(
                connection,
                "planning_resource_reservations",
            ):
                connection.execute(
                    text(
                        """
                        DELETE FROM
                        planning_resource_reservations
                        WHERE shipment_id = ANY(:shipment_ids)
                        """
                    ),
                    {
                        "shipment_ids": legacy_ids
                    },
                )
            if _table_exists(
                connection,
                "shipment_stock_allocations",
            ):
                connection.execute(
                    text(
                        """
                        DELETE FROM
                        shipment_stock_allocations
                        WHERE shipment_id = ANY(:shipment_ids)
                        """
                    ),
                    {
                        "shipment_ids": legacy_ids
                    },
                )

            connection.execute(
                text(
                    """
                    UPDATE mpps_shipment_items
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
                            'Auto Target scheduling requested.',
                        schedule_reason =
                            'Waiting for cumulative auto scheduling.',
                        factory_out_reason = '',
                        planning_version = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE shipment_id = ANY(:shipment_ids)
                    """
                ),
                {
                    "shipment_ids": legacy_ids
                },
            )
            if auto_review_ids:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            status = 'Planned',
                            target_date = NULL,
                            plan_date = COALESCE(
                                shipment_date,
                                CURRENT_DATE
                            ),
                            target_date_is_manual = FALSE,
                            target_date_source =
                                :auto_target_source,
                            dispatch_buffer_days = GREATEST(
                                0,
                                COALESCE(
                                    dispatch_buffer_days,
                                    0
                                )
                            ),
                            factory_can_receive_date = NULL,
                            factory_out_date = NULL,
                            delivery_status =
                                'Pending Planning',
                            delay_days = 0,
                            early_days = 0,
                            planning_status =
                                'Pending Replan',
                            planning_note =
                                'Excel target date missing; earliest '
                                'feasible Factory Can Out scheduling '
                                'requested.',
                            last_replanned_at = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ANY(:shipment_ids)
                        """
                    ),
                    {
                        "shipment_ids": (
                            auto_review_ids
                        ),
                        "auto_target_source": (
                            AUTO_TARGET_SOURCE
                        ),
                    },
                )

            if manual_review_ids:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            status = 'Planned',
                            plan_date = target_date,
                            target_date_is_manual = TRUE,
                            target_date_source =
                                'Manual Approved',
                            factory_can_receive_date = NULL,
                            factory_out_date = NULL,
                            delivery_status =
                                'Pending Planning',
                            delay_days = 0,
                            early_days = 0,
                            planning_status =
                                'Pending Replan',
                            planning_note =
                                'Previously approved manual target '
                                'promoted to active planning.',
                            last_replanned_at = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ANY(:shipment_ids)
                        """
                    ),
                    {
                        "shipment_ids": (
                            manual_review_ids
                        )
                    },
                )

        normalized_count = int(
            connection.execute(
                text(
                    """
                    WITH changed AS (
                        UPDATE mpps_shipments
                        SET
                            target_date_source =
                                :auto_target_source,
                            target_date_is_manual = FALSE,
                            dispatch_buffer_days =
                                GREATEST(
                                    0,
                                    COALESCE(
                                        dispatch_buffer_days,
                                        0
                                    )
                                ),
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE NOT COALESCE(
                                target_date_is_manual,
                                FALSE
                              )
                          AND (
                                LOWER(
                                    COALESCE(
                                        target_date_source,
                                        ''
                                    )
                                ) LIKE 'auto%'
                                OR LOWER(
                                    COALESCE(
                                        target_date_source,
                                        ''
                                    )
                                ) LIKE 'automatic%'
                              )
                          AND target_date_source
                                IS DISTINCT FROM
                                :auto_target_source
                        RETURNING id
                    )
                    SELECT COUNT(*) FROM changed
                    """
                ),
                {
                    "auto_target_source": (
                        AUTO_TARGET_SOURCE
                    )
                },
            ).scalar_one()
        )

        legacy_after = _fetch_shipments(
            connection,
            legacy_ids,
        )
        after_by_id = {
            int(row["id"]): row
            for row in legacy_after
        }
        for before in legacy_before:
            after = after_by_id.get(
                int(before["id"]),
                {},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO
                    auto_target_scheduling_rows (
                        run_id,
                        shipment_id,
                        shipment_no,
                        before_json,
                        after_json,
                        action_text
                    )
                    VALUES (
                        :run_id,
                        :shipment_id,
                        :shipment_no,
                        CAST(:before_json AS JSONB),
                        CAST(:after_json AS JSONB),
                        :action_text
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "shipment_id": int(
                        before["id"]
                    ),
                    "shipment_no": str(
                        before.get(
                            "shipment_no"
                        )
                        or ""
                    ),
                    "before_json": _json(
                        before
                    ),
                    "after_json": _json(
                        after
                    ),
                    "action_text": (
                        "Legacy review shipment promoted "
                        "to Auto Target planning."
                    ),
                },
            )

        summary = {
            "shipments_audited": len(
                all_before
            ),
            "legacy_review_promoted": len(
                legacy_ids
            ),
            "auto_review_promoted": len(
                auto_review_ids
            ),
            "manual_review_promoted": len(
                manual_review_ids
            ),
            "automatic_sources_normalized": (
                normalized_count
            ),
            "auto_target_source": (
                AUTO_TARGET_SOURCE
            ),
        }
        connection.execute(
            text(
                """
                UPDATE auto_target_scheduling_runs
                SET
                    completed_at =
                        CURRENT_TIMESTAMP,
                    status = 'COMPLETED',
                    legacy_review_promoted =
                        :legacy_review_promoted,
                    automatic_sources_normalized =
                        :automatic_sources_normalized,
                    summary_json =
                        CAST(:summary_json AS JSONB)
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "legacy_review_promoted": len(
                    legacy_ids
                ),
                "automatic_sources_normalized": (
                    normalized_count
                ),
                "summary_json": _json(
                    summary
                ),
            },
        )

    report_root = _write_report(
        project_root,
        run_id,
        legacy_before,
        legacy_after,
        summary,
    )
    return {
        "run_id": run_id,
        "report_directory": str(
            report_root
        ),
        **summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        required=True,
    )
    args = parser.parse_args()
    project_root = Path(
        args.project_root
    ).expanduser().resolve()
    result = run(project_root)

    print(
        "AUTO FACTORY-OUT TARGET MIGRATION V6.4 COMPLETED"
    )
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
