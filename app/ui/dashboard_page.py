from __future__ import annotations

from datetime import date
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, not_, select

from app.database import get_session
from app.models import Order, Oven, OvenSchedule, Shift
from app.services.holiday_service import get_holiday_info_for_date
from app.ui.production_calendar_panel import ProductionCalendarPanel

COMPLETED_STATUSES = ["COMPLETED", "DELIVERED", "RECEIVED"]


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

        if self.on_click is not None:
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

        self.open_button = QPushButton("Open details →")
        self.open_button.setObjectName("SoftButton")
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)

        if self.on_click is not None:
            self.open_button.clicked.connect(self.on_click)

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
        layout.setSpacing(10)

        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("SummaryLabel")

        self.value_widget = QLabel(value)
        self.value_widget.setObjectName("SummaryValue")
        self.value_widget.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.value_widget.setWordWrap(True)

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

        self.open_total_shipments_page = open_total_shipments_page or (lambda: None)
        self.open_completed_orders_page = open_completed_orders_page or (lambda: None)
        self.open_pending_orders_page = open_pending_orders_page or (lambda: None)
        self.open_overdue_orders_page = open_overdue_orders_page or (lambda: None)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)

        self.metric_cards: dict[str, MetricCard] = {}

        self._build_metric_cards()
        self._build_middle_section()
        self._build_capacity_panel()

        self.refresh()

    def _build_metric_cards(self) -> None:
        grid = QGridLayout()
        grid.setSpacing(12)

        self.metric_cards["total_shipments"] = MetricCard(
            "Total Shipments",
            "0",
            "All manager-confirmed shipment / order records",
            self.open_total_shipments_page,
        )

        self.metric_cards["production_completed"] = MetricCard(
            "Production Completed",
            "0",
            "Orders marked as completed, delivered or received",
            self.open_completed_orders_page,
        )

        self.metric_cards["to_be_completed"] = MetricCard(
            "To Be Completed",
            "0",
            "Orders still pending production completion",
            self.open_pending_orders_page,
        )

        self.metric_cards["overdue_orders"] = MetricCard(
            "Overdue Orders",
            "0",
            "Confirmed receive date passed but production not completed",
            self.open_overdue_orders_page,
        )

        grid.addWidget(self.metric_cards["total_shipments"], 0, 0)
        grid.addWidget(self.metric_cards["production_completed"], 0, 1)
        grid.addWidget(self.metric_cards["to_be_completed"], 0, 2)
        grid.addWidget(self.metric_cards["overdue_orders"], 0, 3)

        self.main_layout.addLayout(grid)

    def _build_middle_section(self) -> None:
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(14)

        self.calendar_panel = ProductionCalendarPanel()
        self.calendar_panel.selected_date_changed.connect(
            self.refresh_selected_date_summary
        )
        self.calendar_panel.calendar_marks_changed.connect(self.refresh)

        self.summary_panel = self._build_selected_date_summary_panel()

        middle_layout.addWidget(self.calendar_panel, 3)
        middle_layout.addWidget(self.summary_panel, 2)

        self.main_layout.addLayout(middle_layout, 1)

    def _build_selected_date_summary_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelCard")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Selected Date Summary")
        title.setObjectName("CardTitle")

        hint = QLabel(
            "Selected date production capacity, planned load and calendar status."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        self.summary_date_label = QLabel("-")
        self.summary_date_label.setObjectName("InfoPill")

        self.summary_status_label = QLabel("-")
        self.summary_status_label.setObjectName("SuccessPill")
        self.summary_status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.summary_date_label)
        layout.addWidget(self.summary_status_label)

        self.utilisation_row = SummaryRow("Utilisation", "0%")
        self.planned_slots_row = SummaryRow("Planned Slots", "0")
        self.planned_minutes_row = SummaryRow("Planned Minutes", "0")
        self.available_minutes_row = SummaryRow("Available Capacity", "0")
        self.active_ovens_row = SummaryRow("Active Ovens", "0")
        self.day_type_row = SummaryRow("Day Type", "-")

        layout.addWidget(self.utilisation_row)
        layout.addWidget(self.planned_slots_row)
        layout.addWidget(self.planned_minutes_row)
        layout.addWidget(self.available_minutes_row)
        layout.addWidget(self.active_ovens_row)
        layout.addWidget(self.day_type_row)

        self.summary_note = QLabel("-")
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

        title = QLabel("Factory Capacity Health")
        title.setObjectName("CardTitle")

        hint = QLabel(
            "Selected date planned production load compared with available 24/7 working capacity."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        self.capacity_bar = QProgressBar()
        self.capacity_bar.setRange(0, 100)
        self.capacity_bar.setValue(0)
        self.capacity_bar.setMinimumHeight(22)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.capacity_bar)

        self.main_layout.addWidget(panel)

    def refresh(self) -> None:
        metrics = self._load_dashboard_metrics()

        self.metric_cards["total_shipments"].value_widget.setText(
            str(metrics["total_shipments"])
        )
        self.metric_cards["production_completed"].value_widget.setText(
            str(metrics["production_completed"])
        )
        self.metric_cards["to_be_completed"].value_widget.setText(
            str(metrics["to_be_completed"])
        )
        self.metric_cards["overdue_orders"].value_widget.setText(
            str(metrics["overdue_orders"])
        )

        selected_date = self.calendar_panel.selected_date()
        self.refresh_selected_date_summary(selected_date)

    def refresh_selected_date_summary(self, selected_date: date) -> None:
        summary = self._load_selected_date_summary(selected_date)

        self.summary_date_label.setText(
            f"Date: {selected_date.strftime('%A, %Y-%m-%d')}"
        )

        self.summary_status_label.setText(summary["status_text"])

        self._set_label_object_name(
            self.summary_status_label,
            "WarningPill" if summary["is_blocked"] else "SuccessPill",
        )

        self.utilisation_row.update_value(f"{summary['utilisation']}%")
        self.planned_slots_row.update_value(str(summary["planned_slots"]))
        self.planned_minutes_row.update_value(f"{summary['planned_minutes']:,}")
        self.available_minutes_row.update_value(f"{summary['available_minutes']:,}")
        self.active_ovens_row.update_value(str(summary["active_ovens"]))
        self.day_type_row.update_value(summary["day_type"])

        self.summary_note.setText(summary["note"])

        self.capacity_bar.setValue(max(0, min(100, summary["utilisation"])))
        self.capacity_bar.setFormat(
            f"{summary['planned_minutes']:,} planned minutes / "
            f"{summary['available_minutes']:,} available minutes"
        )

    def _load_dashboard_metrics(self) -> dict[str, int]:
        with get_session() as session:
            total_shipments = session.scalar(select(func.count(Order.id))) or 0

            production_completed = (
                session.scalar(
                    select(func.count(Order.id)).where(
                        Order.status.in_(COMPLETED_STATUSES)
                    )
                )
                or 0
            )

            to_be_completed = (
                session.scalar(
                    select(func.count(Order.id)).where(
                        not_(Order.status.in_(COMPLETED_STATUSES))
                    )
                )
                or 0
            )

            overdue_orders = (
                session.scalar(
                    select(func.count(Order.id)).where(
                        not_(Order.status.in_(COMPLETED_STATUSES)),
                        Order.manager_confirmed_receive_date.is_not(None),
                        Order.manager_confirmed_receive_date < date.today(),
                    )
                )
                or 0
            )

        return {
            "total_shipments": total_shipments,
            "production_completed": production_completed,
            "to_be_completed": to_be_completed,
            "overdue_orders": overdue_orders,
        }

    def _load_selected_date_summary(self, selected_date: date) -> dict:
        with get_session() as session:
            holiday_info = get_holiday_info_for_date(session, selected_date)

            is_special_working_day = (
                holiday_info is not None and holiday_info.is_working_day_override
            )

            is_factory_holiday = (
                holiday_info is not None
                and not holiday_info.is_working_day_override
                and holiday_info.holiday_type == "FACTORY_HOLIDAY"
            )

            planned_slots = (
                session.scalar(
                    select(func.count(OvenSchedule.id)).where(
                        OvenSchedule.schedule_date == selected_date,
                        OvenSchedule.slot_type == "PRODUCTION",
                    )
                )
                or 0
            )

            planned_minutes = (
                session.scalar(
                    select(
                        func.coalesce(func.sum(OvenSchedule.duration_minutes), 0)
                    ).where(
                        OvenSchedule.schedule_date == selected_date,
                        OvenSchedule.slot_type == "PRODUCTION",
                    )
                )
                or 0
            )

            active_ovens = (
                session.scalar(
                    select(func.count(Oven.id)).where(Oven.is_active.is_(True))
                )
                or 0
            )

            shift_minutes = (
                session.scalar(
                    select(
                        func.coalesce(func.sum(Shift.max_working_minutes), 0)
                    ).where(
                        Shift.is_active.is_(True)
                    )
                )
                or 0
            )

            normal_available_minutes = active_ovens * shift_minutes

            available_minutes = (
                0 if is_factory_holiday else normal_available_minutes
            )

        utilisation = 0
        if available_minutes > 0:
            utilisation = int(round((planned_minutes / available_minutes) * 100))

        status_text = "Working Day"
        day_type = "WORKING DAY"
        note = "Factory operates 24/7. Production planning is allowed for this date."

        if is_special_working_day:
            status_text = "Special Working Day"
            day_type = "SPECIAL WORKING DAY"
            note = (
                "Manager override is active. Production can be planned for this date."
            )

        if is_factory_holiday:
            status_text = "Factory Holiday"
            day_type = "FACTORY HOLIDAY"
            note = (
                "This date is marked as a factory holiday. Normal production capacity is blocked."
            )

        return {
            "planned_slots": planned_slots,
            "planned_minutes": planned_minutes,
            "active_ovens": active_ovens,
            "available_minutes": available_minutes,
            "utilisation": utilisation,
            "is_blocked": is_factory_holiday,
            "status_text": status_text,
            "day_type": day_type,
            "note": note,
        }

    def _set_label_object_name(self, label: QLabel, object_name: str) -> None:
        label.setObjectName(object_name)
        label.style().unpolish(label)
        label.style().polish(label)