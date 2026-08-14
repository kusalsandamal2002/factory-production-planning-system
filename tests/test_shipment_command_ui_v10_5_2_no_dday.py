from pathlib import Path
import unittest


class ShipmentCommandUIV1052NoDDayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path('app/ui/shipment_orders_page.py')
        cls.source = cls.path.read_text(encoding='utf-8')
        start = cls.source.index('    def _build_list_page(self) -> None:')
        end = cls.source.index('    def clear_list_filters(self) -> None:', start)
        cls.build_list = cls.source[start:end]
        refresh_start = cls.source.index('    def refresh_list(self) -> None:')
        cls.refresh_list = cls.source[refresh_start:]

    def test_portfolio_has_eleven_visible_columns(self):
        self.assertIn('self.list_table = QTableWidget(0, 11)', self.build_list)
        self.assertNotIn('"D-Day",', self.build_list)

    def test_variance_label_is_explicit(self):
        self.assertIn('"Delivery Variance",', self.build_list)
        self.assertNotIn('\n            "Variance",', self.build_list)

    def test_dday_signal_remains_internal_for_risk_engine(self):
        self.assertIn('"days_to_target": profile.days_to_target', self.source)
        self.assertIn('days_to_target = row.get("days_to_target")', self.source)
        self.assertNotIn('d_day_text =', self.source)

    def test_removed_space_is_reallocated_to_decision_columns(self):
        self.assertIn('1: 248', self.source)
        self.assertIn('3: 124', self.source)
        self.assertIn('10: 170', self.source)
        self.assertIn('header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)', self.source)


if __name__ == '__main__':
    unittest.main()
