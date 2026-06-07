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
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import get_session
from app.services.tire_stock_service import (
    add_daily_tire_production,
    delete_daily_production_entry,
    load_current_tire_stock,
    load_daily_production_history,
)


class TireStockPage(QWidget):
    CURRENT_STOCK_INDEX = 0
    DAILY_PRODUCTION_INDEX = 1

    def __init__(self, current_user_id: int | None = None):
        super().__init__()

        self.current_user_id = current_user_id
        self.nav_buttons: list[QPushButton] = []

        self.current_stock_page = CurrentTireStockPage()
        self.daily_production_page = DailyTireProductionPage(
            current_user_id=current_user_id,
            after_save_callback=self.current_stock_page.refresh,
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.current_stock_page)
        self.stack.addWidget(self.daily_production_page)

        self._apply_styles()
        self._build_ui()
        self.navigate_sub_page(self.CURRENT_STOCK_INDEX)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#SubNavCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
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
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        nav_card = QFrame()
        nav_card.setObjectName("SubNavCard")

        nav_layout = QHBoxLayout(nav_card)
        nav_layout.setContentsMargins(18, 14, 18, 14)
        nav_layout.setSpacing(10)

        self._add_sub_nav_button(nav_layout, "Current Tire Stock", self.CURRENT_STOCK_INDEX)
        self._add_sub_nav_button(nav_layout, "Daily Tire Production", self.DAILY_PRODUCTION_INDEX)
        nav_layout.addStretch()

        root.addWidget(nav_card)
        root.addWidget(self.stack, 1)

    def _add_sub_nav_button(self, layout: QHBoxLayout, text_value: str, index: int) -> None:
        button = QPushButton(text_value)
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

        widget = self.stack.widget(index)

        if hasattr(widget, "refresh"):
            widget.refresh()

    def refresh(self) -> None:
        self.current_stock_page.refresh()
        self.daily_production_page.refresh()


class CurrentTireStockPage(QWidget):
    def __init__(self):
        super().__init__()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tire code, tire type or stock status...")
        self.search_input.setMinimumHeight(42)
        self.search_input.textChanged.connect(lambda _text: self.filter_table())

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.count_label = QLabel("0 tires")
        self.count_label.setObjectName("CountBadge")

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Tire Code",
                "Tire Type",
                "Current Stock",
                "Produced IN",
                "Stock OUT",
                "Last Movement",
                "Status",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setAlternatingRowColors(True)

        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ContentCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

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

            QLabel#CountBadge {
                background: #dbeafe;
                color: #1e40af;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 950;
            }

            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
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
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("ContentCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Current Tire Stock")
        title.setObjectName("SectionTitle")

        hint = QLabel("Live stock balance by tire type. Daily production entries increase stock automatically.")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header.addLayout(title_box, 1)
        header.addWidget(self.count_label)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.refresh_btn)

        layout.addLayout(header)
        layout.addLayout(filter_row)
        layout.addWidget(self.table, 1)

        root.addWidget(card, 1)

    def refresh(self) -> None:
        try:
            with get_session() as session:
                rows = load_current_tire_stock(session)
        except Exception as exc:
            QMessageBox.critical(self, "Stock Load Error", str(exc))
            return

        self.table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)

            stock_status = self._stock_status(row.current_stock)

            values = [
                row.tire_code,
                row.tire_name,
                str(row.current_stock),
                str(row.total_produced),
                str(row.total_out),
                self._format_date(row.last_movement_date),
                stock_status,
            ]

            for column, value in enumerate(values):
                item = self._readonly_item(value)

                if column in (0, 2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column in (2, 6):
                    self._apply_stock_style(item, row.current_stock)

                self.table.setItem(row_index, column, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.filter_table()

    def filter_table(self) -> None:
        search_value = self.search_input.text().strip().lower()
        visible_count = 0

        for row in range(self.table.rowCount()):
            row_text = " ".join(
                self.table.item(row, column).text().lower()
                for column in range(self.table.columnCount())
                if self.table.item(row, column) is not None
            )

            hide_row = bool(search_value and search_value not in row_text)
            self.table.setRowHidden(row, hide_row)

            if not hide_row:
                visible_count += 1

        self.count_label.setText(f"{visible_count} tires")

    def _stock_status(self, stock_value: int) -> str:
        if stock_value <= 0:
            return "OUT OF STOCK"

        if stock_value <= 10:
            return "LOW STOCK"

        return "AVAILABLE"

    def _apply_stock_style(self, item: QTableWidgetItem, stock_value: int) -> None:
        if stock_value <= 0:
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        elif stock_value <= 10:
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))
        else:
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))

    def _readonly_item(self, text_value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text_value)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _format_date(self, value) -> str:
        if value is None:
            return "-"

        try:
            return value.strftime("%d %b %Y")
        except AttributeError:
            return str(value)


class DailyTireProductionPage(QWidget):
    def __init__(self, current_user_id: int | None, after_save_callback=None):
        super().__init__()

        self.current_user_id = current_user_id
        self.after_save_callback = after_save_callback

        self.production_date = QDateEdit()
        self.production_date.setCalendarPopup(False)
        self.production_date.setDisplayFormat("dd MMM yyyy")
        self.production_date.setMinimumHeight(42)
        self.production_date.setDate(QDate.currentDate())
        self.production_date.dateChanged.connect(lambda _date: self.refresh())

        self.tire_combo = QComboBox()
        self.tire_combo.setMinimumHeight(42)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setMinimum(1)
        self.quantity_spin.setMaximum(1_000_000)
        self.quantity_spin.setValue(1)
        self.quantity_spin.setMinimumHeight(42)

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Optional note: shift, batch, operator, quality remark...")
        self.note_input.setFixedHeight(96)

        self.add_btn = QPushButton("Add Production to Stock")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setMinimumHeight(44)
        self.add_btn.clicked.connect(self.add_production)

        self.delete_btn = QPushButton("Delete Selected Entry")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.setMinimumHeight(42)
        self.delete_btn.clicked.connect(self.delete_selected_entry)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Date",
                "Tire Code",
                "Tire Type",
                "Quantity",
                "Note",
                "Created At",
            ]
        )
        self.history_table.setColumnHidden(0, True)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.verticalHeader().setDefaultSectionSize(48)
        self.history_table.setAlternatingRowColors(True)

        self.count_label = QLabel("0 entries")
        self.count_label.setObjectName("CountBadge")

        self._apply_styles()
        self._build_ui()
        self.load_tire_types()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ContentCard,
            QFrame#EntryCard,
            QFrame#InfoBox {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QFrame#InfoBox {
                background: #f8fafc;
            }

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

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 900;
            }

            QLabel#InfoTitle {
                color: #0f172a;
                font-size: 10pt;
                font-weight: 950;
            }

            QLabel#InfoText {
                color: #64748b;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#CountBadge {
                background: #dcfce7;
                color: #166534;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 950;
            }

            QDateEdit,
            QComboBox,
            QSpinBox,
            QTextEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }

            QDateEdit:focus,
            QComboBox:focus,
            QSpinBox:focus,
            QTextEdit:focus {
                border: 1px solid #2563eb;
            }

            QComboBox::drop-down,
            QDateEdit::drop-down,
            QSpinBox::up-button,
            QSpinBox::down-button {
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

            QPushButton#DangerButton {
                background: #dc2626;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#DangerButton:hover {
                background: #b91c1c;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
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
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        entry_card = self._build_entry_card()
        entry_card.setFixedWidth(440)

        history_card = self._build_history_card()

        root.addWidget(entry_card)
        root.addWidget(history_card, 1)

    def _build_entry_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("EntryCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Daily Tire Production Entry")
        title.setObjectName("SectionTitle")

        hint = QLabel("Add produced tire quantity for the selected date. The stock balance updates automatically.")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        layout.addWidget(self._field_label("Production Date"))
        layout.addWidget(self.production_date)

        layout.addWidget(self._field_label("Tire Type"))
        layout.addWidget(self.tire_combo)

        layout.addWidget(self._field_label("Quantity Produced"))
        layout.addWidget(self.quantity_spin)

        layout.addWidget(self._field_label("Production Note"))
        layout.addWidget(self.note_input)

        layout.addWidget(self.add_btn)

        info_box = QFrame()
        info_box.setObjectName("InfoBox")

        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(5)

        info_title = QLabel("Stock Movement Rule")
        info_title.setObjectName("InfoTitle")

        info_text = QLabel("Daily production is saved as an IN movement. Current stock is calculated from all IN and OUT movements.")
        info_text.setObjectName("InfoText")
        info_text.setWordWrap(True)

        info_layout.addWidget(info_title)
        info_layout.addWidget(info_text)

        layout.addWidget(info_box)
        layout.addStretch()

        return card

    def _build_history_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("ContentCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Daily Production History")
        title.setObjectName("SectionTitle")

        hint = QLabel("Review production entries for the selected date. Deleting an entry reverses that stock IN movement.")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header.addLayout(title_box, 1)
        header.addWidget(self.count_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()
        button_row.addWidget(self.refresh_btn)
        button_row.addWidget(self.delete_btn)

        layout.addLayout(header)
        layout.addLayout(button_row)
        layout.addWidget(self.history_table, 1)

        return card

    def _field_label(self, text_value: str) -> QLabel:
        label = QLabel(text_value)
        label.setObjectName("FieldLabel")
        return label

    def load_tire_types(self) -> None:
        current_tire_id = self.tire_combo.currentData()
        self.tire_combo.blockSignals(True)
        self.tire_combo.clear()

        try:
            with get_session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT id, tire_code, tire_name
                        FROM tire_types
                        WHERE is_active = TRUE
                        ORDER BY tire_code ASC;
                        """
                    )
                ).mappings()
                tire_rows = list(rows)
        except Exception as exc:
            QMessageBox.critical(self, "Tire Load Error", str(exc))
            self.tire_combo.blockSignals(False)
            return

        for row in tire_rows:
            self.tire_combo.addItem(
                f"{row['tire_code']} - {row['tire_name']}",
                int(row["id"]),
            )

        if current_tire_id is not None:
            index = self.tire_combo.findData(current_tire_id)

            if index >= 0:
                self.tire_combo.setCurrentIndex(index)

        self.tire_combo.blockSignals(False)

    def refresh(self) -> None:
        self.load_tire_types()
        selected_date = self.production_date.date().toPython()

        try:
            with get_session() as session:
                rows = load_daily_production_history(
                    session,
                    production_date=selected_date,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Production History Error", str(exc))
            return

        self.history_table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.history_table.insertRow(row_index)

            values = [
                str(row.movement_id),
                self._format_date(row.movement_date),
                row.tire_code,
                row.tire_name,
                str(row.quantity),
                row.note,
                self._format_datetime(row.created_at),
            ]

            for column, value in enumerate(values):
                item = self._readonly_item(value)

                if column in (1, 2, 4, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column == 4:
                    item.setForeground(QColor("#166534"))
                    item.setBackground(QColor("#dcfce7"))

                self.history_table.setItem(row_index, column, item)

        self.history_table.resizeColumnsToContents()
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.count_label.setText(f"{self.history_table.rowCount()} entries")

    def add_production(self) -> None:
        tire_type_id = self.tire_combo.currentData()

        if tire_type_id is None:
            QMessageBox.warning(self, "Tire Required", "Please select a tire type.")
            return

        movement_date = self.production_date.date().toPython()
        quantity = int(self.quantity_spin.value())
        note = self.note_input.toPlainText().strip()

        answer = QMessageBox.question(
            self,
            "Confirm Daily Production",
            "Do you want to add this daily tire production entry?\n\n"
            f"Tire: {self.tire_combo.currentText()}\n"
            f"Date: {movement_date.strftime('%d %b %Y')}\n"
            f"Quantity: {quantity}\n\n"
            "This will increase current tire stock.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                add_daily_tire_production(
                    session,
                    movement_date=movement_date,
                    tire_type_id=int(tire_type_id),
                    quantity=quantity,
                    note=note,
                    created_by=self.current_user_id,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Production Save Error", str(exc))
            return

        QMessageBox.information(self, "Saved", "Daily tire production added successfully.")
        self.quantity_spin.setValue(1)
        self.note_input.clear()
        self.refresh()

        if self.after_save_callback is not None:
            self.after_save_callback()

    def delete_selected_entry(self) -> None:
        row_index = self.history_table.currentRow()

        if row_index < 0:
            QMessageBox.warning(self, "No Entry Selected", "Please select a production entry to delete.")
            return

        id_item = self.history_table.item(row_index, 0)

        if id_item is None:
            return

        movement_id = int(id_item.text())

        answer = QMessageBox.question(
            self,
            "Confirm Delete",
            "Do you want to delete this daily production entry?\n\n"
            "This will reduce current stock because the IN movement will be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                delete_daily_production_entry(
                    session,
                    movement_id=movement_id,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Delete Error", str(exc))
            return

        QMessageBox.information(self, "Deleted", "Daily production entry deleted successfully.")
        self.refresh()

        if self.after_save_callback is not None:
            self.after_save_callback()

    def _readonly_item(self, text_value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text_value)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

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
