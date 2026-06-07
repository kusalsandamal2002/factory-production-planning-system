from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)
from sqlalchemy import func, select

from app.database import get_session
from app.models import TireType
from app.ui.details.table_page_base import TablePageBase
from app.ui.details.tire_detail_dialogs import NewTireDialog, SimpleFieldEditDialog


@dataclass
class TireMasterRow:
    tire_id: int
    tire_code: str
    tire_name: str
    is_active: bool


class TireMasterDataPage(TablePageBase):
    def __init__(self):
        super().__init__()

        self.tire_rows: list[TireMasterRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tire code, tire type, or status...")
        self.search_input.setMinimumHeight(42)
        self.search_input.textChanged.connect(self.filter_table)

        self.add_row_btn = QPushButton("+ Add New Tire Type")
        self.add_row_btn.setObjectName("PrimaryButton")
        self.add_row_btn.setMinimumHeight(42)
        self.add_row_btn.clicked.connect(self.add_new_tire_row)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tire Code", "Tire Type", "Status", "ID"])
        self.table.setColumnHidden(3, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.cellDoubleClicked.connect(self.open_cell_editor)

        self._apply_common_styles()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)

        title = QLabel("Tire Master Data")
        title.setStyleSheet("font-size: 15pt; font-weight: 950; color: #0f172a;")

        hint = QLabel(
            "Main tire master. Double-click Tire Code, Tire Type or Status to edit after manager confirmation."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        text_box.addWidget(title)
        text_box.addWidget(hint)

        header.addLayout(text_box, 1)
        header.addWidget(self.add_row_btn)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)
        layout.addWidget(self.search_input)
        layout.addWidget(self.table, 1)

        root.addWidget(card, 1)

    def refresh(self) -> None:
        try:
            with get_session() as session:
                tires = list(
                    session.scalars(
                        select(TireType).order_by(TireType.tire_code)
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        self.tire_rows = [
            TireMasterRow(
                tire_id=int(tire.id),
                tire_code=str(tire.tire_code),
                tire_name=str(tire.tire_name),
                is_active=bool(tire.is_active),
            )
            for tire in tires
        ]

        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setAlternatingRowColors(True)

        for row, tire in enumerate(self.tire_rows):
            self.table.insertRow(row)

            code_item = self._readonly_item(tire.tire_code)
            name_item = self._readonly_item(tire.tire_name)
            status_item = self._readonly_item("Active" if tire.is_active else "Inactive")
            id_item = self._readonly_item(str(tire.tire_id))

            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._apply_status_style(status_item, tire.is_active)

            self.table.setItem(row, 0, code_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, id_item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.filter_table(self.search_input.text())

    def filter_table(self, search_text: str) -> None:
        search_value = search_text.strip().lower()

        for row in range(self.table.rowCount()):
            row_text = " ".join(
                self.table.item(row, col).text().lower()
                for col in range(0, 3)
                if self.table.item(row, col) is not None
            )
            self.table.setRowHidden(row, bool(search_value and search_value not in row_text))

    def open_cell_editor(self, row: int, column: int) -> None:
        if column not in (0, 1, 2):
            return

        id_item = self.table.item(row, 3)
        current_item = self.table.item(row, column)

        if id_item is None or current_item is None:
            return

        tire_id = int(id_item.text())
        current_value = current_item.text().strip()

        field_map = {
            0: ("Edit Tire Code", "Tire Code", "code"),
            1: ("Edit Tire Type", "Tire Type", "name"),
            2: ("Edit Status", "Status", "status"),
        }

        dialog_title, field_label, field_type = field_map[column]

        dialog = SimpleFieldEditDialog(
            dialog_title=dialog_title,
            field_label=field_label,
            current_value=current_value,
            field_type=field_type,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            clean_value, display_value, field_name = self._validate_new_value(
                column,
                dialog.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Value", str(exc))
            return

        if str(display_value).strip().lower() == current_value.strip().lower():
            return

        confirm_message = (
            "Do you want to save this tire master change?\n\n"
            f"Field: {field_name}\n"
            f"Old value: {current_value}\n"
            f"New value: {display_value}"
        )

        answer = QMessageBox.question(
            self,
            "Confirm Tire Master Update",
            confirm_message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._save_cell_change(tire_id, column, clean_value)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return

        QMessageBox.information(self, "Saved", "Tire master updated successfully.")
        self.refresh()

    def _validate_new_value(self, column: int, value):
        if column == 0:
            tire_code = str(value).strip().upper()

            if not tire_code:
                raise ValueError("Tire Code cannot be empty.")

            return tire_code, tire_code, "Tire Code"

        if column == 1:
            tire_name = str(value).strip()

            if not tire_name:
                raise ValueError("Tire Type cannot be empty.")

            return tire_name, tire_name, "Tire Type"

        if column == 2:
            is_active = bool(value)
            display_value = "Active" if is_active else "Inactive"
            return is_active, display_value, "Status"

        raise ValueError("This column cannot be edited.")

    def _save_cell_change(self, tire_id: int, column: int, clean_value) -> None:
        with get_session() as session:
            tire = session.get(TireType, tire_id)

            if tire is None:
                raise ValueError("Selected tire type was not found. Please refresh and try again.")

            if column == 0:
                duplicate = session.scalar(
                    select(TireType).where(
                        func.lower(TireType.tire_code) == str(clean_value).lower(),
                        TireType.id != tire_id,
                    )
                )

                if duplicate is not None:
                    raise ValueError(f"Tire code {clean_value} already exists.")

                tire.tire_code = str(clean_value)

            elif column == 1:
                tire.tire_name = str(clean_value)

            elif column == 2:
                tire.is_active = bool(clean_value)

    def add_new_tire_row(self) -> None:
        suggested_code = self._generate_next_tire_code()

        dialog = NewTireDialog(suggested_code=suggested_code, parent=self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        tire_code, tire_name, is_active = dialog.values()

        if not tire_code:
            QMessageBox.warning(self, "Missing Tire Code", "Please enter tire code.")
            return

        if not tire_name:
            QMessageBox.warning(self, "Missing Tire Type", "Please enter tire type.")
            return

        confirm_message = (
            "Do you want to create this tire master record?\n\n"
            f"Tire Code: {tire_code}\n"
            f"Tire Type: {tire_name}\n"
            f"Status: {'Active' if is_active else 'Inactive'}"
        )

        answer = QMessageBox.question(
            self,
            "Confirm New Tire Type",
            confirm_message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                duplicate = session.scalar(
                    select(TireType).where(
                        func.lower(TireType.tire_code) == tire_code.lower()
                    )
                )

                if duplicate is not None:
                    QMessageBox.warning(
                        self,
                        "Duplicate Tire Code",
                        f"Tire code {tire_code} already exists.",
                    )
                    return

                tire = TireType(
                    tire_code=tire_code,
                    tire_name=tire_name,
                    curing_minutes=30,
                    is_active=is_active,
                )
                session.add(tire)

        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return

        QMessageBox.information(
            self,
            "Saved",
            "New tire type added successfully. Set its production time in Tire Production Time tab.",
        )
        self.refresh()

    def _generate_next_tire_code(self) -> str:
        existing_numbers: list[int] = []

        for tire in self.tire_rows:
            code = tire.tire_code.upper().replace("TYPE-", "").strip()

            if code.isdigit():
                existing_numbers.append(int(code))

        next_number = max(existing_numbers, default=0) + 1

        while True:
            candidate = f"TYPE-{next_number:02d}"

            if all(tire.tire_code.upper() != candidate for tire in self.tire_rows):
                return candidate

            next_number += 1