from pathlib import Path
import unittest


class MonthlyOpeningStockUpsertV106Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path('app/services/factory_intelligence_service.py').read_text(encoding='utf-8')
        start = cls.source.index('    def capture_opening_stock(')
        end = cls.source.index('    @staticmethod\n    def _daily_actual_rows', start)
        cls.method = cls.source[start:end]

    def test_monthly_stock_line_uses_atomic_natural_key_upsert(self):
        self.assertIn('ON CONFLICT (stock_count_id, material_code)', self.method)
        self.assertIn('DO UPDATE SET', self.method)
        self.assertIn('fg_qty = EXCLUDED.fg_qty', self.method)

    def test_workbook_duplicates_are_not_summed_into_opening_stock(self):
        self.assertIn('canonical_rows:', self.method)
        self.assertIn('duplicate_rows_merged', self.method)
        self.assertNotIn('opening +=', self.method)

    def test_existing_snapshot_is_not_used_to_choose_insert_vs_update(self):
        self.assertIn('Do NOT use this snapshot to decide INSERT vs UPDATE', self.method)
        # The old branch was vulnerable to DB triggers/normalisation races.
        self.assertNotIn('if sap in existing:', self.method)


if __name__ == '__main__':
    unittest.main()
