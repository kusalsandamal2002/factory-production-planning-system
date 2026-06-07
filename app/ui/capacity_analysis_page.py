from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.oven_capacity_service import CapacityAnalysisRow, build_capacity_analysis
from app.services.production_requirement_service import load_production_requirements
from app.utils.reports_export import export_to_csv


class CapacityAnalysisPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.rows: list[CapacityAnalysisRow] = []
        self.visible_rows: list[CapacityAnalysisRow] = []
        self.total_items = QLabel("0")
        self.capacity_items = QLabel("0")
        self.cannot_complete = QLabel("0")

        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(self.refresh)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search item, description, or warning...")
        self.search_input.textChanged.connect(self.filter_table)
        self.status_combo = QComboBox()
        self.status_combo.addItems(["ALL", "CAN COMPLETE", "CANNOT COMPLETE"])
        self.status_combo.currentTextChanged.connect(self.filter_table)
        self.refresh_btn = QPushButton("Calculate Capacity")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_csv)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Description",
                "Production Required",
                "Running Moulds",
                "Per Mould / Day",
                "Calculated Capacity",
                "Available Capacity",
                "Required Days",
                "Capacity Gap",
                "Estimated Completion",
                "Status",
                "Warning",
            ]
        )
        self._setup_table()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        metrics = QHBoxLayout()
        metrics.addWidget(self._metric_card("Production Required Items", self.total_items), 1)
        metrics.addWidget(self._metric_card("Items With Capacity", self.capacity_items), 1)
        metrics.addWidget(self._metric_card("Cannot Complete / Missing", self.cannot_complete), 1)
        root.addLayout(metrics)
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Quantity-Based Mould Capacity Analysis")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "Capacity is running moulds times approved pieces per mould per day. "
            "No minute utilization or curing time is calculated."
        )
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        heading.addLayout(title_box, 1)
        heading.addWidget(self.refresh_btn)
        heading.addWidget(self.export_btn)
        layout.addLayout(heading)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Planning Date"))
        filters.addWidget(self.plan_date)
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 1)
        filters.addWidget(QLabel("Status"))
        filters.addWidget(self.status_combo)
        layout.addLayout(filters)
        root.addWidget(card)
        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.addWidget(self.table)
        root.addWidget(table_card, 1)

    def _metric_card(self, title_text: str, label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel(title_text)
        title.setObjectName("MetricTitle")
        label.setObjectName("MetricValue")
        layout.addWidget(title)
        layout.addWidget(label)
        return card

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        widths = [115, 220, 110, 95, 100, 110, 110, 90, 95, 125, 125, 220]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card, QFrame#MetricCard { background:white; border:1px solid #e2e8f0; border-radius:14px; }
            QLabel#MetricTitle { color:#64748b; font-size:8.5pt; font-weight:800; }
            QLabel#MetricValue { color:#0f172a; font-size:18pt; font-weight:900; }
            QLabel#SectionTitle { color:#0f172a; font-size:15pt; font-weight:900; }
            QLabel#SectionHint { color:#64748b; font-size:9pt; }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QLineEdit, QComboBox, QDateEdit { background:white; border:1px solid #cbd5e1; border-radius:8px; padding:7px 10px; }
            QTableWidget { background:white; border:1px solid #e2e8f0; border-radius:10px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:0; border-right:1px solid #e2e8f0; padding:9px; font-weight:900; }
            """
        )

    def refresh(self, *args) -> None:
        try:
            selected = self.plan_date.date().toPython()
            with get_session() as session:
                production = load_production_requirements(
                    session, planning_date=selected, production_required_only=True
                )
                self.rows = build_capacity_analysis(
                    session, production_rows=production, planning_date=selected
                )
            self.total_items.setText(f"{len(self.rows):,}")
            self.capacity_items.setText(
                f"{sum(row.available_capacity > 0 for row in self.rows):,}"
            )
            self.cannot_complete.setText(
                f"{sum(row.status == 'CANNOT COMPLETE' for row in self.rows):,}"
            )
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Capacity Analysis Error", str(exc))

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        status = self.status_combo.currentText()
        self.visible_rows = []
        for row in self.rows:
            if status != "ALL" and row.status != status:
                continue
            searchable = f"{row.item_code} {row.item_description} {row.warning}".lower()
            if search and search not in searchable:
                continue
            self.visible_rows.append(row)
        self._populate()

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for row_index, row in enumerate(self.visible_rows):
            self.table.insertRow(row_index)
            values = [
                row.item_code,
                row.item_description,
                f"{row.production_required_qty:,}",
                f"{row.running_moulds:,.2f}",
                f"{row.per_mould_capacity:,.2f}",
                f"{row.calculated_daily_capacity:,.2f}",
                f"{row.available_capacity:,.2f}",
                str(row.required_days) if row.required_days is not None else "-",
                f"{row.capacity_gap:,.2f}",
                row.estimated_completion_date.isoformat()
                if row.estimated_completion_date
                else "-",
                row.status,
                row.warning or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column not in {1, 11}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 10:
                    good = row.status == "CAN COMPLETE"
                    item.setForeground(QColor("#166534" if good else "#991b1b"))
                    item.setBackground(QColor("#dcfce7" if good else "#fee2e2"))
                self.table.setItem(row_index, column, item)

    def export_csv(self) -> None:
        if not self.visible_rows:
            QMessageBox.warning(self, "Export CSV", "There are no visible rows.")
            return
        headers = [
            self.table.horizontalHeaderItem(column).text()
            for column in range(self.table.columnCount())
        ]
        data = [
            [
                self.table.item(row, column).text()
                if self.table.item(row, column) is not None
                else ""
                for column in range(self.table.columnCount())
            ]
            for row in range(self.table.rowCount())
        ]
        path = export_to_csv(headers, data, "capacity_analysis")
        QMessageBox.information(self, "Export Complete", f"CSV exported to:\n\n{path}")
