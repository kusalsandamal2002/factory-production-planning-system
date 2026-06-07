from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text


@dataclass
class HolidayInfo:
    holiday_date: date
    holiday_name: str
    holiday_type: str
    is_working_day_override: bool = False


def ensure_holiday_table(session) -> None:
    """
    Creates the factory holiday table if it does not exist.

    Important:
    - Factory works 24/7.
    - Sunday is NOT treated as a holiday by default.
    - Only manually marked factory holidays block production.
    - Special working day can override a manually marked holiday.
    """
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS factory_holidays (
                id SERIAL PRIMARY KEY,
                holiday_date DATE NOT NULL UNIQUE,
                holiday_name VARCHAR(200) NOT NULL,
                holiday_type VARCHAR(50) NOT NULL DEFAULT 'FACTORY_HOLIDAY',
                is_working_day_override BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    session.commit()


def _to_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()

    raise ValueError(f"Invalid date value: {value}")


def _row_to_holiday_info(row) -> HolidayInfo:
    return HolidayInfo(
        holiday_date=_to_date(row.holiday_date),
        holiday_name=row.holiday_name,
        holiday_type=row.holiday_type,
        is_working_day_override=bool(row.is_working_day_override),
    )


def get_all_holidays(session) -> dict[date, HolidayInfo]:
    """
    Returns only manually saved calendar marks.

    Sunday is NOT auto-added as a holiday.
    """
    ensure_holiday_table(session)

    result = session.execute(
        text(
            """
            SELECT
                holiday_date,
                holiday_name,
                holiday_type,
                is_working_day_override
            FROM factory_holidays
            ORDER BY holiday_date ASC;
            """
        )
    ).all()

    holidays: dict[date, HolidayInfo] = {}

    for row in result:
        info = _row_to_holiday_info(row)
        holidays[info.holiday_date] = info

    return holidays


def get_holiday_info_for_date(session, selected_date: date) -> Optional[HolidayInfo]:
    """
    Returns holiday info only if the selected date was manually marked.

    Factory works 24/7, so Sunday returns None unless manager manually marks it.
    """
    ensure_holiday_table(session)

    selected_date = _to_date(selected_date)

    row = session.execute(
        text(
            """
            SELECT
                holiday_date,
                holiday_name,
                holiday_type,
                is_working_day_override
            FROM factory_holidays
            WHERE holiday_date = :holiday_date
            LIMIT 1;
            """
        ),
        {"holiday_date": selected_date},
    ).first()

    if row is None:
        return None

    return _row_to_holiday_info(row)


def is_non_working_day(session, selected_date: date) -> bool:
    """
    True only when manager manually marked the date as a factory holiday.

    Sunday is working day because factory works 24/7.
    Special working day override means production is allowed.
    """
    holiday_info = get_holiday_info_for_date(session, selected_date)

    if holiday_info is None:
        return False

    if holiday_info.is_working_day_override:
        return False

    return holiday_info.holiday_type == "FACTORY_HOLIDAY"


def mark_factory_holiday(
    session,
    selected_date: date,
    holiday_name: str = "Factory Holiday",
) -> None:
    """
    Marks selected date as a factory holiday.
    Production should not be planned on this date unless manager later overrides it.
    """
    ensure_holiday_table(session)

    selected_date = _to_date(selected_date)
    holiday_name = holiday_name.strip() or "Factory Holiday"

    session.execute(
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
                'FACTORY_HOLIDAY',
                FALSE,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (holiday_date)
            DO UPDATE SET
                holiday_name = EXCLUDED.holiday_name,
                holiday_type = 'FACTORY_HOLIDAY',
                is_working_day_override = FALSE,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {
            "holiday_date": selected_date,
            "holiday_name": holiday_name,
        },
    )
    session.commit()


def mark_working_day_override(
    session,
    selected_date: date,
    holiday_name: str = "Manager Approved Working Day",
) -> None:
    """
    Marks selected date as a working day override.

    This is useful when a date was previously marked as a factory holiday,
    but management approves production for that date.
    """
    ensure_holiday_table(session)

    selected_date = _to_date(selected_date)
    holiday_name = holiday_name.strip() or "Manager Approved Working Day"

    session.execute(
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
                'SPECIAL_WORKING_DAY',
                TRUE,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (holiday_date)
            DO UPDATE SET
                holiday_name = EXCLUDED.holiday_name,
                holiday_type = 'SPECIAL_WORKING_DAY',
                is_working_day_override = TRUE,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {
            "holiday_date": selected_date,
            "holiday_name": holiday_name,
        },
    )
    session.commit()


def remove_holiday_mark(session, selected_date: date) -> None:
    """
    Removes manual holiday / working day mark.

    After removing mark:
    - Date becomes normal working day.
    - Sunday also remains normal working day because factory is 24/7.
    """
    ensure_holiday_table(session)

    selected_date = _to_date(selected_date)

    session.execute(
        text(
            """
            DELETE FROM factory_holidays
            WHERE holiday_date = :holiday_date;
            """
        ),
        {"holiday_date": selected_date},
    )
    session.commit()