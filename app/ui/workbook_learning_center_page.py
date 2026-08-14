from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService
from app.services.operational_source_service import OperationalSourceService
from app.services.factory_intelligence_service import FactoryIntelligenceService


class _AIWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    def run(self) -> None:
        try:
            service = AIPlanningService()
            with get_session() as session:
                service.ensure_schema(session)
                result: dict[str, Any] = {}
                result.update(service.reconcile_plan_vs_actual(session))
                result.update(service.train_models(session))
                factory = FactoryIntelligenceService()
                factory.ensure_schema(session)
                result.update(factory.train_capacity_models(session))
                result.update(factory.train_planner_policy(session))
                result.update(factory.refresh_state(session))
                result.update(service.evaluate_ai_runs(session))
                if self.action == "GENERATE":
                    source = OperationalSourceService.latest(session)
                    target_date = source.next_planning_date
                    result.update(
                        service.generate_candidate_plan(
                            session,
                            plan_date=target_date,
                            source_import_run_id=source.import_run_id,
                        )
                    )
                    result.update(service.evaluate_ai_runs(session))
                result["readiness"] = service.get_readiness(session).__dict__
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class WorkbookLearningCenterPage(QWidget):
    """AI-assisted production planning control center.

    Excel/Oven uploads remain the final production-plan authority. The AI runs in
    shadow mode, learns from verified PROD actuals, shows candidate plans, and
    exposes measurable readiness before any future supervised-auto promotion.
    """

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.service = AIPlanningService()
        self.worker: _AIWorker | None = None
        self.metrics: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AI Production Planning Control Center")
        title.setStyleSheet("font-size:26px;font-weight:950;color:#0f172a;")
        subtitle = QLabel(
            "Daily Excel/Oven plan = FINAL execution authority. MPPS AI learns from "
            "PROD day/night actuals, compares plan vs actual, forecasts execution "
            "reliability and prepares the next-day candidate plan in SHADOW mode."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#64748b;font-size:12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.mode_badge = QLabel("SHADOW MODE")
        self.source_badge = QLabel("Live OVEN: -")
        self.source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_badge.setMinimumWidth(180)
        self.source_badge.setStyleSheet(
            "background:#ecfdf5;color:#166534;border:1px solid #bbf7d0;"
            "border-radius:16px;padding:9px 14px;font-weight:950;"
        )
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_badge.setMinimumWidth(180)
        self.mode_badge.setStyleSheet(
            "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;"
            "border-radius:16px;padding:9px 14px;font-weight:950;"
        )
        header.addWidget(self.source_badge)
        header.addWidget(self.mode_badge)
        root.addLayout(header)

        metric_grid = QGridLayout()
        metric_grid.setSpacing(10)
        specs = [
            ("validation_days", "Validated Production Days"),
            ("accuracy", "Model Validation Accuracy"),
            ("coverage", "Plan / Actual Data Coverage"),
            ("high", "High-Confidence SAP Models"),
            ("models", "SAP Learning Models"),
            ("candidate_items", "Latest AI Candidate Items"),
        ]
        for index, (key, caption) in enumerate(specs):
            metric_grid.addWidget(self._metric_card(key, caption), index // 3, index % 3)
        root.addLayout(metric_grid)

        self.readiness_notice = QLabel("")
        self.readiness_notice.setWordWrap(True)
        self.readiness_notice.setStyleSheet(
            "background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;"
            "border-radius:10px;padding:10px 12px;font-weight:800;"
        )
        root.addWidget(self.readiness_notice)

        actions = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh AI Dashboard")
        self.refresh_btn.setMinimumHeight(40)
        self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_btn)

        self.train_btn = QPushButton("Reconcile + Train Models")
        self.train_btn.setMinimumHeight(40)
        self.train_btn.clicked.connect(lambda: self._start_worker("TRAIN"))
        actions.addWidget(self.train_btn)

        self.generate_btn = QPushButton("Generate Next-Day AI Candidate")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setStyleSheet(
            "background:#2563eb;color:white;border:none;border-radius:8px;"
            "font-weight:950;padding:0 18px;"
        )
        self.generate_btn.clicked.connect(lambda: self._start_worker("GENERATE"))
        actions.addWidget(self.generate_btn)
        actions.addStretch()
        root.addLayout(actions)

        tabs = QTabWidget()
        self.candidate_table = self._table(
            [
                "Priority",
                "SAP",
                "Description",
                "Shipment Demand",
                "Planning Stock",
                "Net Requirement",
                "Learned Completion",
                "AI Day",
                "AI Night",
                "AI Total",
                "Expected Actual",
                "Blended Capacity",
                "Learned Safe Capacity",
                "Planner Policy",
                "Confidence",
                "Band",
                "Status",
                "Explanation",
            ]
        )
        self.actual_table = self._table(
            [
                "Date",
                "SAP",
                "Description",
                "Plan Day",
                "Plan Night",
                "Plan Total",
                "Actual Day",
                "Actual Night",
                "Actual Total",
                "Variance",
                "Achievement %",
                "Status",
            ]
        )
        self.evaluation_table = self._table(
            [
                "Plan Date",
                "AI Run",
                "SAP",
                "AI Plan",
                "AI Expected Actual",
                "Final Excel Plan",
                "Actual",
                "AI vs Final Error %",
                "AI Expected vs Actual Error %",
                "Status",
            ]
        )
        self.model_table = self._table(
            [
                "SAP",
                "Samples",
                "Champion Model",
                "Completion Ratio",
                "Conservative",
                "Day Share",
                "WAPE %",
                "Recent WAPE %",
                "Validation Accuracy %",
                "Drift",
                "Confidence",
                "Band",
                "Last Trained",
            ]
        )
        tabs.addTab(self.candidate_table, "Next-Day AI Candidate")
        tabs.addTab(self.actual_table, "Final Plan vs Actual")
        tabs.addTab(self.evaluation_table, "AI vs Final / Actual")
        tabs.addTab(self.model_table, "Model Health")
        root.addWidget(tabs, 1)

    def _metric_card(self, key: str, caption: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:white;border:1px solid #dbe4ef;border-radius:10px;}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        value = QLabel("0")
        value.setStyleSheet("font-size:20px;font-weight:950;color:#0f172a;")
        label = QLabel(caption)
        label.setWordWrap(True)
        label.setStyleSheet("font-size:10px;font-weight:800;color:#64748b;")
        layout.addWidget(value)
        layout.addWidget(label)
        self.metrics[key] = value
        return card

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet(
            "QTableWidget{border:1px solid #dbe4ef;background:white;gridline-color:#e2e8f0;}"
            "QHeaderView::section{background:#f8fafc;color:#334155;font-weight:900;"
            "border:0;border-bottom:1px solid #cbd5e1;padding:7px;}"
        )
        return table

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        try:
            with get_session() as session:
                dashboard = self.service.dashboard(session)
        except Exception as exc:
            QMessageBox.critical(self, "AI Planning Dashboard", str(exc))
            return

        readiness = dashboard.get("readiness", {})
        try:
            with get_session() as session:
                source = OperationalSourceService.latest(session)
            if source.plan_date:
                self.source_badge.setText(f"Live OVEN: {source.plan_date.isoformat()}")
                self.source_badge.setToolTip(source.workbook_name or source.label)
            else:
                self.source_badge.setText("Live OVEN: not imported")
        except Exception:
            self.source_badge.setText("Live OVEN: unknown")
        mode = str(readiness.get("mode") or "SHADOW")
        eligible = bool(readiness.get("eligible_for_supervised_auto"))
        self.mode_badge.setText(
            f"{mode} / {'AUTO-ELIGIBLE' if eligible else 'LEARNING'}"
        )
        self.metrics["validation_days"].setText(f"{int(readiness.get('validation_days', 0) or 0):,}")
        self.metrics["accuracy"].setText(f"{float(readiness.get('accuracy_pct', 0) or 0):.1f}%")
        self.metrics["coverage"].setText(f"{float(readiness.get('coverage_pct', 0) or 0):.1f}%")
        self.metrics["high"].setText(f"{int(readiness.get('high_confidence_items', 0) or 0):,}")
        self.metrics["models"].setText(f"{int(readiness.get('total_models', 0) or 0):,}")
        latest_run = dashboard.get("latest_run") or {}
        self.metrics["candidate_items"].setText(f"{int(latest_run.get('item_count', 0) or 0):,}")
        self.readiness_notice.setText(
            str(readiness.get("explanation") or "")
            + f" Accuracy basis: {readiness.get('accuracy_basis', 'MODEL_BACKTEST_ONLY')}."
        )

        self._fill(
            self.candidate_table,
            [
                [
                    _num(r.get("priority_score"), 1),
                    r.get("sap_code"),
                    r.get("item_description"),
                    r.get("shipment_demand_qty"),
                    r.get("current_stock_qty"),
                    r.get("net_requirement_qty"),
                    _pct_ratio(r.get("learned_completion_ratio")),
                    r.get("recommended_day_qty"),
                    r.get("recommended_night_qty"),
                    r.get("recommended_total_qty"),
                    r.get("expected_actual_qty"),
                    r.get("daily_capacity_qty"),
                    r.get("learned_capacity_qty"),
                    _num(r.get("planner_policy_ratio"), 3),
                    _pct_ratio(r.get("confidence_score")),
                    r.get("confidence_band"),
                    r.get("status"),
                    r.get("explanation"),
                ]
                for r in dashboard.get("plan_items", [])
            ],
        )
        self._fill(
            self.actual_table,
            [
                [
                    r.get("production_date"),
                    r.get("sap_code"),
                    r.get("item_description"),
                    r.get("plan_day_qty"),
                    r.get("plan_night_qty"),
                    r.get("plan_total_qty"),
                    r.get("actual_day_qty"),
                    r.get("actual_night_qty"),
                    r.get("actual_total_qty"),
                    r.get("variance_qty"),
                    _num(r.get("achievement_pct"), 1),
                    r.get("status"),
                ]
                for r in dashboard.get("reconciliation", [])
            ],
        )
        self._fill(
            self.evaluation_table,
            [
                [
                    r.get("plan_date"),
                    r.get("ai_run_id"),
                    r.get("sap_code"),
                    r.get("ai_recommended_total_qty"),
                    r.get("ai_expected_actual_qty"),
                    r.get("final_excel_total_qty"),
                    r.get("actual_total_qty"),
                    _num(r.get("ai_vs_final_error_pct"), 1) if r.get("ai_vs_final_error_pct") is not None else "",
                    _num(r.get("ai_expected_vs_actual_error_pct"), 1) if r.get("ai_expected_vs_actual_error_pct") is not None else "",
                    r.get("evaluation_status"),
                ]
                for r in dashboard.get("evaluations", [])
            ],
        )
        model_rows = []
        for r in dashboard.get("models", []):
            payload = r.get("model_json") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            model_rows.append(
                [
                    r.get("sap_code"),
                    r.get("sample_days"),
                    payload.get("champion_model", "LEGACY/FALLBACK"),
                    _num(r.get("ewma_completion_ratio"), 3),
                    _num(payload.get("conservative_completion_ratio"), 3),
                    _pct_ratio(r.get("day_share")),
                    _num(r.get("mape_pct"), 1),
                    _num(payload.get("recent_wape_pct"), 1),
                    _num(r.get("validation_accuracy_pct"), 1),
                    _pct_ratio(payload.get("drift_score")),
                    _pct_ratio(r.get("confidence_score")),
                    r.get("confidence_band"),
                    r.get("last_trained_at"),
                ]
            )
        self._fill(self.model_table, model_rows)

    def _start_worker(self, action: str) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.train_btn.setEnabled(False)
        self.generate_btn.setEnabled(False)
        self.mode_badge.setText("AI MODEL RUNNING")
        self.worker = _AIWorker(action)
        self.worker.setParent(self)
        self.worker.completed.connect(self._worker_complete)
        self.worker.failed.connect(self._worker_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _worker_finished(self) -> None:
        self.worker = None
        self.train_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)

    def _worker_complete(self, result: dict[str, Any]) -> None:
        self.train_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.refresh()
        message = (
            f"Models trained: {int(result.get('ai_models_trained', 0) or 0):,}. "
            f"Reconciled rows: {int(result.get('plan_actual_reconciled_rows', 0) or 0):,}."
        )
        if result.get("ai_plan_run_id"):
            message += (
                f" AI candidate #{result['ai_plan_run_id']} generated for "
                f"{result.get('ai_plan_date')} with {int(result.get('ai_plan_items', 0) or 0):,} items."
            )
        message += " Excel plan remains the final execution plan."
        QMessageBox.information(self, "AI Planning Cycle Complete", message)

    def _worker_failed(self, reason: str) -> None:
        self.train_btn.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.mode_badge.setText("AI RUN FAILED")
        QMessageBox.critical(self, "AI Planning Error", reason)

    @staticmethod
    def _fill(table: QTableWidget, rows: list[list[Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))
        table.setSortingEnabled(True)


def _num(value: Any, digits: int = 0) -> str:
    try:
        return f"{float(value or 0):,.{digits}f}"
    except Exception:
        return str(value or "")


def _pct_ratio(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100.0:.1f}%"
    except Exception:
        return ""
