
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeliveryDateNavigationV281Tests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "app" / "ui" / "main_window.py"
        self.source = self.path.read_text(encoding="utf-8-sig")

    def test_python_syntax_is_valid(self):
        ast.parse(self.source)

    def test_v281_marker_exists(self):
        self.assertIn(
            "# MPPS V28.1 DELIVERY DATE NAVIGATION REMOVED",
            self.source,
        )

    def test_delivery_date_nav_call_is_absent(self):
        lines = self.source.splitlines()
        for index, line in enumerate(lines):
            if "self._add_nav_button" not in line:
                continue

            block = [line]
            balance = line.count("(") - line.count(")")
            j = index + 1

            while balance > 0 and j < len(lines):
                block.append(lines[j])
                balance += lines[j].count("(") - lines[j].count(")")
                j += 1

            block_text = "\n".join(block)
            self.assertFalse(
                "Delivery Date Calculation" in block_text
                and "DELIVERY_DATE_INDEX" in block_text
            )

    def test_delivery_date_backend_is_preserved(self):
        self.assertIn(
            "DELIVERY_DATE_INDEX",
            self.source,
        )
        self.assertIn(
            "DeliveryDateControlPage",
            self.source,
        )

    def test_other_planning_navigation_is_preserved(self):
        for label in (
            "Production Planning",
            "Daily Plan",
            "Shift Plan",
            "Material Requirement",
        ):
            self.assertIn(label, self.source)


if __name__ == "__main__":
    unittest.main()
