from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from app.services.material_requirement_service import PlanningAssumptions
from app.services.oven_schedule_service import (
    OvenScheduleRow,
    OvenScheduleSummary,
    calculate_daily_oven_plan,
)
from app.utils.reports_export import export_to_csv


SCHEDULE_STATUSES = [
    "ALL",
    "PLANNED",
    "PARTIAL",
    "UNPLANNED",
    "MISSING CAPACITY",
    "MISSING COMPATIBILITY",
    "MISSING WEIGHT",
    "MISSING DUE DATE",
]


class SchedulePage(QWidget):
    """Quantity/mould/day planning with no unverified minute logic."""

    def __init__(self, current_user_id=None):
        super().__init__()
        self.current_user = current_user_id
        self.plan_rows: list[OvenScheduleRow] = []
        self.visible_rows: list[OvenScheduleRow] = []

        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(self.refresh)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search material, description, oven, status, or risk..."
        )
        self.search_input.textChanged.connect(self.filter_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(SCHEDULE_STATUSES)
        self.status_combo.currentTextChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.recalculate_btn = QPushButton("Recalculate Plan")
        self.recalculate_btn.setObjectName("PrimaryButton")
        self.recalculate_btn.clicked.connect(self.recalculate_plan)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_csv)

        self.metric_labels = {
            "required": QLabel("0"),
            "planned": QLabel("0"),
            "unplanned": QLabel("0"),
            "tons": QLabel("0.00"),
            "missing_capacity": QLabel("0"),
            "missing_compatibility": QLabel("0"),
            "missing_due_date": QLabel("0"),
            "missing_weight": QLabel("0"),
            "warnings": QLabel("0"),
        }
        self.capacity_status = QLabel("NO DATA")
        self.capacity_status.setObjectName("StatusBadge")
        self.assumption_note = QLabel("")
        self.assumption_note.setObjectName("AssumptionNote")
        self.assumption_note.setWordWrap(True)

        self.table = QTableWidget(0, 16)
        self.table.setHorizontalHeaderLabels(
            [
                "Material Code",
                "Item Description",
                "Due Date",
                "Demand Qty",
                "Available Stock",
                "Shortage Qty",
                "Production Required Qty",
                "Effective Daily Capacity",
                "Planned Day Qty",
                "Planned Night Qty",
                "Selected Date Planned Qty",
                "Remaining Qty After Selected Date",
                "Planned Tons",
                "Oven / Press",
                "Status",
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

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        cards = [
            ("Production Required Qty", "required"),
            ("Selected Date Planned Qty", "planned"),
            ("Remaining Qty After Selected Date", "unplanned"),
            ("Planned Tons", "tons"),
            ("Missing Capacity Items", "missing_capacity"),
            ("Missing Compatibility Items", "missing_compatibility"),
            ("Missing Due Date Items", "missing_due_date"),
            ("Missing Weight Items", "missing_weight"),
            ("Warning Items", "warnings"),
        ]
        for index, (title, key) in enumerate(cards):
            metrics.addWidget(
                self._metric_card(title, self.metric_labels[key]),
                index // 3,
                index % 3,
            )
        root.addLayout(metrics)

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 16, 18, 18)
        controls_layout.setSpacing(12)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Daily Quantity-Based Oven Plan")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "Uses shipment shortage, mould/day capacity, and historical active "
            "oven compatibility. Imported mpps_oven_plan rows remain read-only."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        heading.addLayout(title_box, 1)
        heading.addWidget(self.capacity_status)
        heading.addWidget(self.refresh_btn)
        heading.addWidget(self.recalculate_btn)
        heading.addWidget(self.export_btn)
        controls_layout.addLayout(heading)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Planning Date"))
        filters.addWidget(self.plan_date)
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 1)
        filters.addWidget(QLabel("Status"))
        filters.addWidget(self.status_combo)
        controls_layout.addLayout(filters)
        controls_layout.addWidget(self.assumption_note)
        root.addWidget(controls)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(10)
        table_title = QLabel("Day / Night Quantity Allocation and Risk")
        table_title.setObjectName("SectionTitle")
        table_layout.addWidget(table_title)
        table_layout.addWidget(self.table, 1)
        root.addWidget(table_card, 1)

    def _metric_card(self, title_text: str, value_label: QLabel) -> QFrame:
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

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(15, QHeaderView.ResizeMode.Stretch)
        widths = [
            120,
            220,
            95,
            90,
            100,
            90,
            115,
            130,
            105,
            110,
            110,
            120,
            95,
            130,
            145,
            260,
        ]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card, QFrame#MetricCard {
                background:#ffffff; border:1px solid #e2e8f0; border-radius:14px;
            }
            QLabel#MetricTitle { color:#64748b; font-size:8.5pt; font-weight:800; }
            QLabel#MetricValue { color:#0f172a; font-size:18pt; font-weight:900; }
            QLabel#SectionTitle { color:#0f172a; font-size:15pt; font-weight:900; }
            QLabel#SectionHint, QLabel#AssumptionNote { color:#64748b; font-size:9pt; }
            QLabel#StatusBadge {
                background:#e2e8f0; color:#0f172a; border-radius:10px;
                padding:8px 12px; font-weight:900;
            }
            QPushButton#PrimaryButton {
                background:#2563eb; color:white; border:0; border-radius:9px;
                padding:9px 15px; font-weight:900;
            }
            QPushButton#SecondaryButton {
                background:#e2e8f0; color:#0f172a; border:0; border-radius:9px;
                padding:9px 15px; font-weight:900;
            }
            QLineEdit, QComboBox, QDateEdit {
                background:white; color:#0f172a; border:1px solid #cbd5e1;
                border-radius:8px; padding:7px 10px; min-height:24px;
            }
            QTableWidget {
                background:white; color:#0f172a; border:1px solid #e2e8f0;
                border-radius:10px; gridline-color:#e2e8f0;
                alternate-background-color:#f8fafc;
                selection-background-color:#dbeafe; selection-color:#0f172a;
            }
            QHeaderView::section {
                background:#f1f5f9; color:#1e293b; border:0;
                border-right:1px solid #e2e8f0; padding:9px; font-weight:900;
            }
            """
        )

    def refresh(self, *args) -> None:
        self._load_plan(show_message=False)

    def recalculate_plan(self, *args) -> None:
        self._load_plan(show_message=True)

    def _load_plan(self, *, show_message: bool) -> None:
        try:
            with get_session() as session:
                rows, summary = calculate_daily_oven_plan(
                    session,
                    planning_date=self.plan_date.date().toPython(),
                    assumptions=PlanningAssumptions(),
                )
            self._set_plan(rows, summary)
            if show_message:
                QMessageBox.information(
                    self,
                    "Plan Recalculated",
                    "Quantity-based plan recalculated in memory. Imported Excel plan "
                    "rows and all source data were not overwritten.",
                )
        except Exception as exc:
            QMessageBox.critical(self, "Daily Oven Schedule", str(exc))

    def _set_plan(
        self,
        rows: list[OvenScheduleRow],
        summary: OvenScheduleSummary,
    ) -> None:
        self.plan_rows = rows
        values = {
            "required": summary.production_required_qty,
            "planned": summary.planned_qty,
            "unplanned": summary.unplanned_qty,
            "missing_capacity": summary.missing_capacity_items,
            "missing_compatibility": summary.missing_compatibility_items,
            "missing_due_date": summary.missing_due_date_items,
            "missing_weight": summary.missing_weight_items,
            "warnings": summary.risk_warning_count,
        }
        for key, value in values.items():
            self.metric_labels[key].setText(f"{value:,}")
        self.metric_labels["tons"].setText(f"{summary.planned_tons:,.2f}")
        self.capacity_status.setText(summary.capacity_status)
        self.assumption_note.setText(summary.assumption_note)
        self.filter_table()

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        status = self.status_combo.currentText()
        self.visible_rows = []
        for row in self.plan_rows:
            if status != "ALL" and row.status != status:
                continue
            searchable = " ".join(
                [
                    row.material_code,
                    row.item_description,
                    row.oven_code,
                    row.line_category,
                    row.status,
                    row.risk_reason,
                ]
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_rows.append(row)
        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for row_index, row in enumerate(self.visible_rows):
            self.table.insertRow(row_index)
            values = [
                row.material_code,
                row.item_description,
                row.due_date.isoformat() if row.due_date else "MISSING",
                f"{row.demand_qty:,}",
                f"{row.available_stock:,}",
                f"{row.shortage_qty:,}",
                f"{row.production_required_qty:,}",
                f"{row.effective_daily_capacity:,.2f}",
                f"{row.day_qty:,}",
                f"{row.night_qty:,}",
                f"{row.total_planned_qty:,}",
                f"{row.remaining_qty:,}",
                f"{row.planned_tons:,.3f}",
                row.oven_code,
                row.status,
                row.risk_reason or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column not in {1, 15}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 14:
                    self._style_status(item, row.status)
                if column == 15:
                    item.setToolTip(row.risk_reason)
                self.table.setItem(row_index, column, item)

    def _style_status(self, item: QTableWidgetItem, status: str) -> None:
        colors = {
            "PLANNED": ("#166534", "#dcfce7"),
            "PARTIAL": ("#92400e", "#fef3c7"),
            "UNPLANNED": ("#991b1b", "#fee2e2"),
            "MISSING CAPACITY": ("#991b1b", "#fee2e2"),
            "MISSING COMPATIBILITY": ("#991b1b", "#fee2e2"),
            "MISSING WEIGHT": ("#92400e", "#fef3c7"),
            "MISSING DUE DATE": ("#1d4ed8", "#dbeafe"),
        }
        foreground, background = colors.get(status, ("#475569", "#f1f5f9"))
        item.setForeground(QColor(foreground))
        item.setBackground(QColor(background))

    def export_csv(self) -> None:
        if not self.visible_rows:
            QMessageBox.warning(self, "Export CSV", "There are no visible plan rows.")
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
        path = export_to_csv(headers, data, "daily_oven_schedule")
        QMessageBox.information(self, "Export Complete", f"CSV exported to:\n\n{path}")
