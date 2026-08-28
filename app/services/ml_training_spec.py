from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MetricDirection = Literal["min", "max"]


@dataclass(frozen=True)
class SourceCandidate:
    table: str
    date_column: str
    target_candidates: tuple[str, ...]
    feature_candidates: tuple[str, ...]


@dataclass(frozen=True)
class ModelTrainingSpec:
    model_key: str
    metric_name: str
    metric_direction: MetricDirection
    promotion_threshold: float
    min_history_days: int
    min_training_rows: int
    min_validation_rows: int
    min_test_rows: int
    confidence_threshold: float
    source_candidates: tuple[SourceCandidate, ...]
    forbidden_features: tuple[str, ...] = ()


TYRE_QTY = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("actual_qty",),
    ("sap_code", "line", "oven_no", "weight_kg", "day_plan", "night_plan",
     "next_day_plan", "total_to_produce", "current_stock", "scrap", "blocked"),
)
DAY_SHIFT = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("day_produced",),
    ("sap_code", "line", "oven_no", "weight_kg", "day_plan", "night_plan",
     "current_stock", "total_to_produce"),
)
LINE_CLASS = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("line",),
    ("sap_code", "description", "weight_kg"),
)
CAVITY_CLASS = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("oven_no",),
    ("sap_code", "description", "line", "weight_kg"),
)
# Similar-tyre intelligence does not currently have a human/verified similarity
# target.  It must remain NOT READY rather than borrowing the line label and
# pretending line classification is tyre similarity.
SIMILARITY_LABEL = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("similarity_label",),
    ("sap_code", "description", "line", "oven_no", "weight_kg"),
)
WEIGHT = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("weight_kg",),
    ("sap_code", "description", "line", "heel", "soft", "tread"),
)
STOCK = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("current_stock",),
    ("sap_code", "line", "oven_no", "total_stock", "scrap", "blocked",
     "total_to_produce", "day_plan", "night_plan"),
)
STOCKOUT = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("stockout_flag",),
    ("sap_code", "current_stock", "total_stock", "scrap", "blocked",
     "total_to_produce", "day_plan", "night_plan"),
)
SCRAP_BLOCK = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("scrap_block_flag",),
    ("sap_code", "line", "oven_no", "current_stock", "total_to_produce",
     "day_plan", "night_plan"),
)
UNDERPERFORMANCE = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("underperformance_flag",),
    ("sap_code", "line", "oven_no", "weight_kg", "plan_qty", "current_stock"),
)
FACTORY_DAILY = SourceCandidate(
    "mpps_factory_daily_capacity", "production_date", ("total_actual_qty",),
    ("total_plan_qty", "active_sap_count"),
)
ACTUAL_EVENTS = SourceCandidate(
    "mpps_operational_actual_events", "event_date", ("produced_qty",),
    ("shift_name", "sap_code", "line_name", "cavity_no"),
)
PRODUCTION_HISTORY = SourceCandidate(
    "excel_import_production_history", "production_date", ("production_qty",),
    ("sap_code", "item_description"),
)
MATERIAL_QTY = SourceCandidate(
    "mpps_material_training_view", "plan_date", ("total_qty",),
    ("material_type", "material_key", "day_qty", "night_qty", "produced_qty",
     "stock_qty", "unit"),
)
MATERIAL_NEXT = SourceCandidate(
    "mpps_material_training_view", "plan_date", ("next_day_qty",),
    ("material_type", "material_key", "day_qty", "night_qty", "produced_qty",
     "stock_qty", "total_qty", "unit"),
)
MATERIAL_SHORTAGE = SourceCandidate(
    "mpps_material_training_view", "plan_date", ("shortage_flag",),
    ("material_type", "material_key", "day_qty", "night_qty", "produced_qty",
     "stock_qty", "total_qty", "next_day_qty", "unit"),
)
MATERIAL_VARIANCE = SourceCandidate(
    "mpps_material_training_view", "plan_date", ("plan_variance_qty",),
    ("material_type", "material_key", "day_qty", "night_qty", "stock_qty",
     "total_qty", "next_day_qty", "unit"),
)
SHIPMENT_GAP = SourceCandidate(
    "mpps_shipment_training_view", "snapshot_date", ("production_gap_qty",),
    ("priority_no", "sap_code", "demand_qty", "produced_qty", "stock_covered_qty",
     "stock_coverage_ratio", "operational_status"),
)
SHIPMENT_LATE = SourceCandidate(
    "mpps_shipment_training_view", "snapshot_date", ("late_flag",),
    ("priority_no", "sap_code", "demand_qty", "produced_qty", "stock_covered_qty",
     "production_gap_qty", "stock_coverage_ratio", "operational_status"),
)
SHIPMENT_CAN_OUT = SourceCandidate(
    "mpps_shipment_training_view", "snapshot_date", ("actual_lead_days",),
    ("priority_no", "sap_code", "demand_qty", "produced_qty", "stock_covered_qty",
     "production_gap_qty", "stock_coverage_ratio", "operational_status"),
)

# These explicit-label sources intentionally remain unavailable until the app has
# trustworthy labels. The readiness gate therefore reports NOT READY instead of
# fabricating a target from unrelated production quantities.
CURING_LABEL = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("actual_curing_minutes",),
    ("sap_code", "line", "oven_no", "weight_kg", "heel", "soft", "tread"),
)
MOLD_CASING_LABEL = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("mold_casing_label",),
    ("sap_code", "description", "weight_kg", "line", "oven_no"),
)
MASTER_HEALTH_LABEL = SourceCandidate(
    "mpps_tyre_training_view", "plan_date", ("master_health_label",),
    ("sap_code", "description", "weight_kg", "line", "oven_no"),
)


def _regression(key: str, *sources: SourceCandidate, threshold: float = 0.35,
                min_days: int = 180, min_rows: int = 300,
                metric: str = "WAPE") -> ModelTrainingSpec:
    direction: MetricDirection = "min"
    return ModelTrainingSpec(
        model_key=key, metric_name=metric, metric_direction=direction,
        promotion_threshold=threshold, min_history_days=min_days,
        min_training_rows=min_rows, min_validation_rows=max(30, min_rows // 10),
        min_test_rows=max(30, min_rows // 10), confidence_threshold=0.65,
        source_candidates=tuple(sources),
        forbidden_features=("actual_value", "future_actual", "label", "target_value",
                            "actual_factory_out_date", "delivery_variance_days"),
    )


def _classification(key: str, *sources: SourceCandidate, threshold: float = 0.68,
                    min_days: int = 180, min_rows: int = 300) -> ModelTrainingSpec:
    return ModelTrainingSpec(
        model_key=key, metric_name="F1", metric_direction="max",
        promotion_threshold=threshold, min_history_days=min_days,
        min_training_rows=min_rows, min_validation_rows=max(30, min_rows // 10),
        min_test_rows=max(30, min_rows // 10), confidence_threshold=0.65,
        source_candidates=tuple(sources),
        forbidden_features=("actual_value", "future_actual", "label", "target_value",
                            "actual_factory_out_date", "delivery_variance_days"),
    )


def _ranking(key: str, metric: str, *sources: SourceCandidate,
             threshold: float = 0.68, min_days: int = 180,
             min_rows: int = 200) -> ModelTrainingSpec:
    """Chronology-safe historical ranking/compatibility contract.

    The 0.68 promotion gate is intentionally retained.  The metric changes
    because compatibility is multi-valid and recommendation is ranked output;
    forcing those tasks through single-label macro-F1 is semantically wrong.
    """
    return ModelTrainingSpec(
        model_key=key, metric_name=metric, metric_direction="max",
        promotion_threshold=threshold, min_history_days=min_days,
        min_training_rows=min_rows, min_validation_rows=max(30, min_rows // 10),
        min_test_rows=max(30, min_rows // 10), confidence_threshold=0.65,
        source_candidates=tuple(sources),
        forbidden_features=("actual_value", "future_actual", "label", "target_value",
                            "actual_factory_out_date", "delivery_variance_days"),
    )


MODEL_TRAINING_SPECS: dict[str, ModelTrainingSpec] = {
    "production_output": _regression("production_output", TYRE_QTY, ACTUAL_EVENTS, FACTORY_DAILY),
    "plan_actual": _regression("plan_actual", TYRE_QTY, PRODUCTION_HISTORY),
    "day_night": _regression("day_night", DAY_SHIFT, ACTUAL_EVENTS),
    "curing_time": _regression("curing_time", CURING_LABEL, threshold=0.30),
    "production_gap": _regression("production_gap", SHIPMENT_GAP, TYRE_QTY),
    "factory_capacity": _regression("factory_capacity", FACTORY_DAILY, ACTUAL_EVENTS),
    "sap_capacity": _regression("sap_capacity", TYRE_QTY, ACTUAL_EVENTS),
    "line_compatibility": _ranking(
        "line_compatibility", "COMPAT_RECALL", LINE_CLASS, min_rows=200
    ),
    "cavity_compatibility": _ranking(
        "cavity_compatibility", "COMPAT_RECALL", CAVITY_CLASS, min_rows=200
    ),
    "capacity_risk": _classification("capacity_risk", UNDERPERFORMANCE, min_rows=200),
    "similar_tyre": _classification("similar_tyre", SIMILARITY_LABEL, min_rows=200),
    "tyre_weight": _regression("tyre_weight", WEIGHT, threshold=0.20, min_rows=200),
    "mold_casing": _classification("mold_casing", MOLD_CASING_LABEL, min_rows=200),
    "line_recommendation": _ranking(
        "line_recommendation", "TOP1_HIT", LINE_CLASS, min_rows=200
    ),
    "cavity_recommendation": _ranking(
        "cavity_recommendation", "TOP5_HIT", CAVITY_CLASS, min_rows=200
    ),
    "master_health": _classification("master_health", MASTER_HEALTH_LABEL, min_days=90, min_rows=200),
    "compound_requirement": _regression("compound_requirement", MATERIAL_QTY),
    "band_requirement": _regression("band_requirement", MATERIAL_QTY),
    "bead_requirement": _regression("bead_requirement", MATERIAL_QTY),
    "core_requirement": _regression("core_requirement", MATERIAL_QTY),
    "material_forecast": _regression("material_forecast", MATERIAL_QTY),
    "material_variance": _regression("material_variance", MATERIAL_VARIANCE, threshold=0.40),
    "material_shortage": _classification("material_shortage", MATERIAL_SHORTAGE),
    "next_day_material": _regression("next_day_material", MATERIAL_NEXT),
    "stock_trend": _regression("stock_trend", STOCK),
    "stock_forecast": _regression("stock_forecast", STOCK),
    "stockout_risk": _classification("stockout_risk", STOCKOUT),
    "scrap_block_anomaly": _classification("scrap_block_anomaly", SCRAP_BLOCK),
    "replenishment_pressure": _classification("replenishment_pressure", STOCKOUT),
    "delivery_risk": _classification("delivery_risk", SHIPMENT_LATE, min_rows=200),
    "shipment_gap_risk": _classification("shipment_gap_risk", SHIPMENT_LATE, min_rows=200),
    "stock_coverage_risk": _classification("stock_coverage_risk", SHIPMENT_LATE, min_rows=200),
    "factory_can_out": ModelTrainingSpec(
        model_key="factory_can_out", metric_name="MAE_DAYS", metric_direction="min",
        promotion_threshold=3.0, min_history_days=180, min_training_rows=200,
        min_validation_rows=30, min_test_rows=30, confidence_threshold=0.70,
        source_candidates=(SHIPMENT_CAN_OUT,),
        forbidden_features=("actual_factory_out_date", "actual_lead_days",
                            "delivery_variance_days", "late_flag", "future_actual", "label"),
    ),
    "shipment_priority": _classification("shipment_priority", SHIPMENT_LATE, min_rows=200),
}


def get_training_spec(model_key: str) -> ModelTrainingSpec:
    key = str(model_key or "").strip()
    try:
        return MODEL_TRAINING_SPECS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown MPPS model key: {key}") from exc
