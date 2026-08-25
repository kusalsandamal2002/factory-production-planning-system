from __future__ import annotations

from datetime import date
import re
from typing import Any

from sqlalchemy import text

from app.database import engine


MODEL_CATALOG = (
    ("production_output", "PRODUCTION", "Production Output Forecast"),
    ("plan_actual", "PRODUCTION", "Plan vs Actual Learning"),
    ("day_night", "PRODUCTION", "Day / Night Productivity"),
    ("curing_time", "PRODUCTION", "Curing Time Intelligence"),
    ("production_gap", "PRODUCTION", "Production Gap Forecast"),
    ("factory_capacity", "FACTORY / CAPACITY", "Factory Capacity Model"),
    ("sap_capacity", "FACTORY / CAPACITY", "SAP Capacity Model"),
    ("line_compatibility", "FACTORY / CAPACITY", "Line Compatibility Model"),
    ("cavity_compatibility", "FACTORY / CAPACITY", "Cavity / Oven Compatibility Model"),
    ("capacity_risk", "FACTORY / CAPACITY", "Capacity Risk / Constraint Model"),
    ("similar_tyre", "TYRE MASTER", "Similar Tyre Intelligence"),
    ("tyre_weight", "TYRE MASTER", "Tyre Weight Intelligence"),
    ("mold_casing", "TYRE MASTER", "Mold / Casing Pattern Learning"),
    ("line_recommendation", "TYRE MASTER", "Line Recommendation"),
    ("cavity_recommendation", "TYRE MASTER", "Cavity Recommendation"),
    ("master_health", "TYRE MASTER", "Master Data Health"),
    ("compound_requirement", "MATERIAL", "Compound Requirement Model"),
    ("band_requirement", "MATERIAL", "Band Requirement Model"),
    ("bead_requirement", "MATERIAL", "Bead Requirement Model"),
    ("core_requirement", "MATERIAL", "Core Requirement Model"),
    ("material_forecast", "MATERIAL", "Material Requirement Forecast"),
    ("material_variance", "MATERIAL", "Material Usage / Variance Anomaly"),
    ("material_shortage", "MATERIAL", "Material Shortage Risk"),
    ("next_day_material", "MATERIAL", "Next-Day Material Forecast"),
    ("stock_trend", "STOCK", "Stock Consumption Trend"),
    ("stock_forecast", "STOCK", "Stock Forecast"),
    ("stockout_risk", "STOCK", "Stockout Risk"),
    ("scrap_block_anomaly", "STOCK", "Scrap / Block Anomaly"),
    ("replenishment_pressure", "STOCK", "Replenishment Pressure"),
    ("delivery_risk", "SHIPMENTS", "Delivery Risk"),
    ("shipment_gap_risk", "SHIPMENTS", "Production Gap Risk"),
    ("stock_coverage_risk", "SHIPMENTS", "Stock Coverage Risk"),
    ("factory_can_out", "SHIPMENTS", "Factory Can-Out Forecast"),
    ("shipment_priority", "SHIPMENTS", "Shipment Priority Intelligence"),
)


class MLPlatformService:
    """Unifies the model catalog without turning ML into operational authority."""

    @staticmethod
    def _table_exists(connection, table_name: str) -> bool:
        return bool(
            connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"public.{table_name}"},
            ).scalar()
        )

    @staticmethod
    def _norm(value: Any) -> str:
        return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())

    @classmethod
    def _history_span(cls, connection) -> tuple[int, int]:
        dates: list[date] = []
        rows = 0
        for table_name, date_column in (
            ("mpps_factory_daily_capacity", "production_date"),
            ("mpps_tyre_workbook_observation", "plan_date"),
            ("mpps_actual_production", "production_date"),
            ("mpps_operational_actual_events", "event_date"),
        ):
            if not cls._table_exists(connection, table_name):
                continue
            try:
                first, last, count = connection.execute(
                    text(
                        f"SELECT MIN({date_column}), MAX({date_column}), COUNT(*) FROM {table_name}"
                    )
                ).one()
                rows += int(count or 0)
                if first:
                    dates.append(first)
                if last:
                    dates.append(last)
            except Exception:
                continue
        if not dates:
            return rows, 0
        history_days = max(1, (max(dates) - min(dates)).days + 1)
        return rows, history_days

    @classmethod
    def snapshot(cls) -> dict[str, Any]:
        with engine.begin() as connection:
            history_rows, history_days = cls._history_span(connection)
            existing: dict[str, dict[str, Any]] = {}

            if cls._table_exists(connection, "mpps_ml_model_registry_v2"):
                for row in connection.execute(
                    text("SELECT * FROM mpps_ml_model_registry_v2")
                ).mappings().all():
                    existing[str(row.get("model_key") or "")] = dict(row)

            legacy: list[dict[str, Any]] = []
            if cls._table_exists(connection, "mpps_tyre_ml_registry"):
                try:
                    legacy = [
                        dict(row)
                        for row in connection.execute(
                            text(
                                """
                                SELECT module_key,module_name,purpose,status,training_rows,
                                       history_days,readiness_score,model_version,last_trained_at,updated_at
                                FROM mpps_tyre_ml_registry
                                """
                            )
                        ).mappings().all()
                    ]
                except Exception:
                    legacy = []

            legacy_by_name = {}
            for row in legacy:
                for value in (row.get("module_key"), row.get("module_name")):
                    if value:
                        legacy_by_name[cls._norm(value)] = row

            models = []
            for model_key, area, name in MODEL_CATALOG:
                row = existing.get(model_key)
                if row is None:
                    target = cls._norm(name)
                    match = None
                    for key, legacy_row in legacy_by_name.items():
                        if target == key or target in key or key in target:
                            match = legacy_row
                            break
                    training_rows = int((match or {}).get("training_rows") or 0)
                    model_history_days = int((match or {}).get("history_days") or 0)
                    readiness = float((match or {}).get("readiness_score") or 0)
                    status = str((match or {}).get("status") or "REGISTERED").upper()
                    model_version = str((match or {}).get("model_version") or "R6-UNTRAINED")
                    last_trained = (match or {}).get("last_trained_at")
                    last_data = (match or {}).get("updated_at")
                else:
                    training_rows = int(row.get("training_rows") or 0)
                    model_history_days = int(row.get("history_days") or 0)
                    readiness = float(row.get("confidence_score") or 0) * 100.0
                    status = str(row.get("status") or "REGISTERED").upper()
                    model_version = str(row.get("model_version") or "R6-UNTRAINED")
                    last_trained = row.get("last_trained_at")
                    last_data = row.get("last_data_update")

                if training_rows <= 0 and history_rows > 0:
                    # Catalog readiness is informative only. It does not pretend a
                    # model is trained merely because raw history exists.
                    model_history_days = max(model_history_days, history_days)
                    status = "NEEDS TRAINING" if history_days >= 30 else "NEEDS DATA"

                models.append(
                    {
                        "model_key": model_key,
                        "area": area,
                        "model_name": name,
                        "status": status,
                        "training_rows": training_rows,
                        "history_days": model_history_days,
                        "readiness_score": readiness,
                        "model_version": model_version,
                        "last_trained_at": last_trained,
                        "last_data_update": last_data,
                    }
                )

            if cls._table_exists(connection, "mpps_ml_model_registry_v2"):
                for model in models:
                    connection.execute(
                        text(
                            """
                            INSERT INTO mpps_ml_model_registry_v2(
                                model_key,area,model_name,status,training_rows,history_days,
                                confidence_score,model_version,last_trained_at,last_data_update,updated_at
                            ) VALUES(
                                :model_key,:area,:model_name,:status,:training_rows,:history_days,
                                :confidence_score,:model_version,:last_trained_at,:last_data_update,CURRENT_TIMESTAMP
                            )
                            ON CONFLICT(model_key) DO UPDATE SET
                                area=EXCLUDED.area,
                                model_name=EXCLUDED.model_name,
                                history_days=GREATEST(mpps_ml_model_registry_v2.history_days,EXCLUDED.history_days),
                                updated_at=CURRENT_TIMESTAMP
                            """
                        ),
                        {
                            **model,
                            "confidence_score": float(model.get("readiness_score") or 0) / 100.0,
                        },
                    )

        ready = sum(str(row.get("status") or "").upper() in {"READY", "TRAINED", "ACTIVE", "CHAMPION"} for row in models)
        learning = sum(str(row.get("status") or "").upper() in {"LEARNING", "REGISTERED", "NEEDS TRAINING"} for row in models)
        needs = max(0, len(models) - ready - learning)
        return {
            "models": models,
            "history_rows": history_rows,
            "history_days": history_days,
            "total": len(models),
            "ready": ready,
            "learning": learning,
            "needs": needs,
        }
