from __future__ import annotations

from PySide6.QtCore import QDate, Qt
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
from app.services.material_requirement_service import (
    MaterialRequirementRow,
    PlanningAssumptions,
    build_material_requirements,
)
from app.services.production_requirement_service import load_production_requirements
from app.utils.reports_export import export_to_csv


class MaterialRequirementPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.rows: list[MaterialRequirementRow] = []
        self.visible_rows: list[MaterialRequirementRow] = []
        self.metrics = {
            "items": QLabel("0"),
            "bom": QLabel("0.00"),
            "compound": QLabel("0.00"),
            "warnings": QLabel("0"),
        }
        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(self.refresh)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search finished item or component...")
        self.search_input.textChanged.connect(self.filter_table)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["ALL", "BOM", "COMPOUND", "BEAD", "BAND"])
        self.type_combo.currentTextChanged.connect(self.filter_table)
        self.refresh_btn = QPushButton("Calculate Requirements")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_csv)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "Finished Item",
                "Description",
                "Production Required",
                "Type",
                "Material Code",
                "Material Name",
                "Usage / Unit",
                "Base Required",
                "Allowance",
                "Final Required",
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
        for title, key in [
            ("Shortage Products", "items"),
            ("BOM Requirement", "bom"),
            ("Compound Requirement", "compound"),
            ("Missing BOM Warnings", "warnings"),
        ]:
            metrics.addWidget(self._metric_card(title, self.metrics[key]), 1)
        root.addLayout(metrics)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Material Requirement Planning")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "BOM wastage is applied per master record. Compound uses the visible "
            "25% Excel allowance and band uses the visible 15% Excel allowance."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
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
        filters.addWidget(QLabel("Component Type"))
        filters.addWidget(self.type_combo)
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
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        widths = [115, 200, 110, 90, 125, 200, 90, 105, 85, 105, 150]
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
            with get_session() as session:
                production = load_production_requirements(
                    session,
                    planning_date=self.plan_date.date().toPython(),
                    production_required_only=True,
                )
                self.rows = build_material_requirements(
                    session,
                    production_rows=production,
                    assumptions=PlanningAssumptions(),
                )
            self.metrics["items"].setText(f"{len(production):,}")
            self.metrics["bom"].setText(
                f"{sum(row.required_qty for row in self.rows if row.component_type == 'BOM'):,.2f}"
            )
            self.metrics["compound"].setText(
                f"{sum(row.required_qty for row in self.rows if row.component_type == 'COMPOUND'):,.2f}"
            )
            self.metrics["warnings"].setText(
                f"{sum(bool(row.warning) for row in self.rows):,}"
            )
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Material Requirement Error", str(exc))

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        component_type = self.type_combo.currentText()
        self.visible_rows = []
        for row in self.rows:
            if component_type != "ALL" and row.component_type != component_type:
                continue
            searchable = (
                f"{row.finished_item_code} {row.finished_item_description} "
                f"{row.raw_material_code} {row.raw_material_name} {row.warning}"
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
                row.finished_item_code,
                row.finished_item_description,
                f"{row.production_required_qty:,}",
                row.component_type,
                row.raw_material_code,
                row.raw_material_name,
                f"{row.usage_per_unit:,.6f}",
                f"{row.base_required_qty:,.4f}",
                f"{row.allowance_rate:.0%}",
                f"{row.required_qty:,.4f} {row.unit}",
                row.warning or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column not in {1, 5, 10}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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
        path = export_to_csv(headers, data, "material_requirement")
        QMessageBox.information(self, "Export Complete", f"CSV exported to:\n\n{path}")
