
from __future__ import annotations
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class V34Tests(unittest.TestCase):
    def setUp(self):
        self.page=(ROOT/"app/ui/tyre_item_master_pro_page.py").read_text(encoding="utf-8-sig")
        self.service=(ROOT/"app/services/tyre_master_360_service.py").read_text(encoding="utf-8-sig")
        self.main=(ROOT/"app/ui/main_window.py").read_text(encoding="utf-8-sig")

    def test_syntax(self):
        ast.parse(self.page); ast.parse(self.service); ast.parse(self.main)

    def test_tyres_360(self):
        for value in ("Master Items","Tyre 360","Data Quality","AI / ML","Line Compatibility","Cavity / Oven Compatibility"):
            self.assertIn(value,self.page)

    def test_materials(self):
        for value in ("CORE","BAND","COMPOUND","TOTAL BEAD","WGT"):
            self.assertIn(value,self.service)
        self.assertIn("mpps_tyre_material_component",self.service)
        self.assertIn("mpps_tyre_material_observation",self.service)

    def test_compatibility_states(self):
        for value in ("CONFIRMED","INCOMPATIBLE","UNKNOWN"):
            self.assertIn(value,self.service)

    def test_performance(self):
        self.assertIn("QTableView",self.page)
        self.assertIn("PAGE_SIZE = 150",self.page)
        self.assertIn("class ProfileWorker(QThread)",self.page)

    def test_ml_material_modules(self):
        self.assertIn("MATERIAL_COMPONENT_INTELLIGENCE",self.service)
        self.assertIn("MATERIAL_REQUIREMENT_FORECAST",self.service)

    def test_auto_sync(self):
        self.assertIn("# MPPS V34 TYRE 360 MATERIAL ENRICHMENT",self.main)
        self.assertIn("setInterval(30000)",self.main)

if __name__ == "__main__":
    unittest.main()
