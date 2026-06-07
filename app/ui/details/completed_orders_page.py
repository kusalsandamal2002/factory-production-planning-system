from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import get_session
from app.models import Order


@dataclass
class OrderRow:
    order_id: int
    order_no: str
    customer_name: str
    priority: str
    order_received_date: date
    system_can_receive_datetime: datetime
    manager_confirmed_receive_date: date
    status: str
    manager_note: str
    days_late: int = 0


class CompletedOrdersPage(QWidget):
    COMPLETED_STATUSES = ("COMPLETED", "PRODUCTION_COMPLETED", "CLOSED")
    CANCELLED_STATUSES = ("CANCELLED", "CANCELED")
    CLOSED_STATUSES = COMPLETED_STATUSES + CANCELLED_STATUSES

    def __init__(self, on_back=None):
        super().__init__()

        self.on_back = on_back
        self.rows: list[OrderRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search completed order no, customer, status, priority or note..."
        )
        self.search_input.setMinimumHeight(42)
        self.search_input.textChanged.connect(lambda _text: self.filter_table())

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("RefreshButton")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.count_label = QLabel("0 records")
        self.count_label.setObjectName("CountBadge")

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Order No",
                "Customer",
                "Priority",
                "Order Received",
                "System Can Receive",
                "Manager Confirmed",
                "Status",
                "Manager Note",
                "ID",
            ]
        )
        self.table.setColumnHidden(8, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.horizontalHeader().setStretchLastSection(False)

        for column in range(8):
            self.table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            7,
            QHeaderView.ResizeMode.Stretch,
        )

        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#RegisterCard {
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
                background: #dcfce7;
                color: #166534;
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

            QPushButton#RefreshButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#RefreshButton:hover {
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
        card.setObjectName("RegisterCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Completed Orders")
        title.setObjectName("SectionTitle")

        hint = QLabel("Only orders marked as completed, delivered or closed are shown here.")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header_row.addLayout(title_box, 1)
        header_row.addWidget(self.count_label)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.refresh_btn)

        layout.addLayout(header_row)
        layout.addLayout(filter_row)
        layout.addWidget(self.table, 1)

        root.addWidget(card, 1)

    def refresh(self) -> None:
        try:
            with get_session() as session:
                orders = list(
                    session.scalars(
                        select(Order)
                        .options(joinedload(Order.customer))
                        .where(func.upper(Order.status).in_(self.COMPLETED_STATUSES))
                        .order_by(Order.order_received_date.desc(), Order.id.desc())
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        today = date.today()

        self.rows = [
            OrderRow(
                order_id=int(order.id),
                order_no=str(order.order_no),
                customer_name=str(order.customer.customer_name if order.customer else "-"),
                priority=str(order.priority or "-").upper(),
                order_received_date=order.order_received_date,
                system_can_receive_datetime=order.system_can_receive_datetime,
                manager_confirmed_receive_date=order.manager_confirmed_receive_date,
                status=str(order.status or "-").upper(),
                manager_note=str(order.manager_note or "-"),
                days_late=max((today - order.manager_confirmed_receive_date).days, 0)
                if order.manager_confirmed_receive_date
                else 0,
            )
            for order in orders
        ]

        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setAlternatingRowColors(True)

        for row_number, row_data in enumerate(self.rows):
            self.table.insertRow(row_number)

            values = [
                row_data.order_no,
                row_data.customer_name,
                row_data.priority,
                self._format_date(row_data.order_received_date),
                self._format_datetime(row_data.system_can_receive_datetime),
                self._format_date(row_data.manager_confirmed_receive_date),
                row_data.status,
                row_data.manager_note,
                str(row_data.order_id),
            ]

            for col, value in enumerate(values):
                item = self._readonly_item(value)

                if col in (0, 2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 6:
                    self._apply_status_style(item, row_data.status)

                if col == 2:
                    self._apply_priority_style(item, row_data.priority)

                self.table.setItem(row_number, col, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            7,
            QHeaderView.ResizeMode.Stretch,
        )
        self.filter_table()

    def filter_table(self) -> None:
        search_value = self.search_input.text().strip().lower()
        visible_count = 0

        for row in range(self.table.rowCount()):
            row_text = " ".join(
                self.table.item(row, col).text().lower()
                for col in range(0, 8)
                if self.table.item(row, col) is not None
            )

            hide_row = bool(search_value and search_value not in row_text)
            self.table.setRowHidden(row, hide_row)

            if not hide_row:
                visible_count += 1

        self.count_label.setText(f"{visible_count} records")

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _apply_status_style(self, item: QTableWidgetItem, status: str) -> None:
        status_value = (status or "").upper()

        if status_value in ("COMPLETED", "PRODUCTION_COMPLETED", "CLOSED"):
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        elif status_value in ("CANCELLED", "CANCELED"):
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        elif status_value == "CONFIRMED":
            item.setForeground(QColor("#1e40af"))
            item.setBackground(QColor("#dbeafe"))
        else:
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))

    def _apply_priority_style(self, item: QTableWidgetItem, priority: str) -> None:
        priority_value = (priority or "").upper()

        if priority_value == "URGENT":
            item.setForeground(QColor("#991b1b"))
        elif priority_value == "HIGH":
            item.setForeground(QColor("#b45309"))
        else:
            item.setForeground(QColor("#334155"))

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