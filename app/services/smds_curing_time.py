from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.smds_schema import ensure_smds_table


def curing_cycle_to_minutes(value: Any) -> Decimal:
    """Convert SMDS curing cycle values to numeric minutes for planning analysis.

    Supported examples:
    - 8h -> 480
    - 7h 30m -> 450
    - 265 -> 265
    - 8 -> 480, because small positive plain numbers are treated as hours.
    """
    if value is None:
        return Decimal("0")

    if isinstance(value, Decimal):
        numeric = value
        if Decimal("0") < numeric <= Decimal("24"):
            return numeric * Decimal("60")
        return numeric

    if isinstance(value, (int, float)):
        numeric = Decimal(str(value))
        if Decimal("0") < numeric <= Decimal("24"):
            return numeric * Decimal("60")
        return numeric

    text_value = str(value or "").strip().lower()

    if not text_value or text_value in {"-", "nan", "none", "null"}:
        return Decimal("0")

    hours = Decimal("0")
    minutes = Decimal("0")

    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*h", text_value)
    minute_match = re.search(r"(\d+(?:\.\d+)?)\s*m", text_value)

    if hour_match or minute_match:
        if hour_match:
            hours = Decimal(hour_match.group(1))
        if minute_match:
            minutes = Decimal(minute_match.group(1))
        return (hours * Decimal("60")) + minutes

    number_match = re.search(r"(\d+(?:\.\d+)?)", text_value)
    if not number_match:
        return Decimal("0")

    try:
        numeric = Decimal(number_match.group(1))
    except InvalidOperation:
        return Decimal("0")

    if Decimal("0") < numeric <= Decimal("24"):
        return numeric * Decimal("60")

    return numeric


def _clean_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f").rstrip("0").rstrip(".")


def minutes_to_duration_text(minutes_value: Any) -> str:
    """Convert numeric minutes to a clear operator-facing duration string."""
    try:
        minutes_decimal = Decimal(str(minutes_value or 0))
    except (InvalidOperation, ValueError):
        return "-"

    if minutes_decimal <= 0:
        return "-"

    whole_minutes = int(minutes_decimal)
    fractional = minutes_decimal - Decimal(whole_minutes)
    hours = whole_minutes // 60
    minutes = whole_minutes % 60

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or fractional:
        minute_value = Decimal(minutes) + fractional
        parts.append(f"{_clean_decimal(minute_value)}m")

    return " ".join(parts) if parts else f"{_clean_decimal(minutes_decimal)}m"


def minutes_to_display_text(minutes_value: Any) -> str:
    """User-facing text while preserving numeric minutes for calculations."""
    try:
        minutes_decimal = Decimal(str(minutes_value or 0))
    except (InvalidOperation, ValueError):
        return "-"

    if minutes_decimal <= 0:
        return "-"

    duration = minutes_to_duration_text(minutes_decimal)
    return f"{duration} ({_clean_decimal(minutes_decimal)} min)"


def ensure_smds_curing_time_columns() -> None:
    ensure_smds_table()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS normal_curing_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS normal_curing_time_text VARCHAR(64) NOT NULL DEFAULT ''"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_smds_normal_curing_minutes ON smds (normal_curing_minutes)"))


def refresh_smds_curing_time_columns() -> int:
    """Backfill SMDS derived curing columns from smds.curing_cycle.

    normal_curing_minutes stays numeric for analysis.
    normal_curing_time_text stores readable text generated from the numeric value.
    """
    ensure_smds_curing_time_columns()

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, curing_cycle FROM smds ORDER BY id")).mappings().all()

        updates = []
        for row in rows:
            minutes = curing_cycle_to_minutes(row.get("curing_cycle"))
            updates.append(
                {
                    "id": row["id"],
                    "normal_curing_minutes": minutes,
                    "normal_curing_time_text": minutes_to_duration_text(minutes),
                }
            )

        if updates:
            conn.execute(
                text("""
                    UPDATE smds
                    SET normal_curing_minutes = :normal_curing_minutes,
                        normal_curing_time_text = :normal_curing_time_text,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                updates,
            )

    return len(updates)

# MPPS V32 CURING SCHEMA ENSURE ONCE
import threading as _v32_curing_threading

_v32_original_ensure_smds_curing_time_columns = ensure_smds_curing_time_columns
_v32_curing_lock = _v32_curing_threading.Lock()
_v32_curing_schema_ready = False


def ensure_smds_curing_time_columns() -> None:
    global _v32_curing_schema_ready

    if _v32_curing_schema_ready:
        return

    with _v32_curing_lock:
        if _v32_curing_schema_ready:
            return

        _v32_original_ensure_smds_curing_time_columns()
        _v32_curing_schema_ready = True
