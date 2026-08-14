from __future__ import annotations

from typing import Any
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import inspect, text

from app.database import engine, get_session
from app.utils.reports_export import export_to_csv


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


from app.services.stock_control_service import (
    StockMetrics,
    calculate_available_stock,
    stock_status_from_available,
)
from app.services.ai_planning_service import AIPlanningService
from app.services.operational_source_service import OperationalSourceService


class StockEditDialog(QDialog):
    def __init__(self, parent=None, stock_item: dict | None = None):
        super().__init__(parent)
        self.stock_item = stock_item or {}
        self.setWindowTitle("Stock Balance Correction")
        self.setMinimumWidth(680)

        self.sap_code_label = QLabel("-")
        self.description_label = QLabel("-")
        self.current_available_label = QLabel("0")
        self.new_available_label = QLabel("0")

        self.fg_stock_input = self._spin()
        self.qc_stock_input = self._spin()
        self.scrap_stock_input = self._spin()
        self.blocked_stock_input = self._spin()

        for widget in (
            self.fg_stock_input,
            self.qc_stock_input,
            self.scrap_stock_input,
            self.blocked_stock_input,
        ):
            widget.valueChanged.connect(self._refresh_new_available)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText(
            "Required: stock count / SAP correction / QC release / damage / other reason..."
        )

        self.save_btn = QPushButton("Save Stock Correction")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self._validate_and_accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        self._apply_styles()
        self._build_ui()
        self._load_stock_item()

    @staticmethod
    def _spin() -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(0, 999999999)
        widget.setGroupSeparatorShown(True)
        return widget

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background:#f8fafc; font-family:"Segoe UI"; }
            QFrame#Card { background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; }
            QLabel#Title { color:#0f172a; font-size:16pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#FieldLabel { color:#334155; font-size:9pt; font-weight:850; }
            QLabel#ReadonlyValue { background:#f1f5f9; color:#0f172a; border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; font-weight:800; }
            QLabel#CurrentValue { background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; border-radius:10px; padding:10px 12px; font-size:11pt; font-weight:950; }
            QLabel#NewValue { background:#ecfdf5; color:#166534; border:1px solid #bbf7d0; border-radius:10px; padding:10px 12px; font-size:11pt; font-weight:950; }
            QLineEdit, QSpinBox { background:#ffffff; color:#0f172a; border:1px solid #cbd5e1; border-radius:10px; padding:9px 12px; font-size:10pt; font-weight:650; min-height:24px; }
            QLineEdit:focus, QSpinBox:focus { border:1px solid #2563eb; }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:none; border-radius:10px; padding:10px 20px; font-weight:950; min-height:26px; }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:none; border-radius:10px; padding:10px 20px; font-weight:950; min-height:26px; }
            QPushButton#SecondaryButton:hover { background:#cbd5e1; }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Stock Balance Correction")
        title.setObjectName("Title")
        hint = QLabel(
            "Usable Stock = FG + QC. Scrap and Blocked are separate non-usable buckets and are not deducted twice. Every manual correction requires a reason and is written to stock correction history."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        self._add_readonly(form, 0, "SAP Code", self.sap_code_label)
        self._add_readonly(form, 1, "Tyre Description", self.description_label)
        self._add_readonly(form, 2, "Current Snapshot Usable", self.current_available_label, "CurrentValue")
        self._add_field(form, 3, "FG Stock", self.fg_stock_input)
        self._add_field(form, 4, "QC Stock", self.qc_stock_input)
        self._add_field(form, 5, "Scrap Stock", self.scrap_stock_input)
        self._add_field(form, 6, "Blocked Stock", self.blocked_stock_input)
        self._add_readonly(form, 7, "New Snapshot Usable", self.new_available_label, "NewValue")
        self._add_field(form, 8, "Correction Reason", self.reason_input)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        layout.addLayout(buttons)
        root.addWidget(card)

    @staticmethod
    def _add_field(grid: QGridLayout, row: int, text_value: str, widget: QWidget) -> None:
        label = QLabel(text_value)
        label.setObjectName("FieldLabel")
        grid.addWidget(label, row, 0)
        grid.addWidget(widget, row, 1)
        grid.setColumnStretch(1, 1)

    @staticmethod
    def _add_readonly(
        grid: QGridLayout,
        row: int,
        text_value: str,
        widget: QLabel,
        object_name: str = "ReadonlyValue",
    ) -> None:
        label = QLabel(text_value)
        label.setObjectName("FieldLabel")
        widget.setObjectName(object_name)
        widget.setWordWrap(True)
        grid.addWidget(label, row, 0)
        grid.addWidget(widget, row, 1)

    def _load_stock_item(self) -> None:
        self.sap_code_label.setText(str(self.stock_item.get("sap_code") or "-"))
        self.description_label.setText(str(self.stock_item.get("tyre_description") or "-"))
        self.fg_stock_input.setValue(int(self.stock_item.get("fg_stock") or 0))
        self.qc_stock_input.setValue(int(self.stock_item.get("qc_stock") or 0))
        self.scrap_stock_input.setValue(int(self.stock_item.get("scrap_stock") or 0))
        self.blocked_stock_input.setValue(int(self.stock_item.get("blocked_stock") or 0))
        current = calculate_available_stock(
            self.stock_item.get("fg_stock"),
            self.stock_item.get("qc_stock"),
            self.stock_item.get("scrap_stock"),
            self.stock_item.get("blocked_stock"),
        )
        self.current_available_label.setText(f"{current:,}")
        self._refresh_new_available()

    def _refresh_new_available(self, *args) -> None:
        value = calculate_available_stock(
            self.fg_stock_input.value(),
            self.qc_stock_input.value(),
            self.scrap_stock_input.value(),
            self.blocked_stock_input.value(),
        )
        self.new_available_label.setText(f"{value:,}")

    def _validate_and_accept(self) -> None:
        if not self.reason_input.text().strip():
            QMessageBox.warning(self, "Correction Reason Required", "Enter the reason for this stock correction.")
            self.reason_input.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        reason = self.reason_input.text().strip()
        if not reason:
            raise ValueError("Correction reason is required.")
        return {
            "sap_code": self.stock_item.get("sap_code"),
            "fg_stock": self.fg_stock_input.value(),
            "qc_stock": self.qc_stock_input.value(),
            "scrap_stock": self.scrap_stock_input.value(),
            "blocked_stock": self.blocked_stock_input.value(),
            "reason": reason,
        }


class StockMasterPage(QWidget):
    """Operational finished-tyre stock control center."""

    def __init__(self):
        super().__init__()
        self.selected_sap_code: str | None = None

        self.metrics = {
            "items": QLabel("0"),
            "fg": QLabel("0"),
            "qc": QLabel("0"),
            "available": QLabel("0"),
            "out": QLabel("0"),
            "blocked": QLabel("0"),
        }

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP code, tyre description or type...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.stock_status_combo = QComboBox()
        self.stock_status_combo.addItems(
            [
                "ALL STATUS",
                "AVAILABLE",
                "OUT OF STOCK",
                "NO USABLE STOCK",
                "HAS BLOCKED STOCK",
                "HAS SCRAP STOCK",
            ]
        )
        self.stock_status_combo.currentTextChanged.connect(self.refresh_table)

        self.type_combo = QComboBox()
        self.type_combo.addItem("ALL TYPES")
        self.type_combo.currentTextChanged.connect(self.refresh_table)

        self.count_label = QLabel("0 items")
        self.count_label.setObjectName("CountBadge")
        self.source_badge = QLabel("Live OVEN: -")
        self.source_badge.setObjectName("SourceBadge")
        self.source_badge.setToolTip("Newest committed OVEN workbook that is allowed to drive live operations.")

        self.sync_btn = QPushButton("Sync From Tyre Master")
        self.sync_btn.setObjectName("SecondaryButton")
        self.sync_btn.clicked.connect(lambda: self.sync_tyres_from_master(show_message=True))

        self.edit_btn = QPushButton("Correct Selected Stock")
        self.edit_btn.setObjectName("PrimaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_stock)

        self.export_btn = QPushButton("Export Current CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_current_csv)

        self.refresh_btn = QPushButton("Refresh Live Stock")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.history_export_btn = QPushButton("Export History CSV")
        self.history_export_btn.setObjectName("SecondaryButton")
        self.history_export_btn.clicked.connect(self.export_history_csv)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "SAP Code",
                "Tyre Description",
                "Type",
                "PROD Opening",
                "QC",
                "Scrap",
                "Blocked",
                "Workbook Opening",
                "Current Ledger",
                "Status",
                "OVEN Plan Date",
            ]
        )

        self.history_table = QTableWidget(0, 14)
        self.history_table.setHorizontalHeaderLabels(
            [
                "Changed At",
                "SAP Code",
                "Tyre Description",
                "Reason",
                "Old FG",
                "New FG",
                "Old QC",
                "New QC",
                "Old Scrap",
                "New Scrap",
                "Old Blocked",
                "New Blocked",
                "Old Available",
                "New Available",
            ]
        )

        self.tabs = QTabWidget()
        self.tabs.setObjectName("StockTabs")

        self._setup_tables()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard, QFrame#TableCard, QFrame#MetricCard { background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; }
            QLabel#PageTitle { color:#0f172a; font-size:19pt; font-weight:950; }
            QLabel#PageHint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#MetricTitle { color:#64748b; font-size:8.5pt; font-weight:850; }
            QLabel#MetricValue { color:#0f172a; font-size:18pt; font-weight:950; }
            QLabel#FieldLabel { color:#334155; font-size:9pt; font-weight:850; }
            QLabel#CountBadge { background:#dbeafe; color:#1e40af; border-radius:9px; padding:8px 12px; font-weight:900; }
            QLabel#SourceBadge { background:#ecfdf5; color:#166534; border:1px solid #bbf7d0; border-radius:9px; padding:8px 12px; font-weight:950; }
            QLineEdit, QComboBox { background:#ffffff; color:#0f172a; border:1px solid #cbd5e1; border-radius:10px; padding:8px 11px; font-size:9.5pt; font-weight:650; min-height:23px; }
            QLineEdit:focus, QComboBox:focus { border:1px solid #2563eb; }
            QPushButton#PrimaryButton { background:#2563eb; color:#ffffff; border:none; border-radius:10px; padding:9px 16px; font-weight:950; min-height:25px; }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QPushButton#PrimaryButton:disabled { background:#bfdbfe; color:#eff6ff; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:none; border-radius:10px; padding:9px 16px; font-weight:950; min-height:25px; }
            QPushButton#SecondaryButton:hover { background:#cbd5e1; }
            QTabWidget::pane { border:0; background:transparent; }
            QTabBar::tab { background:#e2e8f0; color:#334155; border:0; padding:9px 16px; margin-right:4px; font-weight:900; }
            QTabBar::tab:selected { background:#2563eb; color:white; }
            QTableWidget { background:#ffffff; color:#0f172a; border:1px solid #e2e8f0; border-radius:12px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QTableWidget::item { padding:7px 9px; border:none; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:none; border-right:1px solid #e2e8f0; border-bottom:1px solid #e2e8f0; padding:9px; font-weight:950; }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(12)
        metrics_grid.setVerticalSpacing(12)
        cards = [
            ("Active SAP Items", "items"),
            ("PROD Opening Stock", "fg"),
            ("QC Stock", "qc"),
            ("Current Ledger Stock", "available"),
            ("Out / Negative Items", "out"),
            ("Blocked Qty", "blocked"),
        ]
        for idx, (title, key) in enumerate(cards):
            metrics_grid.addWidget(self._metric_card(title, self.metrics[key]), idx // 3, idx % 3)
        root.addLayout(metrics_grid)
        root.addWidget(self._build_control_card())

        current_tab = QWidget()
        current_layout = QVBoxLayout(current_tab)
        current_layout.setContentsMargins(0, 12, 0, 0)
        current_layout.addWidget(self._build_stock_table_card(), 1)

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 12, 0, 0)
        history_layout.addWidget(self._build_history_card(), 1)

        self.tabs.addTab(current_tab, "Current Stock")
        self.tabs.addTab(history_tab, "Correction History")
        self.tabs.currentChanged.connect(lambda *_: self.refresh_history())
        root.addWidget(self.tabs, 1)

    @staticmethod
    def _metric_card(title_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel(title_text)
        title.setObjectName("MetricTitle")
        value_label.setObjectName("MetricValue")
        layout.addWidget(title)
        layout.addWidget(value_label)
        return card

    def _build_control_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("ControlCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 17)
        layout.setSpacing(13)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Stock Control Center")
        title.setObjectName("PageTitle")
        hint = QLabel(
            "Live finished-tyre stock control. PROD column D is treated as the monthly opening-stock authority. Current Ledger = monthly opening stock + verified actual production - confirmed shipment out through the newest OVEN date. Older workbooks never move live operations backwards; they remain history and ML training evidence."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        header.addWidget(self.source_badge)
        header.addWidget(self.sync_btn)
        header.addWidget(self.export_btn)
        header.addWidget(self.edit_btn)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        filters = QGridLayout()
        filters.setHorizontalSpacing(10)
        search_label = QLabel("Search")
        search_label.setObjectName("FieldLabel")
        status_label = QLabel("Stock Status")
        status_label.setObjectName("FieldLabel")
        type_label = QLabel("Tyre Type")
        type_label.setObjectName("FieldLabel")
        filters.addWidget(search_label, 0, 0)
        filters.addWidget(self.search_input, 0, 1, 1, 3)
        filters.addWidget(status_label, 0, 4)
        filters.addWidget(self.stock_status_combo, 0, 5)
        filters.addWidget(type_label, 0, 6)
        filters.addWidget(self.type_combo, 0, 7)
        filters.addWidget(self.count_label, 0, 8)
        filters.setColumnStretch(1, 1)
        filters.setColumnStretch(2, 1)
        filters.setColumnStretch(3, 1)
        layout.addLayout(filters)
        return card

    def _build_stock_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        hint = QLabel(
            "Double-click a row to correct stock. Zero usable stock is highlighted amber. Scrap and Blocked are shown separately and never create artificial negative stock."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        return card

    def _build_history_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Manual Stock Correction History")
        title.setObjectName("PageTitle")
        hint = QLabel("Before/after quantities and the required correction reason are retained for traceability.")
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        header.addWidget(self.history_export_btn)
        layout.addLayout(header)
        layout.addWidget(self.history_table, 1)
        return card

    def _setup_tables(self) -> None:
        for table in (self.table, self.history_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(42)
            table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        widths = [120, 300, 105, 68, 68, 72, 78, 95, 105, 120, 145]
        for idx, width in enumerate(widths):
            self.table.setColumnWidth(idx, width)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_stock)

        history_header = self.history_table.horizontalHeader()
        for column in range(self.history_table.columnCount()):
            history_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        history_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        history_widths = [145, 115, 250, 260] + [75] * 10
        for idx, width in enumerate(history_widths):
            self.history_table.setColumnWidth(idx, width)

    def refresh(self, *args) -> None:
        try:
            self.ensure_sap_stock_table()
            self.ensure_correction_log_table()
            if self.get_stock_count() == 0:
                self.sync_tyres_from_master(show_message=False)
            self._load_type_filter()
            self.refresh_metrics()
            self.refresh_table()
            self.refresh_history()
        except Exception as exc:
            QMessageBox.critical(self, "Stock Control Error", str(exc))

    def ensure_sap_stock_table(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mpps_sap_stock_items (
                id SERIAL PRIMARY KEY,
                sap_code VARCHAR(100) NOT NULL UNIQUE,
                tyre_description TEXT NOT NULL DEFAULT '',
                tyre_type VARCHAR(150),
                fg_stock INTEGER NOT NULL DEFAULT 0,
                qc_stock INTEGER NOT NULL DEFAULT 0,
                scrap_stock INTEGER NOT NULL DEFAULT 0,
                blocked_stock INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                source_table VARCHAR(150),
                source_note TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS tyre_description TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS tyre_type VARCHAR(150)",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS fg_stock INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS qc_stock INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS scrap_stock INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS blocked_stock INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS source_table VARCHAR(150)",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS source_note TEXT",
            "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ]
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def ensure_correction_log_table(self) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS mpps_stock_correction_log (
                        id BIGSERIAL PRIMARY KEY,
                        sap_code VARCHAR(100) NOT NULL,
                        tyre_description TEXT,
                        old_fg_stock INTEGER NOT NULL DEFAULT 0,
                        new_fg_stock INTEGER NOT NULL DEFAULT 0,
                        old_qc_stock INTEGER NOT NULL DEFAULT 0,
                        new_qc_stock INTEGER NOT NULL DEFAULT 0,
                        old_scrap_stock INTEGER NOT NULL DEFAULT 0,
                        new_scrap_stock INTEGER NOT NULL DEFAULT 0,
                        old_blocked_stock INTEGER NOT NULL DEFAULT 0,
                        new_blocked_stock INTEGER NOT NULL DEFAULT 0,
                        reason TEXT NOT NULL,
                        changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_mpps_stock_correction_log_sap
                    ON mpps_stock_correction_log (sap_code, changed_at DESC);
                    """
                )
            )

    def get_stock_count(self) -> int:
        with engine.begin() as connection:
            return int(
                connection.execute(
                    text("SELECT COUNT(*) FROM mpps_sap_stock_items WHERE is_active = TRUE;")
                ).scalar()
                or 0
            )

    def _operational_source(self):
        try:
            with get_session() as session:
                return OperationalSourceService.latest(session)
        except Exception:
            return None

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT sap_code, fg_stock, qc_stock, blocked_stock
                    FROM mpps_sap_stock_items
                    WHERE is_active = TRUE
                    """
                )
            ).mappings().all()

        ledger: dict[str, int] = {}
        source = self._operational_source()
        as_of = source.plan_date if source and source.plan_date else date.today()
        try:
            with get_session() as session:
                ledger = AIPlanningService().current_stock_snapshot(session, as_of)
        except Exception:
            ledger = {}
        if source and source.plan_date:
            self.source_badge.setText(f"Live OVEN: {source.plan_date.isoformat()}")
            self.source_badge.setToolTip(source.workbook_name or "Newest committed live OVEN workbook")
        else:
            self.source_badge.setText("Live OVEN: not imported")

        total_items = len(rows)
        fg_qty = sum(max(0, int(r["fg_stock"] or 0)) for r in rows)
        qc_qty = sum(max(0, int(r["qc_stock"] or 0)) for r in rows)
        blocked_qty = sum(max(0, int(r["blocked_stock"] or 0)) for r in rows)
        current_values = []
        for r in rows:
            sap = str(r["sap_code"] or "").strip().upper()
            snapshot = max(0, int(r["fg_stock"] or 0)) + max(0, int(r["qc_stock"] or 0))
            current_values.append(max(0, int(ledger.get(sap, snapshot))))

        metrics = StockMetrics(
            total_items=total_items,
            fg_qty=fg_qty,
            qc_qty=qc_qty,
            available_qty=sum(current_values),
            out_of_stock_items=sum(1 for value in current_values if value <= 0),
            blocked_qty=blocked_qty,
        )
        self.metrics["items"].setText(f"{metrics.total_items:,}")
        self.metrics["fg"].setText(f"{metrics.fg_qty:,}")
        self.metrics["qc"].setText(f"{metrics.qc_qty:,}")
        self.metrics["available"].setText(f"{metrics.available_qty:,}")
        self.metrics["out"].setText(f"{metrics.out_of_stock_items:,}")
        self.metrics["blocked"].setText(f"{metrics.blocked_qty:,}")

    def _load_type_filter(self) -> None:
        current = self.type_combo.currentText()
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT COALESCE(NULLIF(TRIM(tyre_type), ''), 'Tyre') AS tyre_type
                    FROM mpps_sap_stock_items
                    WHERE is_active = TRUE
                    ORDER BY tyre_type;
                    """
                )
            ).scalars().all()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("ALL TYPES")
        for value in rows:
            self.type_combo.addItem(str(value))
        index = self.type_combo.findText(current)
        self.type_combo.setCurrentIndex(index if index >= 0 else 0)
        self.type_combo.blockSignals(False)

    def refresh_table(self, *args) -> None:
        self.selected_sap_code = None
        self.edit_btn.setEnabled(False)
        search_text = self.search_input.text().strip()
        status_value = self.stock_status_combo.currentText().strip()
        type_value = self.type_combo.currentText().strip()

        conditions = ["is_active = TRUE"]
        params: dict[str, Any] = {"search": f"%{search_text}%"}
        if search_text:
            conditions.append(
                "(sap_code ILIKE :search OR tyre_description ILIKE :search OR COALESCE(tyre_type, '') ILIKE :search)"
            )
        if status_value == "HAS BLOCKED STOCK":
            conditions.append("blocked_stock > 0")
        elif status_value == "HAS SCRAP STOCK":
            conditions.append("scrap_stock > 0")
        if type_value and type_value != "ALL TYPES":
            conditions.append("COALESCE(NULLIF(TRIM(tyre_type), ''), 'Tyre') = :tyre_type")
            params["tyre_type"] = type_value

        where_sql = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT
                sap_code,
                tyre_description,
                COALESCE(NULLIF(TRIM(tyre_type), ''), 'Tyre') AS tyre_type,
                fg_stock,
                qc_stock,
                scrap_stock,
                blocked_stock,
                updated_at
            FROM mpps_sap_stock_items
            {where_sql}
            ORDER BY sap_code ASC
            LIMIT 5000;
        """
        with engine.begin() as connection:
            rows = [dict(r) for r in connection.execute(text(sql), params).mappings().all()]

        ledger: dict[str, int] = {}
        source = self._operational_source()
        as_of = source.plan_date if source and source.plan_date else date.today()
        try:
            with get_session() as session:
                ledger = AIPlanningService().current_stock_snapshot(session, as_of)
        except Exception:
            ledger = {}
        if source and source.plan_date:
            self.source_badge.setText(f"Live OVEN: {source.plan_date.isoformat()}")
            self.source_badge.setToolTip(source.workbook_name or "Newest committed live OVEN workbook")
        else:
            self.source_badge.setText("Live OVEN: not imported")

        display_rows: list[dict[str, Any]] = []
        for row in rows:
            sap = str(row.get("sap_code") or "").strip().upper()
            snapshot = calculate_available_stock(
                row.get("fg_stock"), row.get("qc_stock"), row.get("scrap_stock"), row.get("blocked_stock")
            )
            current = max(0, int(ledger.get(sap, snapshot)))
            status = stock_status_from_available(current)
            if status_value == "AVAILABLE" and current <= 0:
                continue
            if status_value in {"OUT OF STOCK", "NO USABLE STOCK"} and current > 0:
                continue
            row["snapshot_usable"] = snapshot
            row["current_ledger"] = current
            row["ledger_status"] = status
            display_rows.append(row)

        display_rows.sort(key=lambda r: (0 if int(r["current_ledger"]) <= 0 else 1, int(r["current_ledger"]), r["sap_code"]))

        source_date_text = source.plan_date.isoformat() if source and source.plan_date else "-"
        self.table.setRowCount(0)
        for row_index, row in enumerate(display_rows):
            self.table.insertRow(row_index)
            current = int(row["current_ledger"] or 0)
            values = [
                row["sap_code"],
                row["tyre_description"],
                row["tyre_type"],
                self._format_int(row["fg_stock"]),
                self._format_int(row["qc_stock"]),
                self._format_int(row["scrap_stock"]),
                self._format_int(row["blocked_stock"]),
                self._format_int(row["snapshot_usable"]),
                self._format_int(current),
                row["ledger_status"],
                source_date_text,
            ]
            for column_index, value in enumerate(values):
                item = self._readonly_item(value)
                if column_index not in {1}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column_index in {8, 9}:
                    self._apply_status_style(item, current)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["sap_code"])
                self.table.setItem(row_index, column_index, item)

        self.count_label.setText(f"{len(display_rows):,} items")

    def refresh_history(self, *args) -> None:
        try:
            self.ensure_correction_log_table()
            with engine.begin() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                            changed_at, sap_code, tyre_description, reason,
                            old_fg_stock, new_fg_stock,
                            old_qc_stock, new_qc_stock,
                            old_scrap_stock, new_scrap_stock,
                            old_blocked_stock, new_blocked_stock
                        FROM mpps_stock_correction_log
                        ORDER BY changed_at DESC, id DESC
                        LIMIT 2000;
                        """
                    )
                ).mappings().all()
        except Exception:
            return

        self.history_table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.history_table.insertRow(row_index)
            old_available = calculate_available_stock(
                row["old_fg_stock"], row["old_qc_stock"], row["old_scrap_stock"], row["old_blocked_stock"]
            )
            new_available = calculate_available_stock(
                row["new_fg_stock"], row["new_qc_stock"], row["new_scrap_stock"], row["new_blocked_stock"]
            )
            changed = row.get("changed_at")
            changed_text = changed.strftime("%Y-%m-%d %H:%M:%S") if hasattr(changed, "strftime") else str(changed or "-")
            values = [
                changed_text,
                row["sap_code"],
                row["tyre_description"],
                row["reason"],
                self._format_int(row["old_fg_stock"]),
                self._format_int(row["new_fg_stock"]),
                self._format_int(row["old_qc_stock"]),
                self._format_int(row["new_qc_stock"]),
                self._format_int(row["old_scrap_stock"]),
                self._format_int(row["new_scrap_stock"]),
                self._format_int(row["old_blocked_stock"]),
                self._format_int(row["new_blocked_stock"]),
                self._format_int(old_available),
                self._format_int(new_available),
            ]
            for col, value in enumerate(values):
                item = self._readonly_item(value)
                if col not in {2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 13:
                    self._apply_status_style(item, new_available)
                self.history_table.setItem(row_index, col, item)

    def sync_tyres_from_master(self, show_message: bool = True) -> None:
        self.ensure_sap_stock_table()
        source_rows, source_table = self.find_tyre_master_rows()
        if not source_rows:
            if show_message:
                QMessageBox.warning(
                    self,
                    "No SAP Tyres Found",
                    "Tyre master table with SAP Code was not found. Import or verify the tyre master first.",
                )
            self.refresh_table()
            return

        insert_sql = text(
            """
            INSERT INTO mpps_sap_stock_items
                (sap_code, tyre_description, tyre_type, fg_stock, qc_stock, scrap_stock,
                 blocked_stock, is_active, source_table, source_note, updated_at)
            SELECT
                CAST(:sap_code AS varchar), CAST(:tyre_description AS text), CAST(:tyre_type AS varchar),
                0, 0, 0, 0, TRUE, CAST(:source_table AS varchar),
                'Auto-created from tyre master with zero opening stock.', CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM mpps_sap_stock_items WHERE sap_code = CAST(:sap_code AS varchar)
            );
            """
        )
        inserted = 0
        with engine.begin() as connection:
            for row in source_rows:
                result = connection.execute(
                    insert_sql,
                    {
                        "sap_code": row["sap_code"],
                        "tyre_description": row["tyre_description"],
                        "tyre_type": row["tyre_type"],
                        "source_table": source_table,
                    },
                )
                inserted += int(result.rowcount or 0)
        self._load_type_filter()
        self.refresh_metrics()
        self.refresh_table()
        if show_message:
            QMessageBox.information(
                self,
                "Stock Sync Complete",
                f"Source table: {source_table}\nNew SAP stock items added: {inserted:,}",
            )

    def find_tyre_master_rows(self) -> tuple[list[dict], str]:
        inspector = inspect(engine)
        excluded_keywords = ["stock", "audit", "user", "role", "alembic", "shipment", "plan"]
        sap_candidates = [
            "sap_code", "sapcode", "sap_material_code", "sap_material", "material_code", "item_code", "code"
        ]
        desc_candidates = [
            "tyre_description", "item_description", "description", "product_description", "product_name", "name"
        ]
        type_candidates = ["tyre_type", "product_group", "product_type", "category", "group_name", "type"]

        for table_name in inspector.get_table_names():
            lower_table = table_name.lower()
            if any(keyword in lower_table for keyword in excluded_keywords):
                continue
            columns = [column["name"] for column in inspector.get_columns(table_name)]
            lower_map = {column.lower(): column for column in columns}
            sap_col = self._first_existing_column(lower_map, sap_candidates)
            desc_col = self._first_existing_column(lower_map, desc_candidates)
            type_col = self._first_existing_column(lower_map, type_candidates)
            if not sap_col or not desc_col:
                continue
            type_expr = f"CAST({_quote_ident(type_col)} AS varchar)" if type_col else "'Tyre'"
            sql = f"""
                SELECT DISTINCT
                    CAST({_quote_ident(sap_col)} AS varchar) AS sap_code,
                    CAST({_quote_ident(desc_col)} AS text) AS tyre_description,
                    COALESCE(NULLIF(TRIM({type_expr}), ''), 'Tyre') AS tyre_type
                FROM {_quote_ident(table_name)}
                WHERE {_quote_ident(sap_col)} IS NOT NULL
                  AND TRIM(CAST({_quote_ident(sap_col)} AS varchar)) <> ''
                  AND {_quote_ident(desc_col)} IS NOT NULL
                  AND TRIM(CAST({_quote_ident(desc_col)} AS varchar)) <> ''
                ORDER BY sap_code ASC;
            """
            with engine.begin() as connection:
                rows = connection.execute(text(sql)).mappings().all()
            result_rows = [dict(row) for row in rows]
            if result_rows:
                return result_rows, table_name
        return [], "-"

    @staticmethod
    def _first_existing_column(lower_map: dict[str, str], candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate.lower() in lower_map:
                return lower_map[candidate.lower()]
        return None

    def edit_selected_stock(self, *args) -> None:
        if not self.selected_sap_code:
            return
        stock_item = self.get_stock_item(self.selected_sap_code)
        if stock_item is None:
            QMessageBox.warning(self, "Stock Item Missing", "Selected stock item was not found.")
            return
        dialog = StockEditDialog(self, dict(stock_item))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.save_stock_balance(dialog.get_data())
            self.refresh()
            QMessageBox.information(self, "Stock Updated", "Stock balance and correction history were updated successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Stock Update Failed", str(exc))

    def get_stock_item(self, sap_code: str):
        with engine.begin() as connection:
            return connection.execute(
                text(
                    """
                    SELECT sap_code, tyre_description, tyre_type,
                           fg_stock, qc_stock, scrap_stock, blocked_stock
                    FROM mpps_sap_stock_items
                    WHERE sap_code = :sap_code
                    LIMIT 1;
                    """
                ),
                {"sap_code": sap_code},
            ).mappings().first()

    def save_stock_balance(self, data: dict) -> None:
        self.ensure_correction_log_table()
        with engine.begin() as connection:
            old = connection.execute(
                text(
                    """
                    SELECT sap_code, tyre_description, fg_stock, qc_stock, scrap_stock, blocked_stock
                    FROM mpps_sap_stock_items
                    WHERE sap_code = :sap_code
                    FOR UPDATE;
                    """
                ),
                {"sap_code": data["sap_code"]},
            ).mappings().first()
            if old is None:
                raise ValueError("Selected stock item no longer exists.")

            changed = any(
                int(old[key] or 0) != int(data[key] or 0)
                for key in ("fg_stock", "qc_stock", "scrap_stock", "blocked_stock")
            )
            if not changed:
                raise ValueError("No stock quantity was changed.")

            connection.execute(
                text(
                    """
                    UPDATE mpps_sap_stock_items
                    SET fg_stock=:fg_stock, qc_stock=:qc_stock, scrap_stock=:scrap_stock,
                        blocked_stock=:blocked_stock, source_note=:reason, updated_at=CURRENT_TIMESTAMP
                    WHERE sap_code=:sap_code;
                    """
                ),
                data,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO mpps_stock_correction_log
                        (sap_code, tyre_description,
                         old_fg_stock, new_fg_stock,
                         old_qc_stock, new_qc_stock,
                         old_scrap_stock, new_scrap_stock,
                         old_blocked_stock, new_blocked_stock,
                         reason, changed_at)
                    VALUES
                        (:sap_code, :tyre_description,
                         :old_fg, :new_fg,
                         :old_qc, :new_qc,
                         :old_scrap, :new_scrap,
                         :old_blocked, :new_blocked,
                         :reason, CURRENT_TIMESTAMP);
                    """
                ),
                {
                    "sap_code": data["sap_code"],
                    "tyre_description": old["tyre_description"],
                    "old_fg": int(old["fg_stock"] or 0),
                    "new_fg": int(data["fg_stock"] or 0),
                    "old_qc": int(old["qc_stock"] or 0),
                    "new_qc": int(data["qc_stock"] or 0),
                    "old_scrap": int(old["scrap_stock"] or 0),
                    "new_scrap": int(data["scrap_stock"] or 0),
                    "old_blocked": int(old["blocked_stock"] or 0),
                    "new_blocked": int(data["blocked_stock"] or 0),
                    "reason": data["reason"],
                },
            )

    def export_current_csv(self) -> None:
        headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
        rows: list[list[str]] = []
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            rows.append([
                self.table.item(row, col).text() if self.table.item(row, col) else ""
                for col in range(self.table.columnCount())
            ])
        if not rows:
            QMessageBox.information(self, "Stock Export", "There are no visible stock rows to export.")
            return
        path = export_to_csv(headers, rows, "stock_control_current")
        QMessageBox.information(self, "Stock Export Complete", f"CSV saved to:\n{path}")

    def export_history_csv(self) -> None:
        headers = [self.history_table.horizontalHeaderItem(i).text() for i in range(self.history_table.columnCount())]
        rows = [
            [
                self.history_table.item(row, col).text() if self.history_table.item(row, col) else ""
                for col in range(self.history_table.columnCount())
            ]
            for row in range(self.history_table.rowCount())
        ]
        if not rows:
            QMessageBox.information(self, "History Export", "No correction history is available yet.")
            return
        path = export_to_csv(headers, rows, "stock_correction_history")
        QMessageBox.information(self, "History Export Complete", f"CSV saved to:\n{path}")

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.selected_sap_code = None
            self.edit_btn.setEnabled(False)
            return
        row = selected_items[0].row()
        sap_item = self.table.item(row, 0)
        self.selected_sap_code = sap_item.data(Qt.ItemDataRole.UserRole) if sap_item else None
        self.edit_btn.setEnabled(bool(self.selected_sap_code))

    @staticmethod
    def _readonly_item(text_value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text_value))
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    @staticmethod
    def _apply_status_style(item: QTableWidgetItem, available_stock: int) -> None:
        if available_stock > 0:
            fg, bg = "#166534", "#dcfce7"
        elif available_stock == 0:
            fg, bg = "#92400e", "#fef3c7"
        else:
            fg, bg = "#991b1b", "#fee2e2"
        item.setForeground(QColor(fg))
        item.setBackground(QColor(bg))

    @staticmethod
    def _format_int(value: Any) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"
