from __future__ import annotations

from datetime import date
import json
import uuid
from typing import Any

from sqlalchemy import text

from app.database import engine


CORE_WORKBOOK_ROLES = {
    "PRODUCTION_STOCK_SHIPMENTS",
    "DAILY_PRODUCTION_PLAN",
    "OVEN_CAVITY_PLAN",
}
MATERIAL_WORKBOOK_ROLES = {
    "BEAD_REQUIREMENT",
    "COMPOUND_BOM",
    "BAND_PLAN",
    "CORE_PLAN",
    "WEIGHT_MASTER",
}


class HistoricalDatasetValidationService:
    """Normalize and validate historical MPPS evidence before ML training.

    The service never changes official operational facts. It creates a separate,
    auditable observation layer from committed/imported PostgreSQL history and
    validates chronology, duplicate/revision integrity, source coverage and
    obviously invalid future/negative actuals.
    """

    MIN_HISTORY_DAYS = 365
    MIN_OBSERVATION_DAYS = 180
    MIN_OBSERVATION_ROWS = 1000

    @staticmethod
    def _table_exists(connection, table_name: str) -> bool:
        return bool(
            connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"public.{table_name}"},
            ).scalar()
        )

    @staticmethod
    def _columns(connection, table_name: str) -> set[str]:
        if not HistoricalDatasetValidationService._table_exists(
            connection, table_name
        ):
            return set()
        return {
            str(row[0])
            for row in connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:table_name
                    """
                ),
                {"table_name": table_name},
            ).all()
        }

    @classmethod
    def normalize(cls) -> dict[str, int]:
        """Idempotently rebuild/update the canonical ML observation layer."""
        counts: dict[str, int] = {}
        with engine.begin() as connection:
            if not cls._table_exists(
                connection, "mpps_ml_training_observations_v2"
            ):
                raise RuntimeError(
                    "R6 training observation schema is not installed."
                )

            jobs: list[tuple[str, str]] = []

            if cls._table_exists(
                connection, "mpps_tyre_workbook_observation"
            ):
                jobs.append(
                    (
                        "mpps_tyre_workbook_observation",
                        """
                        INSERT INTO mpps_ml_training_observations_v2(
                            observation_key,observation_date,entity_type,entity_key,
                            source_table,source_row_key,features_json,targets_json,
                            source_hash,updated_at
                        )
                        SELECT
                            'TYRE_OBS:' || id::text,
                            plan_date,
                            'TYRE',
                            COALESCE(sap_code,'') || '|' || COALESCE(line,'') || '|' || COALESCE(oven_no,''),
                            'mpps_tyre_workbook_observation',
                            id::text,
                            jsonb_build_object(
                                'sap_code',sap_code,'description',description,
                                'line',line,'oven_no',oven_no,'heel',heel,'soft',soft,
                                'tread',tread,'remark',remark,'weight_kg',weight_kg,
                                'day_plan',day_plan,'night_plan',night_plan,
                                'next_day_plan',next_day_plan,'total_to_produce',total_to_produce,
                                'total_stock',total_stock,'current_stock',current_stock,
                                'scrap',scrap,'blocked',blocked
                            ),
                            jsonb_build_object(
                                'day_produced',day_produced,
                                'night_produced',night_produced,
                                'today_qty',today_qty
                            ),
                            COALESCE(workbook_hash,''),
                            CURRENT_TIMESTAMP
                        FROM mpps_tyre_workbook_observation
                        WHERE plan_date IS NOT NULL
                        ON CONFLICT(observation_key) DO UPDATE SET
                            observation_date=EXCLUDED.observation_date,
                            entity_key=EXCLUDED.entity_key,
                            features_json=EXCLUDED.features_json,
                            targets_json=EXCLUDED.targets_json,
                            source_hash=EXCLUDED.source_hash,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                    )
                )

            if cls._table_exists(connection, "excel_import_production_history"):
                jobs.append(
                    (
                        "excel_import_production_history",
                        """
                        INSERT INTO mpps_ml_training_observations_v2(
                            observation_key,observation_date,entity_type,entity_key,
                            source_table,source_row_key,features_json,targets_json,
                            source_hash,updated_at
                        )
                        SELECT
                            'PROD_HISTORY:' || h.id::text,
                            h.production_date,
                            'SAP_PRODUCTION',
                            COALESCE(h.sap_code,''),
                            'excel_import_production_history',
                            h.id::text,
                            jsonb_build_object(
                                'sap_code',h.sap_code,
                                'item_description',h.item_description,
                                'source_sheet',h.source_sheet
                            ),
                            jsonb_build_object('production_qty',h.production_qty),
                            COALESCE(r.workbook_hash,''),
                            CURRENT_TIMESTAMP
                        FROM excel_import_production_history h
                        LEFT JOIN excel_import_runs r ON r.id=h.run_id
                        WHERE h.production_date IS NOT NULL
                          AND (r.id IS NULL OR r.status LIKE 'COMMITTED%')
                        ON CONFLICT(observation_key) DO UPDATE SET
                            observation_date=EXCLUDED.observation_date,
                            features_json=EXCLUDED.features_json,
                            targets_json=EXCLUDED.targets_json,
                            source_hash=EXCLUDED.source_hash,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                    )
                )

            if cls._table_exists(connection, "excel_import_material_plans"):
                jobs.append(
                    (
                        "excel_import_material_plans",
                        """
                        INSERT INTO mpps_ml_training_observations_v2(
                            observation_key,observation_date,entity_type,entity_key,
                            source_table,source_row_key,features_json,targets_json,
                            source_hash,updated_at
                        )
                        SELECT
                            'MATERIAL:' || m.id::text,
                            m.plan_date,
                            'MATERIAL',
                            COALESCE(m.material_type,'') || '|' || COALESCE(m.material_key,''),
                            'excel_import_material_plans',
                            m.id::text,
                            jsonb_build_object(
                                'material_type',m.material_type,
                                'material_key',m.material_key,
                                'material_description',m.material_description,
                                'day_qty',m.day_qty,'night_qty',m.night_qty,
                                'produced_qty',m.produced_qty,'stock_qty',m.stock_qty,
                                'unit',m.unit,'source_sheet',m.source_sheet
                            ),
                            jsonb_build_object(
                                'total_qty',m.total_qty,
                                'next_day_qty',m.next_day_qty
                            ),
                            COALESCE(r.workbook_hash,''),
                            CURRENT_TIMESTAMP
                        FROM excel_import_material_plans m
                        LEFT JOIN excel_import_runs r ON r.id=m.run_id
                        WHERE m.plan_date IS NOT NULL
                          AND (r.id IS NULL OR r.status LIKE 'COMMITTED%')
                        ON CONFLICT(observation_key) DO UPDATE SET
                            observation_date=EXCLUDED.observation_date,
                            entity_key=EXCLUDED.entity_key,
                            features_json=EXCLUDED.features_json,
                            targets_json=EXCLUDED.targets_json,
                            source_hash=EXCLUDED.source_hash,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                    )
                )

            if cls._table_exists(connection, "mpps_factory_daily_capacity"):
                jobs.append(
                    (
                        "mpps_factory_daily_capacity",
                        """
                        INSERT INTO mpps_ml_training_observations_v2(
                            observation_key,observation_date,entity_type,entity_key,
                            source_table,source_row_key,features_json,targets_json,
                            source_hash,updated_at
                        )
                        SELECT
                            'FACTORY_DAY:' || production_date::text,
                            production_date,
                            'FACTORY',
                            'FACTORY',
                            'mpps_factory_daily_capacity',
                            production_date::text,
                            jsonb_build_object(
                                'active_sap_count',active_sap_count,
                                'total_plan_qty',total_plan_qty
                            ),
                            jsonb_build_object('total_actual_qty',total_actual_qty),
                            md5(COALESCE(source_workbook,'') || '|' || production_date::text),
                            CURRENT_TIMESTAMP
                        FROM mpps_factory_daily_capacity
                        WHERE production_date IS NOT NULL
                        ON CONFLICT(observation_key) DO UPDATE SET
                            features_json=EXCLUDED.features_json,
                            targets_json=EXCLUDED.targets_json,
                            source_hash=EXCLUDED.source_hash,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                    )
                )

            if cls._table_exists(connection, "mpps_operational_actual_events"):
                jobs.append(
                    (
                        "mpps_operational_actual_events",
                        """
                        INSERT INTO mpps_ml_training_observations_v2(
                            observation_key,observation_date,entity_type,entity_key,
                            source_table,source_row_key,features_json,targets_json,
                            source_hash,updated_at
                        )
                        SELECT
                            'ACTUAL_EVENT:' || id::text,
                            event_date,
                            'PRODUCTION_ACTUAL',
                            COALESCE(sap_code,'') || '|' || COALESCE(line_name,'') || '|' || COALESCE(cavity_no,''),
                            'mpps_operational_actual_events',
                            id::text,
                            jsonb_build_object(
                                'shift_name',shift_name,'sap_code',sap_code,
                                'line_name',line_name,'cavity_no',cavity_no,
                                'scrap_qty',scrap_qty,'blocked_qty',blocked_qty,
                                'source',source
                            ),
                            jsonb_build_object('produced_qty',produced_qty),
                            md5(COALESCE(source_ref,'') || '|' || id::text),
                            CURRENT_TIMESTAMP
                        FROM mpps_operational_actual_events
                        WHERE event_date IS NOT NULL
                        ON CONFLICT(observation_key) DO UPDATE SET
                            features_json=EXCLUDED.features_json,
                            targets_json=EXCLUDED.targets_json,
                            source_hash=EXCLUDED.source_hash,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                    )
                )

            if cls._table_exists(connection, "mpps_planning_snapshots") and cls._table_exists(
                connection, "mpps_planning_snapshot_items"
            ):
                jobs.append(
                    (
                        "mpps_planning_snapshot_items",
                        """
                        INSERT INTO mpps_ml_training_observations_v2(
                            observation_key,observation_date,entity_type,entity_key,
                            source_table,source_row_key,features_json,targets_json,
                            source_hash,updated_at
                        )
                        SELECT
                            'SHIP_SNAPSHOT:' || i.id::text,
                            s.snapshot_date,
                            'SHIPMENT_ITEM',
                            COALESCE(i.shipment_id,0)::text || '|' || COALESCE(i.shipment_item_id,0)::text,
                            'mpps_planning_snapshot_items',
                            i.id::text,
                            jsonb_build_object(
                                'priority_no',i.priority_no,'sap_code',i.sap_code,
                                'demand_qty',i.demand_qty,'produced_qty',i.produced_qty,
                                'stock_covered_qty',i.stock_covered_qty,
                                'production_gap_qty',i.production_gap_qty,
                                'target_date',i.target_date,
                                'operational_status',i.operational_status
                            ),
                            jsonb_build_object(
                                'planned_factory_can_out_date',i.factory_can_out_date,
                                'production_gap_qty',i.production_gap_qty,
                                'late_days',CASE
                                    WHEN i.target_date IS NOT NULL AND i.factory_can_out_date IS NOT NULL
                                    THEN GREATEST((i.factory_can_out_date-i.target_date),0)
                                    ELSE NULL
                                END
                            ),
                            md5(s.snapshot_key || '|' || i.id::text),
                            CURRENT_TIMESTAMP
                        FROM mpps_planning_snapshot_items i
                        JOIN mpps_planning_snapshots s ON s.id=i.snapshot_id
                        WHERE s.snapshot_date IS NOT NULL
                        ON CONFLICT(observation_key) DO UPDATE SET
                            observation_date=EXCLUDED.observation_date,
                            features_json=EXCLUDED.features_json,
                            targets_json=EXCLUDED.targets_json,
                            source_hash=EXCLUDED.source_hash,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                    )
                )

            for name, sql in jobs:
                connection.execute(text(sql))
                counts[name] = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM mpps_ml_training_observations_v2
                            WHERE source_table=:source_table
                            """
                        ),
                        {"source_table": name},
                    ).scalar()
                    or 0
                )
        return counts

    @classmethod
    def _add_issue(
        cls,
        issues: list[dict[str, Any]],
        severity: str,
        code: str,
        source: str,
        message: str,
        **detail: Any,
    ) -> None:
        issues.append(
            {
                "severity": severity.upper(),
                "issue_code": code,
                "source_name": source,
                "message": message,
                "detail": detail,
            }
        )

    @classmethod
    def validate(
        cls,
        *,
        normalize: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        normalized = cls.normalize() if normalize else {}
        issues: list[dict[str, Any]] = []
        source_stats: dict[str, Any] = {}
        today = date.today()

        with engine.begin() as connection:
            if cls._table_exists(connection, "excel_import_runs"):
                committed = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM excel_import_runs
                            WHERE status LIKE 'COMMITTED%'
                            """
                        )
                    ).scalar()
                    or 0
                )
                duplicate_hashes = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            """
                            SELECT workbook_hash,COUNT(*) AS committed_count
                            FROM excel_import_runs
                            WHERE status LIKE 'COMMITTED%'
                            GROUP BY workbook_hash
                            HAVING COUNT(*)>1
                            ORDER BY COUNT(*) DESC
                            LIMIT 100
                            """
                        )
                    ).mappings().all()
                ]
                revisions = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM (
                                SELECT plan_date
                                FROM excel_import_runs
                                WHERE status LIKE 'COMMITTED%'
                                  AND plan_date IS NOT NULL
                                GROUP BY plan_date
                                HAVING COUNT(DISTINCT workbook_hash)>1
                            ) x
                            """
                        )
                    ).scalar()
                    or 0
                )
                source_stats["excel_import_runs"] = {
                    "committed_runs": committed,
                    "revision_dates": revisions,
                    "duplicate_committed_hashes": len(duplicate_hashes),
                }
                if duplicate_hashes:
                    cls._add_issue(
                        issues,
                        "CRITICAL",
                        "DUPLICATE_COMMITTED_WORKBOOK_HASH",
                        "excel_import_runs",
                        "The same workbook hash is committed more than once; duplicate-safe history is required before training.",
                        examples=duplicate_hashes[:10],
                    )

                latest = connection.execute(
                    text(
                        """
                        SELECT id,plan_date
                        FROM excel_import_runs
                        WHERE status LIKE 'COMMITTED%'
                          AND (plan_date IS NULL OR plan_date < DATE '2060-01-01')
                        ORDER BY plan_date DESC NULLS LAST,id DESC
                        LIMIT 1
                        """
                    )
                ).mappings().first()
                if latest and cls._table_exists(connection, "excel_import_sheet_profiles"):
                    roles = {
                        str(row[0] or "")
                        for row in connection.execute(
                            text(
                                """
                                SELECT detected_role
                                FROM excel_import_sheet_profiles
                                WHERE run_id=:run_id
                                """
                            ),
                            {"run_id": latest["id"]},
                        ).all()
                    }
                    missing_core = sorted(CORE_WORKBOOK_ROLES - roles)
                    missing_material = sorted(MATERIAL_WORKBOOK_ROLES - roles)
                    if missing_core:
                        cls._add_issue(
                            issues,
                            "CRITICAL",
                            "MISSING_CORE_WORKBOOK_ROLES",
                            "excel_import_sheet_profiles",
                            "Latest committed workbook is missing core production/stock/oven semantic roles.",
                            missing_roles=missing_core,
                            run_id=latest["id"],
                        )
                    if missing_material:
                        cls._add_issue(
                            issues,
                            "WARNING",
                            "MISSING_MATERIAL_WORKBOOK_ROLES",
                            "excel_import_sheet_profiles",
                            "Some material/weight roles are absent; related material models will remain unavailable.",
                            missing_roles=missing_material,
                            run_id=latest["id"],
                        )

            if cls._table_exists(connection, "mpps_tyre_workbook_observation"):
                future_observations = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM mpps_tyre_workbook_observation
                            WHERE plan_date>CURRENT_DATE
                              AND (COALESCE(day_produced,0)>0 OR COALESCE(night_produced,0)>0)
                            """
                        )
                    ).scalar()
                    or 0
                )
                if future_observations:
                    cls._add_issue(
                        issues,
                        "CRITICAL",
                        "FUTURE_TYRE_ACTUAL_LEAKAGE",
                        "mpps_tyre_workbook_observation",
                        "Tyre workbook observations contain produced quantities dated in the future.",
                        rows=future_observations,
                    )

            actual_sources = (
                ("excel_import_production_history", "production_date", "production_qty"),
                ("mpps_factory_daily_capacity", "production_date", "total_actual_qty"),
                ("mpps_operational_actual_events", "event_date", "produced_qty"),
            )
            for table_name, date_col, qty_col in actual_sources:
                columns = cls._columns(connection, table_name)
                if not columns:
                    source_stats[table_name] = {"rows": 0, "missing": True}
                    continue
                first_day, last_day, rows, future_rows, negative_rows = connection.execute(
                    text(
                        f"""
                        SELECT
                            MIN({date_col}),MAX({date_col}),COUNT(*),
                            COUNT(*) FILTER (WHERE {date_col}>CURRENT_DATE),
                            COUNT(*) FILTER (WHERE COALESCE({qty_col},0)<0)
                        FROM {table_name}
                        WHERE {date_col} IS NOT NULL
                        """
                    )
                ).one()
                source_stats[table_name] = {
                    "rows": int(rows or 0),
                    "first_date": first_day,
                    "last_date": last_day,
                    "future_rows": int(future_rows or 0),
                    "negative_rows": int(negative_rows or 0),
                }
                if future_rows:
                    cls._add_issue(
                        issues,
                        "CRITICAL",
                        "FUTURE_ACTUAL_LEAKAGE",
                        table_name,
                        "Actual-production source contains future-dated observations, which would leak future information into training.",
                        rows=int(future_rows),
                    )
                if negative_rows:
                    cls._add_issue(
                        issues,
                        "CRITICAL",
                        "NEGATIVE_ACTUAL_TARGET",
                        table_name,
                        "Actual-production source contains negative target quantities.",
                        rows=int(negative_rows),
                    )

            if not cls._table_exists(
                connection, "mpps_ml_training_observations_v2"
            ):
                raise RuntimeError("R6 normalized observation table is missing.")

            first_day, last_day, observation_days, total_rows = connection.execute(
                text(
                    """
                    SELECT MIN(observation_date),MAX(observation_date),
                           COUNT(DISTINCT observation_date),COUNT(*)
                    FROM mpps_ml_training_observations_v2
                    """
                )
            ).one()

            first_day = first_day
            last_day = last_day
            history_days = (
                (last_day - first_day).days + 1
                if first_day is not None and last_day is not None
                else 0
            )
            observation_days = int(observation_days or 0)
            total_rows = int(total_rows or 0)

            if history_days < cls.MIN_HISTORY_DAYS:
                cls._add_issue(
                    issues,
                    "WARNING",
                    "INSUFFICIENT_HISTORY_SPAN",
                    "mpps_ml_training_observations_v2",
                    f"Only {history_days} calendar day(s) of normalized history are available; at least {cls.MIN_HISTORY_DAYS} are required for final training readiness.",
                )
            if observation_days < cls.MIN_OBSERVATION_DAYS:
                cls._add_issue(
                    issues,
                    "WARNING",
                    "INSUFFICIENT_OBSERVATION_DAYS",
                    "mpps_ml_training_observations_v2",
                    f"Only {observation_days} distinct observation day(s) are available.",
                )
            if total_rows < cls.MIN_OBSERVATION_ROWS:
                cls._add_issue(
                    issues,
                    "WARNING",
                    "INSUFFICIENT_OBSERVATION_ROWS",
                    "mpps_ml_training_observations_v2",
                    f"Only {total_rows} normalized training observation row(s) are available.",
                )

            critical_count = sum(
                issue["severity"] == "CRITICAL" for issue in issues
            )
            warning_count = sum(
                issue["severity"] == "WARNING" for issue in issues
            )
            ready = bool(
                critical_count == 0
                and history_days >= cls.MIN_HISTORY_DAYS
                and observation_days >= cls.MIN_OBSERVATION_DAYS
                and total_rows >= cls.MIN_OBSERVATION_ROWS
            )

            report = {
                "ready_for_training": ready,
                "first_date": first_day,
                "last_date": last_day,
                "history_days": history_days,
                "observation_days": observation_days,
                "total_rows": total_rows,
                "critical_issue_count": critical_count,
                "warning_count": warning_count,
                "normalized_sources": normalized,
                "source_stats": source_stats,
                "issues": issues,
                "rules": {
                    "minimum_history_days": cls.MIN_HISTORY_DAYS,
                    "minimum_observation_days": cls.MIN_OBSERVATION_DAYS,
                    "minimum_observation_rows": cls.MIN_OBSERVATION_ROWS,
                    "future_actuals_allowed": False,
                    "duplicate_committed_hashes_allowed": False,
                    "same_date_changed_workbook": "allowed_as_revision",
                },
            }

            if persist and cls._table_exists(
                connection, "mpps_training_data_validation_runs"
            ):
                run_key = "R6-DATA-" + uuid.uuid4().hex[:20]
                validation_id = int(
                    connection.execute(
                        text(
                            """
                            INSERT INTO mpps_training_data_validation_runs(
                                run_key,status,first_date,last_date,history_days,
                                observation_days,total_rows,critical_issue_count,
                                warning_count,ready_for_training,report_json,completed_at
                            ) VALUES(
                                :run_key,'COMPLETED',:first_date,:last_date,:history_days,
                                :observation_days,:total_rows,:critical_issue_count,
                                :warning_count,:ready_for_training,CAST(:report_json AS JSONB),
                                CURRENT_TIMESTAMP
                            ) RETURNING id
                            """
                        ),
                        {
                            "run_key": run_key,
                            "first_date": first_day,
                            "last_date": last_day,
                            "history_days": history_days,
                            "observation_days": observation_days,
                            "total_rows": total_rows,
                            "critical_issue_count": critical_count,
                            "warning_count": warning_count,
                            "ready_for_training": ready,
                            "report_json": json.dumps(report, default=str),
                        },
                    ).scalar_one()
                )
                if issues:
                    connection.execute(
                        text(
                            """
                            INSERT INTO mpps_training_data_validation_issues(
                                validation_run_id,severity,issue_code,source_name,
                                message,detail_json
                            ) VALUES(
                                :validation_run_id,:severity,:issue_code,:source_name,
                                :message,CAST(:detail_json AS JSONB)
                            )
                            """
                        ),
                        [
                            {
                                "validation_run_id": validation_id,
                                "severity": issue["severity"],
                                "issue_code": issue["issue_code"],
                                "source_name": issue["source_name"],
                                "message": issue["message"],
                                "detail_json": json.dumps(
                                    issue.get("detail") or {}, default=str
                                ),
                            }
                            for issue in issues
                        ],
                    )
                report["validation_run_id"] = validation_id
                report["validation_run_key"] = run_key

        return report
