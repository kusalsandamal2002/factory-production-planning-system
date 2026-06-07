from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from app.models import Oven
from app.ui.details.table_page_base import TablePageBase


@dataclass
class MachineRow:
    machine_id: int
    machine_code: str
    is_active: bool


class MachineDetailsPage(TablePageBase):
    def __init__(self):
        super().__init__()

        self.rows: list[MachineRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search machine / oven code or status...")
        self.search_input.setMinimumHeight(42)
        self.search_input.textChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Machine / Oven Code", "Status", "ID"])
        self.table.setColumnHidden(2, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )

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

        title = QLabel("Machine Details")
        title.setStyleSheet("font-size: 15pt; font-weight: 950; color: #0f172a;")

        hint = QLabel(
            "Factory machine / oven master visibility. More machine capacity and maintenance fields can be added here later."
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
                ovens = list(
                    session.scalars(
                        select(Oven).order_by(Oven.oven_code)
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        self.rows = [
            MachineRow(
                machine_id=int(oven.id),
                machine_code=str(getattr(oven, "oven_code", f"OVEN-{oven.id}")),
                is_active=bool(getattr(oven, "is_active", True)),
            )
            for oven in ovens
        ]

        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setAlternatingRowColors(True)

        for row_number, row_data in enumerate(self.rows):
            self.table.insertRow(row_number)

            code_item = self._readonly_item(row_data.machine_code)
            status_item = self._readonly_item(
                "Active" if row_data.is_active else "Inactive"
            )
            id_item = self._readonly_item(str(row_data.machine_id))

            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._apply_status_style(status_item, row_data.is_active)

            self.table.setItem(row_number, 0, code_item)
            self.table.setItem(row_number, 1, status_item)
            self.table.setItem(row_number, 2, id_item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.filter_table(self.search_input.text())

    def filter_table(self, search_text: str) -> None:
        search_value = search_text.strip().lower()

        for row in range(self.table.rowCount()):
            row_text = " ".join(
                self.table.item(row, col).text().lower()
                for col in range(0, 2)
                if self.table.item(row, col) is not None
            )
            self.table.setRowHidden(
                row,
                bool(search_value and search_value not in row_text),
            )