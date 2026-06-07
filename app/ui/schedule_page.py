from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import and_, select
from sqlalchemy.orm import joinedload

from app.database import get_session
from app.models import Order, Oven, OvenSchedule, ScheduleChangeLog, Shift
from app.services.schedule_priority_service import (
    load_delay_risks,
    load_priority_items,
    rebuild_schedule_by_manager_priority,
    set_order_item_priority,
)


@dataclass
class ScheduleRow:
    schedule_id: int
    schedule_date: date
    shift_name: str
    oven_code: str
    oven_name: str
    order_no: str
    customer_name: str
    slot_type: str
    tire_name: str
    start_datetime: datetime
    end_datetime: datetime
    duration_minutes: int
    status: str


class SchedulePage(QWidget):
    OVEN_PLAN_INDEX = 0
    PRIORITY_INDEX = 1
    WARNING_INDEX = 2
    MANUAL_INDEX = 3

    def __init__(self, current_user_id: int | None):
        super().__init__()

        self.current_user_id = current_user_id
        self.current_schedule_id: int | None = None
        self.current_order_item_id: int | None = None
        self.rows: list[ScheduleRow] = []
        self.nav_buttons: list[QPushButton] = []

        self._create_widgets()
        self._apply_styles()
        self._build_ui()
        self.load_master_filters()
        self._set_manual_enabled(False)
        self._set_priority_enabled(False)
        self.navigate_sub_page(self.OVEN_PLAN_INDEX)
        self.refresh()

    def _create_widgets(self) -> None:
        self.date_filter = QDateEdit()
        self.date_filter.setCalendarPopup(False)
        self.date_filter.setDisplayFormat("dd MMM yyyy")
        self.date_filter.setMinimumHeight(42)
        self.date_filter.setDate(QDate.currentDate())
        self.date_filter.dateChanged.connect(lambda _date: self.refresh())

        self.prev_day_btn = QPushButton("Previous Day")
        self.prev_day_btn.setObjectName("SecondaryButton")
        self.prev_day_btn.setMinimumHeight(42)
        self.prev_day_btn.clicked.connect(self.go_previous_day)

        self.today_btn = QPushButton("Today")
        self.today_btn.setObjectName("SecondaryButton")
        self.today_btn.setMinimumHeight(42)
        self.today_btn.clicked.connect(self.go_today)

        self.next_day_btn = QPushButton("Next Day")
        self.next_day_btn.setObjectName("SecondaryButton")
        self.next_day_btn.setMinimumHeight(42)
        self.next_day_btn.clicked.connect(self.go_next_day)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.rebuild_btn = QPushButton("Auto Rebuild by Priority")
        self.rebuild_btn.setObjectName("DangerButton")
        self.rebuild_btn.setMinimumHeight(42)
        self.rebuild_btn.clicked.connect(self.rebuild_schedule)

        self.schedule_search = QLineEdit()
        self.schedule_search.setPlaceholderText("Search order, customer, oven, tire or slot...")
        self.schedule_search.setMinimumHeight(42)
        self.schedule_search.textChanged.connect(lambda _text: self.apply_schedule_filters())

        self.oven_filter = QComboBox()
        self.oven_filter.setMinimumHeight(42)
        self.oven_filter.currentIndexChanged.connect(lambda _index: self.apply_schedule_filters())

        self.shift_filter = QComboBox()
        self.shift_filter.setMinimumHeight(42)
        self.shift_filter.currentIndexChanged.connect(lambda _index: self.apply_schedule_filters())

        self.schedule_table = QTableWidget(0, 12)
        self.schedule_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Date",
                "Shift",
                "Oven",
                "Order",
                "Customer",
                "Slot",
                "Tire",
                "Start",
                "End",
                "Duration",
                "Status",
            ]
        )
        self.schedule_table.setColumnHidden(0, True)
        self.schedule_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.schedule_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.schedule_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.verticalHeader().setDefaultSectionSize(48)
        self.schedule_table.horizontalHeader().setStretchLastSection(False)
        self.schedule_table.itemSelectionChanged.connect(self.load_selected_schedule_row)

        self.priority_search = QLineEdit()
        self.priority_search.setPlaceholderText("Search order, customer, tire or priority...")
        self.priority_search.setMinimumHeight(42)
        self.priority_search.textChanged.connect(lambda _text: self.apply_priority_filters())

        self.priority_filter = QComboBox()
        self.priority_filter.setMinimumHeight(42)
        self.priority_filter.addItems(["All Priority", "NORMAL", "HIGH", "URGENT"])
        self.priority_filter.currentIndexChanged.connect(lambda _index: self.apply_priority_filters())

        self.priority_table = QTableWidget(0, 11)
        self.priority_table.setHorizontalHeaderLabels(
            [
                "Item ID",
                "Order No",
                "Customer",
                "Tire Code",
                "Tire Type",
                "Qty",
                "Prod Time",
                "Priority",
                "Confirmed Date",
                "Estimated Finish",
                "Reason",
            ]
        )
        self.priority_table.setColumnHidden(0, True)
        self.priority_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.priority_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.priority_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.priority_table.verticalHeader().setVisible(False)
        self.priority_table.verticalHeader().setDefaultSectionSize(48)
        self.priority_table.itemSelectionChanged.connect(self.load_selected_priority_row)

        self.selected_priority_label = QLabel("Select an order tire item to assign manager priority.")
        self.selected_priority_label.setObjectName("SelectedInfo")
        self.selected_priority_label.setWordWrap(True)

        self.priority_combo = QComboBox()
        self.priority_combo.setMinimumHeight(42)
        self.priority_combo.addItems(["NORMAL", "HIGH", "URGENT"])

        self.priority_reason = QTextEdit()
        self.priority_reason.setPlaceholderText("Required: reason for manager priority decision")
        self.priority_reason.setFixedHeight(72)

        self.apply_priority_btn = QPushButton("Apply Priority & Rebuild Schedule")
        self.apply_priority_btn.setObjectName("DangerButton")
        self.apply_priority_btn.setMinimumHeight(42)
        self.apply_priority_btn.clicked.connect(self.apply_priority_and_rebuild)

        self.delay_table = QTableWidget(0, 7)
        self.delay_table.setHorizontalHeaderLabels(
            [
                "Order No",
                "Customer",
                "Confirmed Date",
                "New Estimated Finish",
                "Delay Days",
                "Risk Status",
                "ID",
            ]
        )
        self.delay_table.setColumnHidden(6, True)
        self.delay_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.delay_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.delay_table.verticalHeader().setVisible(False)
        self.delay_table.verticalHeader().setDefaultSectionSize(46)

        self.new_oven_combo = QComboBox()
        self.new_oven_combo.setMinimumHeight(42)

        self.start_dt = QDateTimeEdit()
        self.start_dt.setCalendarPopup(False)
        self.start_dt.setDisplayFormat("dd MMM yyyy hh:mm AP")
        self.start_dt.setMinimumHeight(42)

        self.end_dt = QDateTimeEdit()
        self.end_dt.setCalendarPopup(False)
        self.end_dt.setDisplayFormat("dd MMM yyyy hh:mm AP")
        self.end_dt.setMinimumHeight(42)

        self.manual_reason = QTextEdit()
        self.manual_reason.setPlaceholderText("Required: explain why this manual oven/time change is needed")
        self.manual_reason.setFixedHeight(72)

        self.selected_slot_label = QLabel("Select an oven slot from the Oven Plan table to enable manual time adjustment.")
        self.selected_slot_label.setObjectName("SelectedInfo")
        self.selected_slot_label.setWordWrap(True)

        self.save_manual_btn = QPushButton("Save Manual Time Change")
        self.save_manual_btn.setObjectName("PrimaryButton")
        self.save_manual_btn.setMinimumHeight(42)
        self.save_manual_btn.clicked.connect(self.save_manual_change)

        self.stack = QStackedWidget()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard,
            QFrame#SubNavCard,
            QFrame#ContentCard,
            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#SectionHint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#SmallLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#SelectedInfo {
                background: #f8fafc;
                color: #475569;
                border: 1px dashed #cbd5e1;
                border-radius: 12px;
                padding: 10px 12px;
                font-weight: 750;
            }

            QLineEdit,
            QDateEdit,
            QDateTimeEdit,
            QComboBox,
            QTextEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }

            QLineEdit:focus,
            QDateEdit:focus,
            QDateTimeEdit:focus,
            QComboBox:focus,
            QTextEdit:focus {
                border: 1px solid #2563eb;
            }

            QComboBox::drop-down,
            QDateEdit::drop-down,
            QDateTimeEdit::drop-down {
                border: none;
                width: 24px;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#PrimaryButton:disabled {
                background: #94a3b8;
                color: #e2e8f0;
            }

            QPushButton#DangerButton {
                background: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#DangerButton:hover {
                background: #6d28d9;
            }

            QPushButton#DangerButton:disabled {
                background: #94a3b8;
                color: #e2e8f0;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 900;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QPushButton#SubNavButton {
                background: #e2e8f0;
                color: #334155;
                border: none;
                border-radius: 10px;
                padding: 9px 16px;
                font-weight: 950;
            }

            QPushButton#SubNavButton:hover {
                background: #cbd5e1;
                color: #0f172a;
            }

            QPushButton#SubNavButton[active="true"] {
                background: #2563eb;
                color: #ffffff;
            }

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                selection-background-color: #eff6ff;
                selection-color: #0f172a;
                alternate-background-color: #f8fafc;
            }

            QTableWidget::item {
                padding: 8px 10px;
                border: none;
            }

            QTableWidget::item:selected {
                background: #eff6ff;
                color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #1e293b;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px;
                font-weight: 950;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_control_card())
        root.addWidget(self._build_sub_nav_card())

        self.stack.addWidget(self._build_oven_plan_page())
        self.stack.addWidget(self._build_priority_page())
        self.stack.addWidget(self._build_warning_page())
        self.stack.addWidget(self._build_manual_page())

        root.addWidget(self.stack, 1)

    def _build_control_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("ControlCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        title = QLabel("Schedule Control")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Manager can assign tire priority and rebuild the future schedule. Priority tires are planned first without locking any tire."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(10)

        row.addWidget(self._field_label("Schedule Date"))
        row.addWidget(self.prev_day_btn)
        row.addWidget(self.date_filter)
        row.addWidget(self.today_btn)
        row.addWidget(self.next_day_btn)
        row.addWidget(self.refresh_btn)
        row.addWidget(self.rebuild_btn)
        row.addStretch()

        layout.addLayout(row)

        return card

    def _build_sub_nav_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("SubNavCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        self._add_sub_nav_button(layout, "Oven Plan", self.OVEN_PLAN_INDEX)
        self._add_sub_nav_button(layout, "Manager Priority", self.PRIORITY_INDEX)
        self._add_sub_nav_button(layout, "Shipment Warnings", self.WARNING_INDEX)
        self._add_sub_nav_button(layout, "Manual Adjustment", self.MANUAL_INDEX)

        layout.addStretch()

        return card

    def _build_oven_plan_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = self._content_card(
            title_text="Daily Oven Plan",
            hint_text="This table shows the auto-created oven plan. Select a row only when manager needs a manual oven/time change.",
        )
        card_layout = card.layout()

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.schedule_search, 1)
        filter_row.addWidget(self.oven_filter)
        filter_row.addWidget(self.shift_filter)

        card_layout.addLayout(filter_row)
        card_layout.addWidget(self.schedule_table, 1)

        layout.addWidget(card, 1)

        return page

    def _build_priority_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = self._content_card(
            title_text="Manager Tire Priority Control",
            hint_text="Select an order tire item, choose NORMAL / HIGH / URGENT, enter reason, then rebuild the schedule.",
        )
        card_layout = card.layout()

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.priority_search, 1)
        filter_row.addWidget(self.priority_filter)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 3)

        form.addWidget(self._field_label("Selected Tire Item"), 0, 0)
        form.addWidget(self.selected_priority_label, 0, 1)

        form.addWidget(self._field_label("Manager Priority"), 1, 0)
        form.addWidget(self.priority_combo, 1, 1)

        card_layout.addLayout(filter_row)
        card_layout.addWidget(self.priority_table, 1)
        card_layout.addLayout(form)
        card_layout.addWidget(self.priority_reason)
        card_layout.addWidget(self.apply_priority_btn)

        layout.addWidget(card, 1)

        return page

    def _build_warning_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = self._content_card(
            title_text="Shipment Date Warning",
            hint_text="If manager priority changes push an order beyond the confirmed shipment date, the warning is shown here.",
        )
        card_layout = card.layout()
        card_layout.addWidget(self.delay_table, 1)

        layout.addWidget(card, 1)

        return page

    def _build_manual_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = self._content_card(
            title_text="Manual Oven / Time Adjustment",
            hint_text="Use this only for real production changes. Every manual change is saved to the schedule change log.",
        )
        card_layout = card.layout()

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 3)

        form.addWidget(self._field_label("Selected Slot"), 0, 0)
        form.addWidget(self.selected_slot_label, 0, 1)

        form.addWidget(self._field_label("New Oven"), 1, 0)
        form.addWidget(self.new_oven_combo, 1, 1)

        form.addWidget(self._field_label("New Start"), 2, 0)
        form.addWidget(self.start_dt, 2, 1)

        form.addWidget(self._field_label("New End"), 3, 0)
        form.addWidget(self.end_dt, 3, 1)

        card_layout.addLayout(form)
        card_layout.addWidget(self.manual_reason)
        card_layout.addWidget(self.save_manual_btn)
        card_layout.addStretch()

        layout.addWidget(card, 1)

        return page

    def _content_card(self, *, title_text: str, hint_text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("ContentCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")

        hint = QLabel(hint_text)
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        return card

    def _add_sub_nav_button(self, layout: QHBoxLayout, text: str, index: int) -> None:
        button = QPushButton(text)
        button.setObjectName("SubNavButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False, idx=index: self.navigate_sub_page(idx))

        self.nav_buttons.append(button)
        layout.addWidget(button)

    def navigate_sub_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        for button_index, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if button_index == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SmallLabel")
        return label

    def load_master_filters(self) -> None:
        self.oven_filter.blockSignals(True)
        self.shift_filter.blockSignals(True)

        self.oven_filter.clear()
        self.shift_filter.clear()
        self.new_oven_combo.clear()

        self.oven_filter.addItem("All Ovens", None)
        self.shift_filter.addItem("All Shifts", None)

        try:
            with get_session() as session:
                ovens = list(
                    session.scalars(
                        select(Oven)
                        .where(Oven.is_active.is_(True))
                        .order_by(Oven.oven_code)
                    )
                )
                shifts = list(
                    session.scalars(
                        select(Shift)
                        .where(Shift.is_active.is_(True))
                        .order_by(Shift.start_time)
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Master Data Error", str(exc))
            return

        for oven in ovens:
            label = f"{oven.oven_code} - {oven.oven_name}"
            self.oven_filter.addItem(label, oven.id)
            self.new_oven_combo.addItem(label, oven.id)

        for shift in shifts:
            self.shift_filter.addItem(shift.shift_name, shift.id)

        self.oven_filter.blockSignals(False)
        self.shift_filter.blockSignals(False)

    def refresh(self) -> None:
        self.refresh_schedule()
        self.refresh_priority_items()
        self.refresh_delay_risks()

    def refresh_schedule(self) -> None:
        selected_date = self.date_filter.date().toPython()

        try:
            with get_session() as session:
                schedules = list(
                    session.scalars(
                        select(OvenSchedule)
                        .options(
                            joinedload(OvenSchedule.shift),
                            joinedload(OvenSchedule.oven),
                            joinedload(OvenSchedule.tire_type),
                            joinedload(OvenSchedule.order).joinedload(Order.customer),
                        )
                        .where(OvenSchedule.schedule_date == selected_date)
                        .order_by(OvenSchedule.start_datetime, OvenSchedule.oven_id)
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Schedule Load Error", str(exc))
            return

        self.rows = [
            ScheduleRow(
                schedule_id=int(row.id),
                schedule_date=row.schedule_date,
                shift_name=str(row.shift.shift_name if row.shift else "-"),
                oven_code=str(row.oven.oven_code if row.oven else "-"),
                oven_name=str(row.oven.oven_name if row.oven else "-"),
                order_no=str(row.order.order_no if row.order else "-"),
                customer_name=str(row.order.customer.customer_name if row.order and row.order.customer else "-"),
                slot_type=str(row.slot_type or "-").upper(),
                tire_name=str(row.tire_type.tire_name if row.tire_type else "-"),
                start_datetime=row.start_datetime,
                end_datetime=row.end_datetime,
                duration_minutes=int(row.duration_minutes),
                status=str(row.status or "-").upper(),
            )
            for row in schedules
        ]

        self._refresh_schedule_table()
        self.clear_schedule_selection_state()

    def _refresh_schedule_table(self) -> None:
        self.schedule_table.setRowCount(0)
        self.schedule_table.setAlternatingRowColors(True)

        for row_index, row in enumerate(self.rows):
            self.schedule_table.insertRow(row_index)

            values = [
                str(row.schedule_id),
                self._format_date(row.schedule_date),
                row.shift_name,
                row.oven_code,
                row.order_no,
                row.customer_name,
                row.slot_type,
                row.tire_name,
                self._format_datetime(row.start_datetime),
                self._format_datetime(row.end_datetime),
                f"{row.duration_minutes} min",
                row.status,
            ]

            for col, value in enumerate(values):
                item = self._readonly_item(value)

                if col in (1, 2, 3, 4, 6, 8, 9, 10, 11):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 6:
                    self._apply_slot_style(item, row.slot_type)

                if col == 11:
                    self._apply_status_style(item, row.status)

                self.schedule_table.setItem(row_index, col, item)

        self.schedule_table.resizeColumnsToContents()
        self.schedule_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.schedule_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.apply_schedule_filters()

    def refresh_priority_items(self) -> None:
        try:
            with get_session() as session:
                rows = load_priority_items(session)
        except Exception as exc:
            QMessageBox.critical(self, "Priority Load Error", str(exc))
            return

        self.priority_table.setRowCount(0)
        self.priority_table.setAlternatingRowColors(True)

        for row_index, row in enumerate(rows):
            self.priority_table.insertRow(row_index)

            values = [
                str(row.order_item_id),
                row.order_no,
                row.customer_name,
                row.tire_code,
                row.tire_name,
                str(row.quantity),
                f"{row.curing_minutes} min",
                row.manager_priority_label,
                self._format_date(row.manager_confirmed_receive_date),
                self._format_datetime(row.current_estimated_completion),
                row.priority_reason,
            ]

            for col, value in enumerate(values):
                item = self._readonly_item(value)

                if col in (1, 3, 5, 6, 7, 8, 9):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 7:
                    self._apply_priority_cell_style(item, row.manager_priority_label)

                self.priority_table.setItem(row_index, col, item)

        self.priority_table.resizeColumnsToContents()
        self.priority_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.priority_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.priority_table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        self.apply_priority_filters()
        self.clear_priority_selection_state()

    def refresh_delay_risks(self) -> None:
        try:
            with get_session() as session:
                risks = load_delay_risks(session)
        except Exception as exc:
            QMessageBox.warning(self, "Delay Risk Load Error", str(exc))
            return

        self.delay_table.setRowCount(0)
        self.delay_table.setAlternatingRowColors(True)

        for row_index, row in enumerate(risks):
            self.delay_table.insertRow(row_index)

            values = [
                row.order_no,
                row.customer_name,
                self._format_date(row.manager_confirmed_receive_date),
                self._format_datetime(row.new_estimated_completion),
                str(row.delay_days),
                row.risk_status,
                str(row.order_id),
            ]

            for col, value in enumerate(values):
                item = self._readonly_item(value)

                if col in (0, 2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col in (4, 5):
                    self._apply_delay_style(item, row.delay_days)

                self.delay_table.setItem(row_index, col, item)

        self.delay_table.resizeColumnsToContents()
        self.delay_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def apply_schedule_filters(self) -> None:
        search_value = self.schedule_search.text().strip().lower()
        oven_id = self.oven_filter.currentData()
        shift_id = self.shift_filter.currentData()

        for row_index in range(self.schedule_table.rowCount()):
            row_id_item = self.schedule_table.item(row_index, 0)

            if row_id_item is None:
                continue

            schedule_id = int(row_id_item.text())
            row_data = next((item for item in self.rows if item.schedule_id == schedule_id), None)

            if row_data is None:
                self.schedule_table.setRowHidden(row_index, True)
                continue

            row_text = " ".join(
                self.schedule_table.item(row_index, col).text().lower()
                for col in range(1, 12)
                if self.schedule_table.item(row_index, col) is not None
            )

            selected_oven_code = ""
            selected_shift_name = ""

            if oven_id is not None:
                selected_oven_code = self.oven_filter.currentText().split(" - ")[0].strip()

            if shift_id is not None:
                selected_shift_name = self.shift_filter.currentText().strip()

            search_ok = not search_value or search_value in row_text
            oven_ok = oven_id is None or row_data.oven_code == selected_oven_code
            shift_ok = shift_id is None or row_data.shift_name == selected_shift_name

            self.schedule_table.setRowHidden(row_index, not (search_ok and oven_ok and shift_ok))

    def apply_priority_filters(self) -> None:
        search_value = self.priority_search.text().strip().lower()
        priority_value = self.priority_filter.currentText().strip().upper()

        for row in range(self.priority_table.rowCount()):
            row_text = " ".join(
                self.priority_table.item(row, col).text().lower()
                for col in range(1, 11)
                if self.priority_table.item(row, col) is not None
            )

            priority_text = (
                self.priority_table.item(row, 7).text().upper()
                if self.priority_table.item(row, 7)
                else ""
            )

            search_ok = not search_value or search_value in row_text
            priority_ok = priority_value == "ALL PRIORITY" or priority_text == priority_value

            self.priority_table.setRowHidden(row, not (search_ok and priority_ok))

    def load_selected_schedule_row(self) -> None:
        row_index = self.schedule_table.currentRow()

        if row_index < 0:
            return

        id_item = self.schedule_table.item(row_index, 0)

        if id_item is None:
            return

        schedule_id = int(id_item.text())

        try:
            with get_session() as session:
                schedule = session.get(OvenSchedule, schedule_id)

                if schedule is None:
                    QMessageBox.warning(self, "Not Found", "Selected schedule slot was not found. Please refresh and try again.")
                    return

                self.current_schedule_id = int(schedule.id)

                oven_index = self.new_oven_combo.findData(schedule.oven_id)

                if oven_index >= 0:
                    self.new_oven_combo.setCurrentIndex(oven_index)

                self.start_dt.setDateTime(self._to_qdatetime(schedule.start_datetime))
                self.end_dt.setDateTime(self._to_qdatetime(schedule.end_datetime))

                selected_text = (
                    f"Selected Slot: {self.schedule_table.item(row_index, 4).text()} | "
                    f"{self.schedule_table.item(row_index, 3).text()} | "
                    f"{self.schedule_table.item(row_index, 8).text()} → {self.schedule_table.item(row_index, 9).text()}"
                )
                self.selected_slot_label.setText(selected_text)

        except Exception as exc:
            QMessageBox.critical(self, "Selection Error", str(exc))
            return

        self._set_manual_enabled(True)

    def load_selected_priority_row(self) -> None:
        row_index = self.priority_table.currentRow()

        if row_index < 0:
            return

        id_item = self.priority_table.item(row_index, 0)

        if id_item is None:
            return

        self.current_order_item_id = int(id_item.text())

        order_no = self.priority_table.item(row_index, 1).text()
        tire_code = self.priority_table.item(row_index, 3).text()
        tire_name = self.priority_table.item(row_index, 4).text()
        priority_label = self.priority_table.item(row_index, 7).text()

        combo_index = self.priority_combo.findText(priority_label)

        if combo_index >= 0:
            self.priority_combo.setCurrentIndex(combo_index)

        self.selected_priority_label.setText(
            f"Selected Tire: {order_no} | {tire_code} - {tire_name}"
        )
        self.priority_reason.clear()
        self._set_priority_enabled(True)

    def clear_schedule_selection_state(self) -> None:
        self.current_schedule_id = None
        self.schedule_table.clearSelection()
        self.selected_slot_label.setText("Select an oven slot from the Oven Plan table to enable manual time adjustment.")
        self.manual_reason.clear()

        selected_date = self.date_filter.date().toPython()
        default_start = datetime.combine(selected_date, time(hour=8, minute=0))
        default_end = datetime.combine(selected_date, time(hour=9, minute=0))

        self.start_dt.setDateTime(self._to_qdatetime(default_start))
        self.end_dt.setDateTime(self._to_qdatetime(default_end))
        self._set_manual_enabled(False)

    def clear_priority_selection_state(self) -> None:
        self.current_order_item_id = None
        self.priority_table.clearSelection()
        self.selected_priority_label.setText("Select an order tire item to assign manager priority.")
        self.priority_reason.clear()
        self._set_priority_enabled(False)

    def _set_manual_enabled(self, enabled: bool) -> None:
        self.new_oven_combo.setEnabled(enabled)
        self.start_dt.setEnabled(enabled)
        self.end_dt.setEnabled(enabled)
        self.manual_reason.setEnabled(enabled)
        self.save_manual_btn.setEnabled(enabled)

    def _set_priority_enabled(self, enabled: bool) -> None:
        self.priority_combo.setEnabled(enabled)
        self.priority_reason.setEnabled(enabled)
        self.apply_priority_btn.setEnabled(enabled)

    def apply_priority_and_rebuild(self) -> None:
        if self.current_order_item_id is None:
            QMessageBox.warning(self, "No Tire Selected", "Please select an order tire item first.")
            return

        priority_label = self.priority_combo.currentText().strip().upper()
        reason = self.priority_reason.toPlainText().strip()

        if not reason:
            QMessageBox.warning(self, "Reason Required", "Please enter a reason for the manager priority decision.")
            return

        selected_date = self.date_filter.date().toPython()
        rebuild_start = datetime.combine(selected_date, time(hour=0, minute=0))

        answer = QMessageBox.question(
            self,
            "Confirm Priority Rebuild",
            "Do you want to apply this manager priority and rebuild the future schedule?\n\n"
            f"Priority: {priority_label}\n"
            f"Rebuild From: {self._format_datetime(rebuild_start)}\n\n"
            "Priority tires will be planned first. If shipment dates become late, warnings will appear in the warning page.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                set_order_item_priority(
                    session,
                    order_item_id=self.current_order_item_id,
                    priority_label=priority_label,
                    reason=reason,
                    user_id=self.current_user_id,
                )
                result = rebuild_schedule_by_manager_priority(
                    session,
                    start_from=rebuild_start,
                    user_id=self.current_user_id,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Priority Rebuild Error", str(exc))
            return

        QMessageBox.information(
            self,
            "Priority Schedule Rebuilt",
            "Manager priority saved and schedule rebuilt successfully.\n\n"
            f"Created Slots: {result.created_slots_count}\n"
            f"Production Slots: {result.production_slots_count}\n"
            f"Break Slots: {result.break_slots_count}\n"
            f"Delay Warnings: {len(result.delay_risks)}",
        )

        self.refresh()
        self.navigate_sub_page(self.WARNING_INDEX if result.delay_risks else self.OVEN_PLAN_INDEX)

    def rebuild_schedule(self) -> None:
        selected_date = self.date_filter.date().toPython()
        rebuild_start = datetime.combine(selected_date, time(hour=0, minute=0))

        answer = QMessageBox.question(
            self,
            "Confirm Auto Rebuild",
            "Do you want to rebuild the future schedule using current manager tire priorities?\n\n"
            f"Rebuild From: {self._format_datetime(rebuild_start)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                result = rebuild_schedule_by_manager_priority(
                    session,
                    start_from=rebuild_start,
                    user_id=self.current_user_id,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Auto Rebuild Error", str(exc))
            return

        QMessageBox.information(
            self,
            "Schedule Rebuilt",
            "Schedule rebuilt successfully using manager priority order.\n\n"
            f"Created Slots: {result.created_slots_count}\n"
            f"Production Slots: {result.production_slots_count}\n"
            f"Break Slots: {result.break_slots_count}\n"
            f"Delay Warnings: {len(result.delay_risks)}",
        )

        self.refresh()
        self.navigate_sub_page(self.WARNING_INDEX if result.delay_risks else self.OVEN_PLAN_INDEX)

    def save_manual_change(self) -> None:
        if self.current_schedule_id is None:
            QMessageBox.warning(self, "No Schedule Selected", "Please select a schedule slot first.")
            return

        new_oven_id = self.new_oven_combo.currentData()
        new_start = self.start_dt.dateTime().toPython()
        new_end = self.end_dt.dateTime().toPython()
        change_reason = self.manual_reason.toPlainText().strip()

        if new_oven_id is None:
            QMessageBox.warning(self, "Oven Required", "Please select an oven.")
            return

        if new_end <= new_start:
            QMessageBox.warning(self, "Invalid Time", "End time must be after start time.")
            return

        if not change_reason:
            QMessageBox.warning(self, "Reason Required", "Please enter a reason for this manual change.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Manual Time Change",
            "Do you want to save this manual schedule change?\n\n"
            f"New Oven: {self.new_oven_combo.currentText()}\n"
            f"New Start: {self._format_datetime(new_start)}\n"
            f"New End: {self._format_datetime(new_end)}\n\n"
            "System will block overlapping oven times and save this action to the change log.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                schedule = session.get(OvenSchedule, self.current_schedule_id)

                if schedule is None:
                    raise ValueError("Selected schedule slot was not found.")

                overlap = session.scalar(
                    select(OvenSchedule)
                    .where(
                        and_(
                            OvenSchedule.id != schedule.id,
                            OvenSchedule.oven_id == new_oven_id,
                            OvenSchedule.status != "CANCELLED",
                            OvenSchedule.start_datetime < new_end,
                            OvenSchedule.end_datetime > new_start,
                        )
                    )
                    .limit(1)
                )

                if overlap is not None:
                    raise ValueError(
                        "This change creates an oven time overlap. Please select another oven or time slot."
                    )

                log = ScheduleChangeLog(
                    schedule_id=schedule.id,
                    old_oven_id=schedule.oven_id,
                    new_oven_id=new_oven_id,
                    old_start_datetime=schedule.start_datetime,
                    new_start_datetime=new_start,
                    old_end_datetime=schedule.end_datetime,
                    new_end_datetime=new_end,
                    change_reason=change_reason,
                    changed_by=self.current_user_id,
                )
                session.add(log)

                schedule.oven_id = new_oven_id
                schedule.start_datetime = new_start
                schedule.end_datetime = new_end
                schedule.schedule_date = new_start.date()
                schedule.duration_minutes = int((new_end - new_start).total_seconds() // 60)

        except Exception as exc:
            QMessageBox.critical(self, "Manual Change Error", str(exc))
            return

        QMessageBox.information(self, "Schedule Updated", "Manual schedule change saved successfully.")
        self.manual_reason.clear()
        self.refresh()

    def go_previous_day(self) -> None:
        self.date_filter.setDate(self.date_filter.date().addDays(-1))

    def go_today(self) -> None:
        self.date_filter.setDate(QDate.currentDate())

    def go_next_day(self) -> None:
        self.date_filter.setDate(self.date_filter.date().addDays(1))

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _apply_slot_style(self, item: QTableWidgetItem, slot_type: str) -> None:
        slot_value = (slot_type or "").upper()

        if slot_value == "PRODUCTION":
            item.setForeground(QColor("#1e40af"))
            item.setBackground(QColor("#dbeafe"))
        elif slot_value == "BREAK":
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))
        elif slot_value == "MAINTENANCE":
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        else:
            item.setForeground(QColor("#334155"))

    def _apply_status_style(self, item: QTableWidgetItem, status: str) -> None:
        status_value = (status or "").upper()

        if status_value in ("PLANNED", "CONFIRMED"):
            item.setForeground(QColor("#1e40af"))
            item.setBackground(QColor("#dbeafe"))
        elif status_value in ("COMPLETED", "DONE", "FINISHED"):
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        elif status_value == "CANCELLED":
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        else:
            item.setForeground(QColor("#475569"))

    def _apply_priority_cell_style(self, item: QTableWidgetItem, priority: str) -> None:
        priority_value = (priority or "").upper()

        if priority_value == "URGENT":
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        elif priority_value == "HIGH":
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))
        else:
            item.setForeground(QColor("#334155"))
            item.setBackground(QColor("#f8fafc"))

    def _apply_delay_style(self, item: QTableWidgetItem, delay_days: int) -> None:
        if delay_days >= 3:
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        else:
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))

    def _format_date(self, value) -> str:
        if value is None:
            return "-"

        try:
            return value.strftime("%d %b %Y")
        except AttributeError:
            return str(value)

    def _format_datetime(self, value) -> str:
        if value is None:
            return "-"

        try:
            return value.strftime("%d %b %Y %I:%M %p")
        except AttributeError:
            return str(value)

    def _to_qdatetime(self, value: datetime) -> QDateTime:
        return QDateTime(
            QDate(value.year, value.month, value.day),
            QTime(value.hour, value.minute, value.second),
        )
