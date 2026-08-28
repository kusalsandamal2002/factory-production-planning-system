from __future__ import annotations

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
from app.services.current_stock_service import CurrentStockService


class _CurrentStockWorker(QThread):
    completed = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, job_id: int):
        super().__init__()
        self.job_id = int(job_id)

    def run(self) -> None:
        try:
            with get_session() as session:
                payload = CurrentStockService.latest_view(session)
            self.completed.emit(self.job_id, payload)
        except Exception as exc:
            self.failed.emit(self.job_id, str(exc))


class CurrentStockPage(QWidget):
    """Latest committed OVEN current stock from PROD HR:HV."""

    RENDER_BATCH = 120

    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.on_back = on_back
        self._job_seq = 0
        self._latest_job = 0
        self._workers: dict[int, _CurrentStockWorker] = {}
        self._rows: list[dict[str, Any]] = []
        self._render_token = 0

        self._build_controls()
        self._apply_styles()
        self._build_ui()
        QTimer.singleShot(0, self.refresh)

    def _build_controls(self) -> None:
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP code or material description...")
        self.search_input.textChanged.connect(self._render_rows)

        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("StockFilter")
        self.filter_combo.addItems(list(CurrentStockService.FILTER_OPTIONS))
        self.filter_combo.setMinimumWidth(155)
        self.filter_combo.currentTextChanged.connect(self._render_rows)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.source_badge = QLabel("LATEST OVEN\nLOADING")
        self.source_badge.setObjectName("SourceBadge")

        self.metric_items = QLabel("0")
        self.metric_ship = QLabel("0")
        self.metric_stock = QLabel("0")
        self.metric_balance = QLabel("0")

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("ProgressCard")
        progress_layout = QHBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(14, 8, 14, 8)
        self.progress_label = QLabel("Loading latest OVEN current stock...")
        self.progress_label.setObjectName("ProgressText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(280)
        progress_layout.addWidget(self.progress_label, 1)
        progress_layout.addWidget(self.progress_bar)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "No.",
                "SAP Code",
                "Material Description",
                "Total To be Shipped",
                "Current Stock",
                "Progress %",
                "Balance to Produce",
                "Total Plan",
                "Total To be Plan",
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
            1: 120,
            3: 145,
            4: 120,
            5: 100,
            6: 145,
            7: 110,
            8: 135,
        }.items():
            self.table.setColumnWidth(column, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard, QFrame#ControlCard, QFrame#MetricCard,
            QFrame#TableCard, QFrame#ProgressCard {
                background:#ffffff; border:1px solid #dbe4f0; border-radius:14px;
            }
            QLabel#Breadcrumb { color:#2563eb; font-size:9pt; font-weight:900; }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
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
            QLineEdit, QComboBox {
                background:#ffffff; border:1px solid #cbd5e1; border-radius:8px;
                padding:7px 9px; color:#0f172a; font-weight:650; min-height:22px;
            }
            QComboBox#StockFilter {
                padding-right:24px;
            }
            QComboBox#StockFilter:hover {
                border-color:#94a3b8;
            }
            QComboBox QAbstractItemView {
                background:#ffffff; color:#0f172a; border:1px solid #cbd5e1;
                selection-background-color:#dbeafe; selection-color:#0f172a;
                padding:4px;
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
        left = QVBoxLayout()
        left.setSpacing(2)
        crumb = QLabel("Master Data  /  Stock Master  /  Current Stock")
        crumb.setObjectName("Breadcrumb")
        title = QLabel("Current Stock")
        title.setObjectName("PageTitle")
        left.addWidget(crumb)
        left.addWidget(title)
        back = QPushButton("Back")
        if self.on_back is not None:
            back.clicked.connect(self.on_back)
        else:
            back.setEnabled(False)
        header_row.addLayout(left, 1)
        header_row.addWidget(back)
        root.addWidget(header)

        controls = QFrame()
        controls.setObjectName("ControlCard")
        control_row = QHBoxLayout(controls)
        control_row.setContentsMargins(14, 10, 14, 10)
        control_row.setSpacing(9)
        control_row.addWidget(self.search_input, 1)
        control_row.addWidget(self.filter_combo)
        control_row.addWidget(self.source_badge)
        control_row.addWidget(self.refresh_btn)
        root.addWidget(controls)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        for value, label in (
            (self.metric_items, "Items"),
            (self.metric_ship, "Total To be Shipped"),
            (self.metric_stock, "Current Stock"),
            (self.metric_balance, "Balance to Produce"),
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

    def refresh(self, *_args) -> None:
        self._job_seq += 1
        job_id = self._job_seq
        self._latest_job = job_id
        worker = _CurrentStockWorker(job_id)
        self._workers[job_id] = worker
        worker.completed.connect(self._worker_completed)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(lambda job=job_id: self._workers.pop(job, None))
        self.progress_label.setText("Loading latest committed OVEN workbook...")
        self.progress_panel.show()
        self.refresh_btn.setEnabled(False)
        worker.start()

    def _worker_completed(self, job_id: int, payload: object) -> None:
        if job_id != self._latest_job:
            return
        self.progress_panel.hide()
        self.refresh_btn.setEnabled(True)
        data = dict(payload or {})
        self._rows = list(data.get("rows") or [])
        source = dict(data.get("source") or {})

        if source:
            source_date = source.get("plan_date") or "-"
            self.source_badge.setText(f"LATEST OVEN\n{source_date}")
            self.source_badge.setToolTip(
                f"Workbook: {source.get('workbook_name') or '-'}\n"
                f"Sheet/columns: PROD HR:HV"
            )
        else:
            self.source_badge.setText("LATEST OVEN\nNO DATA")
            self.source_badge.setToolTip(
                "Import a daily OVEN workbook through Intelligent Excel Import."
            )
        self._render_rows()

    def _worker_failed(self, job_id: int, error: str) -> None:
        if job_id != self._latest_job:
            return
        self.progress_panel.hide()
        self.refresh_btn.setEnabled(True)
        self.source_badge.setText("LATEST OVEN\nERROR")
        self.source_badge.setToolTip(error)
        self._rows = []
        self._render_rows()

    def _render_rows(self, *_args) -> None:
        rows = CurrentStockService.filter_rows(
            self._rows,
            query=self.search_input.text(),
            filter_mode=self.filter_combo.currentText(),
        )
        self._update_metrics(rows)
        self._render_token += 1
        token = self._render_token
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        self.table.setUpdatesEnabled(True)
        self._render_batch(rows, 0, token)

    def _update_metrics(self, rows: list[dict[str, Any]]) -> None:
        summary = CurrentStockService.summarize_rows(rows)
        self.metric_items.setText(f"{int(summary.get('items') or 0):,}")
        self.metric_ship.setText(
            f"{int(summary.get('total_to_be_shipped') or 0):,}"
        )
        self.metric_stock.setText(
            f"{int(summary.get('current_stock') or 0):,}"
        )
        self.metric_balance.setText(
            f"{int(summary.get('balance_to_produce') or 0):,}"
        )

    def _render_batch(
        self,
        rows: list[dict[str, Any]],
        start: int,
        token: int,
    ) -> None:
        if token != self._render_token:
            return
        end = min(len(rows), start + self.RENDER_BATCH)
        self.table.setUpdatesEnabled(False)
        for index in range(start, end):
            row = rows[index]
            shipment = int(row.get("total_to_be_shipped") or 0)
            progress = row.get("progress_percent")
            values = [
                index + 1,
                row.get("sap_code") or "",
                row.get("item_description") or "",
                "-" if shipment <= 0 else shipment,
                int(row.get("current_stock") or 0),
                "-" if shipment <= 0 or progress is None else f"{float(progress):.1f}%",
                int(row.get("balance_to_produce") or 0),
                int(row.get("total_plan") or 0),
                int(row.get("total_to_be_plan") or 0),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(
                    f"{value:,}" if isinstance(value, int) else str(value)
                )
                if column in {0, 3, 4, 5, 6, 7, 8}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(index, column, item)
        self.table.setUpdatesEnabled(True)
        if end < len(rows) and token == self._render_token:
            QTimer.singleShot(0, lambda: self._render_batch(rows, end, token))
