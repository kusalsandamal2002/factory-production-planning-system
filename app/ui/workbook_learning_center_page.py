from __future__ import annotations

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

from app.database import get_session
from app.services.production_learning_service import (
    ProductionLearningService,
)


# INTELLIGENT CONTINUOUS EXCEL SYNC + LEARNING FOUNDATION V7.0


class _LearningWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            result = ProductionLearningService().rebuild_all()
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class WorkbookLearningCenterPage(QWidget):
    """Explainable local learning dashboard.

    Models remain advisory. Workbook plan signals are never treated as verified
    actual production unless the source semantics explicitly say so.
    """

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.service = ProductionLearningService()
        self.worker: _LearningWorker | None = None
        self.metric_values: dict[str, QLabel] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AI / ML Learning Center")
        title.setStyleSheet(
            "font-size:27px;font-weight:950;color:#0f172a;"
        )
        subtitle = QLabel(
            "Local learning mode for recurring OVEN workbooks: demand signals, "
            "production signals, confidence-scored advisory models, Excel-vs-app "
            "reconciliation and feedback history. No model changes the live "
            "production schedule automatically."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#52627a;font-size:12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.status_badge = QLabel("ADVISORY LEARNING MODE")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setMinimumWidth(205)
        self.status_badge.setStyleSheet(
            "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;"
            "border-radius:16px;padding:9px 14px;font-weight:900;"
        )
        header.addWidget(self.status_badge)
        root.addLayout(header)

        metrics = QGridLayout()
        metrics.setSpacing(10)
        specs = [
            ("observations", "Learning Observations"),
            ("workbook_runs", "Workbook Runs"),
            ("models", "Advisory Models"),
            ("high_confidence", "High Confidence"),
            ("feedback_rows", "Feedback Records"),
            ("reconciliation_reviews", "Reconciliation Review"),
        ]
        for index, (key, caption) in enumerate(specs):
            metrics.addWidget(
                self._metric_card(key, caption),
                index // 6,
                index % 6,
            )
        root.addLayout(metrics)

        notice = QLabel(
            "Reliability rule: three monthly workbooks are enough for importer and "
            "model-pipeline validation, but not for autonomous forecasting. Demand "
            "forecast confidence becomes meaningful after roughly 12 comparable "
            "months. Production-rate models need actual line/oven/shift output, "
            "downtime, scrap and changeover data."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;"
            "border-radius:9px;padding:10px;font-weight:750;"
        )
        root.addWidget(notice)

        actions = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Learning Dashboard")
        self.refresh_btn.setMinimumHeight(40)
        self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_btn)

        self.rebuild_btn = QPushButton("Rebuild Advisory Models")
        self.rebuild_btn.setMinimumHeight(40)
        self.rebuild_btn.setStyleSheet(
            "background:#1d4ed8;color:white;font-weight:900;padding:0 18px;"
        )
        self.rebuild_btn.clicked.connect(self.rebuild_models)
        actions.addWidget(self.rebuild_btn)
        actions.addStretch()
        root.addLayout(actions)

        tabs = QTabWidget()
        self.models_table = self._table(
            [
                "Model Type",
                "Entity",
                "Samples",
                "Prediction",
                "Lower",
                "Upper",
                "Confidence",
                "Band",
                "Advisory",
                "Last Trained",
                "Explanation",
            ]
        )
        self.reconciliation_table = self._table(
            [
                "Import Run",
                "Plan Date",
                "SAP",
                "Excel Demand",
                "App Demand",
                "Demand Var",
                "Excel Required",
                "App Required",
                "Required Var",
                "Excel Plan",
                "App Capacity",
                "Plan Var",
                "Status",
                "Explanation",
            ]
        )
        tabs.addTab(self.models_table, "Advisory Models")
        tabs.addTab(
            self.reconciliation_table,
            "Excel vs App Reconciliation",
        )
        root.addWidget(tabs, 1)

    def _metric_card(self, key: str, caption: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:white;border:1px solid #dbe4ef;"
            "border-radius:10px;}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        value = QLabel("0")
        value.setStyleSheet(
            "font-size:21px;font-weight:950;color:#0f172a;"
        )
        label = QLabel(caption)
        label.setWordWrap(True)
        label.setStyleSheet(
            "font-size:10px;font-weight:800;color:#64748b;"
        )
        layout.addWidget(value)
        layout.addWidget(label)
        self.metric_values[key] = value
        return card

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.setStyleSheet(
            "QTableWidget{border:1px solid #dbe4ef;background:white;"
            "gridline-color:#e2e8f0;}"
            "QHeaderView::section{background:#f8fafc;color:#334155;"
            "font-weight:900;border:0;border-bottom:1px solid #cbd5e1;"
            "padding:7px;}"
        )
        return table

    def refresh(self) -> None:
        try:
            with get_session() as session:
                dashboard = self.service.get_dashboard(session)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Learning Dashboard Error",
                str(exc),
            )
            return

        metrics = dashboard.get("metrics", {})
        for key, label in self.metric_values.items():
            label.setText(
                f"{int(metrics.get(key, 0) or 0):,}"
            )

        self._fill_table(
            self.models_table,
            [
                [
                    row.get("model_type"),
                    row.get("entity_key"),
                    row.get("sample_count"),
                    _display_number(row.get("prediction")),
                    _display_number(row.get("lower_bound")),
                    _display_number(row.get("upper_bound")),
                    _display_percent(row.get("confidence_score")),
                    row.get("confidence_band"),
                    "YES" if row.get("is_advisory_only") else "NO",
                    row.get("last_trained_at"),
                    row.get("explanation"),
                ]
                for row in dashboard.get("models", [])
            ],
        )
        self._fill_table(
            self.reconciliation_table,
            [
                [
                    row.get("import_run_id"),
                    row.get("plan_date"),
                    row.get("sap_code"),
                    row.get("excel_shipment_demand"),
                    row.get("app_live_demand"),
                    row.get("demand_variance"),
                    row.get("excel_production_required"),
                    row.get("app_production_required"),
                    row.get("production_variance"),
                    row.get("excel_planned_qty"),
                    row.get("app_daily_capacity"),
                    row.get("plan_variance"),
                    row.get("reconciliation_status"),
                    row.get("explanation"),
                ]
                for row in dashboard.get("reconciliation", [])
            ],
        )

    def rebuild_models(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.rebuild_btn.setEnabled(False)
        self.status_badge.setText("REBUILDING MODELS")
        self.worker = _LearningWorker()
        self.worker.completed.connect(self._rebuild_complete)
        self.worker.failed.connect(self._rebuild_failed)
        self.worker.start()

    def _rebuild_complete(self, result: dict[str, Any]) -> None:
        self.rebuild_btn.setEnabled(True)
        self.status_badge.setText("ADVISORY LEARNING MODE")
        self.refresh()
        QMessageBox.information(
            self,
            "Learning Models Rebuilt",
            (
                f"Advisory models rebuilt: "
                f"{int(result.get('models_total', 0) or 0):,}. "
                "No live production schedule was changed."
            ),
        )

    def _rebuild_failed(self, reason: str) -> None:
        self.rebuild_btn.setEnabled(True)
        self.status_badge.setText("MODEL REBUILD FAILED")
        QMessageBox.critical(
            self,
            "Learning Model Error",
            reason,
        )

    @staticmethod
    def _fill_table(
        table: QTableWidget,
        rows: list[list[Any]],
    ) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                table.setItem(
                    row,
                    column,
                    QTableWidgetItem(
                        "" if value is None else str(value)
                    ),
                )
        table.setSortingEnabled(True)


def _display_number(value: Any) -> str:
    try:
        number = float(value or 0)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}"
    except Exception:
        return str(value or "")


def _display_percent(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except Exception:
        return ""
