from __future__ import annotations

import argparse
from datetime import date
from time import perf_counter

from app.database import get_session
from app.services.cavity_daily_plan_service import (
    CavityPlanSettings,
    generate_cavity_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Planning date YYYY-MM-DD",
    )
    parser.add_argument(
        "--shift",
        choices=["ALL", "DAY", "NIGHT"],
        default="ALL",
    )
    args = parser.parse_args()

    planning_date = date.fromisoformat(args.date)
    day_minutes = 720 if args.shift in {"ALL", "DAY"} else 0
    night_minutes = 720 if args.shift in {"ALL", "NIGHT"} else 0

    last_bucket = -1

    def progress(percent: int, message: str) -> None:
        nonlocal last_bucket
        bucket = percent // 5
        if bucket != last_bucket or percent >= 100:
            last_bucket = bucket
            print(f"[{percent:3d}%] {message}", flush=True)

    started = perf_counter()
    with get_session() as session:
        rows, summary, blocked = generate_cavity_plan(
            session,
            settings=CavityPlanSettings(
                planning_date=planning_date,
                day_shift_minutes=day_minutes,
                night_shift_minutes=night_minutes,
                changeover_minutes=0,
            ),
            progress_callback=progress,
        )
    elapsed = perf_counter() - started

    print()
    print("LIVE PRODUCTION PLANNER V7.2 BENCHMARK COMPLETED")
    print(f"elapsed_seconds: {elapsed:.3f}")
    print(f"display_rows: {len(rows)}")
    print(f"blocked_items: {len(blocked)}")
    print(f"production_required_qty: {summary.production_required_qty}")
    print(f"today_planned_qty: {summary.today_planned_qty}")
    print(f"next_day_planned_qty: {summary.next_day_planned_qty}")
    print(f"status: {summary.status_text}")
    print("No plan was saved by this benchmark.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
