
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FullProfessionalV36Tests(unittest.TestCase):
    def setUp(self):
        self.main = (ROOT / "app/ui/main_window.py").read_text(encoding="utf-8-sig")
        self.dashboard = (ROOT / "app/ui/dashboard_pro_page.py").read_text(encoding="utf-8-sig")
        self.material = (ROOT / "app/ui/material_requirement_pro_page.py").read_text(encoding="utf-8-sig")
        self.ai = (ROOT / "app/ui/ai_ml_control_center_page.py").read_text(encoding="utf-8-sig")
        self.snapshot = (ROOT / "app/services/dashboard_snapshot_service.py").read_text(encoding="utf-8-sig")
        tyre_path = ROOT / "app/services/tyre_master_matrix_service.py"
        self.tyre_matrix = (
            tyre_path.read_text(encoding="utf-8-sig")
            if tyre_path.exists()
            else ""
        )

    def test_python_syntax(self):
        for source in (self.main, self.dashboard, self.material, self.ai, self.snapshot):
            ast.parse(source)

    def test_sidebar_cleanup(self):
        marker = "# MPPS V36 FULL PROFESSIONAL CLEANUP + PERFORMANCE"
        tail = self.main[self.main.rfind(marker):]
        for active in (
            "Dashboard",
            "Shipment Orders",
            "Shipment Details",
            "Factory Capacity",
            "Tyre Item Master",
            "Stock Master",
            "Production Planning",
            "Daily Plan",
            "Shift Plan",
            "Material Requirement",
            "Admin Settings",
            "AI / ML",
        ):
            self.assertIn(active, tail)

        self.assertIn("REPORTS_INDEX", tail)
        self.assertIn("WORKBOOK_LEARNING_INDEX", tail)
        self.assertIn("FACTORY_INTELLIGENCE_INDEX", tail)

    def test_ai_consolidation(self):
        for tab in ("Overview", "Models", "Data & Excel Pipeline", "Training & History"):
            self.assertIn(tab, self.ai)
        for area in (
            "PRODUCTION",
            "FACTORY / CAPACITY",
            "TYRE MASTER",
            "MATERIAL",
            "STOCK",
            "SHIPMENTS",
        ):
            self.assertIn(area, self.ai)

    def test_mrp_is_background_and_two_tab(self):
        self.assertIn("class _MRPWorker(QThread)", self.material)
        self.assertIn('self.tabs.addTab(self.summary_table, "Material Plan")', self.material)
        self.assertIn('self.tabs.addTab(self.detail_table, "Finished Item Breakdown")', self.material)
        self.assertNotIn("Imported Excel Snapshot", self.material)

    def test_dashboard_is_background(self):
        self.assertIn("class _DashboardWorker(QThread)", self.dashboard)
        self.assertIn("Shipment Delivery Risk", self.dashboard)
        self.assertIn("Stock & Material Readiness", self.dashboard)
        self.assertIn("Needs Attention", self.dashboard)

    def test_cached_navigation(self):
        self.assertIn(
            'if stack_index in getattr(self, "_loaded_page_indexes", set()):',
            self.main,
        )
        self.assertIn("self.stack.setCurrentIndex(stack_index)", self.main)

    def test_no_global_wait_cursor(self):
        self.assertIn("use_wait_cursor = False", self.main)

    def test_v35_date_authority_fix(self):
        if not self.tyre_matrix:
            self.skipTest("V35 Tyre matrix service is not installed.")
        self.assertNotIn(
            "EXCLUDED.last_seen<>''",
            self.tyre_matrix,
        )
        self.assertIn(
            "NULLIF(:seen,'')::date",
            self.tyre_matrix,
        )
        self.assertIn(
            "COALESCE(EXCLUDED.last_seen",
            self.tyre_matrix,
        )


    def test_tyremaster_user_tabs_collapsed(self):
        marker = "# MPPS V36 FULL PROFESSIONAL CLEANUP + PERFORMANCE"
        tail = self.main[self.main.rfind(marker):]
        self.assertIn('("Tyre Master", "MATRIX")', tail)


if __name__ == "__main__":
    unittest.main()
