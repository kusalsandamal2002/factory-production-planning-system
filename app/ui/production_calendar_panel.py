from __future__ import annotations

import calendar
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.database import get_session
from app.services.holiday_service import (
    ensure_holiday_table,
    get_all_holidays,
    get_holiday_info_for_date,
    mark_factory_holiday,
    mark_working_day_override,
    remove_holiday_mark,
)


class CalendarDayCell(QLabel):
    clicked = Signal(object)

    def __init__(self, cell_date: date | None):
        super().__init__()
        self.cell_date = cell_date
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(44, 38)

        if self.cell_date is None:
            self.setText("")
            self.setObjectName("CalendarEmptyCell")
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setText(str(self.cell_date.day))
            self.setObjectName("CalendarDayCell")
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if (
            self.cell_date is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.clicked.emit(self.cell_date)

        super().mousePressEvent(event)


class ProductionCalendarPanel(QFrame):
    selected_date_changed = Signal(object)
    calendar_marks_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("ModernCalendarPanel")

        self.today = date.today()
        self.selected = self.today
        self.display_year = self.today.year
        self.display_month = self.today.month

        self.holiday_map = {}
        self.day_cells: list[CalendarDayCell] = []

        with get_session() as session:
            ensure_holiday_table(session)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        main_row = QHBoxLayout()
        main_row.setSpacing(24)

        self.left_panel = QFrame()
        self.left_panel.setObjectName("CalendarLeftPanel")

        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(10, 4, 10, 4)
        left_layout.setSpacing(8)

        self.selected_day_name_label = QLabel("MONDAY")
        self.selected_day_name_label.setObjectName("CalendarSelectedDayName")

        self.selected_day_number_label = QLabel("1")
        self.selected_day_number_label.setObjectName("CalendarSelectedDayNumber")

        self.today_label = QLabel("TODAY")
        self.today_label.setObjectName("CalendarTodayBadge")
        self.today_label.setVisible(False)

        self.selected_status_label = QLabel("Working Day")
        self.selected_status_label.setObjectName("CalendarStatusWorking")
        self.selected_status_label.setWordWrap(True)

        self.selected_hint_label = QLabel(
            "Factory works 24/7. Production can run unless this date is manually marked as a factory holiday."
        )
        self.selected_hint_label.setObjectName("CalendarSelectedHint")
        self.selected_hint_label.setWordWrap(True)

        left_layout.addWidget(self.selected_day_name_label)
        left_layout.addWidget(self.selected_day_number_label)
        left_layout.addWidget(self.today_label, 0, Qt.AlignmentFlag.AlignLeft)
        left_layout.addSpacing(8)
        left_layout.addWidget(self.selected_status_label)
        left_layout.addStretch()
        left_layout.addWidget(self.selected_hint_label)

        self.right_panel = QFrame()
        self.right_panel.setObjectName("CalendarRightPanel")

        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(4, 0, 4, 0)
        right_layout.setSpacing(12)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(10)

        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("CalendarNavButton")
        self.prev_btn.clicked.connect(self.show_previous_month)

        self.next_btn = QPushButton("›")
        self.next_btn.setObjectName("CalendarNavButton")
        self.next_btn.clicked.connect(self.show_next_month)

        self.month_label = QLabel("")
        self.month_label.setObjectName("CalendarMonthTitle")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nav_row.addWidget(self.prev_btn)
        nav_row.addStretch()
        nav_row.addWidget(self.month_label)
        nav_row.addStretch()
        nav_row.addWidget(self.next_btn)

        self.week_header = QGridLayout()
        self.week_header.setHorizontalSpacing(6)
        self.week_header.setVerticalSpacing(4)

        week_names = ["S", "M", "T", "W", "T", "F", "S"]

        for column, name in enumerate(week_names):
            label = QLabel(name)
            label.setObjectName("CalendarWeekDay")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.week_header.addWidget(label, 0, column)

        self.calendar_grid = QGridLayout()
        self.calendar_grid.setHorizontalSpacing(6)
        self.calendar_grid.setVerticalSpacing(6)

        right_layout.addLayout(nav_row)
        right_layout.addLayout(self.week_header)
        right_layout.addLayout(self.calendar_grid)

        main_row.addWidget(self.left_panel, 2)
        main_row.addWidget(self.right_panel, 3)

        root.addLayout(main_row)

        footer_hint = QLabel(
            "Click a date to mark Factory Holiday, Special Working Day, or remove a manual mark."
        )
        footer_hint.setObjectName("CalendarFooterHint")
        footer_hint.setWordWrap(True)

        root.addWidget(footer_hint)

    def selected_date(self) -> date:
        return self.selected

    def show_previous_month(self) -> None:
        if self.display_month == 1:
            self.display_month = 12
            self.display_year -= 1
        else:
            self.display_month -= 1

        self.refresh()

    def show_next_month(self) -> None:
        if self.display_month == 12:
            self.display_month = 1
            self.display_year += 1
        else:
            self.display_month += 1

        self.refresh()

    def refresh(self) -> None:
        with get_session() as session:
            self.holiday_map = get_all_holidays(session)

        self._render_month()
        self._refresh_selected_panel()

    def _render_month(self) -> None:
        while self.calendar_grid.count():
            item = self.calendar_grid.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        self.day_cells.clear()

        month_name = calendar.month_name[self.display_month].upper()
        self.month_label.setText(f"{month_name}  {self.display_year}")

        month_matrix = calendar.monthcalendar(self.display_year, self.display_month)

        for row_index, week in enumerate(month_matrix):
            for column_index, day_number in enumerate(week):
                if day_number == 0:
                    cell = CalendarDayCell(None)
                else:
                    cell_date = date(
                        self.display_year,
                        self.display_month,
                        day_number,
                    )
                    cell = CalendarDayCell(cell_date)
                    cell.clicked.connect(self._on_day_clicked)
                    self._style_day_cell(cell)

                self.calendar_grid.addWidget(cell, row_index, column_index)
                self.day_cells.append(cell)

    def _style_day_cell(self, cell: CalendarDayCell) -> None:
        if cell.cell_date is None:
            cell.setObjectName("CalendarEmptyCell")
            return

        current = cell.cell_date
        holiday_info = self._get_holiday_info(current)

        if current == self.selected:
            cell.setObjectName("CalendarSelectedCell")
        elif holiday_info is not None and holiday_info.is_working_day_override:
            cell.setObjectName("CalendarSpecialDayCell")
        elif holiday_info is not None and holiday_info.holiday_type == "FACTORY_HOLIDAY":
            cell.setObjectName("CalendarHolidayCell")
        elif current == self.today:
            cell.setObjectName("CalendarTodayCell")
        else:
            cell.setObjectName("CalendarDayCell")

        cell.style().unpolish(cell)
        cell.style().polish(cell)

    def _on_day_clicked(self, selected_date: date) -> None:
        self.selected = selected_date

        self._render_month()
        self._refresh_selected_panel()
        self.selected_date_changed.emit(self.selected)

        self._open_date_action_menu()

    def _open_date_action_menu(self) -> None:
        selected = self.selected

        menu = QMenu(self)
        menu.setObjectName("DateActionMenu")

        title_action = menu.addAction(selected.strftime("%A, %Y-%m-%d"))
        title_action.setEnabled(False)

        menu.addSeparator()

        mark_holiday_action = menu.addAction("Mark as Factory Holiday")
        special_working_action = menu.addAction("Mark as Special Working Day")
        remove_mark_action = menu.addAction("Remove Manual Mark")

        menu.addSeparator()

        select_only_action = menu.addAction("Only Select Date")

        action = menu.exec(QCursor.pos())

        if action == mark_holiday_action:
            self.mark_selected_date_as_holiday()
        elif action == special_working_action:
            self.mark_selected_date_as_working_day()
        elif action == remove_mark_action:
            self.remove_selected_date_mark()
        elif action == select_only_action or action is None:
            self._render_month()
            self._refresh_selected_panel()
            self.selected_date_changed.emit(self.selected)

    def mark_selected_date_as_holiday(self) -> None:
        selected = self.selected

        holiday_name, ok = QInputDialog.getText(
            self,
            "Mark Factory Holiday",
            f"Enter holiday name for {selected.strftime('%Y-%m-%d')}:",
            text="Factory Holiday",
        )

        if not ok:
            return

        holiday_name = holiday_name.strip()

        if not holiday_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a holiday name.")
            return

        with get_session() as session:
            mark_factory_holiday(session, selected, holiday_name)

        QMessageBox.information(
            self,
            "Holiday Saved",
            f"{selected.strftime('%Y-%m-%d')} marked as factory holiday.",
        )

        self.refresh()
        self.calendar_marks_changed.emit()
        self.selected_date_changed.emit(selected)

    def remove_selected_date_mark(self) -> None:
        selected = self.selected

        confirm = QMessageBox.question(
            self,
            "Remove Calendar Mark",
            "Remove manual holiday / special working day mark for this date?",
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        with get_session() as session:
            remove_holiday_mark(session, selected)

        self.refresh()
        self.calendar_marks_changed.emit()
        self.selected_date_changed.emit(selected)

    def mark_selected_date_as_working_day(self) -> None:
        selected = self.selected

        confirm = QMessageBox.question(
            self,
            "Special Working Day",
            f"{selected.strftime('%Y-%m-%d')} will be allowed as a working day.\n\n"
            "Use this when a date was previously marked as a factory holiday but management approves production.\n\n"
            "Continue?",
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        with get_session() as session:
            mark_working_day_override(
                session,
                selected,
                holiday_name="Manager Approved Special Working Day",
            )

        QMessageBox.information(
            self,
            "Special Working Day Saved",
            f"{selected.strftime('%Y-%m-%d')} marked as special working day.",
        )

        self.refresh()
        self.calendar_marks_changed.emit()
        self.selected_date_changed.emit(selected)

    def _refresh_selected_panel(self) -> None:
        selected = self.selected

        self.selected_day_name_label.setText(selected.strftime("%A").upper())
        self.selected_day_number_label.setText(str(selected.day))
        self.today_label.setVisible(selected == self.today)

        holiday_info = self._get_holiday_info(selected)

        if holiday_info is None:
            status_text = "Working Day"
            hint_text = (
                "Factory is operating 24/7. Production planning is allowed for this date."
            )
            self.selected_status_label.setObjectName("CalendarStatusWorking")
        elif holiday_info.is_working_day_override:
            status_text = "Special Working Day"
            hint_text = (
                "Manager override is active. Production can be planned for this date."
            )
            self.selected_status_label.setObjectName("CalendarStatusSpecial")
        else:
            status_text = "Factory Holiday"
            hint_text = holiday_info.holiday_name or (
                "Production is blocked for this date."
            )
            self.selected_status_label.setObjectName("CalendarStatusHoliday")

        self.selected_status_label.setText(status_text)
        self.selected_hint_label.setText(hint_text)

        self.selected_status_label.style().unpolish(self.selected_status_label)
        self.selected_status_label.style().polish(self.selected_status_label)

    def _get_holiday_info(self, selected: date):
        with get_session() as session:
            return get_holiday_info_for_date(session, selected)