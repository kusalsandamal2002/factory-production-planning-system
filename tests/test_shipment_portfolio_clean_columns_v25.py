
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShipmentPortfolioCleanColumnsV25Tests(unittest.TestCase):
    def setUp(self):
        self.source = (
            ROOT / "app" / "ui" / "shipment_orders_page.py"
        ).read_text(encoding="utf-8-sig")

        marker = "# MPPS V25 SHIPMENT PORTFOLIO CLEAN COLUMNS"
        self.assertIn(marker, self.source)
        self.v25 = self.source[self.source.index(marker):]

    def test_risk_and_delivery_status_are_hidden(self):
        self.assertIn('"Risk"', self.v25)
        self.assertIn('"Delivery Status"', self.v25)
        self.assertIn(
            "self.list_table.setColumnHidden(",
            self.v25,
        )

    def test_existing_setup_is_preserved(self):
        self.assertIn(
            "_mpps_v25_original_setup_list_table(self)",
            self.v25,
        )

    def test_underlying_business_logic_is_not_deleted(self):
        original = self.source[
            :self.source.index(
                "# MPPS V25 SHIPMENT PORTFOLIO CLEAN COLUMNS"
            )
        ]
        self.assertIn(
            "shipment_risk_profile",
            original,
        )
        self.assertIn(
            "portfolio_metrics",
            original,
        )

    def test_v25_is_final_setup_alias(self):
        self.assertIn(
            "ShipmentDetailsPage._setup_list_table =",
            self.v25,
        )


if __name__ == "__main__":
    unittest.main()
