from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
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
from app.services.production_requirement_service import (
    ProductionRequirementRow,
    load_production_requirements,
    summarize_production_requirements,
)
from app.utils.reports_export import export_to_csv


class StockPlanningPage(QWidget):
    def __init__(self, open_item_detail_callback=None):
        super().__init__()
        self.open_item_detail_callback = open_item_detail_callback
        self.rows: list[ProductionRequirementRow] = []
        self.visible_rows: list[ProductionRequirementRow] = []
        self.selected_material_code: str | None = None

        self.metrics = {
            "items": QLabel("0"),
            "ready": QLabel("0"),
            "required": QLabel("0"),
            "shortage": QLabel("0"),
            "required_qty": QLabel("0"),
            "tons": QLabel("0.00"),
        }
        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(self.refresh)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search material, description, or group...")
        self.search_input.textChanged.connect(self.filter_table)
        self.status_combo = QComboBox()
        self.status_combo.addItems(
            [
                "ALL",
                "READY",
                "PARTIAL READY",
                "PRODUCTION REQUIRED",
                "OUT OF STOCK",
                "MISSING WEIGHT",
                "MISSING DEMAND",
            ]
        )
        self.status_combo.currentTextChanged.connect(self.filter_table)
        self.shortage_only = QCheckBox("Production required only")
        self.shortage_only.stateChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_csv)
        self.open_detail_btn = QPushButton("Open Item Detail")
        self.open_detail_btn.setObjectName("SecondaryButton")
        self.open_detail_btn.setEnabled(False)
        self.open_detail_btn.clicked.connect(self.open_selected_item)

        self.table = QTableWidget(0, 15)
        self.table.setHorizontalHeaderLabels(
            [
                "Material Code",
                "Description",
                "Product Group",
                "FG",
                "QC",
                "Scrap",
                "Blocked",
                "Available",
                "Shipment Demand",
                "Shortage",
                "Production Required",
                "Unit Weight",
                "Production Tons",
                "Status",
                "Warnings",
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
        grid = QGridLayout()
        labels = [
            ("Total Items", "items"),
            ("Ready for Shipment", "ready"),
            ("Production Required Items", "required"),
            ("Total Shortage Qty", "shortage"),
            ("Production Required Qty", "required_qty"),
            ("Production Required Tons", "tons"),
        ]
        for index, (title, key) in enumerate(labels):
            grid.addWidget(self._metric_card(title, self.metrics[key]), index // 3, index % 3)
        root.addLayout(grid)

        controls = QFrame()
        controls.setObjectName("Card")
        layout = QVBoxLayout(controls)
        layout.setContentsMargins(18, 16, 18, 18)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("MPPS Stock and Production Requirement")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "Dated stock, eligible demand, shortage, required pieces and tonnage. "
            "Items with the highest shortage appear first."
        )
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        heading.addLayout(title_box, 1)
        heading.addWidget(self.refresh_btn)
        heading.addWidget(self.export_btn)
        heading.addWidget(self.open_detail_btn)
        layout.addLayout(heading)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Planning Date"))
        filters.addWidget(self.plan_date)
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 1)
        filters.addWidget(QLabel("Status"))
        filters.addWidget(self.status_combo)
        filters.addWidget(self.shortage_only)
        layout.addLayout(filters)
        root.addWidget(controls)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.addWidget(self.table)
        root.addWidget(card, 1)

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
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.Stretch)
        widths = [125, 230, 120, 65, 65, 65, 70, 85, 110, 85, 115, 90, 105, 135, 250]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_selected_item())

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card, QFrame#MetricCard { background:white; border:1px solid #e2e8f0; border-radius:14px; }
            QLabel#MetricTitle { color:#64748b; font-size:8.5pt; font-weight:800; }
            QLabel#MetricValue { color:#0f172a; font-size:19pt; font-weight:900; }
            QLabel#SectionTitle { color:#0f172a; font-size:15pt; font-weight:900; }
            QLabel#SectionHint { color:#64748b; font-size:9pt; }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QLineEdit, QComboBox, QDateEdit { background:white; border:1px solid #cbd5e1; border-radius:8px; padding:7px 10px; }
            QTableWidget { background:white; border:1px solid #e2e8f0; border-radius:10px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:0; border-right:1px solid #e2e8f0; padding:9px; font-weight:900; }
            """
        )

    def refresh(self, *args) -> None:
        try:
            with get_session() as session:
                self.rows = load_production_requirements(
                    session, planning_date=self.plan_date.date().toPython()
                )
            summary = summarize_production_requirements(self.rows)
            self.metrics["items"].setText(f"{summary.total_items:,}")
            self.metrics["ready"].setText(f"{summary.ready_items:,}")
            self.metrics["required"].setText(f"{summary.production_required_items:,}")
            self.metrics["shortage"].setText(f"{summary.total_shortage_qty:,}")
            self.metrics["required_qty"].setText(
                f"{summary.total_production_required_qty:,}"
            )
            self.metrics["tons"].setText(
                f"{summary.total_production_required_tons:,.2f}"
            )
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Stock Planning Error", str(exc))

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        status = self.status_combo.currentText()
        self.visible_rows = []
        for row in self.rows:
            if status != "ALL" and row.status != status:
                continue
            if self.shortage_only.isChecked() and row.production_required_qty <= 0:
                continue
            searchable = (
                f"{row.material_code} {row.item_description} {row.product_group} "
                f"{row.status} {' '.join(row.warnings)}"
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_rows.append(row)
        self._populate_table()

    def _populate_table(self) -> None:
        self.selected_material_code = None
        self.open_detail_btn.setEnabled(False)
        self.table.setRowCount(0)
        for row_index, row in enumerate(self.visible_rows):
            self.table.insertRow(row_index)
            values = [
                row.material_code,
                row.item_description,
                row.product_group,
                f"{row.fg_stock:,}",
                f"{row.qc_stock:,}",
                f"{row.scrap_stock:,}",
                f"{row.blocked_stock:,}",
                f"{row.available_stock_at_date:,}",
                f"{row.eligible_shipment_demand:,}",
                f"{row.shortage_qty:,}",
                f"{row.production_required_qty:,}",
                f"{row.unit_weight_kg:,.3f}",
                f"{row.production_required_tons:,.3f}",
                row.status,
                "; ".join(row.warnings) or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column != 1 and column != 14:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.material_code)
                if column == 13:
                    self._style_status(item, row.status)
                if column == 14 and row.warnings:
                    item.setToolTip("; ".join(row.warnings))
                self.table.setItem(row_index, column, item)

    def _style_status(self, item: QTableWidgetItem, status: str) -> None:
        if status == "READY":
            colors = ("#166534", "#dcfce7")
        elif status in {"PARTIAL READY", "PRODUCTION REQUIRED"}:
            colors = ("#92400e", "#fef3c7")
        elif status == "MISSING DEMAND":
            colors = ("#475569", "#f1f5f9")
        else:
            colors = ("#991b1b", "#fee2e2")
        item.setForeground(QColor(colors[0]))
        item.setBackground(QColor(colors[1]))

    def _selection_changed(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            self.selected_material_code = None
        else:
            self.selected_material_code = self.table.item(selected[0].row(), 0).data(
                Qt.ItemDataRole.UserRole
            )
        self.open_detail_btn.setEnabled(bool(self.selected_material_code))

    def open_selected_item(self) -> None:
        if not self.selected_material_code:
            return
        if self.open_item_detail_callback is None:
            QMessageBox.information(self, "Item Detail", "Item detail page is not connected.")
            return
        self.open_item_detail_callback(self.selected_material_code)

    def export_csv(self) -> None:
        if not self.visible_rows:
            QMessageBox.warning(self, "Export CSV", "There are no visible rows.")
            return
        headers = [
            self.table.horizontalHeaderItem(column).text()
            for column in range(self.table.columnCount())
        ]
        rows = [
            [
                self.table.item(row, column).text()
                if self.table.item(row, column) is not None
                else ""
                for column in range(self.table.columnCount())
            ]
            for row in range(self.table.rowCount())
        ]
        path = export_to_csv(headers, rows, "stock_planning")
        QMessageBox.information(self, "Export Complete", f"CSV exported to:\n\n{path}")
