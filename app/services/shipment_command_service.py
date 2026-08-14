from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ShipmentRiskProfile:
    score: int
    band: str
    label: str
    production_gap: int
    stock_coverage_pct: float
    days_to_target: int | None
    delivery_variance_days: int | None
    action: str
    risk_drivers: tuple[str, ...] = ()


def day_count(value: Any, default: int = 0) -> int:
    """Return a whole-day integer from SQL/Python day-delta values.

    PostgreSQL DATE subtraction returns an integer while Python DATE
    subtraction returns datetime.timedelta. Shipment forecasting can pass
    through either representation, so the UI/risk layer must accept both.
    """
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


def _as_int(value: Any, default: int = 0) -> int:
    return day_count(value, default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def shipment_risk_profile(
    row: Mapping[str, Any],
    *,
    as_of_date: date,
) -> ShipmentRiskProfile:
    """Create a deterministic operational shipment-risk profile.

    This deliberately uses only information already known as of the LIVE OVEN
    operational date: target/factory-out dates, stock coverage, planning state,
    and review flags.  It is a decision-support score, not an ML forecast.
    """

    total_qty = max(0, _as_int(row.get("total_quantity")))
    stock_allocated = max(0, _as_int(row.get("stock_allocated")))
    stock_allocated = min(stock_allocated, total_qty) if total_qty else 0
    production_gap = max(0, total_qty - stock_allocated)
    coverage = (
        (stock_allocated / total_qty) * 100.0
        if total_qty > 0
        else 100.0
    )

    target_date = row.get("target_date")
    factory_out = row.get("factory_can_receive_date")
    promise_state = str(row.get("promise_state") or "pending").strip().lower()
    review_required = bool(row.get("review_required")) or promise_state == "review_required"

    days_to_target = None
    if isinstance(target_date, date):
        days_to_target = (target_date - as_of_date).days

    delivery_variance_days = None
    if isinstance(target_date, date) and isinstance(factory_out, date):
        delivery_variance_days = (target_date - factory_out).days

    if promise_state == "cancelled":
        return ShipmentRiskProfile(
            score=0,
            band="cancelled",
            label="CANCELLED",
            production_gap=production_gap,
            stock_coverage_pct=coverage,
            days_to_target=days_to_target,
            delivery_variance_days=delivery_variance_days,
            action="No action — shipment is cancelled.",
            risk_drivers=("Shipment cancelled",),
        )

    score = 0
    risk_drivers: list[str] = []

    if review_required:
        score += 55
        risk_drivers.append("Source/data review required")

    if target_date is None:
        score += 35
        risk_drivers.append("Target date missing")
    elif days_to_target is not None:
        if days_to_target < 0:
            score += min(45, 20 + abs(days_to_target) * 2)
            risk_drivers.append(f"Target overdue by {abs(days_to_target)} day(s)")
        elif days_to_target <= 2:
            score += 22
            risk_drivers.append(f"Only {max(days_to_target, 0)} day(s) to target")
        elif days_to_target <= 7:
            score += 12
            risk_drivers.append(f"Target within {days_to_target} day(s)")
        elif days_to_target <= 14:
            score += 6

    if factory_out is None:
        score += 18
        risk_drivers.append("Factory Can Out not yet feasible")
    elif delivery_variance_days is not None and delivery_variance_days < 0:
        score += min(35, 18 + abs(delivery_variance_days) * 2)
        risk_drivers.append(f"Factory Can Out misses target by {abs(delivery_variance_days)} day(s)")

    if promise_state == "cannot_meet":
        score += 28
        risk_drivers.append("Delivery promise currently infeasible")
    elif promise_state in {"pending", "review_required"}:
        score += 12
    elif promise_state == "auto_scheduled":
        score += 4

    if total_qty > 0:
        gap_ratio = production_gap / total_qty
        score += round(min(35.0, gap_ratio * 35.0))
        if production_gap > 0:
            risk_drivers.append(f"Production gap {production_gap:,} pcs ({100.0 - coverage:.1f}% uncovered)")
        if coverage <= 0:
            score += 12
        elif coverage < 50:
            score += 7
        elif coverage < 100:
            score += 3

    score = max(0, min(100, int(score)))

    if review_required:
        band = "review"
        label = f"REVIEW {score}"
        action = "Resolve source/date/data-quality review before committing the delivery promise."
    elif score >= 80:
        band = "critical"
        label = f"CRITICAL {score}"
        if production_gap > 0:
            action = f"Escalate now: secure or produce {production_gap:,} pcs and replan delivery."
        else:
            action = "Escalate delivery feasibility now; stock is covered but timing is critical."
    elif score >= 55:
        band = "at_risk"
        label = f"AT RISK {score}"
        if production_gap > 0:
            action = f"Prioritise {production_gap:,} pcs production gap and verify Factory Can Out date."
        else:
            action = "Verify dispatch readiness and Factory Can Out date."
    elif score >= 30:
        band = "watch"
        label = f"WATCH {score}"
        if production_gap > 0:
            action = f"Monitor {production_gap:,} pcs production gap against remaining target window."
        else:
            action = "Monitor execution; current stock coverage is adequate."
    else:
        band = "healthy"
        label = f"HEALTHY {score}"
        action = "No escalation required; continue normal execution monitoring."

    return ShipmentRiskProfile(
        score=score,
        band=band,
        label=label,
        production_gap=production_gap,
        stock_coverage_pct=coverage,
        days_to_target=days_to_target,
        delivery_variance_days=delivery_variance_days,
        action=action,
        risk_drivers=tuple(risk_drivers[:5]),
    )


def portfolio_metrics(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    total_shipments = len(rows)
    total_qty = sum(max(0, _as_int(row.get("total_quantity"))) for row in rows)
    stock_allocated = sum(max(0, _as_int(row.get("stock_allocated"))) for row in rows)
    production_gap = sum(max(0, _as_int(row.get("production_gap"))) for row in rows)
    critical = sum(1 for row in rows if str(row.get("risk_band")) == "critical")
    review = sum(1 for row in rows if str(row.get("risk_band")) == "review")
    at_risk = sum(1 for row in rows if str(row.get("risk_band")) in {"critical", "at_risk"})
    coverage = (stock_allocated / total_qty * 100.0) if total_qty > 0 else 0.0
    return {
        "total_shipments": total_shipments,
        "total_qty": total_qty,
        "stock_allocated": stock_allocated,
        "stock_coverage_pct": coverage,
        "production_gap": production_gap,
        "critical": critical,
        "review": review,
        "at_risk": at_risk,
    }

@dataclass(frozen=True)
class ShipmentExecutionState:
    """Derived shipment execution state from item-level readiness evidence.

    A persisted planning_status can become stale after live ML forecasts are
    generated.  This state is therefore computed from the current item rows and
    live forecast evidence every time the shipment detail workspace is opened.
    """

    label: str
    ready_qty: int
    remaining_qty: int
    forecast_items: int
    blocked_items: int
    scheduled_items: int
    ready_items: int


def shipment_execution_state(items: Iterable[Mapping[str, Any]]) -> ShipmentExecutionState:
    """Return a non-stale shipment planning state from item readiness evidence.

    Each item mapping may provide:
      quantity, ready_qty/completed_qty, remaining_qty,
      verified_receive_date, forecast_receive_date, blocker.

    The function deliberately ignores legacy approval/planning-status strings.
    A shipment is blocked only when a positive remaining quantity has no
    verified/forecast date and carries a real blocker/evidence gap.
    """

    ready_qty = 0
    remaining_qty = 0
    forecast_items = 0
    blocked_items = 0
    scheduled_items = 0
    ready_items = 0
    active_remaining_items = 0

    for raw in items:
        row = dict(raw)
        quantity = max(0, _as_int(row.get("quantity")))
        ready = row.get("ready_qty")
        if ready is None:
            ready = row.get("completed_qty")
        ready = max(0, min(quantity, _as_int(ready))) if quantity else 0

        remaining = row.get("remaining_qty")
        if remaining is None:
            remaining = max(0, quantity - ready)
        remaining = max(0, _as_int(remaining))

        ready_qty += ready
        remaining_qty += remaining

        if remaining <= 0:
            ready_items += 1
            continue

        active_remaining_items += 1
        verified = row.get("verified_receive_date") or row.get("receive_date")
        forecast = row.get("forecast_receive_date") or row.get("forecast_date")
        blocker = str(row.get("blocker") or "").strip()

        if forecast is not None:
            forecast_items += 1
        elif verified is not None:
            scheduled_items += 1
        elif blocker:
            blocked_items += 1
        else:
            # Missing evidence is itself a real blocker for a safe forecast.
            blocked_items += 1

    if remaining_qty <= 0:
        label = "READY"
    elif blocked_items <= 0:
        label = "FORECAST" if forecast_items > 0 else "SCHEDULED"
    elif blocked_items < active_remaining_items:
        label = "PARTIALLY BLOCKED"
    else:
        label = "BLOCKED"

    return ShipmentExecutionState(
        label=label,
        ready_qty=ready_qty,
        remaining_qty=remaining_qty,
        forecast_items=forecast_items,
        blocked_items=blocked_items,
        scheduled_items=scheduled_items,
        ready_items=ready_items,
    )

@dataclass(frozen=True)
class ItemExecutionTimeline:
    """Display-ready stock/production timeline for a shipment item.

    This is intentionally a presentation/decision-support projection. It does
    not overwrite verified database dates. Fully stock-covered items are ready
    now, so they never show a fake production start date.
    """

    quantity: int
    stock_allocated: int
    shortage_qty: int
    completion_pct: float
    production_start_date: date | None
    receive_date: date | None
    state: str
    source: str = ""


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def item_execution_timeline(
    row: Mapping[str, Any],
    *,
    today: date,
    forecast: Any | None = None,
) -> ItemExecutionTimeline:
    """Build the operator-facing item timeline.

    Rules:
    - Stock Allocated is the quantity reserved from total stock for this order.
    - Shortage is the still-uncovered quantity after stock + verified produced.
    - Complete % is covered quantity / order quantity.
    - If stock alone fully covers the line, Production Start is blank and the
      Receive/Finish date is today, because no production is required.
    - Verified dates remain authoritative. Missing dates may be shown from the
      live ML/capacity forecast without persisting them as history.
    """

    quantity = max(0, _as_int(row.get("quantity")))
    stock = max(0, min(quantity, _as_int(row.get("stock_allocated_qty"))))
    produced = max(0, _as_int(row.get("produced_qty")))
    produced_cover = min(max(0, quantity - stock), produced)
    covered = min(quantity, stock + produced_cover)
    shortage = max(0, quantity - covered)
    completion_pct = (covered / quantity * 100.0) if quantity > 0 else 100.0

    verified_start = _as_date(
        row.get("production_start_date") or row.get("start_date")
    )
    verified_receive = _as_date(
        row.get("item_receive_date") or row.get("receive_date") or row.get("end_date")
    )

    # Explicit factory rule: if this order line is already fully allocated from
    # stock, production is not needed. Show '-' for Production Start and today
    # as the ready/receive date.
    if quantity > 0 and stock >= quantity:
        return ItemExecutionTimeline(
            quantity=quantity,
            stock_allocated=stock,
            shortage_qty=0,
            completion_pct=100.0,
            production_start_date=None,
            receive_date=today,
            state="STOCK ALLOCATED",
            source="LIVE STOCK",
        )

    if quantity <= 0:
        return ItemExecutionTimeline(
            quantity=0,
            stock_allocated=0,
            shortage_qty=0,
            completion_pct=100.0,
            production_start_date=None,
            receive_date=today,
            state="NO DEMAND",
            source="NO POSITIVE DEMAND",
        )

    if shortage <= 0:
        return ItemExecutionTimeline(
            quantity=quantity,
            stock_allocated=stock,
            shortage_qty=0,
            completion_pct=100.0,
            production_start_date=verified_start,
            receive_date=verified_receive or today,
            state="READY / PRODUCED",
            source="VERIFIED PRODUCTION",
        )

    forecast_date = _as_date(getattr(forecast, "ready_date", None)) if forecast is not None else None
    forecast_source = str(getattr(forecast, "source", "") or "").strip()
    blocker = str(getattr(forecast, "blocker", "") or "").strip()

    if verified_receive is not None:
        return ItemExecutionTimeline(
            quantity=quantity,
            stock_allocated=stock,
            shortage_qty=shortage,
            completion_pct=completion_pct,
            production_start_date=verified_start or today,
            receive_date=verified_receive,
            state="SCHEDULED",
            source="VERIFIED SCHEDULE",
        )

    if forecast_date is not None:
        start_date = verified_start or today
        # A stale LIVE OVEN source must never make a live production forecast
        # finish before the current day. Re-anchor only the display forecast;
        # verified history is untouched.
        finish_date = forecast_date
        effective_capacity = float(getattr(forecast, "effective_daily_capacity", 0.0) or 0.0)
        if finish_date < start_date and effective_capacity > 0:
            from math import ceil
            finish_date = start_date + timedelta(
                days=max(1, int(ceil(shortage / max(effective_capacity, 1e-9))))
            )
        state = "ML FORECAST" if "LEARNED" in forecast_source.upper() else "FORECAST"
        return ItemExecutionTimeline(
            quantity=quantity,
            stock_allocated=stock,
            shortage_qty=shortage,
            completion_pct=completion_pct,
            production_start_date=start_date,
            receive_date=finish_date,
            state=state,
            source=forecast_source or "CAPACITY FORECAST",
        )

    return ItemExecutionTimeline(
        quantity=quantity,
        stock_allocated=stock,
        shortage_qty=shortage,
        completion_pct=completion_pct,
        production_start_date=verified_start,
        receive_date=None,
        state="BLOCKED" if blocker else "PLANNING",
        source=blocker or "WAITING FOR CAPACITY FORECAST",
    )

