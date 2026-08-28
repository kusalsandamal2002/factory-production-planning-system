
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShipmentDetailUiPolishV27Tests(unittest.TestCase):
    def setUp(self):
        self.source = (
            ROOT / "app" / "ui" / "shipment_orders_page.py"
        ).read_text(encoding="utf-8-sig")

        marker = "# MPPS V27 SHIPMENT DETAIL FINAL UI POLISH"
        self.assertIn(marker, self.source)
        self.v27 = self.source[
            self.source.index(marker):
        ]

    def test_long_source_text_is_reduced(self):
        self.assertIn(
            '"LATEST OVEN EXCEL"',
            self.v27,
        )
        self.assertIn(
            'normalized.startswith(',
            self.v27,
        )
        self.assertIn(
            '"last replanned:"',
            self.v27,
        )

    def test_item_schedule_technical_subtitle_is_hidden(self):
        self.assertIn(
            '"stock allocation"',
            self.v27,
        )
        self.assertIn(
            '"production timing"',
            self.v27,
        )
        self.assertIn(
            "label.hide()",
            self.v27,
        )

    def test_item_description_gets_stretch_width(self):
        self.assertIn(
            '"Item Description"',
            self.v27,
        )
        self.assertIn(
            "QHeaderView.ResizeMode.Stretch",
            self.v27,
        )

    def test_operational_columns_have_balanced_widths(self):
        for fragment in (
            '"SAP Code": 112',
            '"Stock Allocated": 116',
            '"Shortage": 88',
            '"Complete %": 96',
            '"Production Start": 126',
            '"Receive / Finish": 126',
            '"State": 136',
        ):
            self.assertIn(
                fragment,
                self.v27,
            )

    def test_metric_cards_are_polished_not_replaced(self):
        self.assertIn(
            'frame.objectName() == "MetricCard"',
            self.v27,
        )
        self.assertIn(
            'label.objectName() == "MetricValue"',
            self.v27,
        )

    def test_business_logic_still_exists_before_ui_patch(self):
        original = self.source[
            :self.source.index(
                "# MPPS V27 SHIPMENT DETAIL FINAL UI POLISH"
            )
        ]

        self.assertIn(
            "shipment_risk_profile",
            original,
        )
        self.assertIn(
            "FactoryPlanningEngine",
            original,
        )


if __name__ == "__main__":
    unittest.main()
