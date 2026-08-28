
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionPlanningNonBlockingV24Tests(unittest.TestCase):
    def setUp(self):
        self.schedule = (
            ROOT / "app" / "ui" / "schedule_page.py"
        ).read_text(encoding="utf-8-sig")
        self.main = (
            ROOT / "app" / "ui" / "main_window.py"
        ).read_text(encoding="utf-8-sig")

    def test_constructor_has_no_synchronous_database_read(self):
        class_pos = self.schedule.index(
            "class SchedulePage(QWidget):"
        )
        init_pos = self.schedule.index(
            "    def __init__(self, current_user=None):",
            class_pos,
        )
        end = self.schedule.index(
            "    def showEvent",
            init_pos,
        )
        block = self.schedule[init_pos:end]

        self.assertNotIn(
            "with get_session() as session",
            block,
        )
        self.assertIn(
            "self._start_initial_async_load",
            block,
        )
        self.assertIn(
            "self._request_saved_plan_load",
            block,
        )

    def test_saved_plan_database_load_runs_in_worker(self):
        worker_pos = self.schedule.index(
            "class _SavedPlanLoadWorker(QObject):"
        )
        schedule_pos = self.schedule.index(
            "class SchedulePage(QWidget):"
        )
        block = self.schedule[
            worker_pos:schedule_pos
        ]

        self.assertIn(
            "with get_session() as session",
            block,
        )
        self.assertIn(
            "load_latest_saved_plan(",
            block,
        )

    def test_stale_saved_plan_results_are_ignored(self):
        self.assertIn(
            "if token != self._saved_load_token:",
            self.schedule,
        )
        self.assertIn(
            "self._saved_load_jobs",
            self.schedule,
        )

    def test_shift_change_uses_background_recalculate(self):
        start = self.schedule.index(
            "    def _refresh_selected_shift_preview"
        )
        end = self.schedule.index(
            "    def _settings(",
            start,
        )
        block = self.schedule[start:end]

        self.assertNotIn(
            "generate_cavity_plan(",
            block,
        )
        self.assertIn(
            "self.recalculate_plan()",
            block,
        )

    def test_large_table_is_rendered_in_batches(self):
        start = self.schedule.index(
            "    def _populate_table(self) -> None:"
        )
        end = self.schedule.index(
            "    def _populate_blocked_table",
            start,
        )
        block = self.schedule[start:end]

        self.assertIn(
            "batch_size = 32",
            block,
        )
        self.assertIn(
            "QTimer.singleShot(",
            block,
        )
        self.assertIn(
            "self._table_render_token",
            block,
        )

    def test_main_window_does_not_lock_cursor_for_planning(self):
        start = self.main.index(
            "use_wait_cursor ="
        )
        end = self.main.index(
            "if use_wait_cursor:",
            start,
        )
        block = self.main[start:end]

        self.assertIn(
            "self.SCHEDULE_INDEX",
            block,
        )
        self.assertIn(
            "self.SHIPMENT_DETAILS_INDEX",
            block,
        )


if __name__ == "__main__":
    unittest.main()
