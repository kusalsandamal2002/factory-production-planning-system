from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from app.services.factory_resource_intelligence_service import FactoryResourceIntelligenceService


@dataclass(frozen=True)
class ItemFactoryOutForecast:
    shipment_id: int
    sap_code: str
    ready_date: date | None
    source: str
    confidence: float
    blocker: str = ""
    remaining_qty: int = 0
    effective_daily_capacity: float = 0.0
    item_id: int = 0


@dataclass(frozen=True)
class ShipmentFactoryOutForecast:
    shipment_id: int
    factory_out_date: date | None
    source: str
    confidence: float
    blocker: str = ""
    unresolved_items: int = 0
    forecast_items: int = 0
    verified_items: int = 0


def _int(value: Any, default: int = 0) -> int:
    # PostgreSQL INTERVAL values arrive as datetime.timedelta.  Accept them
    # explicitly so dispatch-buffer or compatibility columns cannot crash the
    # forecast path on legacy schemas.
    if isinstance(value, timedelta):
        return int(value.days)
    if hasattr(value, "days") and not isinstance(value, (str, bytes)):
        try:
            return int(value.days)
        except Exception:
            pass
    try:
        return int(float(value or 0))
    except Exception:
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def forecast_item(
    row: Mapping[str, Any],
    *,
    as_of_date: date,
    learned_capacity: Mapping[str, Any] | None = None,
    fallback_capacity: Mapping[str, Any] | None = None,
) -> ItemFactoryOutForecast:
    shipment_id = _int(row.get("shipment_id"))
    item_id = _int(row.get("item_id") or row.get("id"))
    sap_code = str(row.get("sap_code") or "").strip()
    qty = max(0, _int(row.get("quantity")))
    stock = max(0, min(qty, _int(row.get("stock_allocated_qty"))))
    produced = max(0, min(qty, _int(row.get("produced_qty"))))
    completed = min(qty, stock + produced)
    remaining = max(0, qty - completed)

    existing = _date(
        row.get("item_receive_date")
        or row.get("receive_date")
        or row.get("end_date")
        or row.get("start_date")
    )
    if existing is not None:
        return ItemFactoryOutForecast(
            shipment_id=shipment_id,
            sap_code=sap_code,
            ready_date=existing,
            source="VERIFIED PLANNER DATE",
            confidence=1.0,
            remaining_qty=remaining,
            item_id=item_id,
        )

    if qty <= 0:
        return ItemFactoryOutForecast(
            shipment_id=shipment_id,
            sap_code=sap_code,
            ready_date=as_of_date,
            source="NO POSITIVE DEMAND",
            confidence=1.0,
            remaining_qty=0,
            item_id=item_id,
        )

    if remaining <= 0:
        return ItemFactoryOutForecast(
            shipment_id=shipment_id,
            sap_code=sap_code,
            ready_date=as_of_date,
            source="STOCK / PRODUCED READY",
            confidence=1.0,
            remaining_qty=0,
            item_id=item_id,
        )

    # V10.4 REAL-CAPACITY-FIRST policy: when enough verified history exists,
    # the learned factory-capacity model is the primary forecast source.  The
    # legacy planner/SMDS capacities remain conservative fallbacks for sparse
    # history so the system can still operate while the model is learning.
    capacity = 0.0
    source = ""
    confidence = 0.0
    model = dict(learned_capacity or {})
    samples = max(0, _int(model.get("sample_days")))
    model_confidence = max(0.0, min(1.0, _float(model.get("confidence_score"))))
    safe_capacity = max(0.0, _float(model.get("safe_capacity_qty")))
    expected_capacity = max(0.0, _float(model.get("expected_capacity_qty")))

    if samples >= 5 and safe_capacity > 0:
        capacity = safe_capacity
        source = str(model.get("source") or "LEARNED SAP SAFE CAPACITY")
        confidence = max(0.55, model_confidence)
    elif samples >= 3 and expected_capacity > 0:
        capacity = expected_capacity * 0.85
        source = str(model.get("source") or "LEARNED SAP CAPACITY (CONSERVATIVE)")
        confidence = max(0.40, model_confidence * 0.85)
    elif samples >= 1 and max(safe_capacity, expected_capacity, _float(model.get("recent_capacity_qty"))) > 0:
        observed = [
            value
            for value in (
                safe_capacity,
                expected_capacity,
                _float(model.get("recent_capacity_qty")),
            )
            if value > 0
        ]
        capacity = min(observed) * 0.70
        source = str(model.get("source") or "LEARNED SAP SPARSE CAPACITY")
        confidence = max(0.25, min(0.45, model_confidence * 0.70))

    # When a SAP has little/no direct history, do not hard-block the shipment.
    # Use a conservative factory-wide learned per-active-SAP baseline derived
    # from VERIFIED actual production. This starts low confidence and is
    # automatically replaced by SAP-specific evidence as history grows.
    if capacity <= 0:
        fallback = dict(fallback_capacity or {})
        fallback_safe = max(0.0, _float(fallback.get("safe_capacity_qty")))
        fallback_expected = max(0.0, _float(fallback.get("expected_capacity_qty")))
        fallback_samples = max(0, _int(fallback.get("sample_days")))
        fallback_conf = max(0.0, min(1.0, _float(fallback.get("confidence_score"))))
        if fallback_samples >= 1 and max(fallback_safe, fallback_expected) > 0:
            capacity = fallback_safe or (fallback_expected * 0.75)
            source = "LEARNED FACTORY PER-SAP BASELINE"
            confidence = max(0.20, min(0.45, fallback_conf))

    if capacity <= 0:
        planner_capacity = max(0.0, _float(row.get("daily_capacity")))
        if planner_capacity > 0:
            capacity = planner_capacity
            source = "PLANNER DAILY CAPACITY"
            confidence = 0.70

    if capacity <= 0:
        smds_total_plan = max(0.0, _float(row.get("smds_total_plan")))
        cavities = max(0, _int(row.get("allocated_cavity_count")))
        if smds_total_plan > 0 and cavities > 0:
            capacity = smds_total_plan * cavities
            source = "SMDS × ALLOCATED CAVITIES"
            confidence = 0.75

    if capacity <= 0:
        reason = str(
            row.get("factory_out_reason")
            or row.get("schedule_reason")
            or row.get("planning_note")
            or ""
        ).strip()
        # Legacy V6-V10 rows may contain an approval-only blocker.  That flag is
        # no longer operational, so never surface it as a physical constraint.
        normalized_reason = reason.lower()
        if "approval" in normalized_reason and "approved" in normalized_reason:
            reason = ""
        if not reason:
            reason = (
                "No learned real-capacity evidence or usable technical capacity "
                "is available yet for this SAP."
            )
        return ItemFactoryOutForecast(
            shipment_id=shipment_id,
            sap_code=sap_code,
            ready_date=None,
            source="BLOCKED",
            confidence=0.0,
            blocker=reason,
            remaining_qty=remaining,
            item_id=item_id,
        )

    production_days = max(1, int(ceil(remaining / max(capacity, 1e-9))))
    ready_date = as_of_date + timedelta(days=production_days)
    return ItemFactoryOutForecast(
        shipment_id=shipment_id,
        sap_code=sap_code,
        ready_date=ready_date,
        source=source,
        confidence=confidence,
        remaining_qty=remaining,
        effective_daily_capacity=capacity,
        item_id=item_id,
    )


def aggregate_shipment_forecast(
    shipment_id: int,
    item_forecasts: Iterable[ItemFactoryOutForecast],
    *,
    dispatch_buffer_days: int = 0,
) -> ShipmentFactoryOutForecast:
    forecasts = [f for f in item_forecasts if f.shipment_id == shipment_id]
    positive = [f for f in forecasts if f.source != "NO POSITIVE DEMAND"]
    if not positive:
        return ShipmentFactoryOutForecast(
            shipment_id=shipment_id,
            factory_out_date=None,
            source="NO DEMAND",
            confidence=0.0,
            blocker="Shipment has no positive-quantity items.",
        )

    blocked = [f for f in positive if f.ready_date is None]
    dated = [f for f in positive if f.ready_date is not None]
    verified = [f for f in positive if f.source == "VERIFIED PLANNER DATE"]
    estimated = [f for f in positive if f.source != "VERIFIED PLANNER DATE"]

    if blocked:
        blockers = []
        for item in blocked[:3]:
            label = item.sap_code or "UNKNOWN SAP"
            blockers.append(f"{label}: {item.blocker}")
        suffix = "" if len(blocked) <= 3 else f"; +{len(blocked)-3} more"
        return ShipmentFactoryOutForecast(
            shipment_id=shipment_id,
            factory_out_date=None,
            source="BLOCKED",
            confidence=0.0,
            blocker="; ".join(blockers) + suffix,
            unresolved_items=len(blocked),
            forecast_items=len(estimated),
            verified_items=len(verified),
        )

    latest_ready = max(f.ready_date for f in dated if f.ready_date is not None)
    factory_out = latest_ready + timedelta(days=max(0, _int(dispatch_buffer_days)))
    confidence = min((f.confidence for f in dated), default=0.0)

    unique_sources = {f.source for f in dated}
    if unique_sources == {"VERIFIED PLANNER DATE"}:
        source = "VERIFIED"
    elif all(s in {"VERIFIED PLANNER DATE", "STOCK / PRODUCED READY"} for s in unique_sources):
        source = "READY / VERIFIED"
    elif any("LEARNED" in s for s in unique_sources):
        source = "ML CAPACITY FORECAST"
    elif any("SMDS" in s for s in unique_sources):
        source = "CAPACITY FORECAST"
    else:
        source = "PLANNER FORECAST"

    return ShipmentFactoryOutForecast(
        shipment_id=shipment_id,
        factory_out_date=factory_out,
        source=source,
        confidence=confidence,
        forecast_items=len(estimated),
        verified_items=len(verified),
    )


def _safe_mapping_query(connection, statement: str, params: Mapping[str, Any] | None = None):
    """Run an optional compatibility query behind a SAVEPOINT.

    PostgreSQL marks the whole transaction as failed after any SQL error.  The
    Shipment Command Center intentionally probes optional V9/V10 schema
    features, so those probes must never poison the caller's transaction.
    """
    try:
        with connection.begin_nested():
            return connection.execute(
                text(statement),
                dict(params or {}),
            ).mappings().all()
    except Exception:
        return None


def _blocked_forecast_map(ids: Iterable[int], reason: str) -> dict[int, ShipmentFactoryOutForecast]:
    return {
        int(shipment_id): ShipmentFactoryOutForecast(
            shipment_id=int(shipment_id),
            factory_out_date=None,
            source="BLOCKED",
            confidence=0.0,
            blocker=reason,
            unresolved_items=1,
        )
        for shipment_id in ids
    }


def load_shipment_forecasts(
    connection,
    shipment_ids: Iterable[int],
    *,
    as_of_date: date,
    item_forecast_sink: dict[int, ItemFactoryOutForecast] | None = None,
) -> dict[int, ShipmentFactoryOutForecast]:
    ids = sorted({int(value) for value in shipment_ids if int(value) > 0})
    if not ids:
        return {}

    # Capacity models are optional during migration/backfill.  Every optional
    # query is isolated by a SAVEPOINT so an absent table/column cannot leave
    # PostgreSQL in InFailedSqlTransaction state and break Shipment Details.
    model_map: dict[str, dict[str, Any]] = {}
    factory_model: dict[str, Any] = {}
    model_rows = _safe_mapping_query(
        connection,
        """
        SELECT model_level, entity_key, sample_days, safe_capacity_qty,
               expected_capacity_qty, recent_capacity_qty,
               confidence_score, confidence_band
        FROM mpps_factory_capacity_models
        WHERE model_level IN ('SAP', 'FACTORY')
        """,
    )
    if model_rows is not None:
        for row in model_rows:
            level = str(row.get("model_level") or "").strip().upper()
            entity = str(row.get("entity_key") or "").strip()
            if level == "SAP" and entity:
                model_map[entity] = dict(row)
            elif level == "FACTORY":
                factory_model = dict(row)

    # V10.4.1 cold-start fallback.  Some shipment SAPs do not yet have enough
    # direct production history to train a SAP model.  Instead of returning
    # BLOCKED, derive a conservative per-active-SAP baseline from VERIFIED
    # actual factory production.  This remains low confidence until direct SAP
    # evidence replaces it.
    fallback_model: dict[str, Any] = {}
    observed_rows = _safe_mapping_query(
        connection,
        """
        SELECT
            COUNT(*)::integer AS sample_days,
            percentile_cont(0.25) WITHIN GROUP (
                ORDER BY total_actual_qty::numeric / GREATEST(active_sap_count, 1)
            ) AS safe_capacity_qty,
            percentile_cont(0.50) WITHIN GROUP (
                ORDER BY total_actual_qty::numeric / GREATEST(active_sap_count, 1)
            ) AS expected_capacity_qty
        FROM mpps_factory_daily_capacity
        WHERE production_date <= :as_of_date
          AND production_date >= (:as_of_date - 90)
          AND total_actual_qty > 0
          AND active_sap_count > 0
        """,
        {"as_of_date": as_of_date},
    )
    if observed_rows:
        observed = dict(observed_rows[0])
        if _int(observed.get("sample_days")) > 0 and max(
            _float(observed.get("safe_capacity_qty")),
            _float(observed.get("expected_capacity_qty")),
        ) > 0:
            fallback_model = {
                "sample_days": _int(observed.get("sample_days")),
                "safe_capacity_qty": _float(observed.get("safe_capacity_qty")),
                "expected_capacity_qty": _float(observed.get("expected_capacity_qty")),
                "confidence_score": min(
                    0.45,
                    max(
                        0.20,
                        _int(observed.get("sample_days")) / 60.0,
                    ),
                ),
                "confidence_band": "LEARNING",
                "model_level": "FACTORY_PER_ACTIVE_SAP",
            }

    if not fallback_model:
        observed_rows = _safe_mapping_query(
            connection,
            """
            WITH daily AS (
                SELECT production_date,
                       SUM(total_actual_qty)::numeric AS total_actual_qty,
                       COUNT(DISTINCT NULLIF(TRIM(sap_code), ''))::integer AS active_sap_count
                FROM mpps_actual_production
                WHERE production_date <= :as_of_date
                  AND production_date >= (:as_of_date - 90)
                  AND total_actual_qty > 0
                GROUP BY production_date
            )
            SELECT
                COUNT(*)::integer AS sample_days,
                percentile_cont(0.25) WITHIN GROUP (
                    ORDER BY total_actual_qty / GREATEST(active_sap_count, 1)
                ) AS safe_capacity_qty,
                percentile_cont(0.50) WITHIN GROUP (
                    ORDER BY total_actual_qty / GREATEST(active_sap_count, 1)
                ) AS expected_capacity_qty
            FROM daily
            WHERE active_sap_count > 0
            """,
            {"as_of_date": as_of_date},
        )
        if observed_rows:
            observed = dict(observed_rows[0])
            if _int(observed.get("sample_days")) > 0 and max(
                _float(observed.get("safe_capacity_qty")),
                _float(observed.get("expected_capacity_qty")),
            ) > 0:
                fallback_model = {
                    "sample_days": _int(observed.get("sample_days")),
                    "safe_capacity_qty": _float(observed.get("safe_capacity_qty")),
                    "expected_capacity_qty": _float(observed.get("expected_capacity_qty")),
                    "confidence_score": min(
                        0.40,
                        max(0.18, _int(observed.get("sample_days")) / 70.0),
                    ),
                    "confidence_band": "LEARNING",
                    "model_level": "FACTORY_PER_ACTIVE_SAP",
                }

    # If daily observed statistics are not yet available but the factory model
    # exists, scale it by the recent average number of active SAPs.  This is
    # still based on verified actual factory output and remains deliberately
    # low confidence.
    if not fallback_model and factory_model:
        active_rows = _safe_mapping_query(
            connection,
            """
            SELECT AVG(active_sap_count)::numeric AS active_sap_count,
                   COUNT(*)::integer AS sample_days
            FROM mpps_factory_daily_capacity
            WHERE production_date <= :as_of_date
              AND production_date >= (:as_of_date - 90)
              AND active_sap_count > 0
            """,
            {"as_of_date": as_of_date},
        )
        active = dict(active_rows[0]) if active_rows else {}
        active_count = max(1.0, _float(active.get("active_sap_count"), 1.0))
        model_safe = max(0.0, _float(factory_model.get("safe_capacity_qty")))
        model_expected = max(0.0, _float(factory_model.get("expected_capacity_qty")))
        if max(model_safe, model_expected) > 0:
            fallback_model = {
                "sample_days": max(
                    1,
                    _int(active.get("sample_days")),
                    _int(factory_model.get("sample_days")),
                ),
                "safe_capacity_qty": model_safe / active_count if model_safe > 0 else 0,
                "expected_capacity_qty": model_expected / active_count if model_expected > 0 else 0,
                "confidence_score": min(
                    0.35,
                    max(0.18, _float(factory_model.get("confidence_score")) * 0.45),
                ),
                "confidence_band": "LEARNING",
                "model_level": "FACTORY_PER_ACTIVE_SAP",
            }

    params = {"shipment_ids": ids}
    rows = _safe_mapping_query(
        connection,
        """
        SELECT
            item.id AS item_id,
            item.shipment_id,
            item.sap_code,
            item.quantity,
            item.stock_allocated_qty,
            item.produced_qty,
            item.daily_capacity,
            item.allocated_cavity_count,
            item.item_receive_date,
            item.receive_date,
            item.end_date,
            item.start_date,
            item.factory_out_reason,
            item.schedule_reason,
            item.planning_note,
            COALESCE(smds.total_plan, 0) AS smds_total_plan,
            COALESCE(shipment.dispatch_buffer_days, 0) AS dispatch_buffer_days
        FROM mpps_shipment_items item
        JOIN mpps_shipments shipment ON shipment.id = item.shipment_id
        LEFT JOIN smds ON TRIM(COALESCE(smds.sap_code, '')) = TRIM(COALESCE(item.sap_code, ''))
        WHERE item.shipment_id = ANY(:shipment_ids)
        ORDER BY item.shipment_id, item.id
        """,
        params,
    )

    if rows is None:
        # Compatibility path for databases that pre-date the V10 reason fields.
        rows = _safe_mapping_query(
            connection,
            """
            SELECT
                item.id AS item_id,
                item.shipment_id,
                item.sap_code,
                item.quantity,
                item.stock_allocated_qty,
                item.produced_qty,
                item.daily_capacity,
                item.allocated_cavity_count,
                item.item_receive_date,
                item.receive_date,
                item.end_date,
                item.start_date,
                '' AS factory_out_reason,
                '' AS schedule_reason,
                '' AS planning_note,
                COALESCE(smds.total_plan, 0) AS smds_total_plan,
                COALESCE(shipment.dispatch_buffer_days, 0) AS dispatch_buffer_days
            FROM mpps_shipment_items item
            JOIN mpps_shipments shipment ON shipment.id = item.shipment_id
            LEFT JOIN smds ON TRIM(COALESCE(smds.sap_code, '')) = TRIM(COALESCE(item.sap_code, ''))
            WHERE item.shipment_id = ANY(:shipment_ids)
            ORDER BY item.shipment_id, item.id
            """,
            params,
        )

    if rows is None:
        # Minimal legacy path: enough to return stock-ready dates safely even if
        # capacity/reason/date columns have not yet been migrated.
        rows = _safe_mapping_query(
            connection,
            """
            SELECT
                item.id AS item_id,
                item.shipment_id,
                item.sap_code,
                item.quantity,
                item.stock_allocated_qty,
                item.produced_qty,
                0 AS daily_capacity,
                0 AS allocated_cavity_count,
                NULL::date AS item_receive_date,
                NULL::date AS receive_date,
                NULL::date AS end_date,
                NULL::date AS start_date,
                '' AS factory_out_reason,
                '' AS schedule_reason,
                '' AS planning_note,
                0 AS smds_total_plan,
                0 AS dispatch_buffer_days
            FROM mpps_shipment_items item
            WHERE item.shipment_id = ANY(:shipment_ids)
            ORDER BY item.shipment_id, item.id
            """,
            params,
        )

    if rows is None:
        return _blocked_forecast_map(
            ids,
            "Factory-out forecast data could not be read safely; run the V10 schema health check.",
        )

    by_shipment: dict[int, list[ItemFactoryOutForecast]] = {shipment_id: [] for shipment_id in ids}
    buffers: dict[int, int] = {}
    for raw in rows:
        row = dict(raw)
        shipment_id = _int(row.get("shipment_id"))
        sap_code = str(row.get("sap_code") or "").strip()
        buffers[shipment_id] = max(0, _int(row.get("dispatch_buffer_days")))
        # V11 authoritative capacity path.  Every shipment forecast asks the
        # same resolver used by Production Planning / Stock Planning.  The old
        # model tables remain migration fallbacks only.
        try:
            resolution = FactoryResourceIntelligenceService.resolve_capacity(
                connection,
                sap_code,
                on_date=as_of_date,
                ensure_schema=False,
            )
        except Exception:
            resolution = None

        learned = dict(model_map.get(sap_code) or {})
        if resolution is not None and float(resolution.expected_capacity or 0) > 0:
            learned = {
                "sample_days": int(resolution.sample_days or 0),
                "safe_capacity_qty": float(resolution.safe_capacity or 0),
                "expected_capacity_qty": float(resolution.expected_capacity or 0),
                "recent_capacity_qty": float(resolution.expected_capacity or 0),
                "confidence_score": float(resolution.confidence_score or 0),
                "confidence_band": str(resolution.confidence_band or "LEARNING"),
                "source": str(resolution.source or "V11 REAL CAPACITY"),
            }
            # For cold-start / technical fallbacks the resolver may have no
            # model samples.  Feed its constraint-adjusted capacity through the
            # planner-capacity slot without pretending it is learned evidence.
            if int(resolution.sample_days or 0) <= 0:
                row["daily_capacity"] = max(
                    _float(row.get("daily_capacity")),
                    float(resolution.available_capacity or resolution.safe_capacity or 0),
                )

        item_forecast = forecast_item(
            row,
            as_of_date=as_of_date,
            learned_capacity=learned,
            fallback_capacity=fallback_model,
        )
        by_shipment.setdefault(shipment_id, []).append(item_forecast)
        if item_forecast_sink is not None and item_forecast.item_id > 0:
            item_forecast_sink[item_forecast.item_id] = item_forecast

    return {
        shipment_id: aggregate_shipment_forecast(
            shipment_id,
            by_shipment.get(shipment_id, []),
            dispatch_buffer_days=buffers.get(shipment_id, 0),
        )
        for shipment_id in ids
    }
