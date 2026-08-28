
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShipmentDetailHeaderCleanupV271Tests(unittest.TestCase):
    def setUp(self):
        self.source = (
            ROOT / "app" / "ui" / "shipment_orders_page.py"
        ).read_text(encoding="utf-8-sig")

        marker = "# MPPS V27.1 SHIPMENT DETAIL HEADER CLEANUP"
        self.assertIn(marker, self.source)

        self.v271 = self.source[self.source.index(marker):]

    def test_technical_metadata_is_hidden(self):
        self.assertIn(
            'normalized.startswith("xls-final")',
            self.v271,
        )
        self.assertIn(
            'normalized.startswith("last replanned:")',
            self.v271,
        )
        self.assertIn(
            '"final shipment snapshot" in normalized',
            self.v271,
        )

    def test_delayed_forecast_actions_are_hidden(self):
        self.assertIn('"delayed"', self.v271)
        self.assertIn('"forecast"', self.v271)
        self.assertIn('"actions"', self.v271)
        self.assertIn("widget.hide()", self.v271)

    def test_cleanup_retries_after_async_population(self):
        self.assertIn(
            "QTimer.singleShot(",
            self.v271,
        )
        self.assertIn(
            "1200,",
            self.v271,
        )

    def test_business_logic_is_preserved_before_patch(self):
        original = self.source[
            :self.source.index(
                "# MPPS V27.1 SHIPMENT DETAIL HEADER CLEANUP"
            )
        ]

        self.assertIn(
            "FactoryPlanningEngine",
            original,
        )
        self.assertIn(
            "shipment_risk_profile",
            original,
        )


if __name__ == "__main__":
    unittest.main()
