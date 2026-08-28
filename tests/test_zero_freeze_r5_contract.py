from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ZeroFreezeR5Contract(unittest.TestCase):
    def setUp(self):
        self.main = (ROOT / "app/ui/main_window.py").read_text(encoding="utf-8-sig")
        self.tasks = (ROOT / "app/core/task_manager.py").read_text(encoding="utf-8-sig")
        self.threads = (ROOT / "app/core/thread_lifecycle.py").read_text(encoding="utf-8-sig")
        self.stock = (ROOT / "app/ui/stock_workspace_page.py").read_text(encoding="utf-8-sig")
        self.shipments = (ROOT / "app/ui/shipment_details_pro_page.py").read_text(encoding="utf-8-sig")
        self.daily_ui = (ROOT / "app/ui/daily_plan_async_page.py").read_text(encoding="utf-8-sig")
        self.daily_service = (ROOT / "app/services/daily_plan_async_service.py").read_text(encoding="utf-8-sig")
        self.ops = (ROOT / "app/ui/intelligent_operations_pages.py").read_text(encoding="utf-8-sig")

    def test_python_syntax(self):
        for source in (
            self.main,
            self.tasks,
            self.threads,
            self.stock,
            self.shipments,
            self.daily_ui,
            self.daily_service,
            self.ops,
        ):
            ast.parse(source)

    def test_main_window_preloads_route_modules_off_ui_path(self):
        self.assertIn("def _preload_route_module", self.main)
        self.assertIn('f"route-import:{route}"', self.main)
        self.assertIn("TaskManager", self.main)
        self.assertIn('"app.ui.daily_plan_async_page"', self.main)

    def test_shutdown_quiesces_page_qthreads_and_task_pool(self):
        self.assertIn("quiesce_qthreads", self.main)
        self.assertIn("self.task_manager.cancel_all()", self.main)
        self.assertIn("self.task_manager.shutdown(wait_ms=5000)", self.main)
        self.assertIn("requestInterruption", self.threads)
        self.assertIn("thread.wait", self.threads)

    def test_task_manager_uses_dedicated_bounded_pool(self):
        self.assertIn("QThreadPool(self)", self.tasks)
        self.assertIn("setMaxThreadCount", self.tasks)
        self.assertIn("self.pool.clear()", self.tasks)
        self.assertIn("waitForDone", self.tasks)
        self.assertNotIn("QThreadPool.globalInstance()", self.tasks)

    def test_stock_shell_has_no_eager_stock_child_imports(self):
        self.assertNotIn("from app.ui.current_stock_page import", self.stock)
        self.assertNotIn("from app.ui.daily_stock_page import", self.stock)
        self.assertNotIn("from app.ui.monthly_stock_page import", self.stock)
        self.assertIn("import_module", self.stock)
        self.assertIn("TaskManager.instance()", self.stock)
        self.assertIn('priority=-1', self.stock)

    def test_shipment_detail_service_import_is_lazy_and_detail_page_is_lazy(self):
        self.assertNotIn(
            "from app.services.shipment_lifecycle_service import load_detail, load_portfolio, set_lifecycle",
            self.shipments,
        )
        self.assertIn("self.detail_page: QWidget | None = None", self.shipments)
        self.assertIn("if self.detail_page is None", self.shipments)
        self.assertIn("def load_portfolio_job", self.shipments)
        self.assertIn("def load_detail_job", self.shipments)

    def test_daily_plan_is_model_view_and_db_async(self):
        self.assertIn("QAbstractTableModel", self.daily_ui)
        self.assertIn("QTableView", self.daily_ui)
        self.assertNotIn("QTableWidget", self.daily_ui)
        self.assertIn("TaskManager.instance()", self.daily_ui)
        self.assertNotIn("from app.database", self.daily_ui)
        self.assertIn("from app.database import get_session", self.daily_service)
        self.assertIn("LIMIT 5000", self.daily_service)

    def test_shift_plan_removed_constructor_schema_work_and_uses_tasks(self):
        shift_start = self.ops.index("class ShiftPlanPage(_OperationsPage):")
        shift_end = self.ops.index("class OperationsReportsPage", shift_start)
        shift = self.ops[shift_start:shift_end]
        constructor_start = shift.index("def __init__")
        constructor_end = shift.index("def showEvent", constructor_start)
        constructor = shift[constructor_start:constructor_end]
        self.assertNotIn("ShiftDailyReportService.ensure_schema()", constructor)
        self.assertIn("TaskManager.instance()", constructor)
        self.assertIn("def load_dates_job", shift)
        self.assertIn("def load_selected_job", shift)


if __name__ == "__main__":
    unittest.main()
