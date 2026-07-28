from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.database import get_session
from app.services.cavity_daily_plan_service import (
    CavityPlanSettings,
    generate_cavity_plan,
)


def main() -> None:
    settings = CavityPlanSettings(
        planning_date=date.today(),
        day_shift_minutes=720,
        night_shift_minutes=720,
        changeover_minutes=0,
    )

    with get_session() as session:
        database_cavities = int(
            session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM production_line_cavities
                    """
                )
            ).scalar_one()
            or 0
        )

        rows, summary, blocked = generate_cavity_plan(
            session,
            settings=settings,
        )

    displayed_cavities = {
        row.cavity_id for row in rows
    }
    allowed_statuses = {
        "ASSIGNED",
        "AVAILABLE / FREE",
        "CURRENTLY ASSIGNED",
        "BREAKDOWN",
    }
    invalid_statuses = sorted(
        {
            row.oven_status
            for row in rows
            if row.oven_status not in allowed_statuses
        }
    )

    if len(displayed_cavities) != database_cavities:
        raise SystemExit(
            "FAILED: page does not cover every cavity. "
            f"Database={database_cavities}, "
            f"Displayed={len(displayed_cavities)}"
        )

    if invalid_statuses:
        raise SystemExit(
            "FAILED: invalid oven statuses: "
            f"{invalid_statuses}"
        )

    if len(rows) < database_cavities:
        raise SystemExit(
            "FAILED: display row count is smaller than "
            "the cavity count."
        )

    print("CAVITY PLANNING SMOKE TEST PASSED")
    print("Database cavities:", database_cavities)
    print("Displayed unique cavities:", len(displayed_cavities))
    print("Display rows:", len(rows))
    print("Production required:", summary.production_required_qty)
    print("Today planned:", summary.today_planned_qty)
    print("Next day planned:", summary.next_day_planned_qty)
    print("Remaining balance:", summary.remaining_balance_qty)
    print("Blocked items:", len(blocked))
    print("Plan status:", summary.status_text)

    repeated = {}
    for row in rows:
        repeated.setdefault(row.oven_no, 0)
        repeated[row.oven_no] += 1

    multi_rows = sorted(
        (
            oven,
            count,
        )
        for oven, count in repeated.items()
        if count > 1
    )
    print(
        "Ovens with multiple same-day allocation rows:",
        len(multi_rows),
    )
    for oven, count in multi_rows[:10]:
        print(f"  {oven}: {count} rows")


if __name__ == "__main__":
    main()
