from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
import re
from typing import Any

from sqlalchemy import text

from app.database import engine


LINE_COLUMN_CANDIDATES = {
    "Line-400": ["line_400", "line-400", "line400"],
    "Line-800": ["line_800", "line-800", "line800"],
    "Press-LINE": ["press_line", "press-line", "press line", "press -line", "press - line"],
    "NANCY PRESS": ["nancy_press", "nancy press"],
    "400 T PRESS": ["400_t_press", "_400_t_press", "400 t press"],
    "T 600 -01 PRESS": ["t_600_01_press", "t 600 -01 press", "t 600 01 press"],
    "T 600 -02 PRESS": ["t_600_02_press", "t 600 -02 press", "t 600 02 press"],
    "L-PRESS-1250": ["l_press_1250", "l-press-1250", "l press 1250"],
    "L-PRESS-1500": ["l_press_1500", "l-press-1500", "l press 1500"],
    "L-PRESS-1800": ["l_press_1800", "l-press-1800", "l press 1800"],
    "ORING-PRESS": ["oring_press", "oring-press", "o_ring_press"],
    "NEW PRESS": ["new_press", "new press"],
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def _column_map(columns: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for col in columns:
        result.setdefault(_norm(col), col)
    return result


def _find(mapping: dict[str, str], *candidates: str) -> str | None:
    for candidate in candidates:
        found = mapping.get(_norm(candidate))
        if found:
            return found
    return None


@lru_cache(maxsize=1)
def _smds_projection() -> dict[str, Any]:
    """Resolve SMDS schema once per process; never from the GUI thread."""
    with engine.connect() as connection:
        columns = [
            str(row[0])
            for row in connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name='smds'
                    ORDER BY ordinal_position
                    """
                )
            ).all()
        ]
    mapping = _column_map(columns)
    sap_col = _find(mapping, "sap_code", "sap code", "sap")
    if not sap_col:
        return {}
    desc_col = _find(
        mapping,
        "material_description",
        "material description",
        "tyre_description",
        "description",
    ) or sap_col
    fields: list[tuple[str, str | None]] = [
        ("sap_code", sap_col),
        ("tyre_description", desc_col),
        ("key_code", _find(mapping, "key_code", "key code", "mold_key_code")),
        ("casing_type", _find(mapping, "casing_type", "casing type")),
        ("line", _find(mapping, "line")),
        ("day_plan", _find(mapping, "day_plan", "day plan")),
        ("night_plan", _find(mapping, "night_plan", "night plan")),
        ("total_plan", _find(mapping, "total_plan", "total plan")),
        ("curing_time_text", _find(mapping, "normal_curing_time_text", "curing_cycle", "curing cycle")),
        ("curing_minutes", _find(mapping, "normal_curing_minutes", "curing_minutes", "curing minutes")),
        ("handling_minutes", _find(mapping, "handling_minutes", "handling_time", "handling time")),
        ("approval_status", _find(mapping, "planning_manager_approval_status", "approval_status")),
    ]
    line_flags: list[tuple[str, str]] = []
    for display, candidates in LINE_COLUMN_CANDIDATES.items():
        col = _find(mapping, *candidates)
        if col:
            line_flags.append((display, col))
    return {
        "sap_col": sap_col,
        "desc_col": desc_col,
        "fields": fields,
        "line_flags": line_flags,
    }


def search_master_items(query: str, limit: int = 40) -> list[dict[str, Any]]:
    """Search only a bounded SMDS slice. No full-master transfer to the GUI."""
    query = _clean(query)
    if len(query) < 2:
        return []
    projection = _smds_projection()
    if not projection:
        return []

    sap_col = projection["sap_col"]
    desc_col = projection["desc_col"]
    fields = projection["fields"]
    line_flags = projection["line_flags"]

    select_parts: list[str] = []
    for alias, col in fields:
        if col:
            select_parts.append(f"{_quote(col)} AS {_quote(alias)}")
        else:
            select_parts.append(f"NULL AS {_quote(alias)}")
    for index, (_display, col) in enumerate(line_flags):
        select_parts.append(f"{_quote(col)} AS {_quote(f'line_flag_{index}')}")

    params = {
        "prefix": f"{query}%",
        "contains": f"%{query}%",
        "limit": max(5, min(80, int(limit))),
    }
    sql = f"""
        SELECT {', '.join(select_parts)}
        FROM smds
        WHERE {_quote(sap_col)} IS NOT NULL
          AND TRIM({_quote(sap_col)}::text) <> ''
          AND (
                {_quote(sap_col)}::text ILIKE :prefix
                OR {_quote(desc_col)}::text ILIKE :contains
              )
        ORDER BY
            CASE WHEN {_quote(sap_col)}::text ILIKE :prefix THEN 0 ELSE 1 END,
            {_quote(sap_col)} ASC
        LIMIT :limit
    """
    with engine.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        detected: list[str] = []
        for index, (display, _col) in enumerate(line_flags):
            value = _clean(item.get(f"line_flag_{index}"))
            if value.lower() in {"ok", "yes", "y", "1", "true", "x"}:
                detected.append(display)
        line_text = ", ".join(detected) if detected else _clean(item.get("line"))
        result.append(
            {
                "sap_code": _clean(item.get("sap_code")),
                "tyre_description": _clean(item.get("tyre_description")),
                "key_code": _clean(item.get("key_code")),
                "casing_type": _clean(item.get("casing_type")),
                "line": line_text,
                "day_plan": _to_int(item.get("day_plan")),
                "night_plan": _to_int(item.get("night_plan")),
                "total_plan": _to_int(item.get("total_plan")),
                "curing_time_text": _clean(item.get("curing_time_text")),
                "curing_minutes": _to_float(item.get("curing_minutes")),
                "handling_minutes": _to_float(item.get("handling_minutes")),
                "approval_status": _clean(item.get("approval_status")) or "Pending",
            }
        )
    return result


def load_previous_shipments(search: str = "", limit: int = 20) -> list[dict[str, Any]]:
    search = _clean(search)
    params: dict[str, Any] = {"limit": max(1, min(50, int(limit)))}
    where = ""
    if search:
        params["search"] = f"%{search}%"
        where = """
            WHERE s.shipment_no ILIKE :search
               OR COALESCE(s.shipment_name,'') ILIKE :search
               OR COALESCE(s.customer_name,'') ILIKE :search
        """
    query = f"""
        SELECT
            s.id,
            s.shipment_no,
            COALESCE(NULLIF(s.shipment_name,''), s.customer_name, s.shipment_no) AS shipment_name,
            COALESCE(s.target_date, s.plan_date, s.manager_order_date, s.factory_out_date) AS target_date,
            COALESCE(MAX(i.item_receive_date), s.factory_can_receive_date, s.factory_out_date) AS factory_receive_date,
            COUNT(i.id) AS item_count
        FROM mpps_shipments s
        LEFT JOIN mpps_shipment_items i ON s.id=i.shipment_id
        {where}
        GROUP BY
            s.id, s.shipment_no, s.shipment_name, s.customer_name,
            s.target_date, s.plan_date, s.manager_order_date,
            s.factory_can_receive_date, s.factory_out_date
        ORDER BY target_date ASC NULLS LAST, s.id DESC
        LIMIT :limit
    """
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params).mappings().all()]


def get_unallocated_stock(sap_code: str) -> int:
    canonical = str(sap_code or "").strip()
    with engine.connect() as connection:
        current_table = bool(
            connection.execute(
                text("SELECT to_regclass('public.mpps_current_stock_snapshots') IS NOT NULL")
            ).scalar()
        )
        latest_run_id = None
        if current_table:
            latest_run_id = connection.execute(
                text("SELECT MAX(import_run_id) FROM mpps_current_stock_snapshots")
            ).scalar()
        has_current = latest_run_id is not None
        available = 0
        if has_current:
            available = int(
                connection.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(GREATEST(s.current_stock,0)),0)
                        FROM mpps_current_stock_snapshots s
                        WHERE UPPER(TRIM(s.sap_code))=UPPER(TRIM(:sap_code))
                          AND s.import_run_id=:run_id
                        """
                    ),
                    {"sap_code": canonical, "run_id": latest_run_id},
                ).scalar()
                or 0
            )
        if not has_current:
            available = int(
                connection.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(GREATEST(fg_stock,0)+GREATEST(qc_stock,0)
                                                   -GREATEST(scrap_stock,0)-GREATEST(blocked_stock,0)),0)
                        FROM mpps_sap_stock_items
                        WHERE UPPER(TRIM(sap_code))=UPPER(TRIM(:sap_code))
                        """
                    ),
                    {"sap_code": canonical},
                ).scalar()
                or 0
            )
        allocated = int(
            connection.execute(
                text(
                    """
                    SELECT COALESCE(SUM(i.stock_allocated_qty),0)
                    FROM mpps_shipment_items i
                    JOIN mpps_shipments s ON s.id=i.shipment_id
                    WHERE UPPER(TRIM(i.sap_code))=UPPER(TRIM(:sap_code))
                      AND UPPER(COALESCE(s.lifecycle_status,'ACTIVE')) NOT IN ('SHIPPED','CANCELLED')
                      AND LOWER(COALESCE(s.status,'planned')) NOT IN ('shipped','cancelled','canceled','closed')
                    """
                ),
                {"sap_code": canonical},
            ).scalar()
            or 0
        )
    return max(0, available - allocated)


def calculate_cart_plan(
    preview_items: list[dict[str, Any]],
    *,
    target_date: date | None,
    exclude_shipment_id: int | None = None,
    target_date_is_manual: bool = False,
    draft_created_at: datetime | None = None,
) -> list[dict[str, Any]]:
    from app.services.factory_can_out_service import FactoryCanOutService

    return FactoryCanOutService.preview_items(
        preview_items,
        target_date=target_date,
        exclude_shipment_id=exclude_shipment_id,
        target_date_is_manual=target_date_is_manual,
        draft_created_at=draft_created_at,
    )


def _delivery_promise(target_date: date | None, factory_receive_date: date | None) -> tuple[str, str, int, int]:
    if target_date is None or factory_receive_date is None:
        return "pending", "PENDING CALCULATION", 0, 0
    variance_days = (factory_receive_date - target_date).days
    if variance_days > 0:
        return "late", f"{variance_days} DAY(S) LATE", variance_days, 0
    if variance_days < 0:
        return "early", f"{abs(variance_days)} DAY(S) EARLY", 0, abs(variance_days)
    return "on_time", "ON TIME", 0, 0


def _next_shipment_no(connection) -> str:
    prefix = "SHP-" + date.today().strftime("%Y%m%d") + "-"
    count = int(
        connection.execute(
            text("SELECT COUNT(*) FROM mpps_shipments WHERE shipment_no LIKE :prefix"),
            {"prefix": prefix + "%"},
        ).scalar()
        or 0
    )
    return prefix + f"{count + 1:04d}"


def save_shipment(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a planned shipment in one short worker-thread transaction."""
    shipment_name = _clean(payload.get("shipment_name"))
    customer = _clean(payload.get("customer")) or shipment_name
    note = _clean(payload.get("note"))
    manual_target = bool(payload.get("target_date_is_manual"))
    manual_target_date = payload.get("target_date") if manual_target else None
    items = list(payload.get("items") or [])

    if not shipment_name:
        raise ValueError("Shipment name is required.")
    if not items:
        raise ValueError("At least one shipment item is required.")

    receive_dates = [
        item.get("item_receive_date")
        for item in items
        if item.get("item_receive_date") is not None
    ]
    factory_receive_date = max(receive_dates) if receive_dates else None
    target_date = manual_target_date or factory_receive_date
    if target_date is None:
        raise ValueError("Factory Can Out/Receive date is not available for all required production.")

    promise_state, promise_message, delay_days, early_days = _delivery_promise(
        target_date,
        factory_receive_date,
    )
    delivery_status = {
        "late": "Delayed",
        "early": "Can Deliver Early",
        "on_time": "On Time",
    }.get(promise_state, "Pending Calculation")
    planning_status = "At Risk" if promise_state == "late" else "Ready"

    total_qty = sum(int(item.get("quantity") or 0) for item in items)
    stock_allocated = sum(int(item.get("stock_allocated_qty") or 0) for item in items)
    progress_pct = min(100.0, (stock_allocated / total_qty * 100.0) if total_qty else 0.0)

    with engine.begin() as connection:
        shipment_no = _next_shipment_no(connection)
        shipment_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO mpps_shipments (
                        shipment_no, shipment_name, customer_name,
                        shipment_date, manager_order_date, target_date, plan_date,
                        factory_out_date, factory_can_receive_date,
                        delivery_status, delay_days, early_days,
                        total_qty, completed_qty, progress_pct,
                        planning_status, planning_note,
                        status, lifecycle_status,
                        target_date_is_manual, target_date_source,
                        note, updated_at
                    )
                    VALUES (
                        :shipment_no, :shipment_name, :customer_name,
                        :shipment_date, :manager_order_date, :target_date, :plan_date,
                        :factory_out_date, :factory_can_receive_date,
                        :delivery_status, :delay_days, :early_days,
                        :total_qty, 0, :progress_pct,
                        :planning_status, :planning_note,
                        'Planned', 'ACTIVE',
                        :target_date_is_manual, :target_date_source,
                        :note, CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """
                ),
                {
                    "shipment_no": shipment_no,
                    "shipment_name": shipment_name,
                    "customer_name": customer,
                    "shipment_date": target_date,
                    "manager_order_date": target_date,
                    "target_date": target_date,
                    "plan_date": target_date,
                    "factory_out_date": factory_receive_date,
                    "factory_can_receive_date": factory_receive_date,
                    "delivery_status": delivery_status,
                    "delay_days": delay_days,
                    "early_days": early_days,
                    "total_qty": total_qty,
                    "progress_pct": progress_pct,
                    "planning_status": planning_status,
                    "planning_note": promise_message,
                    "target_date_is_manual": manual_target,
                    "target_date_source": "Manual" if manual_target else "Automatic Factory Receive",
                    "note": note,
                },
            ).scalar_one()
        )

        for item in items:
            connection.execute(
                text(
                    """
                    INSERT INTO mpps_shipment_items (
                        shipment_id, sap_code, item_description, quantity,
                        start_date, end_date, item_status, note,
                        stock_allocated_qty, production_required_qty,
                        allocated_cavity_count, daily_capacity,
                        production_days, item_receive_date, receive_date,
                        schedule_reason, updated_at
                    )
                    VALUES (
                        :shipment_id, :sap_code, :item_description, :quantity,
                        :start_date, :end_date, :item_status, '',
                        :stock_allocated_qty, :production_required_qty,
                        :allocated_cavity_count, :daily_capacity,
                        :production_days, :item_receive_date, :item_receive_date,
                        :schedule_reason, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "shipment_id": shipment_id,
                    "sap_code": _clean(item.get("sap_code")),
                    "item_description": _clean(item.get("item_description")),
                    "quantity": int(item.get("quantity") or 0),
                    "start_date": date.today(),
                    "end_date": item.get("item_receive_date") or date.today(),
                    "item_status": _clean(item.get("item_status")) or "Pending",
                    "stock_allocated_qty": int(item.get("stock_allocated_qty") or 0),
                    "production_required_qty": int(item.get("production_required_qty") or 0),
                    "allocated_cavity_count": int(item.get("allocated_cavity_count") or 0),
                    "daily_capacity": int(item.get("daily_capacity") or 0),
                    "production_days": int(item.get("production_days") or 0),
                    "item_receive_date": item.get("item_receive_date"),
                    "schedule_reason": _clean(item.get("schedule_reason")),
                },
            )

    return {
        "shipment_id": shipment_id,
        "shipment_no": shipment_no,
        "target_date": target_date,
        "factory_receive_date": factory_receive_date,
        "delivery_status": delivery_status,
        "promise": promise_message,
    }


def replan_open_shipments(trigger_reason: str) -> dict[str, Any]:
    """Low-priority post-save cumulative replan, separate from the save transaction."""
    from app.services.factory_can_out_service import FactoryCanOutService

    return FactoryCanOutService.replan_open_shipments(
        trigger_reason=trigger_reason,
        created_by="shipment_entry_r6",
    )
