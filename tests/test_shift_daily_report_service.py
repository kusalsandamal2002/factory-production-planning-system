import unittest

from app.services.shift_daily_report_service import (
    LOSS_REASONS,
    aggregate_excel_report_targets,
    build_shift_report_html,
    ShiftDailyReportService,
)


class ShiftDailyReportServiceTests(unittest.TestCase):
    def test_excel_line_mapping_matches_supplied_day_report_totals(self):
        rows = [
            {"line_name": "Press -LINE", "planned_qty": 66, "planned_weight_kg": 1240.9},
            {"line_name": "NANCY PRESS", "planned_qty": 40, "planned_weight_kg": 476.0},
            {"line_name": "400 T PRESS", "planned_qty": 40, "planned_weight_kg": 476.0},
            {"line_name": "T 600 -01 PRESS", "planned_qty": 32, "planned_weight_kg": 416.0},
            {"line_name": "T 600 -02 PRESS", "planned_qty": 2, "planned_weight_kg": 112.42},
            {"line_name": "L-PRESS-1250", "planned_qty": 1, "planned_weight_kg": 344.25},
            {"line_name": "L-PRESS-1500", "planned_qty": 6, "planned_weight_kg": 269.0},
            {"line_name": "Line-400", "planned_qty": 122, "planned_weight_kg": 2564.54245},
            {"line_name": "Line-800", "planned_qty": 41, "planned_weight_kg": 3283.367},
            {"line_name": "ORING-PRESS", "planned_qty": 20, "planned_weight_kg": 248.0},
            {"line_name": "NEW PRESS", "planned_qty": 6, "planned_weight_kg": 197.4},
        ]
        summary = aggregate_excel_report_targets(rows)
        self.assertEqual(summary["raw_total_pcs"], 376)
        self.assertAlmostEqual(summary["raw_total_kg"], 9627.87945, places=4)
        self.assertEqual(summary["lines"]["600 Press"]["target_pcs"], 114)
        self.assertAlmostEqual(summary["lines"]["600 Press"]["target_kg"], 1480.42, places=2)
        self.assertEqual(summary["lines"]["Bard Press"]["target_pcs"], 26)
        self.assertEqual(summary["unmapped"], [])

    def test_unmapped_live_line_is_reported_not_silently_dropped(self):
        summary = aggregate_excel_report_targets(
            [{"line_name": "NEW UNKNOWN LINE", "planned_qty": 4, "planned_weight_kg": 100.0}]
        )
        self.assertEqual(summary["raw_total_pcs"], 4)
        self.assertEqual(summary["mapped_total_pcs"], 0)
        self.assertEqual(len(summary["unmapped"]), 1)


    def test_load_targets_uses_import_trace_line_not_missing_database_column(self):
        class FakeResult:
            def mappings(self):
                return self

            def all(self):
                return [
                    {
                        "oven_code": "L-PRESS-003",
                        "source_note": "Intelligent import run #42; line=Line-400; casing evidence retained=-",
                        "planned_qty": 12,
                        "planned_weight_kg": 240.5,
                    }
                ]

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, statement, params):
                sql = str(statement)
                self_sql = sql.lower()
                if "line_name" in self_sql:
                    raise AssertionError("load_targets must not query missing mpps_oven_plan.line_name")
                self.params = params
                return FakeResult()

        from unittest.mock import patch

        with patch("app.services.shift_daily_report_service._get_session", return_value=FakeSession()):
            summary = ShiftDailyReportService.load_targets("2026-06-01", "DAY")

        self.assertEqual(summary["lines"]["400 Line"]["target_pcs"], 12)
        self.assertAlmostEqual(summary["lines"]["400 Line"]["target_kg"], 240.5)
        self.assertEqual(summary["unmapped"], [])

    def test_print_html_contains_two_page_excel_report_sections(self):
        summary = aggregate_excel_report_targets([])
        html = build_shift_report_html("2026-06-01", "DAY", summary, {})
        self.assertIn("LAUGFS Corporation (Rubber) Ltd.", html)
        self.assertIn("Daily Production Summary Report", html)
        self.assertIn("2nd Stage Compound Production", html)
        self.assertIn("Quality Performance", html)
        self.assertIn("Loss Reasons", html)
        self.assertIn(LOSS_REASONS[0], html)
        self.assertIn("Page: 01 of 02", html)
        self.assertIn("Page: 02 of 02", html)


if __name__ == "__main__":
    unittest.main()
