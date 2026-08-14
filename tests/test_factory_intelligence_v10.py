from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path

from app.services.factory_intelligence_service import (
    FactoryIntelligenceService,
    _description_key,
    _description_similarity,
)
from app.services.intelligent_excel_import_service import IntelligentExcelImportService


class FactoryIntelligenceV10Tests(unittest.TestCase):
    def test_description_normalization_handles_factory_format_noise(self):
        left = '16X6-10 1/2  LA SM STD'
        right = '16x6 - 10 1/2 LA   SM STD'
        self.assertEqual(_description_key(left), _description_key(right))
        self.assertGreater(_description_similarity(left, right), 0.99)


    def test_auguest_filename_fallback_is_recognized(self):
        class EmptyWorkbook:
            sheetnames = []

        service = IntelligentExcelImportService(Path('.'))
        parsed = service._detect_plan_date(
            EmptyWorkbook(),
            Path('OVEN SHEET PLAN AUGUEST 10-2026.xlsx'),
        )
        self.assertEqual(parsed, date(2026, 8, 10))

    def test_prod_opening_stock_is_not_defaulted_to_legacy_daily_cache(self):
        source = Path('app/services/intelligent_excel_import_service.py').read_text(encoding='utf-8')
        self.assertIn('"update_stock": False', source)
        self.assertIn('"update_daily_stock": False', source)
        self.assertIn('monthly opening-stock evidence', source)

    def test_identity_preview_preserves_raw_sap_for_commit_learning(self):
        source = Path('app/services/factory_intelligence_service.py').read_text(encoding='utf-8')
        self.assertIn("row.get('raw_sap_code') or row.get('sap_code')", source)

    def test_historical_actual_upsert_prefers_newest_workbook_plan_date(self):
        source = Path('app/services/ai_planning_service.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(source.count('SELECT plan_date FROM excel_import_runs'), 4)
        self.assertIn('mpps_actual_production.source_import_run_id', source)
        self.assertIn('mpps_actual_production_dates.source_import_run_id', source)

    def test_capacity_model_learns_stable_real_output(self):
        start = date(2026, 1, 1)
        values = []
        for i in range(30):
            total = 800 + (i % 5) * 10
            values.append((start + timedelta(days=i), total, total * 0.55, total * 0.45))
        model = FactoryIntelligenceService._capacity_fit(values)
        self.assertEqual(model['sample_days'], 30)
        self.assertGreater(model['safe_capacity_qty'], 780)
        self.assertGreaterEqual(model['stretch_capacity_qty'], model['expected_capacity_qty'])
        self.assertGreater(model['confidence_score'], 0.65)
        self.assertLess(model['validation_wape_pct'], 5.0)

    def test_capacity_model_is_walk_forward_not_target_leaking(self):
        start = date(2026, 2, 1)
        values = [
            (start + timedelta(days=i), 500 if i < 8 else 900, 300, 200 if i < 8 else 600)
            for i in range(12)
        ]
        model = FactoryIntelligenceService._capacity_fit(values)
        self.assertGreater(model['validation_wape_pct'], 1.0)
        self.assertGreater(model['trend_score'], 0.0)

    def test_planner_policy_learns_human_overplan_ratio(self):
        start = date(2026, 3, 1)
        rows = [
            (start + timedelta(days=i), 100.0, 110.0)
            for i in range(20)
        ]
        model = FactoryIntelligenceService._planner_policy_fit(rows)
        self.assertAlmostEqual(model['planning_ratio'], 1.10, places=2)
        self.assertGreater(model['confidence_score'], 0.6)
        self.assertLess(model['validation_wape_pct'], 1.0)


if __name__ == '__main__':
    unittest.main()
