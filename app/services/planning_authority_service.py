from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.operational_source_service import OperationalSourceService


CLOSED_STATUS = {
    "cancelled",
    "canceled",
    "closed",
    "complete",
    "completed",
    "shipped",
    "done",
}


class PlanningAuthorityService:
    """Canonical read-only planning authority for active MPPS workspaces.

    Official values come from PostgreSQL/committed workbook snapshots. ML outputs
    are deliberately excluded from authoritative stock/demand arithmetic.
    """

    @staticmethod
    def _table_exists(connection, table_name: str) -> bool:
        try:
            return bool(
                connection.execute(
                    text("SELECT to_regclass(:name) IS NOT NULL"),
                    {"name": f"public.{table_name}"},
                ).scalar()
            )
        except Exception:
            return False

    @staticmethod
    def _column_exists(connection, table_name: str, column_name: str) -> bool:
        try:
            return bool(
                connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema='public'
                              AND table_name=:table_name
                              AND column_name=:column_name
                        )
                        """
                    ),
                    {"table_name": table_name, "column_name": column_name},
                ).scalar()
            )
        except Exception:
            return False

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return max(0, int(float(value or 0)))
        except Exception:
            return 0

    @classmethod
    def _source(cls, connection) -> tuple[date | None, str]:
        try:
            source = OperationalSourceService.latest(connection)
            return source.plan_date, str(source.workbook_name or source.label or "")
        except Exception:
            return None, ""

    @classmethod
    def _stock_snapshot(cls, connection) -> tuple[dict[str, int], dict[str, Any]]:
        stock_map: dict[str, int] = {}
        meta: dict[str, Any] = {
            "fg_stock": 0,
            "scrap": 0,
            "blocked": 0,
            "stock_source": "NONE",
            "stock_plan_date": None,
            "stock_snapshot_run_id": None,
        }
        current_snapshot_available = False

        if cls._table_exists(connection, "mpps_current_stock_snapshots"):
            latest = connection.execute(
                text(
                    """
                    SELECT import_run_id, MAX(plan_date) AS plan_date
                    FROM mpps_current_stock_snapshots
                    GROUP BY import_run_id
                    ORDER BY MAX(plan_date) DESC NULLS LAST, import_run_id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if latest:
                current_snapshot_available = True
                rows = connection.execute(
                    text(
                        """
                        SELECT sap_code, GREATEST(COALESCE(current_stock,0),0) AS current_stock
                        FROM mpps_current_stock_snapshots
                        WHERE import_run_id=:run_id
                        """
                    ),
                    {"run_id": latest["import_run_id"]},
                ).mappings().all()
                stock_map = {
                    str(row["sap_code"] or "").strip().upper(): cls._to_int(row["current_stock"])
                    for row in rows
                    if str(row.get("sap_code") or "").strip()
                }
                meta["fg_stock"] = sum(stock_map.values())
                meta["stock_source"] = "CURRENT_STOCK_SNAPSHOT"
                meta["stock_plan_date"] = latest.get("plan_date")
                meta["stock_snapshot_run_id"] = latest.get("import_run_id")

        if (
            not current_snapshot_available
            and cls._table_exists(connection, "mpps_sap_stock_items")
        ):
            rows = connection.execute(
                text(
                    """
                    SELECT
                        sap_code,
                        GREATEST(
                            COALESCE(fg_stock,0)
                            + COALESCE(qc_stock,0)
                            - COALESCE(scrap_stock,0)
                            - COALESCE(blocked_stock,0),
                            0
                        ) AS available_qty,
                        GREATEST(COALESCE(scrap_stock,0),0) AS scrap_qty,
                        GREATEST(COALESCE(blocked_stock,0),0) AS blocked_qty
                    FROM mpps_sap_stock_items
                    """
                )
            ).mappings().all()
            stock_map = {
                str(row["sap_code"] or "").strip().upper(): cls._to_int(row["available_qty"])
                for row in rows
                if str(row.get("sap_code") or "").strip()
            }
            meta["fg_stock"] = sum(stock_map.values())
            meta["scrap"] = sum(cls._to_int(row.get("scrap_qty")) for row in rows)
            meta["blocked"] = sum(cls._to_int(row.get("blocked_qty")) for row in rows)
            meta["stock_source"] = "SAP_STOCK_LEDGER"

        # Scrap/blocked are supplementary workbook facts when direct current-stock
        # snapshots are authoritative and do not carry those fields.
        if (
            meta["stock_source"] == "CURRENT_STOCK_SNAPSHOT"
            and cls._table_exists(connection, "mpps_tyre_workbook_observation")
        ):
            latest_obs = connection.execute(
                text("SELECT MAX(plan_date) FROM mpps_tyre_workbook_observation")
            ).scalar()
            if latest_obs is not None:
                columns = {
                    row[0]
                    for row in connection.execute(
                        text(
                            """
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_schema='public'
                              AND table_name='mpps_tyre_workbook_observation'
                            """
                        )
                    ).all()
                }
                if "scrap" in columns:
                    meta["scrap"] = cls._to_int(
                        connection.execute(
                            text(
                                """
                                SELECT COALESCE(SUM(v),0)
                                FROM (
                                    SELECT sap_code, MAX(GREATEST(COALESCE(scrap,0),0)) AS v
                                    FROM mpps_tyre_workbook_observation
                                    WHERE plan_date=:day
                                    GROUP BY sap_code
                                ) x
                                """
                            ),
                            {"day": latest_obs},
                        ).scalar()
                    )
                if "blocked" in columns:
                    meta["blocked"] = cls._to_int(
                        connection.execute(
                            text(
                                """
                                SELECT COALESCE(SUM(v),0)
                                FROM (
                                    SELECT sap_code, MAX(GREATEST(COALESCE(blocked,0),0)) AS v
                                    FROM mpps_tyre_workbook_observation
                                    WHERE plan_date=:day
                                    GROUP BY sap_code
                                ) x
                                """
                            ),
                            {"day": latest_obs},
                        ).scalar()
                    )
        return stock_map, meta

    @classmethod
    def _verify_stock_authority(
        cls,
        connection,
        stock_map: dict[str, int],
        stock_meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Audit the exact stock source used by planning.

        A legitimate zero in the latest current-stock snapshot remains zero and
        is never replaced by an older ledger value. The ledger comparison is
        diagnostic only when a committed current snapshot exists.
        """
        source = str(stock_meta.get("stock_source") or "NONE")
        result: dict[str, Any] = {
            "verified": False,
            "source": source,
            "item_count": len(stock_map),
            "authoritative_total": sum(stock_map.values()),
            "duplicate_sap_rows": 0,
            "negative_rows": 0,
            "ledger_total": None,
            "difference_vs_ledger": None,
            "message": "",
        }

        if source == "CURRENT_STOCK_SNAPSHOT":
            latest_run = stock_meta.get("stock_snapshot_run_id")
            if latest_run is not None:
                duplicate_rows = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM (
                                SELECT UPPER(TRIM(sap_code))
                                FROM mpps_current_stock_snapshots
                                WHERE import_run_id=:run_id
                                GROUP BY UPPER(TRIM(sap_code))
                                HAVING COUNT(*)>1
                            ) x
                            """
                        ),
                        {"run_id": latest_run},
                    ).scalar()
                    or 0
                )
                negative_rows = int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM mpps_current_stock_snapshots
                            WHERE import_run_id=:run_id
                              AND COALESCE(current_stock,0)<0
                            """
                        ),
                        {"run_id": latest_run},
                    ).scalar()
                    or 0
                )
                result["duplicate_sap_rows"] = duplicate_rows
                result["negative_rows"] = negative_rows

        if cls._table_exists(connection, "mpps_sap_stock_items"):
            ledger_total = cls._to_int(
                connection.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(
                            GREATEST(
                                COALESCE(fg_stock,0)+COALESCE(qc_stock,0)
                                -COALESCE(scrap_stock,0)-COALESCE(blocked_stock,0),
                                0
                            )
                        ),0)
                        FROM mpps_sap_stock_items
                        """
                    )
                ).scalar()
            )
            result["ledger_total"] = ledger_total
            result["difference_vs_ledger"] = (
                result["authoritative_total"] - ledger_total
            )

        if source == "CURRENT_STOCK_SNAPSHOT":
            # The committed OVEN workbook is the stock fact authority. Negative
            # raw HS values can exist in that workbook and are preserved in the
            # snapshot for audit/anomaly learning. They are not allocated as
            # usable stock because _stock_snapshot() clamps planning stock to
            # GREATEST(current_stock, 0).
            result["verified"] = bool(
                result["item_count"] > 0
                and result["duplicate_sap_rows"] == 0
            )
            if result["verified"] and result["negative_rows"] > 0:
                result["message"] = (
                    "Latest committed Current Stock snapshot is the planning authority; "
                    f"{result['negative_rows']} negative raw Current Stock value(s) are "
                    "preserved as source anomalies and treated as 0 usable stock."
                )
            elif result["verified"]:
                result["message"] = (
                    "Latest committed Current Stock snapshot is the planning authority."
                )
            else:
                result["message"] = (
                    "Current Stock snapshot requires review before autonomous planning."
                )
        elif source == "SAP_STOCK_LEDGER":
            result["verified"] = result["item_count"] > 0
            result["message"] = (
                "SAP stock ledger fallback is active because no committed Current Stock snapshot is available."
            )
        else:
            result["message"] = "No usable current-stock authority is available."

        return result

    @classmethod
    def _shipment_items(cls, connection) -> list[dict[str, Any]]:
        if not (
            cls._table_exists(connection, "mpps_shipments")
            and cls._table_exists(connection, "mpps_shipment_items")
        ):
            return []

        rows = connection.execute(
            text(
                """
                WITH active_shipments AS (
                    SELECT
                        s.*,
                        ROW_NUMBER() OVER (
                            ORDER BY
                                CASE
                                    WHEN COALESCE(s.target_date_is_manual,FALSE) THEN 0
                                    WHEN s.target_date IS NOT NULL
                                     AND LOWER(COALESCE(s.target_date_source,'')) NOT LIKE 'auto%'
                                     AND LOWER(COALESCE(s.target_date_source,'')) NOT LIKE 'automatic%'
                                    THEN 0
                                    ELSE 1
                                END,
                                s.target_date ASC NULLS LAST,
                                COALESCE(s.created_at,CURRENT_TIMESTAMP),
                                s.id
                        )::INTEGER AS dynamic_priority_no
                    FROM mpps_shipments s
                    WHERE UPPER(COALESCE(s.lifecycle_status,'ACTIVE')) NOT IN ('SHIPPED','CANCELLED','HOLD','CLOSURE_REVIEW')
                      AND LOWER(COALESCE(s.status,'planned')) NOT IN (
                          'cancelled','canceled','closed','complete','completed','shipped','done'
                      )
                )
                SELECT
                    s.id AS shipment_id,
                    COALESCE(NULLIF(s.shipment_name,''),s.shipment_no) AS shipment_name,
                    s.shipment_no,
                    s.customer_name,
                    s.dynamic_priority_no AS priority_no,
                    s.target_date,
                    COALESCE(s.factory_out_date,s.factory_can_receive_date) AS factory_can_out_date,
                    COALESCE(s.target_date_is_manual,FALSE) AS target_date_is_manual,
                    COALESCE(s.target_date_source,'') AS target_date_source,
                    COALESCE(s.status,'Planned') AS shipment_status,
                    COALESCE(s.planning_status,'') AS planning_status,
                    COALESCE(s.lifecycle_status,'ACTIVE') AS lifecycle_status,
                    i.id AS shipment_item_id,
                    TRIM(COALESCE(i.sap_code,'')) AS sap_code,
                    COALESCE(i.item_description,'') AS item_description,
                    GREATEST(COALESCE(i.quantity,0),0) AS quantity,
                    GREATEST(COALESCE(i.produced_qty,0),0) AS produced_qty,
                    GREATEST(COALESCE(i.completed_qty,0),0) AS completed_qty
                FROM active_shipments s
                JOIN mpps_shipment_items i ON i.shipment_id=s.id
                WHERE TRIM(COALESCE(i.sap_code,'')) <> ''
                  AND COALESCE(i.quantity,0) > 0
                ORDER BY s.dynamic_priority_no, i.id
                """
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    @classmethod
    def _allocate_stock(
        cls,
        item_rows: list[dict[str, Any]],
        stock_map: dict[str, int],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        remaining = dict(stock_map)
        allocated_rows: list[dict[str, Any]] = []
        shipment_totals: dict[int, dict[str, Any]] = {}

        for row in item_rows:
            sap = str(row.get("sap_code") or "").strip().upper()
            quantity = cls._to_int(row.get("quantity"))
            produced = min(quantity, cls._to_int(row.get("produced_qty")))
            open_after_production = max(quantity - produced, 0)
            available = max(0, cls._to_int(remaining.get(sap, 0)))
            stock_covered = min(open_after_production, available)
            remaining[sap] = max(0, available - stock_covered)
            production_gap = max(open_after_production - stock_covered, 0)

            item = dict(row)
            item["stock_covered_qty"] = stock_covered
            item["production_gap_qty"] = production_gap
            item["priority_reason"] = (
                "Manual/manager target date priority"
                if bool(row.get("target_date_is_manual"))
                else "Earliest active shipment target / creation order"
            )
            allocated_rows.append(item)

            sid = int(row.get("shipment_id") or 0)
            bucket = shipment_totals.setdefault(
                sid,
                {
                    "shipment_id": sid,
                    "shipment_name": row.get("shipment_name") or row.get("shipment_no") or str(sid),
                    "priority_no": row.get("priority_no"),
                    "target_date": row.get("target_date"),
                    "factory_can_out_date": row.get("factory_can_out_date"),
                    "shipment_status": row.get("shipment_status"),
                    "planning_status": row.get("planning_status"),
                    "lifecycle_status": row.get("lifecycle_status"),
                    "quantity": 0,
                    "produced_qty": 0,
                    "stock_covered_qty": 0,
                    "production_gap_qty": 0,
                },
            )
            bucket["quantity"] += quantity
            bucket["produced_qty"] += produced
            bucket["stock_covered_qty"] += stock_covered
            bucket["production_gap_qty"] += production_gap

        shipments = list(shipment_totals.values())
        shipments.sort(key=lambda row: (row.get("priority_no") or 10**9, row.get("shipment_id") or 0))
        return allocated_rows, {"shipments": shipments, "remaining_stock": remaining}

    @classmethod
    def _latest_plan_summary(cls, connection, plan_date: date | None) -> dict[str, Any]:
        result = {
            "plan_date": plan_date,
            "run_id": None,
            "production_required_qty": 0,
            "today_planned_qty": 0,
            "next_day_planned_qty": 0,
            "remaining_balance_qty": 0,
            "planned_cavities": 0,
            "free_cavities": 0,
            "status_text": "NO SAVED PLAN",
        }
        if not cls._table_exists(connection, "mpps_cavity_plan_runs"):
            return result
        if plan_date is None:
            plan_date = connection.execute(
                text("SELECT MAX(plan_date) FROM mpps_cavity_plan_runs")
            ).scalar()
        if plan_date is None:
            return result

        row = connection.execute(
            text(
                """
                SELECT id, plan_date, summary_json
                FROM mpps_cavity_plan_runs
                WHERE plan_date=:plan_date
                  AND UPPER(COALESCE(status,'SAVED')) NOT IN ('CANCELLED','VOID','REJECTED')
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"plan_date": plan_date},
        ).mappings().first()
        if not row:
            result["plan_date"] = plan_date
            return result
        summary = row.get("summary_json") or {}
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                summary = {}
        result.update(
            {
                "plan_date": row.get("plan_date"),
                "run_id": int(row.get("id") or 0),
                "production_required_qty": cls._to_int(summary.get("production_required_qty")),
                "today_planned_qty": cls._to_int(summary.get("today_planned_qty")),
                "next_day_planned_qty": cls._to_int(summary.get("next_day_planned_qty")),
                "remaining_balance_qty": cls._to_int(summary.get("remaining_balance_qty")),
                "planned_cavities": cls._to_int(summary.get("planned_cavities")),
                "free_cavities": cls._to_int(summary.get("free_cavities")),
                "status_text": str(summary.get("status_text") or "SAVED"),
            }
        )
        return result

    @classmethod
    def _capacity(cls, connection) -> dict[str, Any]:
        result = {
            "active_lines": 0,
            "active_cavities": 0,
            "breakdown_cavities": 0,
            "estimated_daily_capacity_qty": 0,
        }
        if cls._table_exists(connection, "production_line_cavities"):
            columns = {
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name='production_line_cavities'
                        """
                    )
                ).all()
            }
            status_col = "status" if "status" in columns else None
            line_col = next((name for name in ("line_name", "line", "production_line") if name in columns), None)
            if status_col:
                result["active_cavities"] = cls._to_int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM production_line_cavities
                            WHERE LOWER(COALESCE(status,'')) IN ('active','available','ready')
                            """
                        )
                    ).scalar()
                )
                result["breakdown_cavities"] = cls._to_int(
                    connection.execute(
                        text(
                            """
                            SELECT COUNT(*) FROM production_line_cavities
                            WHERE LOWER(COALESCE(status,'')) NOT IN ('active','available','ready')
                            """
                        )
                    ).scalar()
                )
                if line_col:
                    result["active_lines"] = cls._to_int(
                        connection.execute(
                            text(
                                f"""
                                SELECT COUNT(DISTINCT {line_col})
                                FROM production_line_cavities
                                WHERE LOWER(COALESCE(status,'')) IN ('active','available','ready')
                                """
                            )
                        ).scalar()
                    )

        if cls._table_exists(connection, "mpps_factory_daily_capacity"):
            result["estimated_daily_capacity_qty"] = cls._to_int(
                connection.execute(
                    text(
                        """
                        SELECT COALESCE(ROUND(AVG(total_actual_qty)),0)
                        FROM (
                            SELECT total_actual_qty
                            FROM mpps_factory_daily_capacity
                            WHERE COALESCE(total_actual_qty,0) > 0
                            ORDER BY production_date DESC
                            LIMIT 30
                        ) recent
                        """
                    )
                ).scalar()
            )
        return result

    @classmethod
    def _actual_qty(cls, connection, plan_date: date | None) -> int:
        if plan_date is None:
            return 0
        if cls._table_exists(connection, "mpps_factory_daily_capacity"):
            value = connection.execute(
                text(
                    """
                    SELECT COALESCE(total_actual_qty,0)
                    FROM mpps_factory_daily_capacity
                    WHERE production_date=:day
                    LIMIT 1
                    """
                ),
                {"day": plan_date},
            ).scalar()
            if value is not None:
                return cls._to_int(value)
        return 0

    @classmethod
    def _material_exceptions(cls, connection, plan_date: date | None) -> int:
        if not cls._table_exists(connection, "excel_import_material_plans"):
            return 0
        material_date = plan_date
        if material_date is None:
            material_date = connection.execute(
                text("SELECT MAX(plan_date) FROM excel_import_material_plans")
            ).scalar()
        if material_date is None:
            return 0
        return cls._to_int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM excel_import_material_plans
                    WHERE plan_date=:day
                      AND GREATEST(
                            COALESCE(total_qty,0)
                            - COALESCE(stock_qty,0)
                            - COALESCE(produced_qty,0),
                            0
                          ) > 0
                    """
                ),
                {"day": material_date},
            ).scalar()
        )

    @classmethod
    def _sync_priority_columns(cls, connection, shipments: list[dict[str, Any]]) -> None:
        if not shipments or not cls._column_exists(connection, "mpps_shipments", "priority_no"):
            return
        for row in shipments:
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET priority_no=:priority_no,
                        priority_reason=:priority_reason,
                        priority_updated_at=CURRENT_TIMESTAMP
                    WHERE id=:shipment_id
                      AND (
                            priority_no IS DISTINCT FROM :priority_no
                         OR COALESCE(priority_reason,'') IS DISTINCT FROM :priority_reason
                      )
                    """
                ),
                {
                    "priority_no": row.get("priority_no"),
                    "priority_reason": (
                        "Dynamic active-shipment priority: manual target first, then target date and creation order"
                    ),
                    "shipment_id": row.get("shipment_id"),
                },
            )

    @classmethod
    def load(cls, *, persist_priority: bool = True) -> dict[str, Any]:
        with engine.begin() as connection:
            source_date, source_workbook = cls._source(connection)
            stock_map, stock_meta = cls._stock_snapshot(connection)
            stock_verification = cls._verify_stock_authority(
                connection,
                stock_map,
                stock_meta,
            )
            raw_items = cls._shipment_items(connection)
            items, allocation = cls._allocate_stock(raw_items, stock_map)
            shipments = list(allocation.get("shipments") or [])
            if persist_priority:
                cls._sync_priority_columns(connection, shipments)

            shipment_qty = sum(cls._to_int(row.get("quantity")) for row in items)
            produced_qty = sum(cls._to_int(row.get("produced_qty")) for row in items)
            stock_covered_qty = sum(cls._to_int(row.get("stock_covered_qty")) for row in items)
            production_gap = sum(cls._to_int(row.get("production_gap_qty")) for row in items)

            plan = cls._latest_plan_summary(connection, source_date)
            capacity = cls._capacity(connection)
            actual_qty = cls._actual_qty(connection, plan.get("plan_date") or source_date)
            material_exceptions = cls._material_exceptions(connection, plan.get("plan_date") or source_date)

        planned_today = cls._to_int(plan.get("today_planned_qty"))
        planned_next = cls._to_int(plan.get("next_day_planned_qty"))
        plan_remaining = cls._to_int(plan.get("remaining_balance_qty"))
        plan_required = cls._to_int(plan.get("production_required_qty"))
        formula_required = planned_today + planned_next + plan_remaining
        plan_math_ok = plan_required == formula_required if plan.get("run_id") else True
        demand_matches_plan = plan_required == production_gap if plan.get("run_id") else True
        reconciliation_ok = bool(plan_math_ok and demand_matches_plan)

        notes = []
        if not plan_math_ok:
            notes.append(
                f"Saved plan arithmetic mismatch: required {plan_required:,} != today+next+remaining {formula_required:,}."
            )
        if not demand_matches_plan:
            notes.append(
                f"Saved plan demand {plan_required:,} differs from canonical active production gap {production_gap:,}. Recalculate plan."
            )
        if not notes:
            notes.append("Canonical shipment, stock and saved-plan arithmetic is reconciled.")

        daily_capacity = cls._to_int(capacity.get("estimated_daily_capacity_qty"))
        capacity_usage = (
            min(100.0, planned_today / daily_capacity * 100.0)
            if daily_capacity > 0
            else None
        )

        urgent = sorted(
            shipments,
            key=lambda row: (
                row.get("priority_no") or 10**9,
                -cls._to_int(row.get("production_gap_qty")),
            ),
        )[:5]
        for row in urgent:
            row["production_gap"] = cls._to_int(row.get("production_gap_qty"))
            row["risk_score"] = 100 if row.get("target_date") and row.get("factory_can_out_date") and row["factory_can_out_date"] > row["target_date"] else 0

        critical = sum(
            1
            for row in shipments
            if row.get("target_date") is not None
            and row.get("factory_can_out_date") is not None
            and row.get("factory_can_out_date") > row.get("target_date")
        )

        insights: list[str] = []
        if not stock_verification.get("verified"):
            insights.append(
                str(stock_verification.get("message") or "Stock authority requires review.")
            )
        if not reconciliation_ok:
            insights.extend(notes)
        if critical:
            insights.append(f"{critical:,} shipment(s) are currently forecast late.")
        if material_exceptions:
            insights.append(f"{material_exceptions:,} material shortage/exception row(s) require attention.")
        if cls._to_int(capacity.get("breakdown_cavities")):
            insights.append(f"{cls._to_int(capacity.get('breakdown_cavities')):,} cavity resource(s) are unavailable/breakdown.")
        if not insights:
            insights.append("No high-priority operational exception is currently detected.")

        planned_for_dashboard = planned_today
        remaining_today = max(planned_for_dashboard - actual_qty, 0)
        achievement = actual_qty / planned_for_dashboard * 100.0 if planned_for_dashboard > 0 else None

        exceptions: list[dict[str, Any]] = []
        if not stock_verification.get("verified"):
            exceptions.append(
                {
                    "entity_type": "STOCK",
                    "entity_id": str(stock_verification.get("source") or "NONE"),
                    "exception_code": "STOCK_AUTHORITY_NOT_VERIFIED",
                    "severity": "CRITICAL",
                    "message": str(stock_verification.get("message") or "Stock authority requires review."),
                }
            )
        if not plan_math_ok:
            exceptions.append(
                {
                    "entity_type": "PLAN",
                    "entity_id": str(plan.get("run_id") or ""),
                    "exception_code": "PLAN_ARITHMETIC_MISMATCH",
                    "severity": "CRITICAL",
                    "message": notes[0] if notes else "Saved plan arithmetic does not reconcile.",
                }
            )
        if plan.get("run_id") and not demand_matches_plan:
            exceptions.append(
                {
                    "entity_type": "PLAN",
                    "entity_id": str(plan.get("run_id") or ""),
                    "exception_code": "PLAN_DEMAND_STALE",
                    "severity": "WARNING",
                    "message": f"Saved plan demand {plan_required:,} differs from canonical production gap {production_gap:,}.",
                }
            )
        if material_exceptions:
            exceptions.append(
                {
                    "entity_type": "MATERIAL",
                    "entity_id": str(plan.get("plan_date") or source_date or ""),
                    "exception_code": "MATERIAL_SHORTAGE",
                    "severity": "WARNING",
                    "message": f"{material_exceptions:,} material shortage/exception row(s) require attention.",
                }
            )
        if cls._to_int(capacity.get("breakdown_cavities")):
            exceptions.append(
                {
                    "entity_type": "CAPACITY",
                    "entity_id": str(plan.get("plan_date") or source_date or ""),
                    "exception_code": "BREAKDOWN_CAPACITY",
                    "severity": "WARNING",
                    "message": f"{cls._to_int(capacity.get('breakdown_cavities')):,} cavity resource(s) are unavailable/breakdown.",
                }
            )
        for row in shipments:
            target_date = row.get("target_date")
            can_out = row.get("factory_can_out_date")
            if target_date is not None and can_out is not None and can_out > target_date:
                exceptions.append(
                    {
                        "entity_type": "SHIPMENT",
                        "entity_id": str(row.get("shipment_id") or ""),
                        "exception_code": "DELIVERY_LATE",
                        "severity": "WARNING",
                        "message": f"{row.get('shipment_name') or row.get('shipment_id')} is forecast late by {(can_out-target_date).days} day(s).",
                    }
                )

        return {
            "source_date": source_date,
            "source_workbook": source_workbook,
            "shipment_count": len(shipments),
            "shipment_qty": shipment_qty,
            "produced_qty": produced_qty,
            "stock_covered_qty": stock_covered_qty,
            "production_gap": production_gap,
            "stock_coverage_pct": (stock_covered_qty / shipment_qty * 100.0) if shipment_qty else None,
            "fg_stock": cls._to_int(stock_meta.get("fg_stock")),
            "scrap": cls._to_int(stock_meta.get("scrap")),
            "blocked": cls._to_int(stock_meta.get("blocked")),
            "stock_source": stock_meta.get("stock_source"),
            "stock_verification": stock_verification,
            "stock_authority_verified": bool(stock_verification.get("verified")),
            "planned_qty": planned_for_dashboard,
            "planned_today_qty": planned_today,
            "planned_next_day_qty": planned_next,
            "unscheduled_qty": plan_remaining,
            "plan_required_qty": plan_required,
            "actual_qty": actual_qty,
            "remaining_qty": remaining_today,
            "achievement_pct": achievement,
            "active_cavities": cls._to_int(capacity.get("active_cavities")),
            "breakdown_cavities": cls._to_int(capacity.get("breakdown_cavities")),
            "active_lines": cls._to_int(capacity.get("active_lines")),
            "capacity_qty": daily_capacity,
            "estimated_daily_capacity_qty": daily_capacity,
            "capacity_usage_pct": capacity_usage,
            "material_exceptions": material_exceptions,
            "critical_shipments": critical,
            "urgent_shipments": urgent,
            "items": items,
            "shipments": shipments,
            "plan": plan,
            "reconciliation_ok": reconciliation_ok,
            "reconciliation_note": " ".join(notes),
            "insights": insights[:6],
            "exceptions": exceptions,
        }

    @classmethod
    def persist_snapshot(cls, payload: dict[str, Any] | None = None) -> int | None:
        payload = dict(payload or cls.load())
        source_date = payload.get("source_date")
        snapshot_date = payload.get("plan", {}).get("plan_date") or source_date or date.today()
        source_workbook = str(payload.get("source_workbook") or "")
        key_material = "|".join(
            [
                str(snapshot_date),
                str(source_date),
                source_workbook,
                str(payload.get("shipment_qty") or 0),
                str(payload.get("production_gap") or 0),
                str(payload.get("planned_today_qty") or 0),
                str(payload.get("planned_next_day_qty") or 0),
                str(payload.get("unscheduled_qty") or 0),
            ]
        )
        snapshot_key = "R6-" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:32]

        with engine.begin() as connection:
            if not cls._table_exists(connection, "mpps_planning_snapshots"):
                return None
            snapshot_id = connection.execute(
                text(
                    """
                    INSERT INTO mpps_planning_snapshots(
                        snapshot_key,snapshot_date,source_date,source_workbook,
                        shipment_count,shipment_qty,stock_covered_qty,production_gap_qty,
                        fg_stock_qty,planned_today_qty,planned_next_day_qty,unscheduled_qty,
                        active_cavities,breakdown_cavities,estimated_daily_capacity_qty,
                        material_exception_count,reconciliation_ok,reconciliation_note,
                        metadata_json,updated_at
                    ) VALUES(
                        :snapshot_key,:snapshot_date,:source_date,:source_workbook,
                        :shipment_count,:shipment_qty,:stock_covered_qty,:production_gap_qty,
                        :fg_stock_qty,:planned_today_qty,:planned_next_day_qty,:unscheduled_qty,
                        :active_cavities,:breakdown_cavities,:estimated_daily_capacity_qty,
                        :material_exception_count,:reconciliation_ok,:reconciliation_note,
                        CAST(:metadata_json AS JSONB),CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(snapshot_key) DO UPDATE SET
                        reconciliation_ok=EXCLUDED.reconciliation_ok,
                        reconciliation_note=EXCLUDED.reconciliation_note,
                        metadata_json=EXCLUDED.metadata_json,
                        updated_at=CURRENT_TIMESTAMP
                    RETURNING id
                    """
                ),
                {
                    "snapshot_key": snapshot_key,
                    "snapshot_date": snapshot_date,
                    "source_date": source_date,
                    "source_workbook": source_workbook,
                    "shipment_count": cls._to_int(payload.get("shipment_count")),
                    "shipment_qty": cls._to_int(payload.get("shipment_qty")),
                    "stock_covered_qty": cls._to_int(payload.get("stock_covered_qty")),
                    "production_gap_qty": cls._to_int(payload.get("production_gap")),
                    "fg_stock_qty": cls._to_int(payload.get("fg_stock")),
                    "planned_today_qty": cls._to_int(payload.get("planned_today_qty")),
                    "planned_next_day_qty": cls._to_int(payload.get("planned_next_day_qty")),
                    "unscheduled_qty": cls._to_int(payload.get("unscheduled_qty")),
                    "active_cavities": cls._to_int(payload.get("active_cavities")),
                    "breakdown_cavities": cls._to_int(payload.get("breakdown_cavities")),
                    "estimated_daily_capacity_qty": cls._to_int(payload.get("estimated_daily_capacity_qty")),
                    "material_exception_count": cls._to_int(payload.get("material_exceptions")),
                    "reconciliation_ok": bool(payload.get("reconciliation_ok")),
                    "reconciliation_note": str(payload.get("reconciliation_note") or ""),
                    "metadata_json": json.dumps(
                        {
                            "stock_source": payload.get("stock_source"),
                            "stock_verification": payload.get("stock_verification") or {},
                            "plan_run_id": payload.get("plan", {}).get("run_id"),
                        },
                        default=str,
                    ),
                },
            ).scalar_one()

            connection.execute(
                text("DELETE FROM mpps_planning_snapshot_items WHERE snapshot_id=:snapshot_id"),
                {"snapshot_id": snapshot_id},
            )
            item_payloads = []
            for row in payload.get("items") or []:
                item_payloads.append(
                    {
                        "snapshot_id": snapshot_id,
                        "shipment_id": row.get("shipment_id"),
                        "shipment_item_id": row.get("shipment_item_id"),
                        "priority_no": row.get("priority_no"),
                        "shipment_name": str(row.get("shipment_name") or ""),
                        "sap_code": str(row.get("sap_code") or ""),
                        "item_description": str(row.get("item_description") or ""),
                        "target_date": row.get("target_date"),
                        "factory_can_out_date": row.get("factory_can_out_date"),
                        "demand_qty": cls._to_int(row.get("quantity")),
                        "produced_qty": cls._to_int(row.get("produced_qty")),
                        "stock_covered_qty": cls._to_int(row.get("stock_covered_qty")),
                        "production_gap_qty": cls._to_int(row.get("production_gap_qty")),
                        "operational_status": str(row.get("lifecycle_status") or "ACTIVE"),
                        "explanation": str(row.get("priority_reason") or ""),
                    }
                )
            if item_payloads:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_planning_snapshot_items(
                            snapshot_id,shipment_id,shipment_item_id,priority_no,shipment_name,
                            sap_code,item_description,target_date,factory_can_out_date,demand_qty,
                            produced_qty,stock_covered_qty,production_gap_qty,operational_status,explanation
                        ) VALUES(
                            :snapshot_id,:shipment_id,:shipment_item_id,:priority_no,:shipment_name,
                            :sap_code,:item_description,:target_date,:factory_can_out_date,:demand_qty,
                            :produced_qty,:stock_covered_qty,:production_gap_qty,:operational_status,:explanation
                        )
                        """
                    ),
                    item_payloads,
                )
            if cls._table_exists(connection, "mpps_planning_exceptions"):
                connection.execute(
                    text("DELETE FROM mpps_planning_exceptions WHERE snapshot_id=:snapshot_id"),
                    {"snapshot_id": snapshot_id},
                )
                exception_payloads = [
                    {
                        "snapshot_id": snapshot_id,
                        "entity_type": str(row.get("entity_type") or ""),
                        "entity_id": str(row.get("entity_id") or ""),
                        "exception_code": str(row.get("exception_code") or "UNSPECIFIED"),
                        "severity": str(row.get("severity") or "WARNING").upper(),
                        "message": str(row.get("message") or ""),
                    }
                    for row in (payload.get("exceptions") or [])
                ]
                if exception_payloads:
                    connection.execute(
                        text(
                            """
                            INSERT INTO mpps_planning_exceptions(
                                snapshot_id,entity_type,entity_id,exception_code,severity,message
                            ) VALUES(
                                :snapshot_id,:entity_type,:entity_id,:exception_code,:severity,:message
                            )
                            """
                        ),
                        exception_payloads,
                    )

            connection.execute(
                text(
                    """
                    UPDATE mpps_autonomous_planning_state
                    SET last_source_date=:source_date,
                        last_snapshot_id=:snapshot_id,
                        last_reconciled_at=CURRENT_TIMESTAMP,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=1
                    """
                ),
                {"source_date": source_date, "snapshot_id": snapshot_id},
            )
        return int(snapshot_id)
