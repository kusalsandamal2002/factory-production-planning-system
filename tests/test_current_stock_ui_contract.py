from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CurrentStockUIContractTests(unittest.TestCase):
    def test_stock_workspace_still_has_current_stock_tab(self):
        source = (ROOT / "app" / "ui" / "stock_workspace_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CurrentStockPage", source)
        self.assertIn('"Current Stock"', source)
        self.assertIn("TAB_CURRENT", source)

    def test_current_stock_table_keeps_hr_to_hv_business_columns(self):
        source = (ROOT / "app" / "ui" / "current_stock_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QTableWidget(0, 9)", source)
        for header in (
            '"No."',
            '"SAP Code"',
            '"Material Description"',
            '"Total To be Shipped"',
            '"Current Stock"',
            '"Progress %"',
            '"Balance to Produce"',
            '"Total Plan"',
            '"Total To be Plan"',
        ):
            self.assertIn(header, source)

    def test_current_stock_has_operational_filters(self):
        source = (ROOT / "app" / "ui" / "current_stock_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QComboBox", source)
        self.assertIn("self.filter_combo", source)
        self.assertIn("CurrentStockService.FILTER_OPTIONS", source)
        self.assertIn("filter_rows(", source)
        self.assertIn("_update_metrics(rows)", source)

    def test_no_shipment_rows_show_dash_for_shipment_and_progress(self):
        source = (ROOT / "app" / "ui" / "current_stock_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"-" if shipment <= 0 else shipment', source)
        self.assertIn(
            '"-" if shipment <= 0 or progress is None else',
            source,
        )

    def test_service_preserves_direct_hr_to_hv_values(self):
        source = (
            ROOT / "app" / "services" / "current_stock_service.py"
        ).read_text(encoding="utf-8")
        for column in ("HR", "HS", "HT", "HU", "HV"):
            self.assertIn(
                f'column_index_from_string("{column}")',
                source,
            )
        self.assertIn("data_only=True", source)
        self.assertIn("return None", source)


if __name__ == "__main__":
    unittest.main()
