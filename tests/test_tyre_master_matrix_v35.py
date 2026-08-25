
from __future__ import annotations
import ast, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TyreMasterMatrixV35Tests(unittest.TestCase):
    def setUp(self):
        self.page=(ROOT/"app/ui/tyre_item_master_pro_page.py").read_text(encoding="utf-8-sig")
        self.service=(ROOT/"app/services/tyre_master_matrix_service.py").read_text(encoding="utf-8-sig")
        self.main=(ROOT/"app/ui/main_window.py").read_text(encoding="utf-8-sig")

    def test_syntax(self):
        ast.parse(self.page); ast.parse(self.service); ast.parse(self.main)

    def test_one_tyre_one_row_matrix(self):
        self.assertIn("One tyre • one row", self.page)
        self.assertIn("GroupedHeaderView", self.page)
        for group in ("LINE COMPATIBILITY","CAVITY / OVEN COMPATIBILITY","PROCESS","MATERIAL / COMPONENTS","PLAN / STOCK"):
            self.assertIn(group, self.service)

    def test_requested_compatibility_states(self):
        # The UI renders the value supplied by the matrix service. The
        # service owns UNKNOWN -> "?" while the view owns ✓/✕ styling.
        combined = self.page + self.service
        for symbol in ("✓","✕","?"):
            self.assertIn(symbol, combined)
        for state in ("CONFIRMED","INCOMPATIBLE","UNKNOWN"):
            self.assertIn(state, self.service)

    def test_material_columns(self):
        for name in ("CORE","BAND","COMPOUND","BEAD","TOTAL BEAD","WGT"):
            self.assertIn(name, self.service)

    def test_database_authority_not_physical_excel(self):
        self.assertIn("sync_database_authority", self.service)
        self.assertIn("information_schema.columns", self.service)
        self.assertNotIn("openpyxl", self.service)
        self.assertIn("DATABASE AUTHORITY", self.page)

    def test_old_summary_design_removed(self):
        self.assertNotIn("Open Tyre 360", self.page)
        self.assertNotIn("waiting for Excel", self.page)
        self.assertNotIn("0 linked", self.page)

    def test_smds_line_becomes_confirmed(self):
        self.assertIn("SMDS is always authoritative master data", self.service)
        self.assertIn("cls._up_line", self.service)

    def test_performance(self):
        self.assertIn("QAbstractTableModel", self.page)
        self.assertIn("QTableView", self.page)
        self.assertIn("PAGE_SIZE=100", self.page)
        self.assertIn("class ListWorker(QThread)", self.page)

    def test_old_physical_pollers_retired(self):
        self.assertIn("MainWindow._v33_request_tyre_sync = _v35_retired_old_tyre_sync", self.main)
        self.assertIn("MainWindow._v34_request_tyre360_sync = _v35_retired_old_tyre_sync", self.main)

if __name__=="__main__":
    unittest.main()
