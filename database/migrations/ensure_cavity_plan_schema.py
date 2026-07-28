from __future__ import annotations

from app.database import get_session
from app.services.cavity_daily_plan_service import (
    ensure_cavity_plan_schema,
)


def main() -> None:
    with get_session() as session:
        ensure_cavity_plan_schema(session)

    print("Cavity-level production planning schema is ready.")
    print("Created/verified:")
    print("- mpps_cavity_plan_runs")
    print("- mpps_cavity_plan_rows")


if __name__ == "__main__":
    main()
