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
from sqlalchemy import select

from app.database import get_session
from app.models import TireType
from app.ui.details.table_page_base import TablePageBase
from app.ui.details.tire_detail_dialogs import ProductionTimeEditDialog


@dataclass
class TireProductionTimeRow:
    tire_id: int
    tire_code: str
    tire_name: str
    curing_minutes: int
    is_active: bool


class TireProductionTimePage(TablePageBase):
    def __init__(self):
        super().__init__()

        self.rows: list[TireProductionTimeRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search tire code, tire type, production time, or status..."
        )
        self.search_input.setMinimumHeight(42)
        self.search_input.textChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Tire Code", "Tire Type", "Production Time", "Status", "ID"]
        )
        self.table.setColumnHidden(4, True)
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
        self.table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.cellDoubleClicked.connect(self.open_time_editor)

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

        title = QLabel("Tire Production Time")
        title.setStyleSheet("font-size: 15pt; font-weight: 950; color: #0f172a;")

        hint = QLabel(
            "This production time is used for order receive-date and oven capacity calculation. "
            "Double-click Production Time to update."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        text_box.addWidget(title)
        text_box.addWidget(hint)

        header.addLayout(text_box, 1)
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

        self.rows = [
            TireProductionTimeRow(
                tire_id=int(tire.id),
                tire_code=str(tire.tire_code),
                tire_name=str(tire.tire_name),
                curing_minutes=int(tire.curing_minutes),
                is_active=bool(tire.is_active),
            )
            for tire in tires
        ]

        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setAlternatingRowColors(True)

        for row_number, row_data in enumerate(self.rows):
            self.table.insertRow(row_number)

            code_item = self._readonly_item(row_data.tire_code)
            name_item = self._readonly_item(row_data.tire_name)
            time_item = self._readonly_item(f"{row_data.curing_minutes} min")
            status_item = self._readonly_item(
                "Active" if row_data.is_active else "Inactive"
            )
            id_item = self._readonly_item(str(row_data.tire_id))

            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._apply_status_style(status_item, row_data.is_active)

            self.table.setItem(row_number, 0, code_item)
            self.table.setItem(row_number, 1, name_item)
            self.table.setItem(row_number, 2, time_item)
            self.table.setItem(row_number, 3, status_item)
            self.table.setItem(row_number, 4, id_item)

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
                for col in range(0, 4)
                if self.table.item(row, col) is not None
            )
            self.table.setRowHidden(row, bool(search_value and search_value not in row_text))

    def open_time_editor(self, row: int, column: int) -> None:
        if column != 2:
            QMessageBox.information(
                self,
                "Production Time",
                "Only the Production Time column can be edited here.\n\n"
                "Tire Code and Tire Type should be changed from Tire Master Data.",
            )
            return

        id_item = self.table.item(row, 4)

        if id_item is None:
            return

        tire_id = int(id_item.text())
        selected_row = next(
            (item for item in self.rows if item.tire_id == tire_id),
            None,
        )

        if selected_row is None:
            QMessageBox.warning(
                self,
                "Not Found",
                "Selected tire was not found. Please refresh and try again.",
            )
            return

        dialog = ProductionTimeEditDialog(
            tire_code=selected_row.tire_code,
            tire_name=selected_row.tire_name,
            current_minutes=selected_row.curing_minutes,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            new_minutes = dialog.minutes()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Production Time", str(exc))
            return

        if new_minutes == selected_row.curing_minutes:
            return

        confirm_message = (
            "Do you want to save this production time change?\n\n"
            f"Tire Code: {selected_row.tire_code}\n"
            f"Tire Type: {selected_row.tire_name}\n"
            f"Old Time: {selected_row.curing_minutes} min\n"
            f"New Time: {new_minutes} min\n\n"
            "This new time will be used for future order capacity calculations."
        )

        answer = QMessageBox.question(
            self,
            "Confirm Production Time Update",
            confirm_message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                tire = session.get(TireType, tire_id)

                if tire is None:
                    raise ValueError(
                        "Selected tire was not found. Please refresh and try again."
                    )

                tire.curing_minutes = new_minutes

        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return

        QMessageBox.information(self, "Saved", "Production time updated successfully.")
        self.refresh()