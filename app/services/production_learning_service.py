from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from statistics import mean, median, pstdev
from typing import Any

from sqlalchemy import text


# INTELLIGENT CONTINUOUS EXCEL SYNC + LEARNING FOUNDATION V7.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _code(value: Any) -> str:
    value = _text(value)
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return value.upper()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _confidence(sample_count: int, coefficient_of_variation: float) -> tuple[float, str]:
    sample_score = min(1.0, sample_count / 12.0)
    stability_score = max(0.0, min(1.0, 1.0 - coefficient_of_variation))
    score = round(0.65 * sample_score + 0.35 * stability_score, 4)
    if sample_count < 3:
        return score, "LEARNING"
    if score >= 0.75:
        return score, "HIGH"
    if score >= 0.45:
        return score, "MEDIUM"
    return score, "LOW"


@dataclass(frozen=True)
class LearningModel:
    model_key: str
    model_type: str
    entity_key: str
    sample_count: int
    prediction: float
    lower_bound: float
    upper_bound: float
    confidence_score: float
    confidence_band: str
    explanation: str
    model_json: dict[str, Any]


class ProductionLearningService:
    """Local, explainable learning foundation.

    V7.0 does not use workbook plans as unquestioned actual production. It stores
    source semantics explicitly and keeps all recommendations advisory. The local
    statistical models become more useful as monthly revisions and actual results
    accumulate.
    """

    @staticmethod
    def ensure_schema(session) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS excel_learning_observations (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT,
                plan_date DATE,
                observation_type VARCHAR(50) NOT NULL,
                source_semantics VARCHAR(50) NOT NULL DEFAULT 'UNCLASSIFIED',
                entity_key TEXT NOT NULL,
                sap_code TEXT NOT NULL DEFAULT '',
                customer_key TEXT NOT NULL DEFAULT '',
                line_name TEXT NOT NULL DEFAULT '',
                oven_code TEXT NOT NULL DEFAULT '',
                shift_name TEXT NOT NULL DEFAULT '',
                quantity NUMERIC(18, 5) NOT NULL DEFAULT 0,
                weight_kg NUMERIC(18, 5) NOT NULL DEFAULT 0,
                features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                source_workbook TEXT NOT NULL DEFAULT '',
                source_sheet TEXT NOT NULL DEFAULT '',
                source_row INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    import_run_id,
                    observation_type,
                    entity_key,
                    source_sheet,
                    source_row
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_excel_learning_observations_type_key
            ON excel_learning_observations(observation_type, entity_key, plan_date)
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_learning_models (
                id BIGSERIAL PRIMARY KEY,
                model_key TEXT NOT NULL UNIQUE,
                model_type VARCHAR(50) NOT NULL,
                entity_key TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                prediction NUMERIC(18, 5) NOT NULL DEFAULT 0,
                lower_bound NUMERIC(18, 5) NOT NULL DEFAULT 0,
                upper_bound NUMERIC(18, 5) NOT NULL DEFAULT 0,
                confidence_score NUMERIC(8, 5) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                explanation TEXT NOT NULL DEFAULT '',
                model_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                is_advisory_only BOOLEAN NOT NULL DEFAULT TRUE,
                last_trained_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_excel_learning_models_type
            ON excel_learning_models(model_type, confidence_band, sample_count DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_learning_predictions (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT,
                model_id BIGINT REFERENCES excel_learning_models(id) ON DELETE SET NULL,
                prediction_type VARCHAR(50) NOT NULL,
                entity_key TEXT NOT NULL,
                predicted_value NUMERIC(18, 5) NOT NULL DEFAULT 0,
                lower_bound NUMERIC(18, 5) NOT NULL DEFAULT 0,
                upper_bound NUMERIC(18, 5) NOT NULL DEFAULT 0,
                confidence_score NUMERIC(8, 5) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                explanation TEXT NOT NULL DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'ADVISORY',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_learning_feedback (
                id BIGSERIAL PRIMARY KEY,
                prediction_id BIGINT REFERENCES excel_learning_predictions(id) ON DELETE SET NULL,
                model_id BIGINT REFERENCES excel_learning_models(id) ON DELETE SET NULL,
                entity_key TEXT NOT NULL DEFAULT '',
                decision VARCHAR(30) NOT NULL,
                actual_value NUMERIC(18, 5),
                note TEXT NOT NULL DEFAULT '',
                recorded_by TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_plan_reconciliation (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT NOT NULL,
                plan_date DATE,
                sap_code TEXT NOT NULL,
                excel_shipment_demand INTEGER NOT NULL DEFAULT 0,
                excel_production_required INTEGER NOT NULL DEFAULT 0,
                excel_planned_qty INTEGER NOT NULL DEFAULT 0,
                app_live_demand INTEGER NOT NULL DEFAULT 0,
                app_production_required INTEGER NOT NULL DEFAULT 0,
                app_daily_capacity INTEGER NOT NULL DEFAULT 0,
                demand_variance INTEGER NOT NULL DEFAULT 0,
                production_variance INTEGER NOT NULL DEFAULT 0,
                plan_variance INTEGER NOT NULL DEFAULT 0,
                reconciliation_status VARCHAR(30) NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(import_run_id, sap_code)
            )
            """,
        ]
        for statement in statements:
            session.execute(text(statement))

    @staticmethod
    def _insert_observation(session, values: dict[str, Any]) -> None:
        session.execute(
            text(
                """
                INSERT INTO excel_learning_observations (
                    import_run_id,
                    plan_date,
                    observation_type,
                    source_semantics,
                    entity_key,
                    sap_code,
                    customer_key,
                    line_name,
                    oven_code,
                    shift_name,
                    quantity,
                    weight_kg,
                    features_json,
                    source_workbook,
                    source_sheet,
                    source_row
                )
                VALUES (
                    :import_run_id,
                    :plan_date,
                    :observation_type,
                    :source_semantics,
                    :entity_key,
                    :sap_code,
                    :customer_key,
                    :line_name,
                    :oven_code,
                    :shift_name,
                    :quantity,
                    :weight_kg,
                    CAST(:features_json AS JSONB),
                    :source_workbook,
                    :source_sheet,
                    :source_row
                )
                ON CONFLICT (
                    import_run_id,
                    observation_type,
                    entity_key,
                    source_sheet,
                    source_row
                )
                DO UPDATE SET
                    plan_date = EXCLUDED.plan_date,
                    source_semantics = EXCLUDED.source_semantics,
                    sap_code = EXCLUDED.sap_code,
                    customer_key = EXCLUDED.customer_key,
                    line_name = EXCLUDED.line_name,
                    oven_code = EXCLUDED.oven_code,
                    shift_name = EXCLUDED.shift_name,
                    quantity = EXCLUDED.quantity,
                    weight_kg = EXCLUDED.weight_kg,
                    features_json = EXCLUDED.features_json,
                    source_workbook = EXCLUDED.source_workbook
                """
            ),
            values,
        )

    def capture_import_observations(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
    ) -> dict[str, int]:
        self.ensure_schema(session)
        plan_date = (
            date.fromisoformat(analysis.plan_date)
            if analysis.plan_date
            else date.today()
        )
        counters: dict[str, int] = defaultdict(int)

        demand_by_sap: dict[str, int] = defaultdict(int)
        demand_by_customer: dict[str, int] = defaultdict(int)
        for row in analysis.shipment_rows:
            qty = max(0, int(row.get("quantity") or 0))
            if qty <= 0:
                continue
            sap = _code(row.get("sap_code"))
            customer = _text(row.get("shipment_name")).upper()
            demand_by_sap[sap] += qty
            demand_by_customer[customer] += qty

        for sap, qty in demand_by_sap.items():
            self._insert_observation(
                session,
                {
                    "import_run_id": import_run_id,
                    "plan_date": plan_date,
                    "observation_type": "SAP_DEMAND",
                    "source_semantics": "WORKBOOK_SHIPMENT_DEMAND",
                    "entity_key": sap,
                    "sap_code": sap,
                    "customer_key": "",
                    "line_name": "",
                    "oven_code": "",
                    "shift_name": "",
                    "quantity": qty,
                    "weight_kg": 0,
                    "features_json": json.dumps(
                        {"workbook_hash": analysis.workbook_hash},
                        default=str,
                    ),
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": "PROD",
                    "source_row": 0,
                },
            )
            counters["sap_demand_observations"] += 1

        for customer, qty in demand_by_customer.items():
            key = f"CUSTOMER|{customer}"
            self._insert_observation(
                session,
                {
                    "import_run_id": import_run_id,
                    "plan_date": plan_date,
                    "observation_type": "CUSTOMER_DEMAND",
                    "source_semantics": "WORKBOOK_SHIPMENT_DEMAND",
                    "entity_key": key,
                    "sap_code": "",
                    "customer_key": customer,
                    "line_name": "",
                    "oven_code": "",
                    "shift_name": "",
                    "quantity": qty,
                    "weight_kg": 0,
                    "features_json": json.dumps(
                        {"workbook_hash": analysis.workbook_hash},
                        default=str,
                    ),
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": "PROD",
                    "source_row": 0,
                },
            )
            counters["customer_demand_observations"] += 1

        for row in analysis.production_history_rows:
            sap = _code(row.get("sap_code"))
            qty = max(0, int(row.get("production_qty") or 0))
            if not sap or qty <= 0:
                continue
            observation_date = row.get("production_date")
            try:
                observation_date = date.fromisoformat(str(observation_date))
            except Exception:
                observation_date = plan_date
            self._insert_observation(
                session,
                {
                    "import_run_id": import_run_id,
                    "plan_date": observation_date,
                    "observation_type": "PRODUCTION_SIGNAL",
                    "source_semantics": "WORKBOOK_PLAN_OR_UNCLASSIFIED",
                    "entity_key": sap,
                    "sap_code": sap,
                    "customer_key": "",
                    "line_name": "",
                    "oven_code": "",
                    "shift_name": "UNCLASSIFIED",
                    "quantity": qty,
                    "weight_kg": 0,
                    "features_json": json.dumps(
                        {
                            "description": row.get("description", ""),
                            "warning": (
                                "The workbook does not consistently distinguish "
                                "actual production from plan/forecast values."
                            ),
                        },
                        default=str,
                    ),
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": row.get("source_sheet", "PROD"),
                    "source_row": int(row.get("source_row") or 0),
                },
            )
            counters["production_signal_observations"] += 1

        for row in analysis.oven_rows:
            qty = max(0, int(row.get("planned_qty") or 0))
            if qty <= 0:
                continue
            sap = _code(row.get("sap_code"))
            line = _text(row.get("line_name")).upper()
            shift = _text(row.get("shift_name")).upper()
            oven = _text(row.get("oven_code")).upper()
            key = f"{sap}|{line}|{shift}"
            self._insert_observation(
                session,
                {
                    "import_run_id": import_run_id,
                    "plan_date": plan_date,
                    "observation_type": "OVEN_PLAN_SIGNAL",
                    "source_semantics": "WORKBOOK_PRODUCTION_PLAN",
                    "entity_key": key,
                    "sap_code": sap,
                    "customer_key": "",
                    "line_name": line,
                    "oven_code": oven,
                    "shift_name": shift,
                    "quantity": qty,
                    "weight_kg": _number(row.get("planned_weight_kg")),
                    "features_json": json.dumps(
                        {
                            "description": row.get("description", ""),
                            "source_date": row.get("plan_date"),
                        },
                        default=str,
                    ),
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": row.get("source_sheet", "OVEN"),
                    "source_row": int(row.get("source_row") or 0),
                },
            )
            counters["oven_plan_observations"] += 1

        for row in analysis.stock_rows:
            sap = _code(row.get("sap_code"))
            if not sap:
                continue
            physical = max(
                0,
                max(0, int(row.get("fg_stock") or 0))
                + max(0, int(row.get("qc_stock") or 0))
                - max(0, int(row.get("scrap_stock") or 0))
                - max(0, int(row.get("blocked_stock") or 0)),
            )
            self._insert_observation(
                session,
                {
                    "import_run_id": import_run_id,
                    "plan_date": plan_date,
                    "observation_type": "STOCK_POSITION",
                    "source_semantics": "WORKBOOK_STOCK_SNAPSHOT",
                    "entity_key": sap,
                    "sap_code": sap,
                    "customer_key": "",
                    "line_name": "",
                    "oven_code": "",
                    "shift_name": "",
                    "quantity": physical,
                    "weight_kg": _number(row.get("weight_kg")),
                    "features_json": json.dumps(
                        {
                            "source_fg": row.get("fg_stock", 0),
                            "source_scrap": row.get("scrap_stock", 0),
                            "source_blocked": row.get("blocked_stock", 0),
                        },
                        default=str,
                    ),
                    "source_workbook": analysis.workbook_name,
                    "source_sheet": row.get("source_sheet", "PROD"),
                    "source_row": int(row.get("source_row") or 0),
                },
            )
            counters["stock_observations"] += 1

        return dict(counters)

    @staticmethod
    def _series_models(session, observation_type: str, model_type: str) -> list[LearningModel]:
        rows = session.execute(
            text(
                """
                SELECT
                    entity_key,
                    plan_date,
                    SUM(quantity) AS quantity
                FROM excel_learning_observations
                WHERE observation_type = :observation_type
                  AND quantity > 0
                GROUP BY entity_key, plan_date
                ORDER BY entity_key, plan_date
                """
            ),
            {"observation_type": observation_type},
        ).mappings().all()
        grouped: dict[str, list[tuple[date | None, float]]] = defaultdict(list)
        for row in rows:
            grouped[_text(row["entity_key"])].append(
                (row.get("plan_date"), _number(row.get("quantity")))
            )

        models: list[LearningModel] = []
        for entity_key, observations in grouped.items():
            values = [value for _, value in observations if value > 0][-24:]
            if not values:
                continue
            weights = list(range(1, len(values) + 1))
            weighted = sum(value * weight for value, weight in zip(values, weights)) / sum(weights)
            trend = 0.0
            if len(values) >= 2:
                trend = (values[-1] - values[0]) / (len(values) - 1)
            prediction = max(0.0, weighted + 0.5 * trend)
            dispersion = pstdev(values) if len(values) > 1 else 0.0
            cv = dispersion / mean(values) if mean(values) > 0 else 1.0
            confidence_score, confidence_band = _confidence(len(values), cv)
            lower = max(0.0, prediction - dispersion)
            upper = prediction + dispersion
            explanation = (
                f"Advisory weighted history using {len(values)} dated observations; "
                f"trend={trend:.2f}, median={median(values):.2f}."
            )
            models.append(
                LearningModel(
                    model_key=f"{model_type}|{entity_key}",
                    model_type=model_type,
                    entity_key=entity_key,
                    sample_count=len(values),
                    prediction=round(prediction, 5),
                    lower_bound=round(lower, 5),
                    upper_bound=round(upper, 5),
                    confidence_score=confidence_score,
                    confidence_band=confidence_band,
                    explanation=explanation,
                    model_json={
                        "values": values,
                        "weighted_average": weighted,
                        "trend_per_observation": trend,
                        "median": median(values),
                        "dispersion": dispersion,
                        "coefficient_of_variation": cv,
                    },
                )
            )
        return models

    def rebuild_models(self, session) -> dict[str, int]:
        self.ensure_schema(session)
        models: list[LearningModel] = []
        models.extend(self._series_models(session, "SAP_DEMAND", "SAP_DEMAND_FORECAST"))
        models.extend(
            self._series_models(
                session,
                "CUSTOMER_DEMAND",
                "CUSTOMER_DEMAND_FORECAST",
            )
        )
        models.extend(
            self._series_models(
                session,
                "PRODUCTION_SIGNAL",
                "PRODUCTION_SIGNAL_MODEL",
            )
        )
        models.extend(
            self._series_models(
                session,
                "OVEN_PLAN_SIGNAL",
                "OVEN_PLAN_SIGNAL_MODEL",
            )
        )

        for model in models:
            session.execute(
                text(
                    """
                    INSERT INTO excel_learning_models (
                        model_key,
                        model_type,
                        entity_key,
                        sample_count,
                        prediction,
                        lower_bound,
                        upper_bound,
                        confidence_score,
                        confidence_band,
                        explanation,
                        model_json,
                        is_advisory_only,
                        last_trained_at,
                        updated_at
                    )
                    VALUES (
                        :model_key,
                        :model_type,
                        :entity_key,
                        :sample_count,
                        :prediction,
                        :lower_bound,
                        :upper_bound,
                        :confidence_score,
                        :confidence_band,
                        :explanation,
                        CAST(:model_json AS JSONB),
                        TRUE,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (model_key)
                    DO UPDATE SET
                        sample_count = EXCLUDED.sample_count,
                        prediction = EXCLUDED.prediction,
                        lower_bound = EXCLUDED.lower_bound,
                        upper_bound = EXCLUDED.upper_bound,
                        confidence_score = EXCLUDED.confidence_score,
                        confidence_band = EXCLUDED.confidence_band,
                        explanation = EXCLUDED.explanation,
                        model_json = EXCLUDED.model_json,
                        is_advisory_only = TRUE,
                        last_trained_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    **model.__dict__,
                    "model_json": json.dumps(model.model_json, default=str),
                },
            )

        counts: dict[str, int] = defaultdict(int)
        for model in models:
            counts["models_total"] += 1
            counts[f"models_{model.model_type.lower()}"] += 1
            counts[f"confidence_{model.confidence_band.lower()}"] += 1
        return dict(counts)

    def save_reconciliation(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
    ) -> dict[str, int]:
        self.ensure_schema(session)
        plan_date = (
            date.fromisoformat(analysis.plan_date)
            if analysis.plan_date
            else date.today()
        )
        excel_demand: dict[str, int] = defaultdict(int)
        excel_required: dict[str, int] = defaultdict(int)
        excel_plan: dict[str, int] = defaultdict(int)

        for row in analysis.shipment_rows:
            excel_demand[_code(row.get("sap_code"))] += max(0, int(row.get("quantity") or 0))
        for row in analysis.stock_rows:
            excel_required[_code(row.get("sap_code"))] += max(0, int(row.get("production_required") or 0))
        for row in analysis.oven_rows:
            excel_plan[_code(row.get("sap_code"))] += max(0, int(row.get("planned_qty") or 0))

        app_rows = session.execute(
            text(
                """
                SELECT
                    item.sap_code,
                    COALESCE(SUM(GREATEST(0, item.quantity)), 0) AS demand_qty,
                    COALESCE(SUM(GREATEST(0, item.production_required_qty)), 0) AS required_qty,
                    COALESCE(SUM(GREATEST(0, item.daily_capacity)), 0) AS daily_capacity
                FROM mpps_shipment_items item
                JOIN mpps_shipments shipment
                  ON shipment.id = item.shipment_id
                WHERE COALESCE(LOWER(shipment.status), 'planned') NOT IN (
                    'cancelled',
                    'canceled',
                    'closed',
                    'complete',
                    'completed',
                    'shipped',
                    'done',
                    'review required',
                    'superseded import'
                )
                GROUP BY item.sap_code
                """
            )
        ).mappings().all()
        app = {
            _code(row["sap_code"]): {
                "demand": int(row["demand_qty"] or 0),
                "required": int(row["required_qty"] or 0),
                "capacity": int(row["daily_capacity"] or 0),
            }
            for row in app_rows
        }

        codes = sorted(set(excel_demand) | set(excel_required) | set(excel_plan) | set(app))
        counts: dict[str, int] = defaultdict(int)
        for sap in codes:
            app_values = app.get(sap, {"demand": 0, "required": 0, "capacity": 0})
            demand_variance = app_values["demand"] - excel_demand.get(sap, 0)
            production_variance = app_values["required"] - excel_required.get(sap, 0)
            plan_variance = app_values["capacity"] - excel_plan.get(sap, 0)
            if demand_variance == 0 and production_variance == 0:
                status = "ALIGNED"
                explanation = "Excel demand and live app demand/requirement are aligned."
            elif abs(demand_variance) <= 1 and abs(production_variance) <= 1:
                status = "ROUNDING"
                explanation = "Only a one-piece rounding difference exists."
            else:
                status = "REVIEW"
                explanation = (
                    "Excel and app values differ because of cumulative stock allocation, "
                    "manual/actual protection, removed revisions or other active shipments."
                )
            session.execute(
                text(
                    """
                    INSERT INTO excel_plan_reconciliation (
                        import_run_id,
                        plan_date,
                        sap_code,
                        excel_shipment_demand,
                        excel_production_required,
                        excel_planned_qty,
                        app_live_demand,
                        app_production_required,
                        app_daily_capacity,
                        demand_variance,
                        production_variance,
                        plan_variance,
                        reconciliation_status,
                        explanation,
                        updated_at
                    )
                    VALUES (
                        :import_run_id,
                        :plan_date,
                        :sap_code,
                        :excel_shipment_demand,
                        :excel_production_required,
                        :excel_planned_qty,
                        :app_live_demand,
                        :app_production_required,
                        :app_daily_capacity,
                        :demand_variance,
                        :production_variance,
                        :plan_variance,
                        :reconciliation_status,
                        :explanation,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (import_run_id, sap_code)
                    DO UPDATE SET
                        plan_date = EXCLUDED.plan_date,
                        excel_shipment_demand = EXCLUDED.excel_shipment_demand,
                        excel_production_required = EXCLUDED.excel_production_required,
                        excel_planned_qty = EXCLUDED.excel_planned_qty,
                        app_live_demand = EXCLUDED.app_live_demand,
                        app_production_required = EXCLUDED.app_production_required,
                        app_daily_capacity = EXCLUDED.app_daily_capacity,
                        demand_variance = EXCLUDED.demand_variance,
                        production_variance = EXCLUDED.production_variance,
                        plan_variance = EXCLUDED.plan_variance,
                        reconciliation_status = EXCLUDED.reconciliation_status,
                        explanation = EXCLUDED.explanation,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "import_run_id": import_run_id,
                    "plan_date": plan_date,
                    "sap_code": sap,
                    "excel_shipment_demand": excel_demand.get(sap, 0),
                    "excel_production_required": excel_required.get(sap, 0),
                    "excel_planned_qty": excel_plan.get(sap, 0),
                    "app_live_demand": app_values["demand"],
                    "app_production_required": app_values["required"],
                    "app_daily_capacity": app_values["capacity"],
                    "demand_variance": demand_variance,
                    "production_variance": production_variance,
                    "plan_variance": plan_variance,
                    "reconciliation_status": status,
                    "explanation": explanation,
                },
            )
            counts[f"reconciliation_{status.lower()}"] += 1
            counts["reconciliation_rows"] += 1
        return dict(counts)

    def get_dashboard(self, session, limit: int = 500) -> dict[str, Any]:
        self.ensure_schema(session)
        metrics = dict(
            session.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM excel_learning_observations) AS observations,
                        (SELECT COUNT(DISTINCT import_run_id) FROM excel_learning_observations) AS workbook_runs,
                        (SELECT COUNT(*) FROM excel_learning_models) AS models,
                        (SELECT COUNT(*) FROM excel_learning_models WHERE confidence_band = 'HIGH') AS high_confidence,
                        (SELECT COUNT(*) FROM excel_learning_feedback) AS feedback_rows,
                        (SELECT COUNT(*) FROM excel_plan_reconciliation WHERE reconciliation_status = 'REVIEW') AS reconciliation_reviews
                    """
                )
            ).mappings().one()
        )
        models = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT
                        id,
                        model_type,
                        entity_key,
                        sample_count,
                        prediction,
                        lower_bound,
                        upper_bound,
                        confidence_score,
                        confidence_band,
                        explanation,
                        is_advisory_only,
                        last_trained_at
                    FROM excel_learning_models
                    ORDER BY confidence_score DESC, sample_count DESC, model_type, entity_key
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).mappings().all()
        ]
        reconciliation = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT
                        import_run_id,
                        plan_date,
                        sap_code,
                        excel_shipment_demand,
                        app_live_demand,
                        demand_variance,
                        excel_production_required,
                        app_production_required,
                        production_variance,
                        excel_planned_qty,
                        app_daily_capacity,
                        plan_variance,
                        reconciliation_status,
                        explanation
                    FROM excel_plan_reconciliation
                    ORDER BY import_run_id DESC,
                             CASE reconciliation_status WHEN 'REVIEW' THEN 0 ELSE 1 END,
                             ABS(demand_variance) DESC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).mappings().all()
        ]
        return {
            "metrics": metrics,
            "models": models,
            "reconciliation": reconciliation,
        }

    def rebuild_all(self) -> dict[str, Any]:
        from app.database import get_session

        with get_session() as session:
            result = self.rebuild_models(session)
            return result
