import unittest
from datetime import date

from app.services.material_requirement_service import (
    ExcelMaterialPlanRow,
    MaterialRequirementRow,
    consolidate_material_requirements,
)


class MaterialRequirementServiceTests(unittest.TestCase):
    def _requirement(self, *, warning: str = "") -> MaterialRequirementRow:
        return MaterialRequirementRow(
            finished_item_code="60000001",
            finished_item_description="Test tyre",
            production_required_qty=10,
            day_production_qty=6,
            night_production_qty=4,
            component_type="COMPOUND",
            raw_material_code="CMP-TEST",
            raw_material_name="B 607 (MAIN)",
            planning_key="B 607",
            usage_per_unit=2.0,
            base_required_qty=20.0,
            allowance_rate=0.25,
            required_qty=25.0,
            day_required_qty=15.0,
            night_required_qty=10.0,
            unit="KG",
            demand_source="Oven day + night plan",
            master_source="OVEN.xlsx / compound:4",
            warning=warning,
        )

    def test_excel_reconciliation_matches_calculated_requirement(self) -> None:
        excel = ExcelMaterialPlanRow(
            plan_date=date(2026, 6, 1),
            material_type="COMPOUND",
            material_key="B 607",
            material_description="",
            day_qty=0.0,
            night_qty=0.0,
            total_qty=25.0,
            produced_qty=0.0,
            stock_qty=5.0,
            next_day_qty=0.0,
            unit="KG",
            source="compound :3228",
            workbook_name="OVEN.xlsx",
        )
        result = consolidate_material_requirements([self._requirement()], [excel])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, "MATCH")
        self.assertEqual(result[0].net_to_prepare_qty, 20.0)
        self.assertEqual(result[0].variance_qty, 0.0)

    def test_large_excel_variance_is_flagged(self) -> None:
        excel = ExcelMaterialPlanRow(
            plan_date=date(2026, 6, 1),
            material_type="COMPOUND",
            material_key="B 607",
            material_description="",
            day_qty=0.0,
            night_qty=0.0,
            total_qty=40.0,
            produced_qty=0.0,
            stock_qty=0.0,
            next_day_qty=0.0,
            unit="KG",
            source="compound :3228",
            workbook_name="OVEN.xlsx",
        )
        result = consolidate_material_requirements([self._requirement()], [excel])
        self.assertEqual(result[0].status, "CHECK VARIANCE")
        self.assertEqual(result[0].variance_qty, 15.0)

    def test_excel_only_core_plan_is_preserved(self) -> None:
        core = ExcelMaterialPlanRow(
            plan_date=date(2026, 6, 1),
            material_type="CORE",
            material_key="10.00-20 OPT 2L CORE",
            material_description="Inner core",
            day_qty=2.0,
            night_qty=2.0,
            total_qty=4.0,
            produced_qty=0.0,
            stock_qty=1.0,
            next_day_qty=0.0,
            unit="PCS",
            source="Core:7",
            workbook_name="OVEN.xlsx",
        )
        result = consolidate_material_requirements([], [core])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].component_type, "CORE")
        self.assertEqual(result[0].status, "EXCEL PLAN")
        self.assertEqual(result[0].net_to_prepare_qty, 3.0)


if __name__ == "__main__":
    unittest.main()
