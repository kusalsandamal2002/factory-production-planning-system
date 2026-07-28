from __future__ import annotations

import inspect

from app.ui.mold_master_page import (
    MoldMasterPage,
    MoldRepository,
)


def main() -> None:
    source = inspect.getsource(
        MoldMasterPage
    )

    assert "AUTO_REFRESH_MS = 5000" in source
    assert "Plan Reserved Today" in source
    assert "Future Peak" in source
    assert "Live Production Molds" in source

    repository = MoldRepository()
    stats = repository.stats()
    rows = repository.list_molds(
        "10.00-20 SM"
    )

    required_stats = {
        "total_keys",
        "total_molds",
        "live_production_molds",
        "plan_reserved_today",
        "breakdown_molds",
        "available_molds",
    }
    assert required_stats.issubset(
        stats.keys()
    )

    if rows:
        row = rows[0]
        required_row = {
            "mold_count",
            "manual_production_mold_count",
            "plan_reserved_today",
            "manual_reserved_mold_count",
            "breakdown_mold_count",
            "live_production_mold_count",
            "future_peak_reserved",
            "available_mold_count",
        }
        assert required_row.issubset(
            row.keys()
        )

        expected_available = max(
            0,
            int(row["mold_count"])
            - int(
                row[
                    "manual_production_mold_count"
                ]
            )
            - int(
                row[
                    "plan_reserved_today"
                ]
            )
            - int(
                row[
                    "manual_reserved_mold_count"
                ]
            )
            - int(
                row[
                    "breakdown_mold_count"
                ]
            ),
        )
        assert (
            int(row["available_mold_count"])
            == expected_available
        )

        print(
            "Sample 10.00-20 SM:",
            {
                "total": row["mold_count"],
                "manual_in_use": (
                    row[
                        "manual_production_mold_count"
                    ]
                ),
                "plan_reserved_today": (
                    row["plan_reserved_today"]
                ),
                "live_production": (
                    row[
                        "live_production_mold_count"
                    ]
                ),
                "breakdown": (
                    row["breakdown_mold_count"]
                ),
                "available_now": (
                    row["available_mold_count"]
                ),
                "future_peak": (
                    row["future_peak_reserved"]
                ),
            },
        )

    print(
        "MOLD MASTER LIVE PLANNING SMOKE TEST PASSED"
    )


if __name__ == "__main__":
    main()
