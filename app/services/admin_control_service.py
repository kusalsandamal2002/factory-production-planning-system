from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = Path.home() / "Downloads"
IMPORT_ARCHIVE = PROJECT_ROOT / "data_sources" / "import_archive"


DEFAULT_PLANNING_RULES = {
    "planning_horizon_days": "30",
    "packing_dispatch_buffer_days": "1",
    "safety_stock_pct": "0",
    "auto_replan_enabled": "true",
    "allow_overtime": "false",
    "replan_debounce_seconds": "5",
    "priority_policy": "TARGET_DATE_FIRST",
}


def _table_exists(conn, table_name: str) -> bool:
    try:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema='public'
                          AND table_name=:table_name
                    )
                    """
                ),
                {"table_name": table_name},
            ).scalar()
        )
    except Exception:
        return False


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    try:
        return bool(
            conn.execute(
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
                {
                    "table_name": table_name,
                    "column_name": column_name,
                },
            ).scalar()
        )
    except Exception:
        return False


def _latest_backup() -> tuple[str, str]:
    patterns = (
        "MPPS_PRE_*_DB_*.dump",
        "MPPS_FULL_WORKING_BACKUP_*.zip",
        "MPPS_PRE_*.zip",
    )
    files: list[Path] = []
    try:
        for pattern in patterns:
            files.extend(DOWNLOADS.glob(pattern))
    except Exception:
        return "Not available", ""

    files = [path for path in files if path.is_file()]
    if not files:
        return "Not available", ""

    latest = max(files, key=lambda path: path.stat().st_mtime)
    stamp = datetime.fromtimestamp(latest.stat().st_mtime)
    return stamp.strftime("%Y-%m-%d %H:%M"), str(latest)


def _latest_excel_archive() -> tuple[str, str, int]:
    try:
        files = [
            path
            for path in IMPORT_ARCHIVE.glob("*.xlsx")
            if path.is_file()
        ]
    except Exception:
        return "Not available", "", 0

    if not files:
        return "Not available", "", 0

    latest = max(files, key=lambda path: path.stat().st_mtime)
    stamp = datetime.fromtimestamp(latest.stat().st_mtime)
    return stamp.strftime("%Y-%m-%d %H:%M"), latest.name, len(files)


def _latest_source_from_db(conn) -> dict[str, Any]:
    candidates = (
        ("mpps_excel_import_runs", "plan_date", "workbook_name"),
        ("excel_import_runs", "plan_date", "workbook_name"),
        ("mpps_oven_plan", "plan_date", None),
        ("mpps_tyre_workbook_observation", "plan_date", "source_workbook"),
    )
    for table_name, date_column, name_column in candidates:
        if not _table_exists(conn, table_name):
            continue
        if not _column_exists(conn, table_name, date_column):
            continue

        if name_column and _column_exists(conn, table_name, name_column):
            try:
                row = conn.execute(
                    text(
                        f"""
                        SELECT {date_column} AS source_date,
                               {name_column} AS source_name
                        FROM {table_name}
                        WHERE {date_column} IS NOT NULL
                        ORDER BY {date_column} DESC
                        LIMIT 1
                        """
                    )
                ).mappings().first()
            except Exception:
                row = None
        else:
            try:
                row = conn.execute(
                    text(
                        f"""
                        SELECT MAX({date_column}) AS source_date
                        FROM {table_name}
                        """
                    )
                ).mappings().first()
            except Exception:
                row = None

        if row and row.get("source_date") is not None:
            return {
                "source_date": row.get("source_date"),
                "source_name": row.get("source_name") or table_name,
            }

    return {
        "source_date": None,
        "source_name": "",
    }


def _count_quality_issues(conn) -> int | None:
    candidates = (
        "excel_import_issues",
        "mpps_excel_import_issues",
        "data_quality_warnings",
        "mpps_data_quality_issues",
    )
    for table_name in candidates:
        if not _table_exists(conn, table_name):
            continue
        try:
            return int(
                conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar()
                or 0
            )
        except Exception:
            continue
    return None


def load_admin_health_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {
        "database": "Unavailable",
        "database_name": "",
        "latest_source_date": None,
        "latest_source_name": "",
        "quality_issues": None,
        "last_backup": "Not available",
        "last_backup_path": "",
        "last_excel_archive": "Not available",
        "last_excel_name": "",
        "excel_archive_count": 0,
    }

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
            result["database"] = "Connected"
            result["database_name"] = str(engine.url.database or "")
            result.update(_latest_source_from_db(conn))
            result["quality_issues"] = _count_quality_issues(conn)
    except Exception as exc:
        result["database"] = "Unavailable"
        result["database_error"] = str(exc)

    backup_stamp, backup_path = _latest_backup()
    result["last_backup"] = backup_stamp
    result["last_backup_path"] = backup_path

    excel_stamp, excel_name, excel_count = _latest_excel_archive()
    result["last_excel_archive"] = excel_stamp
    result["last_excel_name"] = excel_name
    result["excel_archive_count"] = excel_count

    return result


def load_planning_rules() -> dict[str, str]:
    rules = dict(DEFAULT_PLANNING_RULES)
    try:
        with engine.connect() as conn:
            if not _table_exists(conn, "mpps_system_settings"):
                return rules
            rows = conn.execute(
                text(
                    """
                    SELECT setting_key, setting_value
                    FROM mpps_system_settings
                    WHERE category='PLANNING'
                    """
                )
            ).mappings().all()
    except Exception:
        return rules

    for row in rows:
        key = str(row.get("setting_key") or "")
        if key in rules:
            rules[key] = str(row.get("setting_value") or "")
    return rules


def save_planning_rules(rules: dict[str, Any]) -> dict[str, str]:
    cleaned = {
        "planning_horizon_days": str(
            max(1, min(365, int(rules.get("planning_horizon_days", 30))))
        ),
        "packing_dispatch_buffer_days": str(
            max(0, min(30, int(rules.get("packing_dispatch_buffer_days", 1))))
        ),
        "safety_stock_pct": str(
            max(0.0, min(100.0, float(rules.get("safety_stock_pct", 0))))
        ),
        "auto_replan_enabled": (
            "true" if bool(rules.get("auto_replan_enabled", True)) else "false"
        ),
        "allow_overtime": (
            "true" if bool(rules.get("allow_overtime", False)) else "false"
        ),
        "replan_debounce_seconds": str(
            max(1, min(120, int(rules.get("replan_debounce_seconds", 5))))
        ),
        "priority_policy": str(
            rules.get("priority_policy") or "TARGET_DATE_FIRST"
        ).strip().upper(),
    }

    with engine.begin() as conn:
        for key, value in cleaned.items():
            conn.execute(
                text(
                    """
                    INSERT INTO mpps_system_settings (
                        category,
                        setting_key,
                        setting_value,
                        updated_at
                    )
                    VALUES (
                        'PLANNING',
                        :setting_key,
                        :setting_value,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (category, setting_key)
                    DO UPDATE SET
                        setting_value=EXCLUDED.setting_value,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "setting_key": key,
                    "setting_value": value,
                },
            )
    return cleaned


def load_calendar_month(year: int, month: int) -> list[dict[str, Any]]:
    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise ValueError("Invalid month")

    first = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    holiday_date,
                    holiday_name,
                    holiday_type,
                    is_working_day_override
                FROM factory_holidays
                WHERE holiday_date >= :first_date
                  AND holiday_date < :next_month
                ORDER BY holiday_date
                """
            ),
            {
                "first_date": first,
                "next_month": next_month,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def set_calendar_day(
    selected_date: date,
    mode: str,
    name: str = "",
) -> dict[str, Any]:
    mode = str(mode or "").strip().upper()
    if mode not in {"HOLIDAY", "WORKING", "CLEAR"}:
        raise ValueError("Unsupported calendar mode")

    with engine.begin() as conn:
        if mode == "CLEAR":
            conn.execute(
                text(
                    """
                    DELETE FROM factory_holidays
                    WHERE holiday_date=:holiday_date
                    """
                ),
                {"holiday_date": selected_date},
            )
        else:
            is_working = mode == "WORKING"
            holiday_type = (
                "SPECIAL_WORKING_DAY"
                if is_working
                else "FACTORY_HOLIDAY"
            )
            holiday_name = (
                name.strip()
                if str(name or "").strip()
                else (
                    "Manager Approved Special Working Day"
                    if is_working
                    else "Factory Holiday"
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO factory_holidays (
                        holiday_date,
                        holiday_name,
                        holiday_type,
                        is_working_day_override,
                        updated_at
                    )
                    VALUES (
                        :holiday_date,
                        :holiday_name,
                        :holiday_type,
                        :is_working_day_override,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (holiday_date)
                    DO UPDATE SET
                        holiday_name=EXCLUDED.holiday_name,
                        holiday_type=EXCLUDED.holiday_type,
                        is_working_day_override=EXCLUDED.is_working_day_override,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "holiday_date": selected_date,
                    "holiday_name": holiday_name,
                    "holiday_type": holiday_type,
                    "is_working_day_override": is_working,
                },
            )

    return {
        "date": selected_date,
        "mode": mode,
    }


def load_data_sources_snapshot() -> dict[str, Any]:
    health = load_admin_health_snapshot()
    return {
        "postgresql_status": health.get("database"),
        "database_name": health.get("database_name"),
        "latest_source_date": health.get("latest_source_date"),
        "latest_source_name": health.get("latest_source_name"),
        "last_excel_archive": health.get("last_excel_archive"),
        "last_excel_name": health.get("last_excel_name"),
        "excel_archive_count": health.get("excel_archive_count"),
        "future_integrations": [
            ("ERP", "Not configured"),
            ("WMS", "Not configured"),
            ("MES", "Not configured"),
            ("Barcode / QR", "Not configured"),
            ("Machine / PLC", "Not configured"),
        ],
    }
