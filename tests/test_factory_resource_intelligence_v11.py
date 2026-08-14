from datetime import date, timedelta

from app.services.factory_resource_intelligence_service import (
    FactoryResourceIntelligenceService,
    _stable_max,
)
from app.services.advanced_capacity_ml import AdvancedCapacityML


def _rows(n=24):
    start = date(2026, 1, 1)
    rows = []
    for i in range(n):
        actual = 90 + (i % 5) * 4
        planned = actual + (3 if i % 3 else 8)
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
            "primary_line": "LINE-400",
            "mold_key": "8.25-15 TR",
            "casing_type": "B5",
        })
    return rows


def test_stable_max_rejects_one_off_peak():
    assert _stable_max([2, 2, 2, 3, 3, 3, 7]) == 3


def test_capacity_profile_learns_safe_expected_stretch_and_cavity_setup():
    profile = FactoryResourceIntelligenceService._fit_profile(_rows())
    assert profile["sample_days"] == 24
    assert 0 < profile["safe"] <= profile["expected"] <= profile["stretch"]
    assert profile["stable_cavities"] in {2, 3}
    assert profile["observed_max_cavities"] == 3
    assert 0 <= profile["confidence"] <= 1
    assert profile["wape"] >= 0


def test_advanced_feature_vector_contains_resource_context():
    row = _rows(1)[0]
    features = AdvancedCapacityML._features(row)
    assert len(features) >= 10
    assert features[0] > 0
    assert features[2] == 2


def test_profile_is_time_ordered_and_handles_zero_actual():
    rows = _rows(12)
    rows.append({**rows[-1], "production_date": date(2026, 2, 1), "actual_total_qty": 0})
    profile = FactoryResourceIntelligenceService._fit_profile(rows)
    assert profile["sample_days"] == 13
    assert profile["expected"] >= 0
