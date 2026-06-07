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
from app.services.oven_capacity_service import build_capacity_analysis
from app.services.oven_schedule_service import build_daily_oven_schedule
from app.services.production_requirement_service import load_production_requirements
from app.services.shipment_risk_service import ShipmentRiskRow, build_shipment_risks
from app.utils.reports_export import export_to_csv


class ShipmentRiskPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.rows: list[ShipmentRiskRow] = []
        self.visible_rows: list[ShipmentRiskRow] = []
        self.metrics = {
            status: QLabel("0")
            for status in ["TOTAL", "LOW RISK", "MEDIUM RISK", "HIGH RISK", "CANNOT COMPLETE", "DATA MISSING"]
        }
        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(self.refresh)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search reference, customer, material, or reason...")
        self.search_input.textChanged.connect(self.filter_table)
        self.risk_combo = QComboBox()
        self.risk_combo.addItems(
            ["ALL", "LOW RISK", "MEDIUM RISK", "HIGH RISK", "CANNOT COMPLETE", "DATA MISSING"]
        )
        self.risk_combo.currentTextChanged.connect(self.filter_table)
        self.refresh_btn = QPushButton("Run Risk Analysis")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_csv)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels(
            [
                "Order / Demand Ref",
                "Customer",
                "Material Code",
                "Due Date",
                "Demand Qty",
                "Available Stock",
                "Shortage",
                "Production Required",
                "Planned",
                "Unplanned",
                "Estimated Completion",
                "Risk Status",
                "Risk Reason",
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
        for title, key in [
            ("Total Demands", "TOTAL"),
            ("Low Risk", "LOW RISK"),
            ("Medium Risk", "MEDIUM RISK"),
            ("High Risk", "HIGH RISK"),
            ("Cannot Complete", "CANNOT COMPLETE"),
            ("Data Missing", "DATA MISSING"),
        ]:
            metrics.addWidget(self._metric_card(title, self.metrics[key]), 1)
        root.addLayout(metrics)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Shipment Risk Assessment")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "Allocates stock and the quantity-based oven preview to active demand "
            "in due-date order and explains every missing-data or completion risk."
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
        filters.addWidget(QLabel("Risk"))
        filters.addWidget(self.risk_combo)
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
        layout.setContentsMargins(12, 10, 12, 10)
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
        header.setSectionResizeMode(12, QHeaderView.ResizeMode.Stretch)
        widths = [115, 170, 115, 95, 85, 95, 85, 110, 80, 85, 125, 125, 250]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card, QFrame#MetricCard { background:white; border:1px solid #e2e8f0; border-radius:14px; }
            QLabel#MetricTitle { color:#64748b; font-size:8pt; font-weight:800; }
            QLabel#MetricValue { color:#0f172a; font-size:17pt; font-weight:900; }
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
                    session, planning_date=selected
                )
                required = [row for row in production if row.production_required_qty > 0]
                capacity = build_capacity_analysis(
                    session, production_rows=required, planning_date=selected
                )
                schedule, _ = build_daily_oven_schedule(
                    session,
                    planning_date=selected,
                    production_rows=required,
                    capacity_rows=capacity,
                )
                self.rows = build_shipment_risks(
                    session,
                    planning_date=selected,
                    production_rows=production,
                    capacity_rows=capacity,
                    schedule_rows=schedule,
                )
            self.metrics["TOTAL"].setText(f"{len(self.rows):,}")
            for status in [
                "LOW RISK",
                "MEDIUM RISK",
                "HIGH RISK",
                "CANNOT COMPLETE",
                "DATA MISSING",
            ]:
                self.metrics[status].setText(
                    f"{sum(row.risk_status == status for row in self.rows):,}"
                )
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Shipment Risk Error", str(exc))

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        risk = self.risk_combo.currentText()
        self.visible_rows = []
        for row in self.rows:
            if risk != "ALL" and row.risk_status != risk:
                continue
            searchable = (
                f"{row.demand_reference} {row.customer_name} {row.material_code} "
                f"{row.risk_status} {row.risk_reason}"
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_rows.append(row)
        self._populate()

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for row_index, row in enumerate(self.visible_rows):
            self.table.insertRow(row_index)
            values = [
                row.demand_reference,
                row.customer_name,
                row.material_code,
                row.due_date.isoformat() if row.due_date else "MISSING",
                f"{row.demand_qty:,}",
                f"{row.available_stock:,}",
                f"{row.shortage_qty:,}",
                f"{row.production_required_qty:,}",
                f"{row.planned_qty:,}",
                f"{row.unplanned_qty:,}",
                row.estimated_completion_date.isoformat()
                if row.estimated_completion_date
                else "-",
                row.risk_status,
                row.risk_reason,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column not in {1, 12}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 11:
                    self._style_risk(item, row.risk_status)
                if column == 12:
                    item.setToolTip(row.risk_reason)
                self.table.setItem(row_index, column, item)

    def _style_risk(self, item: QTableWidgetItem, status: str) -> None:
        colors = {
            "LOW RISK": ("#166534", "#dcfce7"),
            "MEDIUM RISK": ("#1d4ed8", "#dbeafe"),
            "HIGH RISK": ("#92400e", "#fef3c7"),
            "CANNOT COMPLETE": ("#991b1b", "#fee2e2"),
            "DATA MISSING": ("#475569", "#f1f5f9"),
        }
        foreground, background = colors.get(status, ("#475569", "#f1f5f9"))
        item.setForeground(QColor(foreground))
        item.setBackground(QColor(background))

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
        path = export_to_csv(headers, data, "shipment_risk")
        QMessageBox.information(self, "Export Complete", f"CSV exported to:\n\n{path}")
