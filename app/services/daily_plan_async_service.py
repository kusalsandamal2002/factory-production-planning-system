from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.database import get_session


def _exists(session, table_name: str) -> bool:
    try:
        return bool(
            session.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"public.{table_name}"},
            ).scalar()
        )
    except Exception:
        return False


def list_plan_dates(limit: int = 180) -> list[str]:
    limit = max(1, min(365, int(limit)))
    with get_session() as session:
        selects: list[str] = []
        if _exists(session, "mpps_cavity_plan_rows"):
            selects.append("SELECT plan_date FROM mpps_cavity_plan_rows")
        if _exists(session, "mpps_oven_plan"):
            selects.append("SELECT plan_date FROM mpps_oven_plan")
        if _exists(session, "mpps_ai_plan_runs"):
            selects.append("SELECT plan_date FROM mpps_ai_plan_runs")
        if not selects:
            return []
        sql = " UNION ".join(selects)
        rows = session.execute(
            text(
                f"""
                SELECT DISTINCT plan_date
                FROM ({sql}) dates
                WHERE plan_date IS NOT NULL
                ORDER BY plan_date DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).scalars().all()
        return [str(value) for value in rows]


def load_daily_plan(plan_date: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "plan_date": str(plan_date or ""),
        "cavity": [],
        "imported": [],
        "ai": [],
    }
    if not plan_date:
        return payload

    with get_session() as session:
        if _exists(session, "mpps_cavity_plan_rows"):
            rows = session.execute(
                text(
                    """
                    SELECT
                        plan_date,
                        line_name,
                        cavity_no,
                        oven_no,
                        shift_name,
                        priority_no,
                        tyre_code,
                        description,
                        day_plan_pcs,
                        night_plan_pcs,
                        total_plan,
                        balance,
                        allocation_status,
                        risk_reason
                    FROM mpps_cavity_plan_rows
                    WHERE plan_date = CAST(:plan_date AS DATE)
                    ORDER BY line_name, cavity_no, sequence_no
                    LIMIT 5000
                    """
                ),
                {"plan_date": plan_date},
            ).mappings().all()
            payload["cavity"] = [dict(row) for row in rows]

        if _exists(session, "mpps_oven_plan"):
            rows = session.execute(
                text(
                    """
                    SELECT
                        plan_date,
                        oven_code,
                        shift_name,
                        material_code,
                        item_description,
                        planned_qty,
                        planned_weight_kg,
                        plan_status,
                        CONCAT(
                            COALESCE(source_workbook, ''),
                            ' / ',
                            COALESCE(source_sheet, '')
                        ) AS source
                    FROM mpps_oven_plan
                    WHERE plan_date = CAST(:plan_date AS DATE)
                    ORDER BY oven_code, shift_name, material_code
                    LIMIT 5000
                    """
                ),
                {"plan_date": plan_date},
            ).mappings().all()
            payload["imported"] = [dict(row) for row in rows]

        if _exists(session, "mpps_ai_plan_items") and _exists(session, "mpps_ai_plan_runs"):
            rows = session.execute(
                text(
                    """
                    SELECT i.*
                    FROM mpps_ai_plan_items i
                    JOIN (
                        SELECT MAX(id) AS run_id
                        FROM mpps_ai_plan_runs
                        WHERE plan_date = CAST(:plan_date AS DATE)
                    ) latest ON latest.run_id = i.run_id
                    ORDER BY i.priority_score DESC, i.sap_code
                    LIMIT 5000
                    """
                ),
                {"plan_date": plan_date},
            ).mappings().all()
            payload["ai"] = [dict(row) for row in rows]

    return payload
