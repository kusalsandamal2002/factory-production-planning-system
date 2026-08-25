from __future__ import annotations

from calendar import month_name
from datetime import date
from typing import Any, Callable

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.monthly_stock_snapshot_service import MonthlyStockSnapshotService


class _MonthlyStockWorker(QThread):
    completed = Signal(int, str, object)
    failed = Signal(int, str, str)

    def __init__(self, job_id: int, action: str, month_key: str = ""):
        super().__init__()
        self.job_id = int(job_id)
        self.action = action
        self.month_key = month_key

    def run(self) -> None:
        try:
            with get_session() as session:
                service = MonthlyStockSnapshotService()
                service.ensure_schema(session)
                if self.action == "months":
                    service.bootstrap_from_committed_imports(session)
                    payload = service.list_month_keys(session)
                elif self.action == "month":
                    payload = service.month_view(session, self.month_key)
                else:
                    payload = None
            self.completed.emit(self.job_id, self.action, payload)
        except Exception as exc:
            self.failed.emit(self.job_id, self.action, str(exc))


class MonthlyStockPage(QWidget):
    """Monthly OVEN stock history with deterministic authority + advisory ML."""

    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.on_back = on_back
        self._job_seq = 0
        self._workers: dict[int, _MonthlyStockWorker] = {}
        self._latest_job: dict[str, int] = {}
        self._available_months: list[str] = []
        self._rows: list[dict[str, Any]] = []

        self._build_controls()
        self._apply_styles()
        self._build_ui()
        QTimer.singleShot(0, self._load_month_index)

    def _build_controls(self) -> None:
        self.year_combo = QComboBox()
        self.month_combo = QComboBox()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP code or material description...")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.source_badge = QLabel("OVEN SOURCE\nLOADING")
        self.source_badge.setObjectName("SourceBadge")

        self.metric_items = QLabel("0")
        self.metric_stock = QLabel("0")
        self.metric_scrap = QLabel("0")
        self.metric_block = QLabel("0")

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("ProgressCard")
        progress_layout = QHBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(14, 8, 14, 8)
        self.progress_label = QLabel("Loading monthly stock...")
        self.progress_label.setObjectName("ProgressText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(280)
        progress_layout.addWidget(self.progress_label, 1)
        progress_layout.addWidget(self.progress_bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                "No.",
                "SAP Code",
                "Material Description",
                "Total Stock",
                "Scrap",
                "Block",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSortingEnabled(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in {
            0: 55,
            1: 125,
            3: 125,
            4: 100,
            5: 100,
        }.items():
            self.table.setColumnWidth(column, width)

        current_year = str(date.today().year)
        self.year_combo.addItem(current_year)
        for month in range(1, 13):
            self.month_combo.addItem(month_name[month], month)
        self.month_combo.setCurrentIndex(date.today().month - 1)

        self.year_combo.currentTextChanged.connect(self._on_year_changed)
        self.month_combo.currentIndexChanged.connect(self.refresh)
        self.search_input.textChanged.connect(self._render_rows)
        self.refresh_btn.clicked.connect(self.refresh)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard, QFrame#ControlCard, QFrame#MetricCard,
            QFrame#TableCard, QFrame#ProgressCard {
                background:#ffffff; border:1px solid #dbe4f0; border-radius:14px;
            }
            QLabel#Breadcrumb { color:#2563eb; font-size:9pt; font-weight:900; }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:8.8pt; font-weight:650; }
            QLabel#FieldLabel { color:#334155; font-size:8.5pt; font-weight:900; }
            QLabel#SourceBadge {
                background:#ecfdf5; color:#047857; border:1px solid #a7f3d0;
                border-radius:10px; padding:7px 10px; font-weight:900;
            }
            QLabel#MetricValue { color:#0f172a; font-size:17pt; font-weight:950; }
            QLabel#MetricTitle { color:#64748b; font-size:8.2pt; font-weight:850; }
            QLabel#ProgressText { color:#475569; font-weight:850; }
            QProgressBar {
                background:#e2e8f0; border:1px solid #cbd5e1; border-radius:7px;
                min-height:18px;
            }
            QProgressBar::chunk { background:#2563eb; border-radius:6px; }
            QComboBox, QLineEdit {
                background:#ffffff; border:1px solid #cbd5e1; border-radius:8px;
                padding:7px 9px; color:#0f172a; font-weight:650; min-height:22px;
            }
            QPushButton {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:8px;
                padding:8px 13px; font-weight:850;
            }
            QPushButton:hover { background:#cbd5e1; }
            QPushButton#PrimaryButton { background:#2563eb; color:#ffffff; }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QTableWidget {
                background:#ffffff; alternate-background-color:#f8fafc;
                gridline-color:#dbe4f0; selection-background-color:#dbeafe;
                selection-color:#0f172a; border:1px solid #e2e8f0;
            }
            QTableWidget::item { padding:6px 8px; }
            QHeaderView::section {
                background:#eef2f7; color:#0f172a; border:none;
                border-right:1px solid #dbe4f0; border-bottom:1px solid #dbe4f0;
                padding:7px; font-size:8.5pt; font-weight:900;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("HeaderCard")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(20, 13, 20, 13)
        header_row.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(2)
        crumb = QLabel("Master Data  /  Stock Master  /  Monthly Stock")
        crumb.setObjectName("Breadcrumb")
        title = QLabel("Monthly Stock")
        title.setObjectName("PageTitle")
        hint = QLabel(
            "Official values come only from committed OVEN Excel data. "
            "ML trend, forecast and risk are advisory and never overwrite stock."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        left.addWidget(crumb)
        left.addWidget(title)
        left.addWidget(hint)
        back = QPushButton("Back")
        if self.on_back is not None:
            back.clicked.connect(self.on_back)
        else:
            back.setEnabled(False)
        header_row.addLayout(left, 1)
        header_row.addWidget(self.source_badge)
        header_row.addWidget(back)
        root.addWidget(header)

        controls = QFrame()
        controls.setObjectName("ControlCard")
        control_row = QHBoxLayout(controls)
        control_row.setContentsMargins(14, 10, 14, 10)
        control_row.setSpacing(9)
        control_row.addWidget(self._field_label("Year"))
        control_row.addWidget(self.year_combo)
        control_row.addWidget(self._field_label("Month"))
        control_row.addWidget(self.month_combo)
        control_row.addWidget(self.search_input, 1)
        control_row.addWidget(self.refresh_btn)
        root.addWidget(controls)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        for value, label in (
            (self.metric_items, "Items"),
            (self.metric_stock, "Total Stock"),
            (self.metric_scrap, "Scrap"),
            (self.metric_block, "Block"),
        ):
            metrics.addWidget(self._metric_card(value, label), 1)
        root.addLayout(metrics)

        root.addWidget(self.progress_panel)
        self.progress_panel.hide()

        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.addWidget(self.table)
        root.addWidget(table_card, 1)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    @staticmethod
    def _metric_card(value: QLabel, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        value.setObjectName("MetricValue")
        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")
        layout.addWidget(value)
        layout.addWidget(title_label)
        return card

    def _start_worker(self, action: str, month_key: str = "") -> None:
        self._job_seq += 1
        job_id = self._job_seq
        self._latest_job[action] = job_id
        worker = _MonthlyStockWorker(job_id, action, month_key)
        self._workers[job_id] = worker
        worker.completed.connect(self._worker_completed)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(lambda job=job_id: self._workers.pop(job, None))
        self.progress_label.setText(
            "Loading available months..." if action == "months" else f"Loading {month_key} stock..."
        )
        self.progress_panel.show()
        worker.start()

    def _load_month_index(self) -> None:
        self._start_worker("months")

    def _worker_completed(self, job_id: int, action: str, payload: object) -> None:
        if self._latest_job.get(action) != job_id:
            return
        if action == "months":
            self._apply_month_index(list(payload or []))
            return
        if action == "month":
            self.progress_panel.hide()
            self._apply_month_payload(dict(payload or {}))

    def _worker_failed(self, job_id: int, action: str, error: str) -> None:
        if self._latest_job.get(action) != job_id:
            return
        self.progress_panel.hide()
        self.source_badge.setText("OVEN SOURCE\nERROR")
        self.source_badge.setToolTip(error)
        if action == "month":
            self._rows = []
            self._render_rows()

    def _apply_month_index(self, month_keys: list[str]) -> None:
        self._available_months = sorted(
            {key for key in month_keys if len(key) == 7 and key[4] == "-"},
            reverse=True,
        )
        latest = self._available_months[0] if self._available_months else date.today().strftime("%Y-%m")
        available_years = {key[:4] for key in self._available_months}
        available_years.add(str(date.today().year))

        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in sorted(available_years, reverse=True):
            self.year_combo.addItem(year)
        self.year_combo.setCurrentText(latest[:4])
        self.year_combo.blockSignals(False)

        self.month_combo.blockSignals(True)
        self.month_combo.setCurrentIndex(max(0, int(latest[5:7]) - 1))
        self.month_combo.blockSignals(False)
        self.refresh()

    def _on_year_changed(self, _value: str) -> None:
        self.refresh()

    def _selected_month_key(self) -> str:
        year = self.year_combo.currentText().strip() or str(date.today().year)
        month = int(self.month_combo.currentData() or date.today().month)
        return f"{year}-{month:02d}"

    def refresh(self, *_args) -> None:
        if not self.year_combo.count() or not self.month_combo.count():
            return
        self._start_worker("month", self._selected_month_key())

    def _apply_month_payload(self, payload: dict[str, Any]) -> None:
        self._rows = list(payload.get("rows") or [])
        source = payload.get("source") or {}
        summary = payload.get("summary") or {}

        self.metric_items.setText(f"{int(summary.get('items') or 0):,}")
        self.metric_stock.setText(f"{int(summary.get('total_stock') or 0):,}")
        self.metric_scrap.setText(f"{int(summary.get('scrap') or 0):,}")
        self.metric_block.setText(f"{int(summary.get('blocked') or 0):,}")

        if source:
            status = str(source.get("status") or source.get("source_kind") or "-")
            source_date = source.get("source_plan_date") or "-"
            self.source_badge.setText(f"{status}\n{source_date}")
            self.source_badge.setToolTip(
                f"Workbook: {source.get('workbook_name') or '-'}\n"
                f"Columns: {source.get('source_columns') or '-'}\n"
                f"Import mode: {source.get('import_mode') or '-'}"
            )
        else:
            self.source_badge.setText("NO STOCK DATA\nSELECTED MONTH")
            self.source_badge.setToolTip(
                "Import the normal daily OVEN workbook through Intelligent Excel Import."
            )
        self._render_rows()

    def _render_rows(self, *_args) -> None:
        query = self.search_input.text().strip().lower()
        rows = [
            row
            for row in self._rows
            if not query
            or query in str(row.get("sap_code") or "").lower()
            or query in str(row.get("item_description") or "").lower()
        ]
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [
                index + 1,
                row.get("sap_code") or "",
                row.get("item_description") or "",
                int(row.get("total_stock") or 0),
                int(row.get("scrap_qty") or 0),
                int(row.get("blocked_qty") or 0),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(
                    f"{value:,}" if isinstance(value, int) else str(value)
                )
                if column in {0, 3, 4, 5}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(index, column, item)
