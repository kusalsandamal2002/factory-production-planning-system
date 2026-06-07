from __future__ import annotations

from datetime import date

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
from sqlalchemy import text

from app.database import get_session
from app.services.material_requirement_service import PlanningAssumptions
from app.services.oven_capacity_service import build_capacity_analysis
from app.services.oven_schedule_service import (
    OvenScheduleRow,
    OvenScheduleSummary,
    build_daily_oven_schedule,
    load_imported_oven_plan,
)
from app.services.production_requirement_service import load_production_requirements
from app.utils.reports_export import export_to_csv


class SchedulePage(QWidget):
    """Quantity-based daily oven planning page.

    The legacy minute scheduler remains available to the order enquiry workflow,
    but this page intentionally uses only MPPS quantity, mould, and oven evidence.
    """

    def __init__(self, current_user_id=None):
        super().__init__()
        self.current_user = current_user_id
        self.plan_rows: list[OvenScheduleRow] = []
        self.visible_rows: list[OvenScheduleRow] = []
        self.plan_source = "CALCULATED"

        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(self.refresh)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search material, description, oven, or risk...")
        self.search_input.textChanged.connect(self.filter_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(
            ["ALL", "PLANNED", "PARTIALLY PLANNED", "UNPLANNED", "IMPORTED"]
        )
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
            "active_ovens": QLabel("0"),
            "required": QLabel("0"),
            "planned": QLabel("0"),
            "unplanned": QLabel("0"),
            "tons": QLabel("0.00"),
            "warnings": QLabel("0"),
        }
        self.capacity_status = QLabel("NO DATA")
        self.capacity_status.setObjectName("StatusBadge")
        self.assumption_note = QLabel("")
        self.assumption_note.setObjectName("AssumptionNote")
        self.assumption_note.setWordWrap(True)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels(
            [
                "Date",
                "Material Code",
                "Description",
                "Oven / Press",
                "Line / Category",
                "Day Qty",
                "Night Qty",
                "Total Planned",
                "Remaining",
                "Planned Tons",
                "Status",
                "Risk Reason",
                "Source",
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
            ("Active Ovens / Presses", self.metric_labels["active_ovens"]),
            ("Production Required Qty", self.metric_labels["required"]),
            ("Planned Qty", self.metric_labels["planned"]),
            ("Unplanned Qty", self.metric_labels["unplanned"]),
            ("Planned Tons", self.metric_labels["tons"]),
            ("Risk Warnings", self.metric_labels["warnings"]),
        ]
        for index, (title, label) in enumerate(cards):
            metrics.addWidget(self._metric_card(title, label), index // 3, index % 3)
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
            "Plans pieces by approved mould/day capacity and observed Excel oven "
            "compatibility. No curing-minute or downtime values are invented."
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
        table_title = QLabel("Day / Night Allocation and Unplanned Risk")
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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        widths = [92, 125, 230, 135, 120, 78, 82, 98, 90, 95, 135, 260, 90]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card, QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
            }
            QLabel#MetricTitle { color:#64748b; font-size:8.5pt; font-weight:800; }
            QLabel#MetricValue { color:#0f172a; font-size:19pt; font-weight:900; }
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
        """Load preserved Excel plan for the date, or calculate a read-only preview."""
        try:
            selected = self.plan_date.date().toPython()
            with get_session() as session:
                imported = load_imported_oven_plan(session, planning_date=selected)
                if imported:
                    production = load_production_requirements(
                        session, planning_date=selected
                    )
                    required = sum(
                        row.production_required_qty
                        for row in production
                        if row.production_required_qty > 0
                    )
                    planned = sum(row.total_planned_qty for row in imported)
                    active_ovens = int(
                        session.execute(
                            text("SELECT COUNT(*) FROM ovens WHERE is_active = TRUE")
                        ).scalar_one()
                    )
                    summary = OvenScheduleSummary(
                        active_ovens=active_ovens,
                        production_required_qty=required,
                        planned_qty=planned,
                        unplanned_qty=max(required - planned, 0),
                        planned_tons=round(sum(row.planned_tons for row in imported), 4),
                        capacity_status="IMPORTED EXCEL PLAN",
                        risk_warning_count=sum(bool(row.risk_reason) for row in imported),
                        assumption_note=(
                            "Read-only imported OVEN workbook plan. Imported rows preserve "
                            "TOTAL quantity, so day/night detail is unavailable."
                        ),
                    )
                    self._set_plan(imported, summary, "IMPORTED")
                    return
            self.recalculate_plan(show_message=False)
        except Exception as exc:
            QMessageBox.critical(self, "Daily Oven Schedule", str(exc))

    def recalculate_plan(self, *args, show_message: bool = True) -> None:
        try:
            selected: date = self.plan_date.date().toPython()
            with get_session() as session:
                production = load_production_requirements(
                    session,
                    planning_date=selected,
                    production_required_only=True,
                )
                capacity = build_capacity_analysis(
                    session,
                    production_rows=production,
                    planning_date=selected,
                )
                rows, summary = build_daily_oven_schedule(
                    session,
                    planning_date=selected,
                    production_rows=production,
                    capacity_rows=capacity,
                    assumptions=PlanningAssumptions(),
                )
            self._set_plan(rows, summary, "CALCULATED")
            if show_message:
                QMessageBox.information(
                    self,
                    "Plan Recalculated",
                    "Quantity-based preview recalculated. Preserved Excel plan rows "
                    "and database data were not overwritten.",
                )
        except Exception as exc:
            QMessageBox.critical(self, "Plan Recalculation Failed", str(exc))

    def _set_plan(
        self,
        rows: list[OvenScheduleRow],
        summary: OvenScheduleSummary,
        source: str,
    ) -> None:
        self.plan_rows = rows
        self.plan_source = source
        self.metric_labels["active_ovens"].setText(f"{summary.active_ovens:,}")
        self.metric_labels["required"].setText(f"{summary.production_required_qty:,}")
        self.metric_labels["planned"].setText(f"{summary.planned_qty:,}")
        self.metric_labels["unplanned"].setText(f"{summary.unplanned_qty:,}")
        self.metric_labels["tons"].setText(f"{summary.planned_tons:,.2f}")
        self.metric_labels["warnings"].setText(f"{summary.risk_warning_count:,}")
        self.capacity_status.setText(summary.capacity_status)
        self.assumption_note.setText(summary.assumption_note)
        self.filter_table()

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        status = self.status_combo.currentText()
        self.visible_rows = []
        for row in self.plan_rows:
            if status != "ALL" and status not in {row.status, self.plan_source}:
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
                row.plan_date.isoformat(),
                row.material_code,
                row.item_description,
                row.oven_code,
                row.line_category,
                f"{row.day_qty:,}",
                f"{row.night_qty:,}",
                f"{row.total_planned_qty:,}",
                f"{row.remaining_qty:,}",
                f"{row.planned_tons:,.3f}",
                row.status,
                row.risk_reason or "-",
                self.plan_source,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column in {0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 12}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 10:
                    self._style_status(item, row.status)
                if column == 11 and row.risk_reason:
                    item.setToolTip(row.risk_reason)
                self.table.setItem(row_index, column, item)

    def _style_status(self, item: QTableWidgetItem, status: str) -> None:
        if status in {"PLANNED", "IMPORTED"}:
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        elif status == "PARTIALLY PLANNED":
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))
        else:
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))

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
