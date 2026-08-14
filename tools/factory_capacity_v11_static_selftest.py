from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.factory_resource_intelligence_service import (
    FactoryResourceIntelligenceService,
    _stable_max,
)
from app.services.advanced_capacity_ml import AdvancedCapacityML


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main() -> int:
    assert_true(_stable_max([2, 2, 2, 3, 3, 3, 7]) == 3, "stable max must reject one-off peak")
    rows = []
    start = date(2026, 1, 1)
    for i in range(24):
        actual = 90 + (i % 5) * 4
        planned = actual + 5
        rows.append({
            "production_date": start + timedelta(days=i),
            "sap_code": "6000139",
            "planned_day_qty": planned // 2,
            "planned_night_qty": planned - planned // 2,
            "planned_total_qty": planned,
            "actual_day_qty": actual // 2,
            "actual_night_qty": actual - actual // 2,
            "actual_total_qty": actual,
            "distinct_cavity_count": 2 if i < 16 else 3,
            "allocation_slot_count": 3,
            "distinct_line_count": 1,
            "primary_line": "Line-400",
            "mold_key": "8.25-15 TR",
            "casing_type": "B5",
        })
    model = FactoryResourceIntelligenceService._fit_profile(rows)
    assert_true(model["safe"] > 0, "safe capacity")
    assert_true(model["safe"] <= model["expected"] <= model["stretch"], "capacity envelope ordering")
    assert_true(model["observed_max_cavities"] == 3, "cavity evidence")
    assert_true(len(AdvancedCapacityML._features(rows[0])) >= 10, "advanced resource features")

    hub = (ROOT / "app/ui/master_data_hub_page.py").read_text(encoding="utf-8")
    assert_true("self.root.addLayout(self._build_metrics())" not in hub, "Master Data decorative cards should be removed")
    cap = (ROOT / "app/ui/factory_capacity_page.py").read_text(encoding="utf-8")
    for token in ("Production Lines", "Cavities", "Molds", "Casings", "Real Capacity", "Model Health"):
        assert_true(token in cap, f"missing Capacity Intelligence tab: {token}")

    print("[MPPS V11 SELFTEST] PASS")
    print(f"[MPPS V11 SELFTEST] Safe={model['safe']:.1f} Expected={model['expected']:.1f} Stretch={model['stretch']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
