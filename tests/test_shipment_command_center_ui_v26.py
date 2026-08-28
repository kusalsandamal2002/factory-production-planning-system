
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShipmentCommandCenterUiV26Tests(unittest.TestCase):
    def setUp(self):
        source = (
            ROOT / "app" / "ui" / "shipment_orders_page.py"
        ).read_text(encoding="utf-8-sig")

        marker = "# MPPS V26 SHIPMENT COMMAND CENTER UI POLISH"
        self.assertIn(marker, source)

        self.full = source
        self.v26 = source[source.index(marker):]

    def test_balanced_column_widths(self):
        for fragment in (
            '"Priority": 72',
            '"Target": 108',
            '"Factory Can Out": 132',
            '"Delivery Variance": 128',
            '"Qty": 88',
            '"Stock": 88',
            '"Coverage": 100',
            '"Prod Gap": 108',
        ):
            self.assertIn(fragment, self.v26)

        self.assertIn(
            'columns.get("Shipment")',
            self.v26,
        )
        self.assertIn(
            "QHeaderView.ResizeMode.Stretch",
            self.v26,
        )

    def test_prod_gap_is_not_stretched_as_last_column(self):
        self.assertIn(
            "header.setStretchLastSection(False)",
            self.v26,
        )

    def test_dense_rows_and_selection_are_applied(self):
        self.assertIn(
            "setDefaultSectionSize(40)",
            self.v26,
        )
        self.assertIn(
            "QTableWidget::item:selected",
            self.v26,
        )

    def test_filters_are_kept_and_normalized(self):
        for prefix in (
            'current.startswith("Risk:")',
            'current.startswith("Promise:")',
            'current.startswith("Stock:")',
            'current.startswith("Target:")',
        ):
            self.assertIn(prefix, self.v26)

    def test_kpi_cards_are_preserved(self):
        for label in (
            "Visible Shipments",
            "Shipment Qty",
            "Stock Coverage",
            "Production Gap",
            "Critical / Late",
            "Needs Review",
        ):
            self.assertIn(label, self.v26)

    def test_business_logic_remains_before_ui_patch(self):
        original = self.full[
            :self.full.index(
                "# MPPS V26 SHIPMENT COMMAND CENTER UI POLISH"
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
        self.assertIn(
            "_ShipmentPortfolioWorker",
            original,
        )


if __name__ == "__main__":
    unittest.main()
