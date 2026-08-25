from __future__ import annotations

from copy import deepcopy
from datetime import date
from html import escape
import json
import re
from typing import Any

from sqlalchemy import text



def _get_session():
    from app.database import get_session

    return get_session()


TYRE_LINE_ORDER = (
    "200 Line",
    "600 Press",
    "Super Solid",
    "400 Line",
    "800 Line",
    "Bard Press",
)

LOSS_REASONS = (
    "Stock Counting",
    "Power Cut",
    "Absenteeism",
    "Mold Breakdown",
    "Mill Breakdown",
    "Press Breakdown",
    "Kneder Breakdown",
    "Sand Blast Breakdwon",
    "Other Breakdown",
    "Band Delay",
    "No Band (Factory)",
    "No Mold Changing",
    "Core Changing",
    "1st Compound Delay",
    "1st Compound Delay (Not Materials)",
    "1st Compound Delay (Grey/NM)",
    "2nd Compound Delay",
    "2nd Chemical Delay",
    "Temperature Delay",
    "Temperature Delay (New Mold)",
    "Quality Problem Delay",
    "R&D Testing",
    "Mold Cleaning Delay",
    "Operators Inefficiency",
)

LOSS_COLUMNS = (
    "200_kg",
    "200_pcs",
    "600_kg",
    "600_pcs",
    "400_kg",
    "400_pcs",
    "800_kg",
    "800_pcs",
)


def blank_payload() -> dict[str, Any]:
    return {
        "supervisor_name": "",
        "production_notes": "",
        "tyre_actuals": {
            line: {"kg": "", "pcs": ""} for line in TYRE_LINE_ORDER
        },
        "compound_rows": [
            {"compound_type": "", "target": "", "actual": ""}
            for _ in range(6)
        ],
        "scrap_tyre_rows": [
            {"tyre_size": "", "pcs": "", "defect": "", "operator": ""}
            for _ in range(3)
        ],
        "scrap_compound_rows": [
            {"compound_type": "", "weight": "", "defect": "", "operator": ""}
            for _ in range(3)
        ],
        "used_man_hours": "",
        "loss_reasons": {
            reason: {column: "" for column in LOSS_COLUMNS}
            for reason in LOSS_REASONS
        },
    }


def _normalise_line_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def classify_excel_report_line(line_name: Any) -> str | None:
    """Map the detailed OVEN sheet line names to the six Excel report lines.

    The mapping mirrors the formulas in the supplied OVEN workbook:
    - Press -LINE -> 200 Line
    - NANCY / 400 T / T600 presses -> 600 Press
    - L-PRESS-1250/1500/1800 -> Super Solid
    - Line-400 -> 400 Line
    - Line-800 -> 800 Line
    - ORING / NEW PRESS -> Bard Press
    """

    name = _normalise_line_name(line_name)
    if not name:
        return None

    if "PRESS -LINE" in name or "LINE-200" in name or "LINE 200" in name:
        return "200 Line"

    if (
        "NANCY PRESS" in name
        or "400 T PRESS" in name
        or name.startswith("T 600")
        or name.startswith("T600")
        or "600 T PRESS" in name
    ):
        return "600 Press"

    if (
        "L-PRESS-1250" in name
        or "L-PRESS-1500" in name
        or "L-PRESS-1800" in name
        or "SUPER SOLID" in name
        or "SUPER SOILD" in name
    ):
        return "Super Solid"

    if "LINE-400" in name or "LINE 400" in name:
        return "400 Line"

    if "LINE-800" in name or "LINE 800" in name:
        return "800 Line"

    if "ORING-PRESS" in name or "O'RING" in name or "NEW PRESS" in name:
        return "Bard Press"

    return None


def aggregate_excel_report_targets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targets = {
        line: {"target_kg": 0.0, "target_pcs": 0}
        for line in TYRE_LINE_ORDER
    }
    raw_pcs = 0
    raw_kg = 0.0
    mapped_pcs = 0
    mapped_kg = 0.0
    unmapped: list[dict[str, Any]] = []

    for row in rows:
        qty = int(round(float(row.get("planned_qty") or 0)))
        kg = float(row.get("planned_weight_kg") or 0)
        raw_pcs += qty
        raw_kg += kg

        report_line = classify_excel_report_line(row.get("line_name"))
        if report_line is None:
            if qty or abs(kg) > 1e-9:
                unmapped.append(
                    {
                        "line_name": str(row.get("line_name") or ""),
                        "planned_qty": qty,
                        "planned_weight_kg": kg,
                    }
                )
            continue

        targets[report_line]["target_pcs"] += qty
        targets[report_line]["target_kg"] += kg
        mapped_pcs += qty
        mapped_kg += kg

    for line in TYRE_LINE_ORDER:
        targets[line]["target_kg"] = round(targets[line]["target_kg"], 5)

    return {
        "lines": targets,
        "raw_total_pcs": raw_pcs,
        "raw_total_kg": round(raw_kg, 5),
        "mapped_total_pcs": mapped_pcs,
        "mapped_total_kg": round(mapped_kg, 5),
        "unmapped": unmapped,
    }


def _merge_payload(stored: dict[str, Any] | None) -> dict[str, Any]:
    result = blank_payload()
    if not isinstance(stored, dict):
        return result

    for key in ("supervisor_name", "production_notes", "used_man_hours"):
        if key in stored:
            result[key] = stored[key]

    actuals = stored.get("tyre_actuals")
    if isinstance(actuals, dict):
        for line in TYRE_LINE_ORDER:
            if isinstance(actuals.get(line), dict):
                result["tyre_actuals"][line].update(actuals[line])

    for key in ("compound_rows", "scrap_tyre_rows", "scrap_compound_rows"):
        rows = stored.get(key)
        if isinstance(rows, list):
            for index, row in enumerate(rows[: len(result[key])]):
                if isinstance(row, dict):
                    result[key][index].update(row)

    loss = stored.get("loss_reasons")
    if isinstance(loss, dict):
        for reason in LOSS_REASONS:
            row = loss.get(reason)
            if isinstance(row, dict):
                for column in LOSS_COLUMNS:
                    if column in row:
                        result["loss_reasons"][reason][column] = row[column]

    return result


def _table_exists(session, table_name: str) -> bool:
    try:
        return bool(
            session.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"public.{table_name}"},
            ).scalar()
        )
    except Exception:
        return False


def _latest_saved_run_id(session, report_date: str | date) -> int | None:
    if not _table_exists(session, "mpps_cavity_plan_runs"):
        return None
    row = session.execute(
        text(
            """
            SELECT id
            FROM mpps_cavity_plan_runs
            WHERE plan_date=CAST(:report_date AS DATE)
              AND UPPER(COALESCE(status,'SAVED')) NOT IN (
                  'CANCELLED','VOID','REJECTED'
              )
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"report_date": str(report_date)},
    ).first()
    return int(row[0]) if row else None


def _saved_shift_rows(
    session,
    report_date: str | date,
    shift_name: str | None = None,
) -> tuple[int | None, list[dict[str, Any]]]:
    run_id = _latest_saved_run_id(session, report_date)
    if run_id is None or not _table_exists(session, "mpps_cavity_plan_rows"):
        return None, []

    where_shift = ""
    params: dict[str, Any] = {"run_id": run_id}
    if shift_name:
        shift = str(shift_name).strip().upper()
        if shift not in {"DAY", "NIGHT"}:
            return run_id, []
        params["shift_name"] = shift
        where_shift = """
          AND (
                CASE
                    WHEN :shift_name='DAY' THEN COALESCE(day_plan_pcs,0)
                    ELSE COALESCE(night_plan_pcs,0)
                END
              ) > 0
        """

    rows = session.execute(
        text(
            f"""
            SELECT
                run_id,
                plan_date,
                priority_no,
                shipment_id,
                shipment_item_id,
                line_name,
                oven_no,
                tyre_code AS sap_code,
                description,
                day_plan_pcs,
                night_plan_pcs,
                day_plan_weight,
                night_plan_weight,
                allocation_status
            FROM mpps_cavity_plan_rows
            WHERE run_id=:run_id
              AND UPPER(COALESCE(allocation_status,'PLANNED'))='PLANNED'
              {where_shift}
            ORDER BY
                COALESCE(priority_no,2147483647),
                line_name,
                oven_no,
                sequence_no,
                id
            """
        ),
        params,
    ).mappings().all()
    return run_id, [dict(row) for row in rows]


def _oven_shift_rows(
    session,
    report_date: str | date,
    shift_name: str | None = None,
) -> list[dict[str, Any]]:
    if not _table_exists(session, "mpps_oven_plan"):
        return []

    params: dict[str, Any] = {"report_date": str(report_date)}
    where_shift = ""
    if shift_name:
        params["shift_name"] = str(shift_name).strip().upper()
        where_shift = (
            "AND UPPER(COALESCE(shift_name,'')) = UPPER(:shift_name)"
        )

    rows = session.execute(
        text(
            f"""
            SELECT
                COALESCE(NULLIF(shift_name,''),'UNSPECIFIED') AS shift_name,
                COALESCE(oven_code,'') AS oven_no,
                COALESCE(material_code,'') AS sap_code,
                COALESCE(item_description,'') AS description,
                COALESCE(source_note,'') AS source_note,
                COALESCE(planned_qty,0) AS planned_qty,
                COALESCE(planned_weight_kg,0) AS planned_weight_kg,
                CONCAT(
                    COALESCE(source_workbook,''),
                    ' / ',
                    COALESCE(source_sheet,'')
                ) AS source
            FROM mpps_oven_plan
            WHERE plan_date=CAST(:report_date AS DATE)
              {where_shift}
            ORDER BY shift_name, oven_code, material_code, source_row
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


class ShiftDailyReportService:
    @staticmethod
    def ensure_schema() -> None:
        with _get_session() as session:
            session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS mpps_shift_daily_reports (
                        id BIGSERIAL PRIMARY KEY,
                        report_date DATE NOT NULL,
                        shift_name VARCHAR(16) NOT NULL,
                        report_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_by TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(report_date, shift_name)
                    )
                    """
                )
            )
            session.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_mpps_shift_daily_reports_date
                    ON mpps_shift_daily_reports(report_date DESC, shift_name)
                    """
                )
            )

    @staticmethod
    def list_plan_dates(limit: int = 180) -> list[str]:
        """Saved production-plan dates first; imported OVEN dates are fallback/history."""
        bounded = max(1, min(730, int(limit)))
        with _get_session() as session:
            dates: list[date] = []
            if _table_exists(session, "mpps_cavity_plan_runs"):
                dates.extend(
                    row[0]
                    for row in session.execute(
                        text(
                            """
                            SELECT DISTINCT plan_date
                            FROM mpps_cavity_plan_runs
                            WHERE plan_date IS NOT NULL
                              AND UPPER(COALESCE(status,'SAVED')) NOT IN (
                                  'CANCELLED','VOID','REJECTED'
                              )
                            ORDER BY plan_date DESC
                            LIMIT :limit
                            """
                        ),
                        {"limit": bounded},
                    ).all()
                    if row[0] is not None
                )
            if _table_exists(session, "mpps_oven_plan"):
                dates.extend(
                    row[0]
                    for row in session.execute(
                        text(
                            """
                            SELECT DISTINCT plan_date
                            FROM mpps_oven_plan
                            WHERE plan_date IS NOT NULL
                            ORDER BY plan_date DESC
                            LIMIT :limit
                            """
                        ),
                        {"limit": bounded},
                    ).all()
                    if row[0] is not None
                )
        return [
            str(value)
            for value in sorted(set(dates), reverse=True)[:bounded]
        ]

    @staticmethod
    def load_live_plan(report_date: str | date) -> dict[str, Any]:
        """Canonical shift-plan view.

        A saved cavity-level R6 plan is the operational planning authority.
        Imported OVEN allocations are used only when no saved plan exists for
        the requested date, preserving historical/fallback visibility.
        """
        with _get_session() as session:
            run_id, saved = _saved_shift_rows(session, report_date)

            if saved:
                rows: list[dict[str, Any]] = []
                summary_map: dict[str, dict[str, Any]] = {
                    "DAY": {
                        "shift_name": "DAY",
                        "allocation_rows": 0,
                        "planned_qty": 0,
                        "planned_weight_kg": 0.0,
                        "ovens": set(),
                    },
                    "NIGHT": {
                        "shift_name": "NIGHT",
                        "allocation_rows": 0,
                        "planned_qty": 0,
                        "planned_weight_kg": 0.0,
                        "ovens": set(),
                    },
                }
                for row in saved:
                    for shift, qty_key, weight_key in (
                        ("DAY", "day_plan_pcs", "day_plan_weight"),
                        ("NIGHT", "night_plan_pcs", "night_plan_weight"),
                    ):
                        qty = int(row.get(qty_key) or 0)
                        weight = float(row.get(weight_key) or 0)
                        if qty <= 0 and abs(weight) <= 1e-12:
                            continue
                        target = summary_map[shift]
                        target["allocation_rows"] += 1
                        target["planned_qty"] += qty
                        target["planned_weight_kg"] += weight
                        target["ovens"].add(str(row.get("oven_no") or ""))
                        rows.append(
                            {
                                "shift_name": shift,
                                "oven_code": row.get("oven_no"),
                                "material_code": row.get("sap_code"),
                                "item_description": row.get("description"),
                                "planned_qty": qty,
                                "planned_weight_kg": weight,
                                "priority_no": row.get("priority_no"),
                                "source": f"SAVED R6 PLAN / RUN {run_id}",
                            }
                        )
                summary = []
                for shift in ("DAY", "NIGHT"):
                    item = summary_map[shift]
                    if item["allocation_rows"] <= 0:
                        continue
                    summary.append(
                        {
                            "shift_name": shift,
                            "allocation_rows": item["allocation_rows"],
                            "planned_qty": item["planned_qty"],
                            "planned_weight_kg": round(
                                item["planned_weight_kg"], 5
                            ),
                            "ovens": len(
                                {value for value in item["ovens"] if value}
                            ),
                        }
                    )
                return {
                    "plan_date": str(report_date),
                    "authority": "SAVED_R6_CAVITY_PLAN",
                    "run_id": run_id,
                    "summary": summary,
                    "rows": rows,
                }

            imported = _oven_shift_rows(session, report_date)
            summary_map: dict[str, dict[str, Any]] = {}
            rows: list[dict[str, Any]] = []
            for row in imported:
                shift = str(row.get("shift_name") or "UNSPECIFIED").upper()
                bucket = summary_map.setdefault(
                    shift,
                    {
                        "shift_name": shift,
                        "allocation_rows": 0,
                        "planned_qty": 0,
                        "planned_weight_kg": 0.0,
                        "ovens": set(),
                    },
                )
                qty = int(row.get("planned_qty") or 0)
                weight = float(row.get("planned_weight_kg") or 0)
                bucket["allocation_rows"] += 1
                bucket["planned_qty"] += qty
                bucket["planned_weight_kg"] += weight
                bucket["ovens"].add(str(row.get("oven_no") or ""))
                rows.append(
                    {
                        "shift_name": shift,
                        "oven_code": row.get("oven_no"),
                        "material_code": row.get("sap_code"),
                        "item_description": row.get("description"),
                        "planned_qty": qty,
                        "planned_weight_kg": weight,
                        "priority_no": None,
                        "source": row.get("source") or "IMPORTED OVEN FALLBACK",
                    }
                )
            summary = [
                {
                    "shift_name": value["shift_name"],
                    "allocation_rows": value["allocation_rows"],
                    "planned_qty": value["planned_qty"],
                    "planned_weight_kg": round(
                        value["planned_weight_kg"], 5
                    ),
                    "ovens": len(
                        {item for item in value["ovens"] if item}
                    ),
                }
                for value in summary_map.values()
            ]
            return {
                "plan_date": str(report_date),
                "authority": "IMPORTED_OVEN_FALLBACK",
                "run_id": None,
                "summary": sorted(
                    summary, key=lambda row: row["shift_name"]
                ),
                "rows": rows,
            }

    @staticmethod
    def load_targets(report_date: str | date, shift_name: str) -> dict[str, Any]:
        shift = str(shift_name or "").strip().upper()
        if shift not in {"DAY", "NIGHT"}:
            raise ValueError("Shift target must be DAY or NIGHT.")

        with _get_session() as session:
            run_id, saved = _saved_shift_rows(
                session,
                report_date,
                shift,
            )
            if saved:
                qty_key = "day_plan_pcs" if shift == "DAY" else "night_plan_pcs"
                weight_key = (
                    "day_plan_weight" if shift == "DAY" else "night_plan_weight"
                )
                rows = [
                    {
                        "line_name": row.get("line_name"),
                        "planned_qty": row.get(qty_key) or 0,
                        "planned_weight_kg": row.get(weight_key) or 0,
                    }
                    for row in saved
                ]
                result = aggregate_excel_report_targets(rows)
                result["authority"] = "SAVED_R6_CAVITY_PLAN"
                result["run_id"] = run_id
                return result

            database_rows = _oven_shift_rows(
                session,
                report_date,
                shift,
            )

        rows: list[dict[str, Any]] = []
        for row in database_rows:
            source_note = str(row.get("source_note") or "")
            match = re.search(
                r"(?:^|;\s*)line=([^;]*)",
                source_note,
                flags=re.IGNORECASE,
            )
            imported_line = match.group(1).strip() if match else ""
            rows.append(
                {
                    "line_name": imported_line
                    or str(row.get("oven_no") or ""),
                    "planned_qty": row.get("planned_qty") or 0,
                    "planned_weight_kg": row.get("planned_weight_kg") or 0,
                }
            )

        result = aggregate_excel_report_targets(rows)
        result["authority"] = "IMPORTED_OVEN_FALLBACK"
        result["run_id"] = None
        return result

    @staticmethod
    def load_report(report_date: str | date, shift_name: str) -> dict[str, Any]:
        with _get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT report_payload
                    FROM mpps_shift_daily_reports
                    WHERE report_date = CAST(:report_date AS DATE)
                      AND UPPER(shift_name) = UPPER(:shift_name)
                    LIMIT 1
                    """
                ),
                {"report_date": str(report_date), "shift_name": shift_name},
            ).mappings().first()
        return _merge_payload(dict(row["report_payload"]) if row and row["report_payload"] else None)

    @staticmethod
    def save_report(
        report_date: str | date,
        shift_name: str,
        payload: dict[str, Any],
        updated_by: str = "",
    ) -> None:
        clean_payload = _merge_payload(payload)
        with _get_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_shift_daily_reports (
                        report_date,
                        shift_name,
                        report_payload,
                        updated_by,
                        updated_at
                    )
                    VALUES (
                        CAST(:report_date AS DATE),
                        UPPER(:shift_name),
                        CAST(:report_payload AS JSONB),
                        :updated_by,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (report_date, shift_name)
                    DO UPDATE SET
                        report_payload = EXCLUDED.report_payload,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "report_date": str(report_date),
                    "shift_name": shift_name.upper(),
                    "report_payload": json.dumps(clean_payload),
                    "updated_by": updated_by or "",
                },
            )


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: Any, decimals: int = 2, blank_zero: bool = False) -> str:
    number = _number(value)
    if blank_zero and abs(number) < 1e-12:
        return ""
    if decimals == 0:
        return f"{int(round(number)):,}"
    return f"{number:,.{decimals}f}"


def _safe(value: Any) -> str:
    return escape(str(value or ""))


def build_shift_report_html(
    report_date: str,
    shift_name: str,
    target_summary: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    payload = _merge_payload(deepcopy(payload))
    shift = shift_name.upper()
    target_lines = target_summary.get("lines", {})
    tyre_actuals = payload["tyre_actuals"]

    target_kg_total = sum(
        _number(target_lines.get(line, {}).get("target_kg"))
        for line in TYRE_LINE_ORDER
    )
    target_pcs_total = sum(
        _number(target_lines.get(line, {}).get("target_pcs"))
        for line in TYRE_LINE_ORDER
    )
    actual_kg_total = sum(
        _number(tyre_actuals.get(line, {}).get("kg"))
        for line in TYRE_LINE_ORDER
    )
    actual_pcs_total = sum(
        _number(tyre_actuals.get(line, {}).get("pcs"))
        for line in TYRE_LINE_ORDER
    )
    man_hours = _number(payload.get("used_man_hours"))
    kg_per_man_hour = actual_kg_total / man_hours if man_hours else 0.0

    tyre_rows = []
    for line in TYRE_LINE_ORDER:
        target = target_lines.get(line, {})
        actual = tyre_actuals.get(line, {})
        tyre_rows.append(
            "<tr>"
            f"<td>{_safe(line)}</td>"
            f"<td class='num'>{_fmt(target.get('target_kg'), 2)}</td>"
            f"<td class='num'>{_fmt(actual.get('kg'), 2, True)}</td>"
            f"<td class='num'>{_fmt(target.get('target_pcs'), 0)}</td>"
            f"<td class='num'>{_fmt(actual.get('pcs'), 0, True)}</td>"
            "</tr>"
        )
    tyre_rows.append(
        "<tr class='total'>"
        "<td>Total</td>"
        f"<td class='num'>{_fmt(target_kg_total, 2)}</td>"
        f"<td class='num'>{_fmt(actual_kg_total, 2, True)}</td>"
        f"<td class='num'>{_fmt(target_pcs_total, 0)}</td>"
        f"<td class='num'>{_fmt(actual_pcs_total, 0, True)}</td>"
        "</tr>"
    )

    compound_rows = []
    compound_target_total = 0.0
    compound_actual_total = 0.0
    for row in payload["compound_rows"]:
        target = _number(row.get("target"))
        actual = _number(row.get("actual"))
        compound_target_total += target
        compound_actual_total += actual
        achievement = actual / target * 100 if target else 0.0
        compound_rows.append(
            "<tr>"
            f"<td>{_safe(row.get('compound_type'))}</td>"
            f"<td class='num'>{_fmt(target, 2, True)}</td>"
            f"<td class='num'>{_fmt(actual, 2, True)}</td>"
            f"<td class='num'>{_fmt(achievement, 1, True)}{'%' if target else ''}</td>"
            "</tr>"
        )
    compound_rows.append(
        "<tr class='total'><td>Total</td>"
        f"<td class='num'>{_fmt(compound_target_total, 2, True)}</td>"
        f"<td class='num'>{_fmt(compound_actual_total, 2, True)}</td>"
        f"<td class='num'>{_fmt((compound_actual_total / compound_target_total * 100) if compound_target_total else 0, 1, True)}{'%' if compound_target_total else ''}</td></tr>"
    )

    scrap_tyre_rows = "".join(
        "<tr>"
        f"<td>{_safe(row.get('tyre_size'))}</td>"
        f"<td class='num'>{_safe(row.get('pcs'))}</td>"
        f"<td>{_safe(row.get('defect'))}</td>"
        f"<td>{_safe(row.get('operator'))}</td>"
        "</tr>"
        for row in payload["scrap_tyre_rows"]
    )
    scrap_compound_rows = "".join(
        "<tr>"
        f"<td>{_safe(row.get('compound_type'))}</td>"
        f"<td class='num'>{_safe(row.get('weight'))}</td>"
        f"<td>{_safe(row.get('defect'))}</td>"
        f"<td>{_safe(row.get('operator'))}</td>"
        "</tr>"
        for row in payload["scrap_compound_rows"]
    )

    loss_rows = []
    for reason in LOSS_REASONS:
        values = payload["loss_reasons"].get(reason, {})
        loss_rows.append(
            "<tr>"
            f"<td>{_safe(reason)}</td>"
            + "".join(
                f"<td class='num'>{_safe(values.get(column))}</td>"
                for column in LOSS_COLUMNS
            )
            + "</tr>"
        )

    notes = _safe(payload.get("production_notes")).replace("\n", "<br>") or "&nbsp;<br>&nbsp;<br>&nbsp;"
    supervisor = _safe(payload.get("supervisor_name"))

    unmapped = target_summary.get("unmapped") or []
    reconciliation_note = ""
    if unmapped:
        items = ", ".join(
            f"{_safe(row.get('line_name'))} ({_fmt(row.get('planned_qty'), 0)} pcs)"
            for row in unmapped
        )
        reconciliation_note = (
            "<div class='warning'><b>Unmapped live plan lines:</b> " + items + "</div>"
        )

    return f"""
    <html>
    <head>
    <style>
        @page {{ size: A4 portrait; margin: 8mm; }}
        body {{ font-family: Arial, Helvetica, sans-serif; font-size: 8.2pt; color: #000; }}
        table {{ border-collapse: collapse; width: 100%; }}
        td, th {{ border: 1px solid #000; padding: 3px 4px; vertical-align: middle; }}
        th {{ font-weight: 700; text-align: center; background: #f1f1f1; }}
        .header td {{ font-size: 11pt; font-weight: 700; text-align: center; padding: 5px; }}
        .meta td {{ border-top: 0; padding: 4px; }}
        .section {{ font-weight: 700; background: #e9e9e9; }}
        .num {{ text-align: right; }}
        .total td {{ font-weight: 700; }}
        .two-col > tbody > tr > td {{ width: 50%; vertical-align: top; border: 0; padding: 0 4px 0 0; }}
        .two-col > tbody > tr > td:last-child {{ padding: 0 0 0 4px; }}
        .spacer {{ height: 4px; }}
        .notes {{ min-height: 55px; height: 55px; vertical-align: top; }}
        .signature {{ border: 0; text-align: center; padding-top: 18px; }}
        .footer td {{ font-size: 7.2pt; text-align: center; }}
        .page-break {{ page-break-after: always; }}
        .warning {{ border: 1px solid #000; padding: 4px; margin: 5px 0; font-size: 7pt; }}
        .loss th, .loss td {{ font-size: 7pt; padding: 2px 3px; }}
    </style>
    </head>
    <body>
      <table class='header'>
        <tr><td style='width:32%'>LAUGFS Corporation (Rubber) Ltd.</td><td>Daily Production Summary Report</td></tr>
      </table>
      <table class='meta'>
        <tr><td style='width:50%'><b>Date:</b> {_safe(report_date)}</td><td><b>Shift:</b> {_safe(shift)}</td></tr>
      </table>
      {reconciliation_note}
      <table class='two-col'><tr>
        <td>
          <table>
            <tr><td class='section'>Production performance</td></tr>
            <tr><td><b>Details For SAP</b></td></tr>
            <tr><td class='notes'>{notes}</td></tr>
          </table>
          <div class='spacer'></div>
          <table>
            <tr><td class='section' colspan='4'>2nd Stage Compound Production</td></tr>
            <tr><th>Compound Type</th><th>Target</th><th>Actual</th><th>Achievement (%)</th></tr>
            {''.join(compound_rows)}
          </table>
          <div class='spacer'></div>
          <table>
            <tr><td class='section' colspan='4'>Quality Performance</td></tr>
            <tr><td class='section' colspan='4'>Scrap Tyres</td></tr>
            <tr><th>Tyre Size</th><th>PCS</th><th>Defect</th><th>Responsible Operator</th></tr>
            {scrap_tyre_rows}
          </table>
          <div class='spacer'></div>
          <table>
            <tr><td class='section' colspan='4'>Scrap Compound</td></tr>
            <tr><th>Compound Type</th><th>Weights</th><th>Defect</th><th>Responsible Operator</th></tr>
            {scrap_compound_rows}
          </table>
          <div class='spacer'></div>
          <table>
            <tr><td><b>Used man hours</b></td><td class='num'>{_safe(payload.get('used_man_hours'))}</td></tr>
            <tr><td><b>Production (Kg)</b></td><td class='num'>{_fmt(actual_kg_total, 2, True)}</td></tr>
            <tr><td><b>Man hours (Kg)</b></td><td class='num'>{_fmt(kg_per_man_hour, 2, True)}</td></tr>
          </table>
        </td>
        <td>
          <table>
            <tr><td class='section' colspan='2'>Supervisor Name</td></tr>
            <tr><td colspan='2'>{supervisor or '&nbsp;'}</td></tr>
          </table>
          <div class='spacer'></div>
          <table>
            <tr><td class='section' colspan='5'>Tyre production</td></tr>
            <tr><th>Line No</th><th>Target (Kg)</th><th>Actual (Kg)</th><th>Target (pcs)</th><th>Actual (Pcs)</th></tr>
            {''.join(tyre_rows)}
          </table>
          <div class='signature'>Supervisor:- ............................................................</div>
        </td>
      </tr></table>
      <table class='footer' style='margin-top:6px'>
        <tr><td>Doc #: LR-ST-PP-014</td><td>Issue #: 09</td><td>Issue Date: 02.09.2025</td><td>Page: 01 of 02</td></tr>
      </table>

      <div class='page-break'></div>

      <table class='header'>
        <tr><td style='width:32%'>LAUGFS Corporation (Rubber) Ltd.</td><td>Daily Production Summary Report</td></tr>
      </table>
      <table class='meta'>
        <tr><td style='width:50%'><b>Date:</b> {_safe(report_date)}</td><td><b>Shift:</b> {_safe(shift)}</td></tr>
      </table>
      <table class='loss'>
        <tr><th rowspan='2'>Loss Reasons</th><th colspan='8'>Line</th></tr>
        <tr>
          <th colspan='2'>200 Line</th><th colspan='2'>600/400, Super Solid</th><th colspan='2'>400 Line</th><th colspan='2'>800 Line</th>
        </tr>
        <tr><th></th><th>KG</th><th>PCS</th><th>KG</th><th>PCS</th><th>KG</th><th>PCS</th><th>KG</th><th>PCS</th></tr>
        {''.join(loss_rows)}
      </table>
      <div class='signature'>Supervisor:- ............................................................</div>
      <table class='footer' style='margin-top:6px'>
        <tr><td>Doc #: LR-ST-PP-014</td><td>Issue #: 09</td><td>Issue Date: 02.09.2025</td><td>Page: 02 of 02</td></tr>
      </table>
    </body>
    </html>
    """
