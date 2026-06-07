from __future__ import annotations

from datetime import date
from math import floor
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import get_session
from app.services.oven_capacity_service import build_capacity_analysis
from app.services.oven_schedule_service import build_daily_oven_schedule
from app.services.production_requirement_service import (
    load_production_requirements,
    summarize_production_requirements,
)
from app.ui.production_calendar_panel import ProductionCalendarPanel


class MetricCard(QFrame):
    def __init__(
        self,
        label: str,
        value: str,
        hint: str,
        on_click: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.setObjectName("MetricCard")
        self.on_click = on_click
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("MetricLabel")
        self.value_widget = QLabel(value)
        self.value_widget.setObjectName("MetricValue")
        self.hint_widget = QLabel(hint)
        self.hint_widget.setObjectName("MetricHint")
        self.hint_widget.setWordWrap(True)
        self.open_button = QPushButton("Open details")
        self.open_button.setObjectName("SoftButton")
        self.open_button.setEnabled(on_click is not None)
        if on_click is not None:
            self.open_button.clicked.connect(on_click)

        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_widget)
        layout.addWidget(self.hint_widget)
        layout.addStretch()
        layout.addWidget(self.open_button)

    def mousePressEvent(self, event) -> None:
        if self.on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self.on_click()
        super().mousePressEvent(event)


class SummaryRow(QFrame):
    def __init__(self, label: str, value: str = "-"):
        super().__init__()
        self.setObjectName("SummaryRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("SummaryLabel")
        self.value_widget = QLabel(value)
        self.value_widget.setObjectName("SummaryValue")
        self.value_widget.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.label_widget, 1)
        layout.addWidget(self.value_widget, 1)

    def update_value(self, value: str) -> None:
        self.value_widget.setText(value)


class DashboardPage(QWidget):
    def __init__(
        self,
        open_total_shipments_page: Callable[[], None] | None = None,
        open_completed_orders_page: Callable[[], None] | None = None,
        open_pending_orders_page: Callable[[], None] | None = None,
        open_overdue_orders_page: Callable[[], None] | None = None,
    ):
        super().__init__()
        shipment_callback = open_total_shipments_page or (lambda: None)
        planning_callback = open_pending_orders_page or shipment_callback

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)
        self.metric_cards: dict[str, MetricCard] = {}

        self._build_metric_cards(shipment_callback, planning_callback)
        self._build_middle_section()
        self._build_capacity_panel()
        self.refresh()

    def _build_metric_cards(
        self,
        shipment_callback: Callable[[], None],
        planning_callback: Callable[[], None],
    ) -> None:
        grid = QGridLayout()
        grid.setSpacing(12)
        cards = [
            (
                "Active Shipment Demands",
                "active_demands",
                "MPPS demand rows currently included in planning",
                shipment_callback,
            ),
            (
                "Production Required Items",
                "required_items",
                "Materials with a stock shortage for the selected date",
                planning_callback,
            ),
            (
                "Production Required Qty",
                "required_qty",
                "Total quantity required after available stock",
                planning_callback,
            ),
            (
                "Planning Warnings",
                "warnings",
                "Missing due date, weight, capacity, or compatibility warnings",
                planning_callback,
            ),
        ]
        for index, (title, key, hint, callback) in enumerate(cards):
            card = MetricCard(title, "0", hint, callback)
            self.metric_cards[key] = card
            grid.addWidget(card, 0, index)
        self.main_layout.addLayout(grid)

    def _build_middle_section(self) -> None:
        middle = QHBoxLayout()
        middle.setSpacing(14)
        self.calendar_panel = ProductionCalendarPanel()
        self.calendar_panel.selected_date_changed.connect(
            self.refresh_selected_date_summary
        )
        self.summary_panel = self._build_selected_date_summary_panel()
        middle.addWidget(self.calendar_panel, 3)
        middle.addWidget(self.summary_panel, 2)
        self.main_layout.addLayout(middle, 1)

    def _build_selected_date_summary_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Selected Date Quantity Plan")
        title.setObjectName("CardTitle")
        hint = QLabel(
            "Excel-derived production requirement, mould/category capacity, "
            "and active historical oven compatibility."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        self.summary_date_label = QLabel("-")
        self.summary_date_label.setObjectName("InfoPill")
        self.summary_status_label = QLabel("-")
        self.summary_status_label.setObjectName("SuccessPill")

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.summary_date_label)
        layout.addWidget(self.summary_status_label)

        self.planned_qty_row = SummaryRow("Selected Date Planned Qty", "0")
        self.quantity_capacity_row = SummaryRow("Quantity Capacity", "0")
        self.capacity_usage_row = SummaryRow("Capacity Usage", "0%")
        self.active_ovens_row = SummaryRow("Active Ovens", "0")
        self.plan_status_row = SummaryRow("Quantity-Based Plan Status", "-")
        for row in (
            self.planned_qty_row,
            self.quantity_capacity_row,
            self.capacity_usage_row,
            self.active_ovens_row,
            self.plan_status_row,
        ):
            layout.addWidget(row)

        self.summary_note = QLabel(
            "This dashboard uses quantity capacity. Verified cycle-time data is "
            "not available for minute-level utilization."
        )
        self.summary_note.setObjectName("SectionHint")
        self.summary_note.setWordWrap(True)
        layout.addWidget(self.summary_note)
        layout.addStretch()
        return frame

    def _build_capacity_panel(self) -> None:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("Selected Date Quantity Capacity Usage")
        title.setObjectName("CardTitle")
        hint = QLabel(
            "Planned quantity compared with relevant available mould/category "
            "capacity for materials requiring production."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        self.capacity_bar = QProgressBar()
        self.capacity_bar.setRange(0, 100)
        self.capacity_bar.setMinimumHeight(22)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.capacity_bar)
        self.main_layout.addWidget(panel)

    def refresh(self) -> None:
        self.refresh_selected_date_summary(self.calendar_panel.selected_date())

    def refresh_selected_date_summary(self, selected_date: date) -> None:
        try:
            data = self._load_dashboard_data(selected_date)
        except Exception as exc:
            QMessageBox.warning(self, "Dashboard Refresh", str(exc))
            return

        metrics = data["metrics"]
        for key, value in metrics.items():
            self.metric_cards[key].value_widget.setText(f"{value:,}")

        self.summary_date_label.setText(
            f"Date: {selected_date.strftime('%A, %Y-%m-%d')}"
        )
        status = data["status"]
        self.summary_status_label.setText(status)
        self._set_label_object_name(
            self.summary_status_label,
            "SuccessPill"
            if status in {"FULLY PLANNED", "NO PRODUCTION REQUIRED"}
            else "WarningPill",
        )
        self.planned_qty_row.update_value(f"{data['planned_qty']:,}")
        self.quantity_capacity_row.update_value(f"{data['quantity_capacity']:,}")
        self.capacity_usage_row.update_value(f"{data['capacity_usage']}%")
        self.active_ovens_row.update_value(f"{data['active_ovens']:,}")
        self.plan_status_row.update_value(status)
        self.capacity_bar.setValue(max(0, min(100, data["capacity_usage"])))
        self.capacity_bar.setFormat(
            f"{data['planned_qty']:,} planned / "
            f"{data['quantity_capacity']:,} quantity capacity"
        )

    def _load_dashboard_data(self, selected_date: date) -> dict:
        with get_session() as session:
            active_demands = int(
                session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM mpps_shipment_demand
                        WHERE UPPER(status) IN (
                            'PENDING', 'CONFIRMED', 'PLANNED', 'PARTIALLY_PLANNED'
                        )
                          AND demand_qty > 0;
                        """
                    )
                ).scalar_one()
            )
            production = load_production_requirements(
                session, planning_date=selected_date
            )
            production_summary = summarize_production_requirements(production)
            required = [
                row for row in production if row.production_required_qty > 0
            ]
            capacity = build_capacity_analysis(
                session,
                production_rows=required,
                planning_date=selected_date,
            )
            _, plan_summary = build_daily_oven_schedule(
                session,
                planning_date=selected_date,
                production_rows=required,
                capacity_rows=capacity,
            )

        capacity_by_key: dict[str, int] = {}
        for row in capacity:
            if row.capacity_key and row.available_capacity > 0:
                capacity_by_key[row.capacity_key] = max(
                    capacity_by_key.get(row.capacity_key, 0),
                    int(floor(row.available_capacity)),
                )
        quantity_capacity = sum(capacity_by_key.values())
        capacity_usage = (
            int(round(plan_summary.planned_qty / quantity_capacity * 100))
            if quantity_capacity > 0
            else 0
        )
        return {
            "metrics": {
                "active_demands": active_demands,
                "required_items": production_summary.production_required_items,
                "required_qty": production_summary.total_production_required_qty,
                "warnings": max(
                    production_summary.warning_count,
                    plan_summary.risk_warning_count,
                ),
            },
            "planned_qty": plan_summary.planned_qty,
            "quantity_capacity": quantity_capacity,
            "capacity_usage": capacity_usage,
            "active_ovens": plan_summary.active_ovens,
            "status": plan_summary.capacity_status,
        }

    def _set_label_object_name(self, label: QLabel, object_name: str) -> None:
        label.setObjectName(object_name)
        label.style().unpolish(label)
        label.style().polish(label)
