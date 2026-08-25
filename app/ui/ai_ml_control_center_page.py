from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.core.task_manager import TaskManager


class _ModelTable(QAbstractTableModel):
    COLUMNS = (
        ("Area", "area"),
        ("Model", "model_name"),
        ("Status", "status"),
        ("Training Rows", "training_rows"),
        ("History Days", "history_days"),
        ("Readiness %", "readiness_score"),
        ("Version", "model_version"),
        ("Last Trained", "last_trained_at"),
        ("Last Data Update", "last_data_update"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows or [])
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.COLUMNS)
        ):
            return self.COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        key = self.COLUMNS[index.column()][1]
        row = self.rows[index.row()]
        value = row.get(key)

        if role == Qt.ItemDataRole.DisplayRole:
            if value in (None, ""):
                return "—"
            if key == "readiness_score":
                try:
                    return f"{float(value):.1f}%"
                except Exception:
                    return "—"
            return str(value)

        if role == Qt.ItemDataRole.ForegroundRole and key == "status":
            status = str(value or "").upper()
            if status in {"TRAINED", "READY", "ACTIVE", "CHAMPION"}:
                return QColor("#047857")
            if status in {"LEARNING", "REGISTERED", "NEEDS TRAINING"}:
                return QColor("#b45309")
            if status == "NEEDS DATA":
                return QColor("#b91c1c")
            return QColor("#475569")

        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and key not in {"model_name", "area"}
        ):
            return int(
                Qt.AlignmentFlag.AlignCenter
                | Qt.AlignmentFlag.AlignVCenter
            )

        return None


class _ReadinessTable(QAbstractTableModel):
    COLUMNS = (
        ("Model Key", "model_key"),
        ("Ready", "ready_to_train"),
        ("Source", "source_table"),
        ("Target", "target"),
        ("History Days", "history_days"),
        ("Target Rows", "target_rows"),
        ("Metric", "metric_name"),
        ("Gate", "promotion_threshold"),
        ("Reason", "reason"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows or [])
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.COLUMNS)
        ):
            return self.COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = self.COLUMNS[index.column()][1]
        row = self.rows[index.row()]
        value = row.get(key)

        if role == Qt.ItemDataRole.DisplayRole:
            if key == "ready_to_train":
                return "READY" if bool(value) else "NOT READY"
            if value in (None, ""):
                return "—"
            return str(value)

        if role == Qt.ItemDataRole.ForegroundRole and key == "ready_to_train":
            return QColor("#047857" if bool(value) else "#b45309")

        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and key not in {"model_key", "source_table", "target", "reason"}
        ):
            return int(
                Qt.AlignmentFlag.AlignCenter
                | Qt.AlignmentFlag.AlignVCenter
            )
        return None


class AIMLControlCenterPage(QWidget):
    """One user-facing home for MPPS AI/ML and the Excel/data pipeline.

    Model state is advisory. Operational stock, demand, capacity and saved-plan
    values remain PostgreSQL/committed-source authority.
    """

    TASK_KEY = "ai-ml-r6:model-snapshot"

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.tasks = TaskManager.instance()
        self._refresh_running = False
        self._pipeline_page = None
        self.model = _ModelTable(self)
        self.history_model = _ModelTable(self)
        self.readiness_model = _ReadinessTable(self)
        self._readiness_running = False
        self._training_running = False
        self._build_ui()
        QTimer.singleShot(250, self.refresh_async)

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget { font-family:"Segoe UI"; }
            QFrame#Header, QFrame#Metric, QFrame#Panel {
                background:#fff; border:1px solid #dbe4ef; border-radius:16px;
            }
            QLabel#Title { color:#0f172a; font-size:24pt; font-weight:950; }
            QLabel#Sub { color:#64748b; font-size:9pt; font-weight:650; }
            QLabel#MetricValue { color:#0f172a; font-size:20pt; font-weight:950; }
            QLabel#MetricTitle { color:#64748b; font-size:8.4pt; font-weight:850; }
            QLabel#Status {
                background:#f8fafc; color:#475569; border:1px solid #e2e8f0;
                border-radius:8px; padding:7px 10px; font-weight:750;
            }
            QPushButton {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:9px;
                padding:9px 13px; font-weight:900;
            }
            QTableView {
                background:#fff; alternate-background-color:#f8fafc;
                border:1px solid #dbe4ef; gridline-color:#e2e8f0;
            }
            QHeaderView::section {
                background:#edf3f9; color:#1e293b; border:none;
                border-right:1px solid #dbe4ef; border-bottom:1px solid #dbe4ef;
                padding:8px; font-weight:950;
            }
            QTabBar::tab {
                background:#f1f5f9; color:#475569; padding:9px 15px;
                margin-right:3px; font-weight:850;
            }
            QTabBar::tab:selected { background:#2563eb; color:white; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 14, 20, 14)

        left = QVBoxLayout()
        title = QLabel("AI / ML Control Center")
        title.setObjectName("Title")
        sub = QLabel(
            "All MPPS learning models and the operational Excel/data pipeline in one "
            "workspace. AI predicts and recommends; database facts remain final."
        )
        sub.setObjectName("Sub")
        left.addWidget(title)
        left.addWidget(sub)
        hl.addLayout(left, 1)

        self.validate_btn = QPushButton("Validate Training Readiness")
        self.validate_btn.clicked.connect(self.validate_training_readiness)
        hl.addWidget(self.validate_btn)

        self.train_btn = QPushButton("Train / Retrain Eligible")
        self.train_btn.clicked.connect(self.train_eligible_models)
        hl.addWidget(self.train_btn)

        self.inbox_btn = QPushButton("Open Historical Inbox")
        self.inbox_btn.clicked.connect(self.open_historical_inbox)
        hl.addWidget(self.inbox_btn)

        self.refresh_btn = QPushButton("Refresh Models")
        self.refresh_btn.clicked.connect(self.refresh_async)
        hl.addWidget(self.refresh_btn)
        root.addWidget(header)

        self.metric_values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (key, caption) in enumerate(
            (
                ("total", "Registered Models"),
                ("ready", "Ready / Trained"),
                ("learning", "Needs Training"),
                ("history_days", "Historical Days"),
            )
        ):
            grid.addWidget(self._metric_card(key, caption), 0, i)
        root.addLayout(grid)

        self.status = QLabel(
            "Loading the model registry in the shared background worker pool..."
        )
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        self.progress.hide()
        root.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)

        self.overview = QFrame()
        self.overview.setObjectName("Panel")
        ovl = QVBoxLayout(self.overview)
        ovl.setContentsMargins(16, 14, 16, 14)
        self.overview_text = QLabel(
            "MPPS R6 keeps operational authority deterministic: shipment demand, "
            "current stock, factory resources, saved plans and actual production are "
            "official facts. Historical data trains advisory models through chronological "
            "train / validation / test windows; a model is never marked trained merely "
            "because raw history exists. Use Open Historical Inbox for the bulk R7 final "
            "training workflow, then validate readiness before training eligible models."
        )
        self.overview_text.setWordWrap(True)
        self.overview_text.setStyleSheet(
            "color:#334155;font-weight:750;"
        )
        ovl.addWidget(self.overview_text)
        ovl.addStretch()

        self.models_table = self._model_table(self.model)

        self.pipeline_container = QWidget()
        pcl = QVBoxLayout(self.pipeline_container)
        pcl.setContentsMargins(0, 0, 0, 0)
        self.pipeline_placeholder = QLabel(
            "Open this tab to load Intelligent Excel Import on demand."
        )
        self.pipeline_placeholder.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.pipeline_placeholder.setStyleSheet(
            "color:#64748b;font-weight:800;padding:30px;"
        )
        pcl.addWidget(self.pipeline_placeholder, 1)

        self.readiness_table = QTableView()
        self.readiness_table.setModel(self.readiness_model)
        self.readiness_table.setAlternatingRowColors(True)
        self.readiness_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.readiness_table.verticalHeader().setVisible(False)
        self.readiness_table.verticalHeader().setDefaultSectionSize(34)
        self.readiness_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.readiness_table.horizontalHeader().setSectionResizeMode(
            8,
            QHeaderView.ResizeMode.Stretch,
        )

        self.history_table = self._model_table(self.history_model)

        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.models_table, "Models")
        self.tabs.addTab(
            self.pipeline_container,
            "Data & Excel Pipeline",
        )
        self.tabs.addTab(
            self.readiness_table,
            "Training Readiness",
        )
        self.tabs.addTab(
            self.history_table,
            "Training & History",
        )
        root.addWidget(self.tabs, 1)

    def _metric_card(self, key, caption):
        card = QFrame()
        card.setObjectName("Metric")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        value = QLabel("—")
        value.setObjectName("MetricValue")
        title = QLabel(caption)
        title.setObjectName("MetricTitle")
        self.metric_values[key] = value
        layout.addWidget(value)
        layout.addWidget(title)
        return card

    def _model_table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        return table

    def _tab_changed(self, index):
        if index == 2 and self._pipeline_page is None:
            QTimer.singleShot(0, self._load_pipeline)

    def _load_pipeline(self):
        if self._pipeline_page is not None:
            return

        self.pipeline_placeholder.setText(
            "Loading Intelligent Excel Import..."
        )
        try:
            from app.ui.raw_excel_viewer_page import RawExcelViewerPage

            page = RawExcelViewerPage(self.current_user)
            tabs = getattr(page, "preview_tabs", None)
            if tabs is not None:
                allowed = {
                    "Stock & Demand",
                    "Oven / Shift Plan",
                    "Materials",
                    "Import History",
                }
                for i in range(tabs.count() - 1, -1, -1):
                    if tabs.tabText(i) not in allowed:
                        tabs.removeTab(i)

            layout = self.pipeline_container.layout()
            layout.removeWidget(self.pipeline_placeholder)
            self.pipeline_placeholder.deleteLater()
            layout.addWidget(page)
            self._pipeline_page = page
        except Exception as exc:
            self.pipeline_placeholder.setText(
                "Data & Excel Pipeline could not be loaded: "
                + str(exc)
            )

    def refresh_async(self):
        if self._refresh_running:
            return

        self._refresh_running = True
        self.progress.show()
        self.refresh_btn.setEnabled(False)
        self.status.setText(
            "Reading model registry and historical coverage in background..."
        )

        def load_models():
            from app.services.ml_platform_service import MLPlatformService

            return MLPlatformService.snapshot()

        self.tasks.submit(
            self.TASK_KEY,
            load_models,
            on_result=self._loaded,
            on_error=self._failed,
            replace=True,
        )

    def _loaded(self, payload):
        self._refresh_running = False
        self.progress.hide()
        self.refresh_btn.setEnabled(True)

        data = dict(payload or {})
        rows = list(data.get("models") or [])
        self.model.set_rows(rows)

        history = sorted(
            rows,
            key=lambda row: str(
                row.get("last_trained_at")
                or row.get("last_data_update")
                or ""
            ),
            reverse=True,
        )
        self.history_model.set_rows(history)

        total = int(data.get("total") or len(rows))
        ready = int(data.get("ready") or 0)
        learning = int(data.get("learning") or 0)
        history_days = int(data.get("history_days") or 0)

        self.metric_values["total"].setText(f"{total:,}")
        self.metric_values["ready"].setText(f"{ready:,}")
        self.metric_values["learning"].setText(f"{learning:,}")
        self.metric_values["history_days"].setText(
            f"{history_days:,}"
        )

        if history_days >= 365:
            history_note = (
                f"{history_days:,} historical days are available for "
                "chronological training/validation."
            )
        elif history_days > 0:
            history_note = (
                f"{history_days:,} historical days are available; more history "
                "will improve validation coverage."
            )
        else:
            history_note = (
                "No validated historical span is registered yet."
            )

        self.status.setText(
            f"{ready:,}/{total:,} models currently report ready/trained. "
            f"{history_note} Untrained models remain advisory/inactive."
        )

    def open_historical_inbox(self):
        inbox = Path(__file__).resolve().parents[2] / "ml_workspace" / "historical_inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(inbox))
            else:
                self.status.setText(f"Historical Training Inbox: {inbox}")
                return
            self.status.setText(
                "Historical Training Inbox opened. Copy only OVEN/MPPS .xlsx/.xlsm "
                "history here; the R7 finalizer imports it as historical evidence only."
            )
        except Exception as exc:
            self.status.setText(
                f"Historical Training Inbox: {inbox} • could not open automatically: {exc}"
            )

    def validate_training_readiness(self):
        if self._readiness_running:
            return
        self._readiness_running = True
        self.validate_btn.setEnabled(False)
        self.progress.show()
        self.status.setText(
            "Normalizing historical evidence and running leakage-safe training checks..."
        )

        def readiness_job():
            from app.services.ml_training_orchestrator import (
                MLTrainingOrchestrator,
            )

            return MLTrainingOrchestrator.readiness_report()

        self.tasks.submit(
            "ai-ml-r6:training-readiness",
            readiness_job,
            on_result=self._readiness_loaded,
            on_error=self._readiness_failed,
            priority=2,
            replace=True,
        )

    def _readiness_loaded(self, payload):
        self._readiness_running = False
        self.validate_btn.setEnabled(True)
        self.progress.hide()
        data = dict(payload or {})
        rows = list(data.get("models") or [])
        self.readiness_model.set_rows(rows)
        ready = int(data.get("ready_models") or 0)
        total = int(data.get("total_models") or len(rows))
        dataset = dict(data.get("dataset") or {})
        history_days = int(dataset.get("history_days") or 0)
        critical = int(dataset.get("critical_issue_count") or 0)
        warnings = int(dataset.get("warning_count") or 0)
        self.tabs.setCurrentWidget(self.readiness_table)
        if bool(data.get("ready_for_training")):
            self.status.setText(
                f"Training gate PASS: {ready}/{total} model dataset(s) are ready. "
                f"Validated history {history_days} days • critical issues {critical} • warnings {warnings}."
            )
        else:
            self.status.setText(
                f"Training gate not yet passed: {ready}/{total} model dataset(s) ready. "
                f"Validated history {history_days} days • critical issues {critical} • warnings {warnings}. "
                "Import the historical dataset and resolve listed model reasons before training."
            )

    def train_eligible_models(self):
        if self._training_running:
            return
        self._training_running = True
        self.train_btn.setEnabled(False)
        self.validate_btn.setEnabled(False)
        self.progress.show()
        self.status.setText(
            "Training eligible models in the background. Chronological split, leakage checks, unseen-test gates and champion promotion are enforced."
        )

        def training_job():
            from app.services.ml_training_engine import MLTrainingEngine

            return MLTrainingEngine.train_ready_models(auto_promote=True)

        self.tasks.submit(
            "ai-ml-r6:train-eligible",
            training_job,
            on_result=self._training_loaded,
            on_error=self._training_failed,
            priority=3,
            replace=False,
        )

    def _training_loaded(self, payload):
        self._training_running = False
        self.train_btn.setEnabled(True)
        self.validate_btn.setEnabled(True)
        self.progress.hide()
        data = dict(payload or {})
        attempted = int(data.get("attempted") or 0)
        trained = int(data.get("trained") or 0)
        promoted = int(data.get("promoted") or 0)
        failed = int(data.get("failed") or 0)
        self.status.setText(
            f"Training finished: attempted {attempted} • trained {trained} • champion promoted {promoted} • failed {failed}. "
            "Rejected candidates remain out of production planning authority."
        )
        self.refresh_async()
        QTimer.singleShot(250, self.validate_training_readiness)

    def _training_failed(self, message):
        self._training_running = False
        self.train_btn.setEnabled(True)
        self.validate_btn.setEnabled(True)
        self.progress.hide()
        detail = str(message or "").splitlines()
        reason = detail[-1] if detail else "unknown error"
        self.status.setText("Model training blocked/failed: " + reason)

    def _readiness_failed(self, message):
        self._readiness_running = False
        self.validate_btn.setEnabled(True)
        self.progress.hide()
        detail = str(message or "").splitlines()
        reason = detail[-1] if detail else "unknown error"
        self.status.setText(
            "Training-readiness validation failed: " + reason
        )

    def _failed(self, message):
        self._refresh_running = False
        self.progress.hide()
        self.refresh_btn.setEnabled(True)
        detail = str(message or "").splitlines()
        reason = detail[-1] if detail else "unknown error"
        self.status.setText(
            "Model registry refresh failed: " + reason
        )

    def notify_source_changed(self, *args, **kwargs):
        self.refresh_async()
        if self._pipeline_page is not None:
            for method_name in (
                "refresh_history_async",
                "refresh_history",
                "refresh",
                "refresh_page",
            ):
                method = getattr(
                    self._pipeline_page,
                    method_name,
                    None,
                )
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break

    def refresh(self):
        self.refresh_async()

    refresh_page = refresh
    load_data = refresh


AIMLPage = AIMLControlCenterPage
