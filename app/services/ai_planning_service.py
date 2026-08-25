from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
import math
from statistics import mean, median
from typing import Any

from sqlalchemy import text

from app.services.operational_source_service import OperationalSourceService
from app.services.factory_intelligence_service import FactoryIntelligenceService


# MPPS AI PLANNER V10 — hybrid execution + capacity + human-policy decision support
# Design rule: imported Excel/Oven plan is the FINAL human-authorized plan.
# AI remains in SHADOW mode until validation gates are satisfied and a human
# explicitly changes the control mode.


def _code(value: Any) -> str:
    value = str(value or "").strip()
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return value.upper()


def _int(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except Exception:
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Readiness:
    mode: str
    validation_days: int
    accuracy_pct: float
    coverage_pct: float
    high_confidence_items: int
    total_models: int
    target_accuracy_pct: float
    min_validation_days: int
    min_coverage_pct: float
    eligible_for_supervised_auto: bool
    accuracy_basis: str
    explanation: str


class AIPlanningService:
    """Explainable adaptive planning layer for the MPPS factory workflow.

    The model learns plan-to-actual completion behaviour per SAP item using a
    leakage-safe, one-step-ahead exponentially weighted completion-ratio model.
    It combines that learned execution reliability with live shipment demand,
    monthly opening stock, confirmed actual production and production capacity.

    No AI run silently replaces the imported Excel plan. Excel remains the final
    execution authority until a user explicitly promotes the system mode.
    """

    DEFAULT_TARGET_ACCURACY = 95.0
    DEFAULT_MIN_VALIDATION_DAYS = 30
    DEFAULT_MIN_COVERAGE = 95.0

    @staticmethod
    def ensure_schema(session) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mpps_ai_settings (
                id INTEGER PRIMARY KEY,
                control_mode VARCHAR(30) NOT NULL DEFAULT 'SHADOW',
                target_accuracy_pct NUMERIC(8,3) NOT NULL DEFAULT 95,
                min_validation_days INTEGER NOT NULL DEFAULT 30,
                min_coverage_pct NUMERIC(8,3) NOT NULL DEFAULT 95,
                human_final_plan_required BOOLEAN NOT NULL DEFAULT TRUE,
                auto_write_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            INSERT INTO mpps_ai_settings (
                id, control_mode, target_accuracy_pct, min_validation_days,
                min_coverage_pct, human_final_plan_required, auto_write_enabled
            ) VALUES (1, 'SHADOW', 95, 30, 95, TRUE, FALSE)
            ON CONFLICT (id) DO NOTHING
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_final_plan_history (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT NOT NULL,
                plan_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                day_plan_qty INTEGER NOT NULL DEFAULT 0,
                night_plan_qty INTEGER NOT NULL DEFAULT 0,
                total_plan_qty INTEGER NOT NULL DEFAULT 0,
                planned_weight_kg NUMERIC(18,5) NOT NULL DEFAULT 0,
                source_workbook TEXT NOT NULL DEFAULT '',
                source_authority VARCHAR(30) NOT NULL DEFAULT 'EXCEL_FINAL',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(import_run_id, plan_date, sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_final_plan_history_date_sap
            ON mpps_final_plan_history(plan_date, sap_code, import_run_id DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_actual_production (
                id BIGSERIAL PRIMARY KEY,
                production_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                day_actual_qty INTEGER NOT NULL DEFAULT 0,
                night_actual_qty INTEGER NOT NULL DEFAULT 0,
                total_actual_qty INTEGER NOT NULL DEFAULT 0,
                source_day_column VARCHAR(10) NOT NULL DEFAULT '',
                source_night_column VARCHAR(10) NOT NULL DEFAULT '',
                source_workbook TEXT NOT NULL DEFAULT '',
                source_sheet TEXT NOT NULL DEFAULT 'PROD',
                source_import_run_id BIGINT,
                source_semantics VARCHAR(50) NOT NULL DEFAULT 'VERIFIED_ACTUAL_PRODUCTION',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(production_date, sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_actual_production_date_sap
            ON mpps_actual_production(production_date, sap_code)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_actual_production_dates (
                production_date DATE PRIMARY KEY,
                source_workbook TEXT NOT NULL DEFAULT '',
                source_sheet TEXT NOT NULL DEFAULT 'PROD',
                source_day_column VARCHAR(10) NOT NULL DEFAULT '',
                source_night_column VARCHAR(10) NOT NULL DEFAULT '',
                source_import_run_id BIGINT,
                is_complete BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_plan_actual_reconciliation (
                id BIGSERIAL PRIMARY KEY,
                production_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                plan_day_qty INTEGER NOT NULL DEFAULT 0,
                plan_night_qty INTEGER NOT NULL DEFAULT 0,
                plan_total_qty INTEGER NOT NULL DEFAULT 0,
                actual_day_qty INTEGER NOT NULL DEFAULT 0,
                actual_night_qty INTEGER NOT NULL DEFAULT 0,
                actual_total_qty INTEGER NOT NULL DEFAULT 0,
                variance_qty INTEGER NOT NULL DEFAULT 0,
                achievement_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
                abs_error_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
                status VARCHAR(30) NOT NULL DEFAULT '',
                source_plan_run_id BIGINT,
                source_actual_run_id BIGINT,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(production_date, sap_code)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_ai_model_state (
                id BIGSERIAL PRIMARY KEY,
                model_key TEXT NOT NULL UNIQUE,
                sap_code TEXT NOT NULL,
                sample_days INTEGER NOT NULL DEFAULT 0,
                ewma_completion_ratio NUMERIC(12,6) NOT NULL DEFAULT 1,
                median_completion_ratio NUMERIC(12,6) NOT NULL DEFAULT 1,
                day_share NUMERIC(12,6) NOT NULL DEFAULT 0.5,
                mae_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                mape_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
                validation_accuracy_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
                confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                model_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_trained_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_ai_model_state_confidence
            ON mpps_ai_model_state(confidence_band, sample_days DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_ai_plan_evaluation (
                id BIGSERIAL PRIMARY KEY,
                ai_run_id BIGINT NOT NULL,
                plan_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                ai_recommended_total_qty INTEGER NOT NULL DEFAULT 0,
                ai_expected_actual_qty INTEGER NOT NULL DEFAULT 0,
                final_excel_total_qty INTEGER,
                actual_total_qty INTEGER,
                ai_vs_final_error_pct NUMERIC(10,4),
                ai_expected_vs_actual_error_pct NUMERIC(10,4),
                evaluation_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ai_run_id, sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_ai_plan_evaluation_date
            ON mpps_ai_plan_evaluation(plan_date, evaluation_status)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_ai_plan_runs (
                id BIGSERIAL PRIMARY KEY,
                plan_date DATE NOT NULL,
                source_import_run_id BIGINT,
                model_version VARCHAR(50) NOT NULL DEFAULT 'MPPS-AI-V10-HYBRID',
                control_mode VARCHAR(30) NOT NULL DEFAULT 'SHADOW',
                overall_confidence_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
                item_count INTEGER NOT NULL DEFAULT 0,
                shortage_items INTEGER NOT NULL DEFAULT 0,
                generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(30) NOT NULL DEFAULT 'ADVISORY'
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_ai_plan_runs_date
            ON mpps_ai_plan_runs(plan_date, id DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_ai_plan_items (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL REFERENCES mpps_ai_plan_runs(id) ON DELETE CASCADE,
                plan_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                shipment_demand_qty INTEGER NOT NULL DEFAULT 0,
                current_stock_qty INTEGER NOT NULL DEFAULT 0,
                net_requirement_qty INTEGER NOT NULL DEFAULT 0,
                learned_completion_ratio NUMERIC(12,6) NOT NULL DEFAULT 1,
                recommended_day_qty INTEGER NOT NULL DEFAULT 0,
                recommended_night_qty INTEGER NOT NULL DEFAULT 0,
                recommended_total_qty INTEGER NOT NULL DEFAULT 0,
                expected_actual_qty INTEGER NOT NULL DEFAULT 0,
                daily_capacity_qty INTEGER NOT NULL DEFAULT 0,
                confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                priority_score NUMERIC(12,4) NOT NULL DEFAULT 0,
                status VARCHAR(30) NOT NULL DEFAULT 'ADVISORY',
                explanation TEXT NOT NULL DEFAULT '',
                UNIQUE(run_id, sap_code)
            )
            """,
            "ALTER TABLE mpps_ai_plan_items ADD COLUMN IF NOT EXISTS learned_capacity_qty INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE mpps_ai_plan_items ADD COLUMN IF NOT EXISTS capacity_confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0",
            "ALTER TABLE mpps_ai_plan_items ADD COLUMN IF NOT EXISTS planner_policy_ratio NUMERIC(10,6) NOT NULL DEFAULT 1",
            "ALTER TABLE mpps_ai_plan_items ADD COLUMN IF NOT EXISTS planner_policy_confidence NUMERIC(10,6) NOT NULL DEFAULT 0",
        ]
        for statement in statements:
            session.execute(text(statement))

    @staticmethod
    def _latest_final_plan_rows(session, production_date: date | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        where = ""
        if production_date is not None:
            where = "WHERE f.plan_date = :plan_date"
            params["plan_date"] = production_date
        rows = session.execute(
            text(
                f"""
                SELECT f.*
                FROM mpps_final_plan_history f
                JOIN (
                    SELECT plan_date, sap_code, MAX(import_run_id) AS latest_run
                    FROM mpps_final_plan_history
                    GROUP BY plan_date, sap_code
                ) latest
                  ON latest.plan_date = f.plan_date
                 AND latest.sap_code = f.sap_code
                 AND latest.latest_run = f.import_run_id
                {where}
                ORDER BY f.plan_date, f.sap_code
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]

    def capture_final_excel_plan(self, session, *, import_run_id: int, analysis) -> dict[str, int]:
        """Persist per-workbook final-plan truth with one batched PostgreSQL write.

        R7.4.3 MAX-THROUGHPUT keeps the exact row semantics but removes one
        client/server round trip per SAP/date item.
        """
        self.ensure_schema(session)
        grouped: dict[tuple[date, str], dict[str, Any]] = {}
        for row in analysis.oven_rows:
            shift = str(row.get("shift_name") or "").upper().strip()
            if shift not in {"DAY", "NIGHT"}:
                continue
            sap = _code(row.get("sap_code"))
            if not sap:
                continue
            try:
                plan_date = date.fromisoformat(str(row.get("plan_date")))
            except Exception:
                continue
            key = (plan_date, sap)
            record = grouped.setdefault(
                key,
                {
                    "plan_date": plan_date,
                    "sap_code": sap,
                    "item_description": str(row.get("description") or ""),
                    "day_plan_qty": 0,
                    "night_plan_qty": 0,
                    "planned_weight_kg": 0.0,
                },
            )
            qty = max(0, _int(row.get("planned_qty")))
            if shift == "DAY":
                record["day_plan_qty"] += qty
            else:
                record["night_plan_qty"] += qty
            record["planned_weight_kg"] += max(0.0, _float(row.get("planned_weight_kg")))

        params = []
        for record in grouped.values():
            params.append(
                {
                    "import_run_id": int(import_run_id),
                    "total_plan_qty": record["day_plan_qty"] + record["night_plan_qty"],
                    "source_workbook": analysis.workbook_name,
                    **record,
                }
            )
        if params:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_final_plan_history (
                        import_run_id, plan_date, sap_code, item_description,
                        day_plan_qty, night_plan_qty, total_plan_qty,
                        planned_weight_kg, source_workbook, source_authority
                    ) VALUES (
                        :import_run_id, :plan_date, :sap_code, :item_description,
                        :day_plan_qty, :night_plan_qty, :total_plan_qty,
                        :planned_weight_kg, :source_workbook, 'EXCEL_FINAL'
                    )
                    ON CONFLICT (import_run_id, plan_date, sap_code)
                    DO UPDATE SET
                        item_description = EXCLUDED.item_description,
                        day_plan_qty = EXCLUDED.day_plan_qty,
                        night_plan_qty = EXCLUDED.night_plan_qty,
                        total_plan_qty = EXCLUDED.total_plan_qty,
                        planned_weight_kg = EXCLUDED.planned_weight_kg,
                        source_workbook = EXCLUDED.source_workbook
                    """
                ),
                params,
            )
        return {"final_excel_plan_items": len(grouped)}

    def capture_actual_production(self, session, *, import_run_id: int, analysis) -> dict[str, int]:
        """Persist verified actual-production truth using batched UPSERTs."""
        self.ensure_schema(session)
        rows = getattr(analysis, "production_history_rows", []) or []
        actual_dates = getattr(analysis, "actual_production_dates", []) or []

        date_params = []
        for date_row in actual_dates:
            try:
                production_date = date.fromisoformat(str(date_row.get("production_date")))
            except Exception:
                continue
            date_params.append(
                {
                    "production_date": production_date,
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": str(date_row.get("source_sheet") or "PROD"),
                    "source_day_column": str(date_row.get("source_day_column") or ""),
                    "source_night_column": str(date_row.get("source_night_column") or ""),
                    "source_import_run_id": int(import_run_id),
                    "is_complete": bool(date_row.get("is_complete", True)),
                }
            )
        if date_params:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_actual_production_dates (
                        production_date, source_workbook, source_sheet,
                        source_day_column, source_night_column,
                        source_import_run_id, is_complete, updated_at
                    ) VALUES (
                        :production_date, :source_workbook, :source_sheet,
                        :source_day_column, :source_night_column,
                        :source_import_run_id, :is_complete, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (production_date)
                    DO UPDATE SET
                        source_workbook = EXCLUDED.source_workbook,
                        source_sheet = EXCLUDED.source_sheet,
                        source_day_column = EXCLUDED.source_day_column,
                        source_night_column = EXCLUDED.source_night_column,
                        source_import_run_id = EXCLUDED.source_import_run_id,
                        is_complete = EXCLUDED.is_complete,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE COALESCE(
                              (SELECT plan_date FROM excel_import_runs
                               WHERE id = EXCLUDED.source_import_run_id),
                              DATE '1900-01-01'
                          ) >= COALESCE(
                              (SELECT plan_date FROM excel_import_runs
                               WHERE id = mpps_actual_production_dates.source_import_run_id),
                              DATE '1900-01-01'
                          )
                    """
                ),
                date_params,
            )

        row_params = []
        for row in rows:
            sap = _code(row.get("sap_code"))
            if not sap:
                continue
            try:
                production_date = date.fromisoformat(str(row.get("production_date")))
            except Exception:
                continue
            day_qty = max(0, _int(row.get("day_actual_qty", row.get("production_qty"))))
            night_qty = max(0, _int(row.get("night_actual_qty", 0)))
            total_qty = max(0, _int(row.get("production_qty", day_qty + night_qty)))
            if total_qty <= 0:
                continue
            if day_qty + night_qty > 0:
                total_qty = day_qty + night_qty
            row_params.append(
                {
                    "production_date": production_date,
                    "sap_code": sap,
                    "item_description": str(row.get("description") or ""),
                    "day_actual_qty": day_qty,
                    "night_actual_qty": night_qty,
                    "total_actual_qty": total_qty,
                    "source_day_column": str(row.get("source_day_column") or ""),
                    "source_night_column": str(row.get("source_night_column") or ""),
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": str(row.get("source_sheet") or "PROD"),
                    "source_import_run_id": int(import_run_id),
                }
            )
        if row_params:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_actual_production (
                        production_date, sap_code, item_description,
                        day_actual_qty, night_actual_qty, total_actual_qty,
                        source_day_column, source_night_column,
                        source_workbook, source_sheet, source_import_run_id,
                        source_semantics, updated_at
                    ) VALUES (
                        :production_date, :sap_code, :item_description,
                        :day_actual_qty, :night_actual_qty, :total_actual_qty,
                        :source_day_column, :source_night_column,
                        :source_workbook, :source_sheet, :source_import_run_id,
                        'VERIFIED_ACTUAL_PRODUCTION', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (production_date, sap_code)
                    DO UPDATE SET
                        item_description = EXCLUDED.item_description,
                        day_actual_qty = EXCLUDED.day_actual_qty,
                        night_actual_qty = EXCLUDED.night_actual_qty,
                        total_actual_qty = EXCLUDED.total_actual_qty,
                        source_day_column = EXCLUDED.source_day_column,
                        source_night_column = EXCLUDED.source_night_column,
                        source_workbook = EXCLUDED.source_workbook,
                        source_sheet = EXCLUDED.source_sheet,
                        source_import_run_id = EXCLUDED.source_import_run_id,
                        source_semantics = EXCLUDED.source_semantics,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE COALESCE(
                              (SELECT plan_date FROM excel_import_runs
                               WHERE id = EXCLUDED.source_import_run_id),
                              DATE '1900-01-01'
                          ) >= COALESCE(
                              (SELECT plan_date FROM excel_import_runs
                               WHERE id = mpps_actual_production.source_import_run_id),
                              DATE '1900-01-01'
                          )
                    """
                ),
                row_params,
            )
        return {
            "verified_actual_production_rows": len(row_params),
            "verified_actual_production_dates": len(date_params),
        }

    def reconcile_plan_vs_actual(self, session) -> dict[str, int]:
        """Rebuild plan-vs-actual reconciliation without rewriting unchanged rows.

        R7.4.2 batches PostgreSQL writes and adds an IS DISTINCT FROM guard.
        This preserves the exact reconciliation truth while avoiding millions of
        no-op UPDATE row versions during repeated learning refreshes.
        """
        self.ensure_schema(session)
        final_rows = self._latest_final_plan_rows(session)
        actual_rows = session.execute(
            text("SELECT * FROM mpps_actual_production ORDER BY production_date, sap_code")
        ).mappings().all()
        actual_map = {
            (row["production_date"], _code(row["sap_code"])): dict(row)
            for row in actual_rows
        }
        complete_dates = {
            row["production_date"]
            for row in session.execute(
                text("SELECT production_date FROM mpps_actual_production_dates WHERE is_complete = TRUE")
            ).mappings().all()
        }

        upsert_sql = text(
            """
            INSERT INTO mpps_plan_actual_reconciliation (
                production_date, sap_code, item_description,
                plan_day_qty, plan_night_qty, plan_total_qty,
                actual_day_qty, actual_night_qty, actual_total_qty,
                variance_qty, achievement_pct, abs_error_pct, status,
                source_plan_run_id, source_actual_run_id, updated_at
            ) VALUES (
                :production_date, :sap_code, :item_description,
                :plan_day_qty, :plan_night_qty, :plan_total_qty,
                :actual_day_qty, :actual_night_qty, :actual_total_qty,
                :variance_qty, :achievement_pct, :abs_error_pct, :status,
                :source_plan_run_id, :source_actual_run_id, CURRENT_TIMESTAMP
            )
            ON CONFLICT (production_date, sap_code)
            DO UPDATE SET
                item_description = EXCLUDED.item_description,
                plan_day_qty = EXCLUDED.plan_day_qty,
                plan_night_qty = EXCLUDED.plan_night_qty,
                plan_total_qty = EXCLUDED.plan_total_qty,
                actual_day_qty = EXCLUDED.actual_day_qty,
                actual_night_qty = EXCLUDED.actual_night_qty,
                actual_total_qty = EXCLUDED.actual_total_qty,
                variance_qty = EXCLUDED.variance_qty,
                achievement_pct = EXCLUDED.achievement_pct,
                abs_error_pct = EXCLUDED.abs_error_pct,
                status = EXCLUDED.status,
                source_plan_run_id = EXCLUDED.source_plan_run_id,
                source_actual_run_id = EXCLUDED.source_actual_run_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE (
                mpps_plan_actual_reconciliation.item_description,
                mpps_plan_actual_reconciliation.plan_day_qty,
                mpps_plan_actual_reconciliation.plan_night_qty,
                mpps_plan_actual_reconciliation.plan_total_qty,
                mpps_plan_actual_reconciliation.actual_day_qty,
                mpps_plan_actual_reconciliation.actual_night_qty,
                mpps_plan_actual_reconciliation.actual_total_qty,
                mpps_plan_actual_reconciliation.variance_qty,
                mpps_plan_actual_reconciliation.achievement_pct,
                mpps_plan_actual_reconciliation.abs_error_pct,
                mpps_plan_actual_reconciliation.status,
                mpps_plan_actual_reconciliation.source_plan_run_id,
                mpps_plan_actual_reconciliation.source_actual_run_id
            ) IS DISTINCT FROM (
                EXCLUDED.item_description,
                EXCLUDED.plan_day_qty,
                EXCLUDED.plan_night_qty,
                EXCLUDED.plan_total_qty,
                EXCLUDED.actual_day_qty,
                EXCLUDED.actual_night_qty,
                EXCLUDED.actual_total_qty,
                EXCLUDED.variance_qty,
                EXCLUDED.achievement_pct,
                EXCLUDED.abs_error_pct,
                EXCLUDED.status,
                EXCLUDED.source_plan_run_id,
                EXCLUDED.source_actual_run_id
            )
            """
        )

        batch: list[dict[str, Any]] = []
        reconciled = 0
        for plan in final_rows:
            key = (plan["plan_date"], _code(plan["sap_code"]))
            actual = actual_map.get(key)
            if actual is None and plan["plan_date"] in complete_dates:
                actual = {
                    "item_description": plan.get("item_description") or "",
                    "day_actual_qty": 0,
                    "night_actual_qty": 0,
                    "total_actual_qty": 0,
                    "source_import_run_id": None,
                }
            if actual is None:
                continue

            plan_total = max(0, _int(plan.get("total_plan_qty")))
            actual_total = max(0, _int(actual.get("total_actual_qty")))
            variance = actual_total - plan_total
            achievement = (actual_total / plan_total * 100.0) if plan_total > 0 else 0.0
            abs_error_pct = (
                abs(actual_total - plan_total) / max(plan_total, 1) * 100.0
                if plan_total > 0
                else 0.0
            )
            if plan_total <= 0 and actual_total > 0:
                status = "UNPLANNED PRODUCTION"
            elif actual_total == plan_total:
                status = "PLAN ACHIEVED"
            elif actual_total < plan_total:
                status = "SHORT PRODUCTION"
            else:
                status = "OVER PRODUCED"

            batch.append(
                {
                    "production_date": plan["plan_date"],
                    "sap_code": plan["sap_code"],
                    "item_description": plan.get("item_description") or actual.get("item_description") or "",
                    "plan_day_qty": _int(plan.get("day_plan_qty")),
                    "plan_night_qty": _int(plan.get("night_plan_qty")),
                    "plan_total_qty": plan_total,
                    "actual_day_qty": _int(actual.get("day_actual_qty")),
                    "actual_night_qty": _int(actual.get("night_actual_qty")),
                    "actual_total_qty": actual_total,
                    "variance_qty": variance,
                    "achievement_pct": round(achievement, 4),
                    "abs_error_pct": round(abs_error_pct, 4),
                    "status": status,
                    "source_plan_run_id": plan.get("import_run_id"),
                    "source_actual_run_id": actual.get("source_import_run_id"),
                }
            )
            reconciled += 1
            if len(batch) >= 5000:
                session.execute(upsert_sql, batch)
                batch.clear()

        if batch:
            session.execute(upsert_sql, batch)
        return {"plan_actual_reconciled_rows": reconciled}

    @staticmethod
    def _quantile(values: list[float], q: float, default: float = 1.0) -> float:
        cleaned = sorted(float(v) for v in values if math.isfinite(float(v)))
        if not cleaned:
            return default
        q = _clamp(q, 0.0, 1.0)
        pos = (len(cleaned) - 1) * q
        lower = int(math.floor(pos))
        upper = int(math.ceil(pos))
        if lower == upper:
            return cleaned[lower]
        weight = pos - lower
        return cleaned[lower] * (1.0 - weight) + cleaned[upper] * weight

    @staticmethod
    def _trend_ratio(ratios: list[float]) -> float:
        """Small-data-safe local trend forecast with bounded slope."""
        values = ratios[-12:]
        if len(values) < 4:
            return values[-1] if values else 1.0
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = mean(values)
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator <= 0:
            return values[-1]
        slope = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values)) / denominator
        slope = _clamp(slope, -0.05, 0.05)
        return _clamp(y_mean + slope * (n - x_mean), 0.50, 1.25)

    @staticmethod
    def _fit_item_model(
        observations: list[dict[str, Any]],
        global_prior: float = 1.0,
    ) -> dict[str, Any]:
        """Fit MPPS AI V9 champion/challenger execution model.

        Every validation prediction is one-step-ahead: the target day's actual is
        never visible when its prediction is created. Five explainable candidate
        models compete on walk-forward WAPE. Sparse SAPs are shrunk toward the
        factory-wide prior, while mature SAPs can select EWMA, weekday or local
        trend behavior. A conservative lower completion quantile is retained for
        shortage-risk planning instead of pretending the point forecast is certain.
        """
        observations = sorted(observations, key=lambda r: r["production_date"])
        global_prior = _clamp(global_prior or 1.0, 0.50, 1.25)
        ratios: list[float] = []
        day_shares: list[float] = []
        weekday_ratios: dict[int, list[float]] = defaultdict(list)
        weekday_day_shares: dict[int, list[float]] = defaultdict(list)
        alpha = 0.35
        ewma = global_prior
        initialized = False
        candidate_errors: dict[str, list[tuple[float, float]]] = defaultdict(list)
        champion_validation_rows: list[dict[str, Any]] = []

        def candidate_ratios(target_date: date) -> dict[str, float]:
            if not ratios:
                return {"GLOBAL_SHRINKAGE": global_prior}
            robust = _clamp(median(ratios[-30:]), 0.50, 1.25)
            sample_weight = len(ratios) / (len(ratios) + 6.0)
            shrink = _clamp(sample_weight * robust + (1.0 - sample_weight) * global_prior, 0.50, 1.25)
            candidates = {
                "GLOBAL_SHRINKAGE": shrink,
                "ROBUST_MEDIAN": robust,
                "EWMA": _clamp(ewma, 0.50, 1.25),
            }
            weekday_values = weekday_ratios.get(target_date.weekday(), [])
            if len(weekday_values) >= 2:
                weekday = _clamp(mean(weekday_values[-8:]), 0.50, 1.25)
                candidates["WEEKDAY_ENSEMBLE"] = _clamp(
                    0.50 * ewma + 0.25 * robust + 0.25 * weekday,
                    0.50,
                    1.25,
                )
            if len(ratios) >= 4:
                trend = AIPlanningService._trend_ratio(ratios)
                candidates["TREND_ENSEMBLE"] = _clamp(
                    0.45 * ewma + 0.25 * robust + 0.30 * trend,
                    0.50,
                    1.25,
                )
            return candidates

        for row in observations:
            plan = max(0, _int(row.get("plan_total_qty")))
            actual = max(0, _int(row.get("actual_total_qty")))
            if plan <= 0:
                continue
            production_date = row.get("production_date")
            if not isinstance(production_date, date):
                try:
                    production_date = date.fromisoformat(str(production_date))
                except Exception:
                    continue

            if initialized:
                for name, ratio_prediction in candidate_ratios(production_date).items():
                    candidate_errors[name].append((plan * ratio_prediction, float(actual)))

            ratio = _clamp(actual / plan, 0.0, 1.5)
            ratios.append(ratio)
            weekday_ratios[production_date.weekday()].append(ratio)
            if actual > 0:
                day_share = _clamp(_int(row.get("actual_day_qty")) / actual, 0.0, 1.0)
                day_shares.append(day_share)
                weekday_day_shares[production_date.weekday()].append(day_share)
            ewma = ratio if not initialized else alpha * ratio + (1.0 - alpha) * ewma
            initialized = True

        def score(rows: list[tuple[float, float]]) -> dict[str, float]:
            if not rows:
                return {"wape_pct": 100.0, "mae_qty": 0.0, "accuracy_pct": 0.0}
            abs_error = sum(abs(p - a) for p, a in rows)
            actual_total = sum(abs(a) for _, a in rows)
            wape = abs_error / max(actual_total, 1.0) * 100.0
            mae = mean(abs(p - a) for p, a in rows)
            return {
                "wape_pct": round(wape, 4),
                "mae_qty": round(mae, 5),
                "accuracy_pct": round(max(0.0, 100.0 - min(100.0, wape)), 4),
            }

        candidate_scores = {name: score(rows) for name, rows in candidate_errors.items()}
        eligible_scores = {
            name: value
            for name, value in candidate_scores.items()
            if len(candidate_errors.get(name, [])) >= 3
        }
        if eligible_scores:
            champion = min(eligible_scores, key=lambda name: eligible_scores[name]["wape_pct"])
        elif "EWMA" in candidate_scores:
            champion = "EWMA"
        elif "ROBUST_MEDIAN" in candidate_scores:
            champion = "ROBUST_MEDIAN"
        else:
            champion = "GLOBAL_SHRINKAGE"

        all_candidates = candidate_ratios(date.today())
        champion_ratio = all_candidates.get(champion)
        if champion_ratio is None:
            champion_ratio = all_candidates.get("EWMA", global_prior)

        sample_days = len(ratios)
        robust = median(ratios) if ratios else global_prior
        p25 = AIPlanningService._quantile(ratios[-40:], 0.25, global_prior)
        conservative = _clamp(min(champion_ratio, p25), 0.55, 1.15)

        # Drift compares recent execution with the immediately preceding window.
        drift_score = 0.0
        if len(ratios) >= 8:
            recent = ratios[-4:]
            previous = ratios[-8:-4]
            drift_score = _clamp(abs(mean(recent) - mean(previous)) / 0.25, 0.0, 1.0)

        champion_rows = candidate_errors.get(champion, [])
        champion_metrics = score(champion_rows)
        recent_metrics = score(champion_rows[-8:]) if champion_rows else champion_metrics
        validation_accuracy = champion_metrics["accuracy_pct"]
        stability = 1.0
        if len(ratios) >= 2:
            spread = mean(abs(r - mean(ratios)) for r in ratios[-30:])
            stability = _clamp(1.0 - spread / 0.35, 0.0, 1.0)
        sample_score = _clamp(sample_days / 24.0, 0.0, 1.0)
        validation_score = _clamp(validation_accuracy / 100.0, 0.0, 1.0)
        confidence = _clamp(
            0.38 * sample_score
            + 0.37 * validation_score
            + 0.20 * stability
            + 0.05 * (1.0 - drift_score),
            0.0,
            1.0,
        )
        if sample_days < 4:
            band = "LEARNING"
        elif drift_score >= 0.70:
            band = "DRIFT REVIEW"
        elif confidence >= 0.82:
            band = "HIGH"
        elif confidence >= 0.58:
            band = "MEDIUM"
        else:
            band = "LOW"

        weekday_summary = {
            str(key): {
                "ratio": round(mean(values[-8:]), 6),
                "samples": len(values),
                "day_share": round(mean(weekday_day_shares.get(key, [0.5])[-8:]), 6),
            }
            for key, values in weekday_ratios.items()
            if values
        }
        return {
            "sample_days": sample_days,
            "ewma_completion_ratio": round(_clamp(champion_ratio, 0.50, 1.25), 6),
            "median_completion_ratio": round(_clamp(robust, 0.50, 1.25), 6),
            "day_share": round(mean(day_shares[-30:]), 6) if day_shares else 0.5,
            "mae_qty": champion_metrics["mae_qty"],
            "mape_pct": champion_metrics["wape_pct"],
            "validation_accuracy_pct": validation_accuracy,
            "confidence_score": round(confidence, 6),
            "confidence_band": band,
            "ratios": ratios[-60:],
            "weekday_completion": weekday_summary,
            "validation_predictions": len(champion_rows),
            "champion_model": champion,
            "candidate_scores": candidate_scores,
            "conservative_completion_ratio": round(conservative, 6),
            "drift_score": round(drift_score, 6),
            "recent_wape_pct": recent_metrics["wape_pct"],
            "global_prior": round(global_prior, 6),
        }

    @staticmethod
    def _completion_for_date(model: dict[str, Any], plan_date: date) -> float:
        base = _clamp(_float(model.get("ewma_completion_ratio")) or 1.0, 0.50, 1.25)
        payload = model.get("model_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        weekday_map = payload.get("weekday_completion", {}) if isinstance(payload, dict) else {}
        champion = str(payload.get("champion_model") or "") if isinstance(payload, dict) else ""
        weekday_info = weekday_map.get(str(plan_date.weekday()), {}) if isinstance(weekday_map, dict) else {}
        weekday_ratio = _float(weekday_info.get("ratio")) if isinstance(weekday_info, dict) else 0.0
        weekday_samples = _int(weekday_info.get("samples")) if isinstance(weekday_info, dict) else 0
        if weekday_samples >= 2 and weekday_ratio > 0:
            weekday_weight = 0.30 if champion == "WEEKDAY_ENSEMBLE" else 0.15
            return _clamp((1.0 - weekday_weight) * base + weekday_weight * weekday_ratio, 0.50, 1.25)
        return base

    @staticmethod
    def _conservative_completion_for_date(model: dict[str, Any], plan_date: date) -> float:
        point = AIPlanningService._completion_for_date(model, plan_date)
        payload = model.get("model_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        lower = _float(payload.get("conservative_completion_ratio")) if isinstance(payload, dict) else 0.0
        if lower <= 0:
            lower = max(0.60, point * 0.90)
        return _clamp(min(point, lower), 0.55, 1.15)

    @staticmethod
    def _day_share_for_date(model: dict[str, Any], plan_date: date) -> float:
        base = _clamp(_float(model.get("day_share")) or 0.5, 0.10, 0.90)
        payload = model.get("model_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        weekday_map = payload.get("weekday_completion", {}) if isinstance(payload, dict) else {}
        info = weekday_map.get(str(plan_date.weekday()), {}) if isinstance(weekday_map, dict) else {}
        samples = _int(info.get("samples")) if isinstance(info, dict) else 0
        weekday_share = _float(info.get("day_share")) if isinstance(info, dict) else 0.0
        if samples >= 3 and weekday_share > 0:
            return _clamp(0.70 * base + 0.30 * weekday_share, 0.10, 0.90)
        return base

    def train_models(self, session) -> dict[str, int]:
        self.ensure_schema(session)
        rows = session.execute(
            text(
                """
                SELECT *
                FROM mpps_plan_actual_reconciliation
                WHERE plan_total_qty > 0
                ORDER BY sap_code, production_date
                """
            )
        ).mappings().all()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        global_ratios: list[float] = []
        for row in rows:
            record = dict(row)
            sap = _code(record.get("sap_code"))
            if not sap:
                continue
            grouped[sap].append(record)
            plan = max(0, _int(record.get("plan_total_qty")))
            actual = max(0, _int(record.get("actual_total_qty")))
            if plan > 0:
                global_ratios.append(_clamp(actual / plan, 0.0, 1.5))

        global_prior = _clamp(median(global_ratios), 0.50, 1.25) if global_ratios else 1.0
        high = 0
        drift_review = 0
        for sap, observations in grouped.items():
            model = self._fit_item_model(observations, global_prior=global_prior)
            if model["confidence_band"] == "HIGH":
                high += 1
            if model["confidence_band"] == "DRIFT REVIEW":
                drift_review += 1
            payload = {
                "algorithm": "MPPS-AI-V10 execution champion/challenger walk-forward ensemble",
                "leakage_safe": True,
                "global_prior": model["global_prior"],
                "champion_model": model["champion_model"],
                "candidate_scores": model["candidate_scores"],
                "conservative_completion_ratio": model["conservative_completion_ratio"],
                "drift_score": model["drift_score"],
                "recent_wape_pct": model["recent_wape_pct"],
                "ratios": model["ratios"],
                "weekday_completion": model["weekday_completion"],
                "validation_predictions": model["validation_predictions"],
                "features": [
                    "historical plan-vs-actual completion",
                    "recency/EWMA",
                    "robust median",
                    "same weekday execution",
                    "bounded local trend",
                    "factory-wide sparse-data prior",
                    "day/night execution split",
                ],
            }
            session.execute(
                text(
                    """
                    INSERT INTO mpps_ai_model_state (
                        model_key, sap_code, sample_days, ewma_completion_ratio,
                        median_completion_ratio, day_share, mae_qty, mape_pct,
                        validation_accuracy_pct, confidence_score, confidence_band,
                        model_json, last_trained_at, updated_at
                    ) VALUES (
                        :model_key, :sap_code, :sample_days, :ewma_completion_ratio,
                        :median_completion_ratio, :day_share, :mae_qty, :mape_pct,
                        :validation_accuracy_pct, :confidence_score, :confidence_band,
                        CAST(:model_json AS JSONB), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (model_key)
                    DO UPDATE SET
                        sample_days = EXCLUDED.sample_days,
                        ewma_completion_ratio = EXCLUDED.ewma_completion_ratio,
                        median_completion_ratio = EXCLUDED.median_completion_ratio,
                        day_share = EXCLUDED.day_share,
                        mae_qty = EXCLUDED.mae_qty,
                        mape_pct = EXCLUDED.mape_pct,
                        validation_accuracy_pct = EXCLUDED.validation_accuracy_pct,
                        confidence_score = EXCLUDED.confidence_score,
                        confidence_band = EXCLUDED.confidence_band,
                        model_json = EXCLUDED.model_json,
                        last_trained_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "model_key": f"EXECUTION_RELIABILITY|{sap}",
                    "sap_code": sap,
                    "sample_days": model["sample_days"],
                    "ewma_completion_ratio": model["ewma_completion_ratio"],
                    "median_completion_ratio": model["median_completion_ratio"],
                    "day_share": model["day_share"],
                    "mae_qty": model["mae_qty"],
                    "mape_pct": model["mape_pct"],
                    "validation_accuracy_pct": model["validation_accuracy_pct"],
                    "confidence_score": model["confidence_score"],
                    "confidence_band": model["confidence_band"],
                    "model_json": json.dumps(payload, default=str),
                },
            )
        return {
            "ai_models_trained": len(grouped),
            "ai_high_confidence_models": high,
            "ai_drift_review_models": drift_review,
        }

    def evaluate_ai_runs(self, session) -> dict[str, int]:
        """Evaluate all shadow AI plan items with batched, no-op-safe upserts.

        The evaluation table is derived state. R7.4.2 avoids one round trip and
        one new row version per AI item by batching writes and updating only
        rows whose evaluation values actually changed.
        """
        self.ensure_schema(session)
        final_map = {
            (row["plan_date"], _code(row["sap_code"])): row
            for row in self._latest_final_plan_rows(session)
        }
        actual_map = {
            (row["production_date"], _code(row["sap_code"])): dict(row)
            for row in session.execute(
                text("SELECT * FROM mpps_actual_production")
            ).mappings().all()
        }
        complete_dates = {
            row["production_date"]
            for row in session.execute(
                text("SELECT production_date FROM mpps_actual_production_dates WHERE is_complete = TRUE")
            ).mappings().all()
        }
        rows = session.execute(
            text(
                """
                SELECT i.*, r.plan_date AS run_plan_date, r.generated_at AS run_generated_at
                FROM mpps_ai_plan_items i
                JOIN mpps_ai_plan_runs r ON r.id = i.run_id
                ORDER BY i.run_id, i.sap_code
                """
            )
        ).mappings().all()

        upsert_sql = text(
            """
            INSERT INTO mpps_ai_plan_evaluation (
                ai_run_id, plan_date, sap_code,
                ai_recommended_total_qty, ai_expected_actual_qty,
                final_excel_total_qty, actual_total_qty,
                ai_vs_final_error_pct, ai_expected_vs_actual_error_pct,
                evaluation_status, updated_at
            ) VALUES (
                :ai_run_id, :plan_date, :sap_code,
                :ai_recommended_total_qty, :ai_expected_actual_qty,
                :final_excel_total_qty, :actual_total_qty,
                :ai_vs_final_error_pct, :ai_expected_vs_actual_error_pct,
                :evaluation_status, CURRENT_TIMESTAMP
            )
            ON CONFLICT (ai_run_id, sap_code)
            DO UPDATE SET
                plan_date = EXCLUDED.plan_date,
                ai_recommended_total_qty = EXCLUDED.ai_recommended_total_qty,
                ai_expected_actual_qty = EXCLUDED.ai_expected_actual_qty,
                final_excel_total_qty = EXCLUDED.final_excel_total_qty,
                actual_total_qty = EXCLUDED.actual_total_qty,
                ai_vs_final_error_pct = EXCLUDED.ai_vs_final_error_pct,
                ai_expected_vs_actual_error_pct = EXCLUDED.ai_expected_vs_actual_error_pct,
                evaluation_status = EXCLUDED.evaluation_status,
                updated_at = CURRENT_TIMESTAMP
            WHERE (
                mpps_ai_plan_evaluation.plan_date,
                mpps_ai_plan_evaluation.ai_recommended_total_qty,
                mpps_ai_plan_evaluation.ai_expected_actual_qty,
                mpps_ai_plan_evaluation.final_excel_total_qty,
                mpps_ai_plan_evaluation.actual_total_qty,
                mpps_ai_plan_evaluation.ai_vs_final_error_pct,
                mpps_ai_plan_evaluation.ai_expected_vs_actual_error_pct,
                mpps_ai_plan_evaluation.evaluation_status
            ) IS DISTINCT FROM (
                EXCLUDED.plan_date,
                EXCLUDED.ai_recommended_total_qty,
                EXCLUDED.ai_expected_actual_qty,
                EXCLUDED.final_excel_total_qty,
                EXCLUDED.actual_total_qty,
                EXCLUDED.ai_vs_final_error_pct,
                EXCLUDED.ai_expected_vs_actual_error_pct,
                EXCLUDED.evaluation_status
            )
            """
        )

        evaluated = 0
        validated = 0
        batch: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            plan_date = row.get("run_plan_date") or row.get("plan_date")
            sap = _code(row.get("sap_code"))
            final = final_map.get((plan_date, sap))
            actual = actual_map.get((plan_date, sap))
            ai_total = max(0, _int(row.get("recommended_total_qty")))
            expected = max(0, _int(row.get("expected_actual_qty")))
            final_total = max(0, _int(final.get("total_plan_qty"))) if final else None
            if actual is not None:
                actual_total = max(0, _int(actual.get("total_actual_qty")))
            elif plan_date in complete_dates:
                actual_total = 0
            else:
                actual_total = None
            final_error = (
                abs(ai_total - final_total) / max(final_total, 1) * 100.0
                if final_total is not None
                else None
            )
            actual_error = (
                abs(expected - actual_total) / max(actual_total, 1) * 100.0
                if actual_total is not None
                else None
            )
            generated_at = row.get("run_generated_at")
            generated_on_time = True
            if generated_at is not None:
                try:
                    generated_on_time = generated_at.date() <= plan_date
                except Exception:
                    generated_on_time = True
            if actual_total is not None and generated_on_time:
                status = "VALIDATED"
                validated += 1
            elif actual_total is not None:
                status = "RETROSPECTIVE"
            elif final_total is not None and generated_on_time:
                status = "FINAL PLAN AVAILABLE"
            elif final_total is not None:
                status = "RETROSPECTIVE"
            else:
                status = "PENDING"

            batch.append(
                {
                    "ai_run_id": int(row["run_id"]),
                    "plan_date": plan_date,
                    "sap_code": sap,
                    "ai_recommended_total_qty": ai_total,
                    "ai_expected_actual_qty": expected,
                    "final_excel_total_qty": final_total,
                    "actual_total_qty": actual_total,
                    "ai_vs_final_error_pct": round(final_error, 4) if final_error is not None else None,
                    "ai_expected_vs_actual_error_pct": round(actual_error, 4) if actual_error is not None else None,
                    "evaluation_status": status,
                }
            )
            evaluated += 1
            if len(batch) >= 5000:
                session.execute(upsert_sql, batch)
                batch.clear()

        if batch:
            session.execute(upsert_sql, batch)

        return {
            "ai_plan_evaluations": evaluated,
            "ai_plan_validated_items": validated,
        }

    def get_readiness(self, session) -> Readiness:
        self.ensure_schema(session)
        settings = session.execute(
            text("SELECT * FROM mpps_ai_settings WHERE id = 1")
        ).mappings().first() or {}
        ai_validation_days = _int(
            session.execute(
                text(
                    "SELECT COUNT(DISTINCT plan_date) FROM mpps_ai_plan_evaluation "
                    "WHERE evaluation_status = 'VALIDATED'"
                )
            ).scalar()
        )
        model_validation_days = _int(
            session.execute(
                text("SELECT COUNT(DISTINCT production_date) FROM mpps_plan_actual_reconciliation")
            ).scalar()
        )
        counts = session.execute(
            text(
                """
                SELECT
                    COUNT(*)::INTEGER AS total,
                    COUNT(*) FILTER (WHERE confidence_band = 'HIGH')::INTEGER AS high,
                    COALESCE(AVG(validation_accuracy_pct), 0) AS accuracy
                FROM mpps_ai_model_state
                """
            )
        ).mappings().first() or {}
        ai_eval = session.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE e.plan_date <= CURRENT_DATE
                          AND DATE(r.generated_at) <= e.plan_date
                    ) AS due_items,
                    COUNT(*) FILTER (WHERE e.evaluation_status = 'VALIDATED') AS validated_items,
                    COALESCE(AVG(100.0 - LEAST(100.0, e.ai_expected_vs_actual_error_pct))
                        FILTER (WHERE e.evaluation_status = 'VALIDATED'), 0) AS accuracy
                FROM mpps_ai_plan_evaluation e
                JOIN mpps_ai_plan_runs r ON r.id = e.ai_run_id
                """
            )
        ).mappings().first() or {}
        due_items = _int(ai_eval.get("due_items"))
        validated_items = _int(ai_eval.get("validated_items"))
        coverage_pct = (100.0 * validated_items / due_items) if due_items > 0 else 0.0
        if validated_items > 0:
            accuracy = _float(ai_eval.get("accuracy"))
            accuracy_basis = "END_TO_END_AI_CANDIDATE_VS_ACTUAL"
            validation_days = ai_validation_days
        else:
            accuracy = _float(counts.get("accuracy"))
            accuracy_basis = "MODEL_BACKTEST_ONLY"
            validation_days = ai_validation_days
        target_accuracy = _float(settings.get("target_accuracy_pct")) or self.DEFAULT_TARGET_ACCURACY
        min_days = _int(settings.get("min_validation_days")) or self.DEFAULT_MIN_VALIDATION_DAYS
        min_coverage = _float(settings.get("min_coverage_pct")) or self.DEFAULT_MIN_COVERAGE
        eligible = (
            validation_days >= min_days
            and accuracy >= target_accuracy
            and coverage_pct >= min_coverage
            and _int(counts.get("total")) > 0
        )
        if eligible:
            explanation = (
                "Validation gates passed. AI may be promoted only by an authorized user; "
                "Excel remains final until that explicit promotion."
            )
        else:
            explanation = (
                f"Shadow learning continues: need >= {min_days} validated days, "
                f">= {target_accuracy:.1f}% validation accuracy and >= {min_coverage:.1f}% data coverage. "
                f"Current accuracy basis: {accuracy_basis}; historical plan/actual days available: {model_validation_days}."
            )
        return Readiness(
            mode=str(settings.get("control_mode") or "SHADOW"),
            validation_days=validation_days,
            accuracy_pct=round(accuracy, 2),
            coverage_pct=round(coverage_pct, 2),
            high_confidence_items=_int(counts.get("high")),
            total_models=_int(counts.get("total")),
            target_accuracy_pct=target_accuracy,
            min_validation_days=min_days,
            min_coverage_pct=min_coverage,
            eligible_for_supervised_auto=eligible,
            accuracy_basis=accuracy_basis,
            explanation=explanation,
        )

    @staticmethod
    def _active_shipment_demand(session) -> dict[str, dict[str, Any]]:
        rows = session.execute(
            text(
                """
                SELECT
                    i.sap_code,
                    MAX(COALESCE(i.item_description, '')) AS item_description,
                    COALESCE(SUM(GREATEST(
                        COALESCE(i.remaining_qty, 0),
                        COALESCE(i.production_required_qty, 0),
                        COALESCE(i.quantity, 0) - COALESCE(i.completed_qty, 0),
                        0
                    )), 0) AS demand_qty,
                    MIN(COALESCE(s.factory_out_date, s.target_date, s.shipment_date)) AS nearest_due_date,
                    COALESCE(MAX(GREATEST(COALESCE(i.daily_capacity, 0), 0)), 0) AS daily_capacity
                FROM mpps_shipment_items i
                JOIN mpps_shipments s ON s.id = i.shipment_id
                WHERE COALESCE(LOWER(s.status), 'planned') NOT IN (
                    'cancelled','canceled','closed','complete','completed','shipped','done','superseded import'
                )
                  AND COALESCE(i.source_removed_from_latest, FALSE) = FALSE
                GROUP BY i.sap_code
                HAVING COALESCE(SUM(GREATEST(
                    COALESCE(i.remaining_qty, 0),
                    COALESCE(i.production_required_qty, 0),
                    COALESCE(i.quantity, 0) - COALESCE(i.completed_qty, 0),
                    0
                )), 0) > 0
                """
            )
        ).mappings().all()
        return {_code(row["sap_code"]): dict(row) for row in rows if _code(row["sap_code"])}

    @staticmethod
    def _latest_monthly_opening(session, as_of: date) -> tuple[date | None, dict[str, int]]:
        # Monthly stock is the manually supplied opening-stock authority.
        month_key = as_of.strftime("%Y-%m")
        header = session.execute(
            text(
                """
                SELECT id, month_key
                FROM monthly_stock_counts
                WHERE is_active = TRUE AND month_key <= :month_key
                ORDER BY month_key DESC, uploaded_at DESC
                LIMIT 1
                """
            ),
            {"month_key": month_key},
        ).mappings().first()
        if not header:
            return None, {}
        opening_date = date.fromisoformat(str(header["month_key"]) + "-01")
        rows = session.execute(
            text(
                """
                SELECT material_code, final_stock_qty
                FROM monthly_stock_count_lines
                WHERE stock_count_id = :stock_count_id
                """
            ),
            {"stock_count_id": int(header["id"])},
        ).mappings().all()
        return opening_date, {_code(r["material_code"]): max(0, _int(r["final_stock_qty"])) for r in rows}

    def current_stock_snapshot(self, session, as_of: date) -> dict[str, int]:
        self.ensure_schema(session)
        try:
            opening_date, stock = self._latest_monthly_opening(session, as_of)
        except Exception:
            opening_date, stock = None, {}
        if opening_date is None:
            # Safe fallback for installations that have not yet imported monthly stock.
            rows = session.execute(
                text(
                    """
                    SELECT sap_code, GREATEST(COALESCE(fg_stock,0) + COALESCE(qc_stock,0), 0) AS qty
                    FROM mpps_sap_stock_items
                    WHERE is_active = TRUE
                    """
                )
            ).mappings().all()
            return {_code(r["sap_code"]): _int(r["qty"]) for r in rows}

        production = session.execute(
            text(
                """
                SELECT sap_code, SUM(total_actual_qty) AS qty
                FROM mpps_actual_production
                WHERE production_date >= :opening_date
                  AND production_date <= :as_of
                GROUP BY sap_code
                """
            ),
            {"opening_date": opening_date, "as_of": as_of},
        ).mappings().all()
        for row in production:
            sap = _code(row["sap_code"])
            stock[sap] = stock.get(sap, 0) + max(0, _int(row["qty"]))

        # Only confirmed/completed shipment states reduce physical stock.
        try:
            shipped = session.execute(
                text(
                    """
                    SELECT i.sap_code, SUM(GREATEST(COALESCE(i.quantity,0),0)) AS qty
                    FROM mpps_shipment_items i
                    JOIN mpps_shipments s ON s.id = i.shipment_id
                    WHERE LOWER(COALESCE(s.status,'')) IN ('shipped','complete','completed','closed','done')
                      AND COALESCE(s.factory_out_date, s.shipment_date) >= :opening_date
                      AND COALESCE(s.factory_out_date, s.shipment_date) <= :as_of
                    GROUP BY i.sap_code
                    """
                ),
                {"opening_date": opening_date, "as_of": as_of},
            ).mappings().all()
            for row in shipped:
                sap = _code(row["sap_code"])
                stock[sap] = max(0, stock.get(sap, 0) - max(0, _int(row["qty"])))
        except Exception:
            # Shipment status/date completeness can vary in old databases. Never
            # invent a dispatch deduction when confirmed data is unavailable.
            pass
        return stock

    def projected_stock_for_plan(
        self,
        session,
        *,
        plan_date: date,
        models: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Return planning stock available for *plan_date*.

        Physical stock is built only from the monthly opening, verified actual
        production and confirmed shipments.  If the immediately preceding day
        has a FINAL Excel plan but its PROD actual pair is not complete yet, the
        system adds only the model-expected remainder of that committed plan.
        This is critical for next-day planning: today's final plan influences
        tomorrow without ever being posted as historical actual production.
        """
        self.ensure_schema(session)
        cutoff = plan_date - timedelta(days=1)
        stock = self.current_stock_snapshot(session, cutoff)
        models = models or {
            _code(row["sap_code"]): dict(row)
            for row in session.execute(text("SELECT * FROM mpps_ai_model_state")).mappings().all()
        }
        date_state = session.execute(
            text(
                """
                SELECT is_complete
                FROM mpps_actual_production_dates
                WHERE production_date = :production_date
                """
            ),
            {"production_date": cutoff},
        ).mappings().first()
        if date_state and bool(date_state.get("is_complete")):
            return stock, {}

        final_rows = self._latest_final_plan_rows(session, cutoff)
        if not final_rows:
            return stock, {}
        known_rows = session.execute(
            text(
                """
                SELECT sap_code, total_actual_qty
                FROM mpps_actual_production
                WHERE production_date = :production_date
                """
            ),
            {"production_date": cutoff},
        ).mappings().all()
        known = {_code(r["sap_code"]): max(0, _int(r["total_actual_qty"])) for r in known_rows}
        projected_in: dict[str, int] = {}
        for row in final_rows:
            sap = _code(row.get("sap_code"))
            plan_qty = max(0, _int(row.get("total_plan_qty")))
            if not sap or plan_qty <= 0:
                continue
            model = models.get(sap, {})
            completion = _clamp(self._completion_for_date(model, cutoff), 0.60, 1.20)
            expected = max(0, int(round(plan_qty * completion)))
            remainder = max(0, expected - known.get(sap, 0))
            if remainder <= 0:
                continue
            stock[sap] = stock.get(sap, 0) + remainder
            projected_in[sap] = remainder
        return stock, projected_in

    def generate_candidate_plan(
        self,
        session,
        *,
        plan_date: date,
        source_import_run_id: int | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema(session)
        factory_intelligence = FactoryIntelligenceService()
        factory_intelligence.ensure_schema(session)
        demand = self._active_shipment_demand(session)
        models = {
            _code(row["sap_code"]): dict(row)
            for row in session.execute(text("SELECT * FROM mpps_ai_model_state")).mappings().all()
        }
        stock, projected_in = self.projected_stock_for_plan(
            session, plan_date=plan_date, models=models
        )
        settings = session.execute(text("SELECT * FROM mpps_ai_settings WHERE id=1")).mappings().first() or {}
        mode = str(settings.get("control_mode") or "SHADOW")
        item_rows: list[dict[str, Any]] = []
        for sap, d in demand.items():
            demand_qty = max(0, _int(d.get("demand_qty")))
            current_stock = max(0, stock.get(sap, 0))
            net = max(0, demand_qty - current_stock)
            if net <= 0:
                continue
            model = models.get(sap, {})
            completion = _clamp(self._completion_for_date(model, plan_date), 0.60, 1.20)
            conservative_completion = _clamp(
                self._conservative_completion_for_date(model, plan_date), 0.55, 1.15
            )
            day_share = self._day_share_for_date(model, plan_date)
            static_capacity = max(0, _int(d.get("daily_capacity")))
            capacity_model = factory_intelligence.capacity_for_sap(session, sap)
            learned_capacity = max(0, _int(capacity_model.get("safe_capacity_qty")))
            capacity_confidence = _clamp(_float(capacity_model.get("confidence_score")), 0.0, 1.0)
            if learned_capacity > 0 and static_capacity > 0:
                learned_weight = 0.70 if capacity_confidence >= 0.70 else 0.35
                capacity = int(round(learned_weight * learned_capacity + (1.0 - learned_weight) * static_capacity))
            elif learned_capacity > 0:
                capacity = learned_capacity
            else:
                capacity = static_capacity

            planner_policy = factory_intelligence.planner_policy_for_sap(session, sap)
            policy_ratio = _clamp(_float(planner_policy.get("planning_ratio")) or 1.0, 0.60, 1.60)
            policy_confidence = _clamp(_float(planner_policy.get("confidence_score")), 0.0, 1.0)
            due = d.get("nearest_due_date")
            days_to_due = 999
            if due:
                try:
                    days_to_due = (due - plan_date).days
                except Exception:
                    days_to_due = 999
            urgency = 100.0 if days_to_due <= 0 else max(0.0, 60.0 - days_to_due * 5.0)
            confidence = _float(model.get("confidence_score"))
            band = str(model.get("confidence_band") or "LEARNING")
            # Risk-aware planning: urgent/low-confidence items use the conservative
            # completion estimate, while stable high-confidence items use the point estimate.
            risk_weight = 0.0
            if days_to_due <= 1:
                risk_weight = 1.0
            elif band in {"LOW", "LEARNING", "DRIFT REVIEW"}:
                risk_weight = 0.75
            elif confidence < 0.75:
                risk_weight = 0.40
            planning_completion = _clamp(
                (1.0 - risk_weight) * completion + risk_weight * conservative_completion,
                0.55,
                1.20,
            )
            point_needed = int(math.ceil(net / max(completion, 0.60)))
            execution_needed = int(math.ceil(net / max(planning_completion, 0.55)))
            human_policy_needed = int(math.ceil(net * policy_ratio))
            # V10 learns both execution reliability and the planner's historical
            # decision policy.  Execution remains the stronger signal until the
            # human-policy model has enough validated history.
            policy_weight = 0.35 * policy_confidence
            gross_needed = int(math.ceil(
                (1.0 - policy_weight) * execution_needed
                + policy_weight * human_policy_needed
            ))
            gross_needed = max(net, gross_needed)
            recommended_total = min(gross_needed, capacity) if capacity > 0 else gross_needed
            day_qty = int(round(recommended_total * day_share))
            night_qty = max(0, recommended_total - day_qty)
            expected_actual = int(round(recommended_total * completion))
            safety_buffer = max(0, recommended_total - point_needed)
            intelligence_weights = [(confidence, 0.65)]
            if learned_capacity > 0:
                intelligence_weights.append((capacity_confidence, 0.20))
            if planner_policy:
                intelligence_weights.append((policy_confidence, 0.15))
            total_weight = sum(weight for _, weight in intelligence_weights)
            combined_confidence = sum(value * weight for value, weight in intelligence_weights) / max(total_weight, 0.01)
            confidence = _clamp(combined_confidence, 0.0, 1.0)
            shortage_pressure = min(100.0, net / max(demand_qty, 1) * 100.0)
            priority = 0.55 * shortage_pressure + 0.35 * urgency + 0.10 * confidence * 100.0
            if capacity > 0 and gross_needed > capacity:
                status = "CAPACITY CONSTRAINED"
            elif band in {"LOW", "LEARNING", "DRIFT REVIEW"}:
                status = "HUMAN REVIEW"
            else:
                status = "AI ADVISORY"
            committed_projection = max(0, projected_in.get(sap, 0))
            projection_note = (
                f" Includes {committed_projection:,} expected units from the previous day's "
                "FINAL Excel plan that are not yet available as verified PROD actual."
                if committed_projection > 0
                else ""
            )
            explanation = (
                f"Demand {demand_qty:,}; planning stock {current_stock:,}; net {net:,}."
                f"{projection_note} V10 execution completion {completion:.3f}; conservative {conservative_completion:.3f}; "
                f"risk planning ratio {planning_completion:.3f}; learned human-plan ratio {policy_ratio:.3f} "
                f"(conf {policy_confidence:.0%}); learned safe capacity {learned_capacity:,} "
                f"(conf {capacity_confidence:.0%}); blended capacity {capacity:,}; safety buffer {safety_buffer:,}. "
                f"AI recommends {recommended_total:,} to expect about {expected_actual:,} actual. "
                "Newest OVEN Excel remains final operational authority; older workbooks train the models only."
            )
            item_rows.append(
                {
                    "sap_code": sap,
                    "item_description": d.get("item_description") or "",
                    "shipment_demand_qty": demand_qty,
                    "current_stock_qty": current_stock,
                    "net_requirement_qty": net,
                    "learned_completion_ratio": completion,
                    "recommended_day_qty": day_qty,
                    "recommended_night_qty": night_qty,
                    "recommended_total_qty": recommended_total,
                    "expected_actual_qty": expected_actual,
                    "daily_capacity_qty": capacity,
                    "learned_capacity_qty": learned_capacity,
                    "capacity_confidence_score": capacity_confidence,
                    "planner_policy_ratio": policy_ratio,
                    "planner_policy_confidence": policy_confidence,
                    "confidence_score": confidence,
                    "confidence_band": band,
                    "priority_score": round(priority, 4),
                    "status": status,
                    "explanation": explanation,
                }
            )
        item_rows.sort(key=lambda r: (-r["priority_score"], r["sap_code"]))
        overall_conf = mean([r["confidence_score"] for r in item_rows]) * 100.0 if item_rows else 0.0
        shortage_items = sum(1 for r in item_rows if r["net_requirement_qty"] > 0)
        run_id = session.execute(
            text(
                """
                INSERT INTO mpps_ai_plan_runs (
                    plan_date, source_import_run_id, model_version, control_mode,
                    overall_confidence_pct, item_count, shortage_items, status
                ) VALUES (
                    :plan_date, :source_import_run_id, 'MPPS-AI-V10-HYBRID', :control_mode,
                    :overall_confidence_pct, :item_count, :shortage_items, 'ADVISORY'
                ) RETURNING id
                """
            ),
            {
                "plan_date": plan_date,
                "source_import_run_id": source_import_run_id,
                "control_mode": mode,
                "overall_confidence_pct": round(overall_conf, 4),
                "item_count": len(item_rows),
                "shortage_items": shortage_items,
            },
        ).scalar_one()
        for row in item_rows:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_ai_plan_items (
                        run_id, plan_date, sap_code, item_description,
                        shipment_demand_qty, current_stock_qty, net_requirement_qty,
                        learned_completion_ratio, recommended_day_qty,
                        recommended_night_qty, recommended_total_qty,
                        expected_actual_qty, daily_capacity_qty, learned_capacity_qty,
                        capacity_confidence_score, planner_policy_ratio, planner_policy_confidence, confidence_score,
                        confidence_band, priority_score, status, explanation
                    ) VALUES (
                        :run_id, :plan_date, :sap_code, :item_description,
                        :shipment_demand_qty, :current_stock_qty, :net_requirement_qty,
                        :learned_completion_ratio, :recommended_day_qty,
                        :recommended_night_qty, :recommended_total_qty,
                        :expected_actual_qty, :daily_capacity_qty, :learned_capacity_qty,
                        :capacity_confidence_score, :planner_policy_ratio, :planner_policy_confidence, :confidence_score,
                        :confidence_band, :priority_score, :status, :explanation
                    )
                    """
                ),
                {"run_id": int(run_id), "plan_date": plan_date, **row},
            )
        return {
            "ai_plan_run_id": int(run_id),
            "ai_plan_date": plan_date.isoformat(),
            "ai_plan_items": len(item_rows),
            "ai_plan_shortage_items": shortage_items,
            "ai_overall_confidence_pct": round(overall_conf, 2),
        }

    def rebuild_after_historical_ingestion(self, session) -> dict[str, Any]:
        """Run the expensive global AI refresh exactly once after bulk history.

        Historical workbooks still capture their final-plan and verified-actual
        evidence transactionally. Only whole-history reconciliation/model/evaluation
        and shadow-plan regeneration are deferred until ingestion is complete.
        """
        self.ensure_schema(session)
        result: dict[str, Any] = {}
        result.update(self.reconcile_plan_vs_actual(session))
        result.update(self.train_models(session))
        result.update(self.evaluate_ai_runs(session))

        source = OperationalSourceService.latest(session)
        if source.plan_date:
            target_date = source.plan_date + timedelta(days=1)
            source_run_id = source.import_run_id
        else:
            latest_plan_date = session.execute(
                text("SELECT MAX(plan_date) FROM mpps_final_plan_history")
            ).scalar()
            target_date = (latest_plan_date or date.today()) + timedelta(days=1)
            source_run_id = None

        result.update(
            self.generate_candidate_plan(
                session,
                plan_date=target_date,
                source_import_run_id=source_run_id,
            )
        )
        result.update(self.evaluate_ai_runs(session))
        result["ai_operational_source_date"] = source.plan_date.isoformat() if source.plan_date else None
        result["ai_import_mode"] = "DEFERRED_HISTORICAL_REBUILD"
        result["ai_history_training_only"] = False
        return result

    def post_excel_import(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
        import_mode: str = "LIVE",
    ) -> dict[str, Any]:
        """Capture workbook AI evidence and refresh global AI state when appropriate.

        R7.4.2 keeps per-workbook truth capture unchanged. During the dedicated
        historical bulk-training launcher, however, global reconciliation/model/
        evaluation/shadow-plan work is deferred and rebuilt once after ingestion.
        Normal LIVE app imports retain the original immediate-refresh behavior.
        """
        self.ensure_schema(session)
        result: dict[str, Any] = {}
        result.update(self.capture_final_excel_plan(session, import_run_id=import_run_id, analysis=analysis))
        result.update(self.capture_actual_production(session, import_run_id=import_run_id, analysis=analysis))

        normalized_mode = str(import_mode or "LIVE").upper()
        bulk_history = (
            normalized_mode == "HISTORICAL"
            and str(os.environ.get("MPPS_R741_BULK_HISTORY") or "").strip().lower()
            in {"1", "true", "yes", "on"}
            and str(os.environ.get("MPPS_R742_DEFER_AI_GLOBAL") or "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        source = OperationalSourceService.latest(session)

        if bulk_history:
            result["ai_global_rebuild_deferred"] = True
            result["ai_operational_source_date"] = source.plan_date.isoformat() if source.plan_date else None
            result["ai_import_mode"] = normalized_mode
            result["ai_history_training_only"] = True
            return result

        result.update(self.reconcile_plan_vs_actual(session))
        result.update(self.train_models(session))
        result.update(self.evaluate_ai_runs(session))

        if source.plan_date:
            target_date = source.plan_date + timedelta(days=1)
            source_run_id = source.import_run_id
        else:
            try:
                base_date = date.fromisoformat(analysis.plan_date) if analysis.plan_date else date.today()
            except Exception:
                base_date = date.today()
            target_date = base_date + timedelta(days=1)
            source_run_id = import_run_id

        result.update(
            self.generate_candidate_plan(
                session,
                plan_date=target_date,
                source_import_run_id=source_run_id,
            )
        )
        result.update(self.evaluate_ai_runs(session))
        result["ai_operational_source_date"] = source.plan_date.isoformat() if source.plan_date else None
        result["ai_import_mode"] = normalized_mode
        result["ai_history_training_only"] = normalized_mode == "HISTORICAL"
        return result

    def dashboard(self, session, limit: int = 500) -> dict[str, Any]:
        self.ensure_schema(session)
        readiness = self.get_readiness(session)
        latest_run = session.execute(
            text("SELECT * FROM mpps_ai_plan_runs ORDER BY id DESC LIMIT 1")
        ).mappings().first()
        plan_items: list[dict[str, Any]] = []
        if latest_run:
            plan_items = [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT * FROM mpps_ai_plan_items
                        WHERE run_id = :run_id
                        ORDER BY priority_score DESC, sap_code
                        LIMIT :limit
                        """
                    ),
                    {"run_id": int(latest_run["id"]), "limit": max(1, min(5000, int(limit)))},
                ).mappings().all()
            ]
        reconciliation = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT * FROM mpps_plan_actual_reconciliation
                    ORDER BY production_date DESC, ABS(variance_qty) DESC, sap_code
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(5000, int(limit)))},
            ).mappings().all()
        ]
        models = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT * FROM mpps_ai_model_state
                    ORDER BY confidence_score DESC, sample_days DESC, sap_code
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(5000, int(limit)))},
            ).mappings().all()
        ]
        evaluations = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT * FROM mpps_ai_plan_evaluation
                    ORDER BY plan_date DESC, ai_run_id DESC, sap_code
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(5000, int(limit)))},
            ).mappings().all()
        ]
        return {
            "readiness": readiness.__dict__,
            "latest_run": dict(latest_run) if latest_run else None,
            "plan_items": plan_items,
            "reconciliation": reconciliation,
            "models": models,
            "evaluations": evaluations,
        }
