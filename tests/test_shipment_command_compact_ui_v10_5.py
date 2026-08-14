from pathlib import Path
import unittest


class ShipmentCommandCompactUIV105Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path('app/ui/shipment_orders_page.py')
        cls.source = cls.path.read_text(encoding='utf-8')
        start = cls.source.index('    def _build_list_page(self) -> None:')
        end = cls.source.index('    def clear_list_filters(self) -> None:', start)
        cls.build_list = cls.source[start:end]

    def test_marked_descriptive_copy_is_not_rendered(self):
        self.assertNotIn('Executive delivery control for the latest LIVE OVEN source', self.build_list)
        self.assertNotIn('Priority is driven by target-date urgency and delivery feasibility', self.build_list)
        self.assertNotIn('Operational as-of:', self.build_list)
        self.assertIn('self.last_refresh_label.setVisible(False)', self.build_list)

    def test_large_top_action_row_replaced_by_compact_actions_menu(self):
        self.assertNotIn('action_row = QHBoxLayout()', self.build_list)
        self.assertIn('self.actions_btn = QPushButton("Actions ▾")', self.build_list)
        self.assertIn('actions_menu = QMenu(self.actions_btn)', self.build_list)
        self.assertIn('table_heading.addWidget(self.actions_btn)', self.build_list)

    def test_table_is_primary_vertical_workspace(self):
        self.assertIn('table_layout.addWidget(self.list_table, 1)', self.build_list)
        self.assertIn('layout.addWidget(table_card, 1)', self.build_list)
        self.assertIn('self.list_table.verticalHeader().setDefaultSectionSize(36)', self.source)
        self.assertIn('self.list_table.setWordWrap(False)', self.source)

    def test_kpis_are_compact(self):
        self.assertIn('card.setMaximumHeight(76)', self.source)
        self.assertIn('layout.setContentsMargins(12, 7, 12, 7)', self.source)


if __name__ == '__main__':
    unittest.main()
