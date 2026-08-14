from pathlib import Path
import unittest


class ShipmentCommandCompactUIV1051Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path('app/ui/shipment_orders_page.py')
        cls.source = cls.path.read_text(encoding='utf-8')
        start = cls.source.index('    def _build_list_page(self) -> None:')
        end = cls.source.index('    def clear_list_filters(self) -> None:', start)
        cls.build_list = cls.source[start:end]

    def test_marked_decision_strip_is_removed(self):
        self.assertNotIn('decision_row = QHBoxLayout()', self.build_list)
        self.assertNotIn('self.selection_brief_card = QFrame()', self.build_list)
        self.assertNotIn('self.quick_target_btn = QPushButton("Set Target")', self.build_list)
        self.assertNotIn('self.quick_auto_target_btn = QPushButton("Auto Target")', self.build_list)
        self.assertNotIn('self.quick_replan_btn = QPushButton("Replan")', self.build_list)
        self.assertNotIn('Select a shipment for a decision brief.', self.build_list)

    def test_removed_controls_are_preserved_in_actions_menu(self):
        self.assertIn('self.target_action = actions_menu.addAction("Set Target Date...")', self.build_list)
        self.assertIn('self.auto_target_action = actions_menu.addAction("Reset to Auto Target")', self.build_list)
        self.assertIn('self.replan_action = actions_menu.addAction("Replan Portfolio")', self.build_list)
        self.assertIn('self.target_action.triggered.connect(self.change_selected_target_date)', self.build_list)
        self.assertIn('self.auto_target_action.triggered.connect(self.reset_selected_to_auto_target)', self.build_list)
        self.assertIn('self.replan_action.triggered.connect(self.replan_all_from_list)', self.build_list)

    def test_table_follows_filters_directly_and_owns_remaining_space(self):
        filter_pos = self.build_list.index('header_layout.addLayout(filter_row)')
        header_pos = self.build_list.index('layout.addWidget(header)', filter_pos)
        table_pos = self.build_list.index('table_card = self._card()', header_pos)
        self.assertLess(filter_pos, header_pos)
        self.assertLess(header_pos, table_pos)
        between = self.build_list[filter_pos:header_pos]
        self.assertNotIn('addWidget(self.selection_brief_card', between)
        self.assertIn('table_layout.addWidget(self.list_table, 1)', self.build_list)
        self.assertIn('layout.addWidget(table_card, 1)', self.build_list)

    def test_dense_row_height_remains_enabled(self):
        self.assertIn('self.list_table.verticalHeader().setDefaultSectionSize(36)', self.source)
        self.assertIn('self.list_table.setWordWrap(False)', self.source)


if __name__ == '__main__':
    unittest.main()
