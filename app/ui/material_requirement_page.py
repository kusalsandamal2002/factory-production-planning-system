from __future__ import annotations

from datetime import date

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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.material_requirement_service import (
    DEMAND_BASIS_OVEN,
    DEMAND_BASIS_SHORTAGE,
    ConsolidatedMaterialRow,
    ExcelMaterialPlanRow,
    MaterialRequirementRow,
    PlanningAssumptions,
    build_material_requirements,
    consolidate_material_requirements,
    latest_material_planning_date,
    load_excel_material_plan_snapshot,
    load_material_demands,
)
from app.utils.reports_export import export_to_csv


class MaterialRequirementPage(QWidget):
    """Professional daily MRP and Excel reconciliation workspace."""

    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.rows: list[MaterialRequirementRow] = []
        self.visible_rows: list[MaterialRequirementRow] = []
        self.summary_rows: list[ConsolidatedMaterialRow] = []
        self.visible_summary_rows: list[ConsolidatedMaterialRow] = []
        self.excel_rows: list[ExcelMaterialPlanRow] = []
        self.visible_excel_rows: list[ExcelMaterialPlanRow] = []
        self.demand_item_count = 0
        self.snapshot_date: date | None = None
        self.snapshot_workbook = ""

        self.metrics = {
            "items": QLabel("0"),
            "compound": QLabel("0.00 kg"),
            "bead": QLabel("0 pcs"),
            "band": QLabel("0 pcs"),
            "core": QLabel("0 pcs"),
            "warnings": QLabel("0"),
        }

        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())

        self.basis_combo = QComboBox()
        self.basis_combo.addItem("Oven Day + Night Plan", DEMAND_BASIS_OVEN)
        self.basis_combo.addItem("Shipment Shortage / MRP", DEMAND_BASIS_SHORTAGE)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search finished item, material, code, source, or status...")
        self.search_input.textChanged.connect(self.filter_tables)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["ALL", "COMPOUND", "BOM", "BEAD", "BAND", "CORE"])
        self.type_combo.currentTextChanged.connect(self.filter_tables)

        self.exceptions_only = QCheckBox("Exceptions only")
        self.exceptions_only.stateChanged.connect(self.filter_tables)

        self.refresh_btn = QPushButton("Calculate MRP")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.latest_btn = QPushButton("Latest Plan")
        self.latest_btn.setObjectName("SecondaryButton")
        self.latest_btn.clicked.connect(self.use_latest_plan_date)
        self.export_btn = QPushButton("Export Current View")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_current_view)

        self.source_label = QLabel("Source: -")
        self.source_label.setObjectName("SourceStatus")
        self.source_label.setWordWrap(True)

        self.summary_table = QTableWidget(0, 14)
        self.summary_table.setHorizontalHeaderLabels(
            [
                "Type",
                "Material Code",
                "Material / Planning Key",
                "Unit",
                "Calculated Required",
                "Excel Plan",
                "Excel Stock",
                "Produced",
                "Net To Prepare",
                "Next Day",
                "Variance",
                "Finished Items",
                "Status",
                "Source",
            ]
        )
        self.detail_table = QTableWidget(0, 15)
        self.detail_table.setHorizontalHeaderLabels(
            [
                "Finished Item",
                "Description",
                "Day Plan",
                "Night Plan",
                "Total Plan",
                "Type",
                "Material Code",
                "Material Name",
                "Usage / Unit",
                "Base Required",
                "Allowance",
                "Day Required",
                "Night Required",
                "Final Required",
                "Warning",
            ]
        )
        self.excel_table = QTableWidget(0, 12)
        self.excel_table.setHorizontalHeaderLabels(
            [
                "Plan Date",
                "Type",
                "Material",
                "Day",
                "Night",
                "Total Plan",
                "Stock",
                "Produced",
                "Net Gap",
                "Next Day",
                "Unit",
                "Source",
            ]
        )

        self._setup_tables()
        self._apply_styles()
        self._build_ui()
        self._select_initial_date()

        self.plan_date.dateChanged.connect(self.refresh)
        self.basis_combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(14)
        metric_grid.setVerticalSpacing(12)
        labels = [
            ("Planned Finished Items", "items"),
            ("Compound Requirement", "compound"),
            ("Bead Requirement", "bead"),
            ("Band Requirement", "band"),
            ("Core Excel Plan", "core"),
            ("MRP Exceptions", "warnings"),
        ]
        for index, (title, key) in enumerate(labels):
            metric_grid.addWidget(
                self._metric_card(title, self.metrics[key]), index // 3, index % 3
            )
        root.addLayout(metric_grid)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 16)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Professional Material Requirement Planning")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "Workbook rules are reproduced explicitly: compound +25%, band +15%, "
            "and bead quantity from the approved bead master. Calculated MRP is "
            "reconciled with the imported Excel material plan when both dates match. "
            "CORE stays Excel-controlled until a per-tyre core master is approved."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        heading.addLayout(title_box, 1)
        heading.addWidget(self.latest_btn)
        heading.addWidget(self.refresh_btn)
        heading.addWidget(self.export_btn)
        layout.addLayout(heading)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Planning Date"))
        filters.addWidget(self.plan_date)
        filters.addWidget(QLabel("Demand Basis"))
        filters.addWidget(self.basis_combo)
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 1)
        filters.addWidget(QLabel("Type"))
        filters.addWidget(self.type_combo)
        filters.addWidget(self.exceptions_only)
        layout.addLayout(filters)
        layout.addWidget(self.source_label)
        root.addWidget(card)

        tabs_card = QFrame()
        tabs_card.setObjectName("Card")
        tabs_layout = QVBoxLayout(tabs_card)
        tabs_layout.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.summary_table, "Consolidated Material Plan")
        self.tabs.addTab(self.detail_table, "Finished Item Breakdown")
        self.tabs.addTab(self.excel_table, "Imported Excel Snapshot")
        tabs_layout.addWidget(self.tabs)
        root.addWidget(tabs_card, 1)

    def _metric_card(self, title_text: str, label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 11, 16, 11)
        title = QLabel(title_text)
        title.setObjectName("MetricTitle")
        label.setObjectName("MetricValue")
        layout.addWidget(title)
        layout.addWidget(label)
        return card

    def _setup_tables(self) -> None:
        for table in (self.summary_table, self.detail_table, self.excel_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(38)
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)

        summary_header = self.summary_table.horizontalHeader()
        for column in range(self.summary_table.columnCount()):
            summary_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        summary_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        summary_header.setSectionResizeMode(13, QHeaderView.ResizeMode.Stretch)
        for index, width in enumerate(
            [88, 125, 230, 65, 120, 100, 95, 90, 115, 90, 95, 92, 115, 210]
        ):
            self.summary_table.setColumnWidth(index, width)

        detail_header = self.detail_table.horizontalHeader()
        for column in range(self.detail_table.columnCount()):
            detail_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        detail_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        detail_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        detail_header.setSectionResizeMode(14, QHeaderView.ResizeMode.Stretch)
        for index, width in enumerate(
            [115, 210, 78, 82, 85, 88, 120, 210, 90, 105, 78, 105, 105, 115, 190]
        ):
            self.detail_table.setColumnWidth(index, width)

        excel_header = self.excel_table.horizontalHeader()
        for column in range(self.excel_table.columnCount()):
            excel_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        excel_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        excel_header.setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        for index, width in enumerate(
            [95, 90, 250, 85, 85, 100, 90, 90, 95, 90, 70, 170]
        ):
            self.excel_table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card, QFrame#MetricCard { background:white; border:1px solid #e2e8f0; border-radius:14px; }
            QLabel#MetricTitle { color:#64748b; font-size:8.5pt; font-weight:800; }
            QLabel#MetricValue { color:#0f172a; font-size:17pt; font-weight:900; }
            QLabel#SectionTitle { color:#0f172a; font-size:15pt; font-weight:900; }
            QLabel#SectionHint { color:#64748b; font-size:9pt; }
            QLabel#SourceStatus { color:#334155; background:#f8fafc; border:1px solid #e2e8f0; border-radius:7px; padding:7px 10px; }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:0; border-radius:9px; padding:9px 13px; font-weight:900; }
            QLineEdit, QComboBox, QDateEdit { background:white; border:1px solid #cbd5e1; border-radius:8px; padding:7px 10px; }
            QCheckBox { color:#334155; font-weight:700; }
            QTableWidget { background:white; border:1px solid #e2e8f0; border-radius:9px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:0; border-right:1px solid #e2e8f0; padding:8px; font-weight:900; }
            QTabWidget::pane { border:0; }
            QTabBar::tab { background:#f1f5f9; color:#475569; padding:9px 16px; margin-right:4px; border-top-left-radius:7px; border-top-right-radius:7px; font-weight:800; }
            QTabBar::tab:selected { background:#2563eb; color:white; }
            """
        )

    def _select_initial_date(self) -> None:
        try:
            with get_session() as session:
                latest = latest_material_planning_date(session)
            if latest and latest != date.today():
                self.plan_date.setDate(QDate(latest.year, latest.month, latest.day))
        except Exception:
            # The normal refresh path will show a useful database error if needed.
            pass

    def use_latest_plan_date(self) -> None:
        try:
            with get_session() as session:
                latest = latest_material_planning_date(session)
            if not latest:
                QMessageBox.information(self, "Latest Plan", "No oven or Excel material plan is available yet.")
                return
            self.plan_date.setDate(QDate(latest.year, latest.month, latest.day))
        except Exception as exc:
            QMessageBox.critical(self, "Latest Plan", str(exc))

    def refresh(self, *args) -> None:
        try:
            planning_date = self.plan_date.date().toPython()
            basis = str(self.basis_combo.currentData() or DEMAND_BASIS_OVEN)
            with get_session() as session:
                demand_rows = load_material_demands(
                    session,
                    planning_date=planning_date,
                    basis=basis,
                )
                self.rows = build_material_requirements(
                    session,
                    demand_rows=demand_rows,
                    assumptions=PlanningAssumptions(),
                )
                (
                    self.excel_rows,
                    self.snapshot_date,
                    self.snapshot_workbook,
                ) = load_excel_material_plan_snapshot(
                    session,
                    planning_date=planning_date,
                )

            self.demand_item_count = len(demand_rows)
            reconcile_rows = (
                self.excel_rows
                if basis == DEMAND_BASIS_OVEN and self.snapshot_date == planning_date
                else []
            )
            self.summary_rows = consolidate_material_requirements(self.rows, reconcile_rows)
            self._update_metrics()
            self._update_source_status(planning_date, basis)
            self.filter_tables()
        except Exception as exc:
            QMessageBox.critical(self, "Material Requirement Error", str(exc))

    def _update_metrics(self) -> None:
        self.metrics["items"].setText(f"{self.demand_item_count:,}")
        compound = sum(
            row.calculated_required_qty
            for row in self.summary_rows
            if row.component_type == "COMPOUND"
        )
        bead = sum(
            row.calculated_required_qty
            for row in self.summary_rows
            if row.component_type == "BEAD"
        )
        band = sum(
            row.calculated_required_qty
            for row in self.summary_rows
            if row.component_type == "BAND"
        )
        core = sum(row.total_qty for row in self.excel_rows if row.material_type == "CORE")
        exceptions = sum(bool(row.warning) for row in self.rows) + sum(
            row.status in {"CHECK VARIANCE", "MASTER WARNING"} for row in self.summary_rows
        )
        self.metrics["compound"].setText(f"{compound:,.2f} kg")
        self.metrics["bead"].setText(f"{bead:,.0f} pcs")
        self.metrics["band"].setText(f"{band:,.0f} pcs")
        self.metrics["core"].setText(f"{core:,.0f} pcs")
        self.metrics["warnings"].setText(f"{exceptions:,}")

    def _update_source_status(self, planning_date: date, basis: str) -> None:
        basis_text = (
            "Oven day + night production plan"
            if basis == DEMAND_BASIS_OVEN
            else "shipment shortage / production requirement"
        )
        if self.snapshot_date is None:
            snapshot_text = "No imported Excel material snapshot available"
        else:
            workbook = f" · {self.snapshot_workbook}" if self.snapshot_workbook else ""
            if self.snapshot_date == planning_date:
                snapshot_text = f"Excel reconciliation ACTIVE: {self.snapshot_date}{workbook}"
            else:
                age = (planning_date - self.snapshot_date).days
                age_text = f"{abs(age)} day(s) {'older' if age >= 0 else 'newer'}"
                snapshot_text = (
                    f"Excel snapshot: {self.snapshot_date}{workbook} · {age_text}; "
                    "shown for audit only, not used for variance reconciliation"
                )
        self.source_label.setText(
            f"Demand source: {basis_text} · Planning date: {planning_date} · {snapshot_text}"
        )

    def filter_tables(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        component_type = self.type_combo.currentText()
        exceptions_only = self.exceptions_only.isChecked()

        self.visible_summary_rows = []
        for row in self.summary_rows:
            if component_type != "ALL" and row.component_type != component_type:
                continue
            if exceptions_only and row.status not in {"CHECK VARIANCE", "MASTER WARNING"}:
                continue
            searchable = (
                f"{row.component_type} {row.material_code} {row.material_name} "
                f"{row.status} {row.source}"
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_summary_rows.append(row)

        self.visible_rows = []
        for row in self.rows:
            if component_type != "ALL" and row.component_type != component_type:
                continue
            if exceptions_only and not row.warning:
                continue
            searchable = (
                f"{row.finished_item_code} {row.finished_item_description} "
                f"{row.raw_material_code} {row.raw_material_name} {row.warning} "
                f"{row.master_source}"
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_rows.append(row)

        self.visible_excel_rows = []
        for row in self.excel_rows:
            if component_type != "ALL" and row.material_type != component_type:
                continue
            if exceptions_only:
                continue
            searchable = (
                f"{row.material_type} {row.material_key} {row.material_description} "
                f"{row.source} {row.workbook_name}"
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_excel_rows.append(row)

        self._populate_summary()
        self._populate_detail()
        self._populate_excel()

    def _populate_summary(self) -> None:
        table = self.summary_table
        table.setRowCount(len(self.visible_summary_rows))
        for row_index, row in enumerate(self.visible_summary_rows):
            values = [
                row.component_type,
                row.material_code,
                row.material_name,
                row.unit,
                _qty(row.calculated_required_qty),
                _qty(row.excel_plan_qty) if row.excel_plan_qty else "-",
                _qty(row.excel_stock_qty) if row.excel_stock_qty else "-",
                _qty(row.excel_produced_qty) if row.excel_produced_qty else "-",
                _qty(row.net_to_prepare_qty),
                _qty(row.excel_next_day_qty) if row.excel_next_day_qty else "-",
                _signed_qty(row.variance_qty) if row.excel_plan_qty else "-",
                f"{row.finished_item_count:,}",
                row.status,
                row.source,
            ]
            for column, value in enumerate(values):
                item = self._item(value, center=column not in {2, 13})
                if column == 12:
                    item.setForeground(_status_color(row.status))
                if column == 10 and row.status == "CHECK VARIANCE":
                    item.setForeground(QColor("#b91c1c"))
                item.setToolTip(row.source)
                table.setItem(row_index, column, item)

    def _populate_detail(self) -> None:
        table = self.detail_table
        table.setRowCount(len(self.visible_rows))
        for row_index, row in enumerate(self.visible_rows):
            values = [
                row.finished_item_code,
                row.finished_item_description,
                f"{row.day_production_qty:,}" if row.day_production_qty else "-",
                f"{row.night_production_qty:,}" if row.night_production_qty else "-",
                f"{row.production_required_qty:,}",
                row.component_type,
                row.raw_material_code,
                row.raw_material_name,
                f"{row.usage_per_unit:,.6f}",
                _qty(row.base_required_qty),
                f"{row.allowance_rate:.0%}",
                _qty(row.day_required_qty) if row.day_required_qty else "-",
                _qty(row.night_required_qty) if row.night_required_qty else "-",
                f"{_qty(row.required_qty)} {row.unit}",
                row.warning or "-",
            ]
            for column, value in enumerate(values):
                item = self._item(value, center=column not in {1, 7, 14})
                item.setToolTip(
                    f"Demand: {row.demand_source}\nMaster: {row.master_source or '-'}"
                )
                if row.warning and column == 14:
                    item.setForeground(QColor("#b91c1c"))
                table.setItem(row_index, column, item)

    def _populate_excel(self) -> None:
        table = self.excel_table
        table.setRowCount(len(self.visible_excel_rows))
        for row_index, row in enumerate(self.visible_excel_rows):
            values = [
                str(row.plan_date or "-"),
                row.material_type,
                row.material_key,
                _qty(row.day_qty),
                _qty(row.night_qty),
                _qty(row.total_qty),
                _qty(row.stock_qty),
                _qty(row.produced_qty),
                _qty(row.net_gap_qty),
                _qty(row.next_day_qty),
                row.unit,
                row.source,
            ]
            for column, value in enumerate(values):
                item = self._item(value, center=column not in {2, 11})
                item.setToolTip(row.workbook_name or row.source)
                table.setItem(row_index, column, item)

    def _item(self, value: object, *, center: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(str(value))
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def export_current_view(self) -> None:
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget) or table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "There are no rows in the current view.")
            return
        headers = [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ]
        data = [
            [
                table.item(row, column).text()
                if table.item(row, column) is not None
                else ""
                for column in range(table.columnCount())
            ]
            for row in range(table.rowCount())
        ]
        tab_index = self.tabs.currentIndex()
        prefix = ["material_requirement_summary", "material_requirement_detail", "material_requirement_excel_snapshot"][tab_index]
        path = export_to_csv(headers, data, prefix)
        QMessageBox.information(self, "Export Complete", f"CSV exported to:\n\n{path}")


def _qty(value: float) -> str:
    if abs(value - round(value)) < 0.000001:
        return f"{value:,.0f}"
    return f"{value:,.3f}".rstrip("0").rstrip(".")


def _signed_qty(value: float) -> str:
    text = _qty(abs(value))
    if value > 0:
        return f"+{text}"
    if value < 0:
        return f"-{text}"
    return "0"


def _status_color(status: str) -> QColor:
    return QColor(
        {
            "MATCH": "#15803d",
            "CHECK VARIANCE": "#b91c1c",
            "MASTER WARNING": "#b91c1c",
            "EXCEL PLAN": "#1d4ed8",
            "CALCULATED": "#475569",
        }.get(status, "#334155")
    )
