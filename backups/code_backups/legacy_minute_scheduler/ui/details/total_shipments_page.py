from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
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
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import get_session
from app.models import Order, OrderItem


@dataclass
class ShipmentRow:
    order_id: int
    order_no: str
    customer_name: str
    priority: str
    order_received_date: date
    system_can_receive_datetime: datetime
    manager_confirmed_receive_date: date
    status: str
    manager_note: str


class OrderDetailsDialog(QDialog):
    def __init__(self, *, order_data: dict, parent: QWidget | None = None):
        super().__init__(parent)

        self.order_data = order_data
        self.setWindowTitle("Shipment Order Details")
        self.setModal(True)
        self.setMinimumSize(780, 520)

        self._apply_styles()
        self._build_ui()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f8fafc;
            }

            QFrame#DialogCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#DialogTitle {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }

            QLabel#DialogHint {
                color: #64748b;
                font-weight: 650;
            }

            QLabel#FieldLabel {
                color: #64748b;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#FieldValue {
                background: #f1f5f9;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 8px 10px;
                font-weight: 850;
            }

            QLabel#StatusBadge {
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: 950;
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

            QHeaderView::section {
                background: #f1f5f9;
                color: #1e293b;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px;
                font-weight: 950;
            }

            QPushButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 950;
            }

            QPushButton:hover {
                background: #1d4ed8;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Shipment Order Details")
        title.setObjectName("DialogTitle")

        hint = QLabel("Review confirmed order details, date commitments and tire item quantities.")
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(hint)

        card = QFrame()
        card.setObjectName("DialogCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._add_field(grid, 0, 0, "Order No", self.order_data["order_no"])
        self._add_field(grid, 0, 2, "Customer", self.order_data["customer_name"])
        self._add_field(grid, 1, 0, "Priority", self.order_data["priority"])
        self._add_status_field(grid, 1, 2, "Status", self.order_data["status"])
        self._add_field(grid, 2, 0, "Order Received", self.order_data["order_received_date"])
        self._add_field(grid, 2, 2, "System Can Receive", self.order_data["system_can_receive_datetime"])
        self._add_field(grid, 3, 0, "Manager Confirmed Date", self.order_data["manager_confirmed_receive_date"])
        self._add_field(grid, 3, 2, "Manager Note", self.order_data["manager_note"])

        card_layout.addLayout(grid)

        items_title = QLabel("Tire Items")
        items_title.setStyleSheet("font-size: 12pt; font-weight: 950; color: #0f172a;")
        card_layout.addWidget(items_title)

        self.items_table = QTableWidget(0, 3)
        self.items_table.setHorizontalHeaderLabels(["Tire Code", "Tire Type", "Quantity"])
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.setAlternatingRowColors(True)

        self._load_items_table()
        card_layout.addWidget(self.items_table, 1)

        root.addWidget(card, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        root.addLayout(button_row)

    def _add_field(self, grid: QGridLayout, row: int, col: int, label_text: str, value_text: str) -> None:
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")

        value = QLabel(value_text or "-")
        value.setObjectName("FieldValue")
        value.setWordWrap(True)
        value.setMinimumHeight(38)

        grid.addWidget(label, row * 2, col)
        grid.addWidget(value, row * 2 + 1, col)

    def _add_status_field(self, grid: QGridLayout, row: int, col: int, label_text: str, value_text: str) -> None:
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")

        value = QLabel(value_text or "-")
        value.setObjectName("StatusBadge")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setStyleSheet(self._status_badge_style(value_text))

        grid.addWidget(label, row * 2, col)
        grid.addWidget(value, row * 2 + 1, col)

    def _status_badge_style(self, status: str) -> str:
        status_value = (status or "").upper()

        if status_value in ("COMPLETED", "PRODUCTION_COMPLETED", "CLOSED"):
            return "background:#dcfce7; color:#166534; border:1px solid #bbf7d0;"

        if status_value in ("CANCELLED", "CANCELED"):
            return "background:#fee2e2; color:#991b1b; border:1px solid #fecaca;"

        if status_value == "CONFIRMED":
            return "background:#dbeafe; color:#1e40af; border:1px solid #bfdbfe;"

        return "background:#fef3c7; color:#92400e; border:1px solid #fde68a;"

    def _load_items_table(self) -> None:
        self.items_table.setRowCount(0)

        for row, item in enumerate(self.order_data["items"]):
            self.items_table.insertRow(row)

            code_item = self._readonly_item(item["tire_code"])
            name_item = self._readonly_item(item["tire_name"])
            qty_item = self._readonly_item(str(item["quantity"]))

            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.items_table.setItem(row, 0, code_item)
            self.items_table.setItem(row, 1, name_item)
            self.items_table.setItem(row, 2, qty_item)

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item


class TotalShipmentsPage(QWidget):
    def __init__(self, on_back=None):
        super().__init__()

        self.on_back = on_back
        self.rows: list[ShipmentRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search order no, customer, status, priority or note...")
        self.search_input.setMinimumHeight(42)
        self.search_input.textChanged.connect(lambda _text: self.filter_table())

        self.status_filter = QComboBox()
        self.status_filter.setMinimumHeight(42)
        self.status_filter.addItems(["All Status", "CONFIRMED", "COMPLETED", "CLOSED", "CANCELLED"])
        self.status_filter.currentTextChanged.connect(lambda _text: self.filter_table())

        self.priority_filter = QComboBox()
        self.priority_filter.setMinimumHeight(42)
        self.priority_filter.addItems(["All Priority", "NORMAL", "HIGH", "URGENT"])
        self.priority_filter.currentTextChanged.connect(lambda _text: self.filter_table())

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
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.open_order_details)

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
                background: #dbeafe;
                color: #1e40af;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 950;
            }

            QLineEdit,
            QComboBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }

            QLineEdit:focus,
            QComboBox:focus {
                border: 1px solid #2563eb;
            }

            QComboBox::drop-down {
                border: none;
                width: 28px;
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

        title = QLabel("All Shipment Orders")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Complete shipment/order register. Double-click a row to review tire items and confirmed delivery details."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header_row.addLayout(title_box, 1)
        header_row.addWidget(self.count_label)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(self.priority_filter)
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
                        .order_by(Order.order_received_date.desc(), Order.id.desc())
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        self.rows = [
            ShipmentRow(
                order_id=int(order.id),
                order_no=str(order.order_no),
                customer_name=str(order.customer.customer_name if order.customer else "-"),
                priority=str(order.priority or "-").upper(),
                order_received_date=order.order_received_date,
                system_can_receive_datetime=order.system_can_receive_datetime,
                manager_confirmed_receive_date=order.manager_confirmed_receive_date,
                status=str(order.status or "-").upper(),
                manager_note=str(order.manager_note or "-"),
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
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.filter_table()

    def filter_table(self) -> None:
        search_value = self.search_input.text().strip().lower()
        status_value = self.status_filter.currentText().strip().upper()
        priority_value = self.priority_filter.currentText().strip().upper()

        visible_count = 0

        for row in range(self.table.rowCount()):
            row_text = " ".join(
                self.table.item(row, col).text().lower()
                for col in range(0, 8)
                if self.table.item(row, col) is not None
            )

            status_text = self.table.item(row, 6).text().upper() if self.table.item(row, 6) else ""
            priority_text = self.table.item(row, 2).text().upper() if self.table.item(row, 2) else ""

            search_ok = not search_value or search_value in row_text
            status_ok = status_value == "ALL STATUS" or status_text == status_value
            priority_ok = priority_value == "ALL PRIORITY" or priority_text == priority_value

            hide_row = not (search_ok and status_ok and priority_ok)
            self.table.setRowHidden(row, hide_row)

            if not hide_row:
                visible_count += 1

        self.count_label.setText(f"{visible_count} records")

    def open_order_details(self, row: int, column: int) -> None:
        id_item = self.table.item(row, 8)

        if id_item is None:
            return

        order_id = int(id_item.text())

        try:
            order_data = self._load_order_details(order_id)
        except Exception as exc:
            QMessageBox.critical(self, "Order Details Error", str(exc))
            return

        dialog = OrderDetailsDialog(order_data=order_data, parent=self)
        dialog.exec()

    def _load_order_details(self, order_id: int) -> dict:
        with get_session() as session:
            order = (
                session.execute(
                    select(Order)
                    .options(
                        joinedload(Order.customer),
                        joinedload(Order.items).joinedload(OrderItem.tire_type),
                    )
                    .where(Order.id == order_id)
                )
                .unique()
                .scalar_one_or_none()
            )

            if order is None:
                raise ValueError("Selected order was not found. Please refresh and try again.")

            items = [
                {
                    "tire_code": str(item.tire_type.tire_code if item.tire_type else "-"),
                    "tire_name": str(item.tire_type.tire_name if item.tire_type else "-"),
                    "quantity": int(item.quantity),
                }
                for item in order.items
            ]

            order_data = {
                "order_no": str(order.order_no),
                "customer_name": str(order.customer.customer_name if order.customer else "-"),
                "priority": str(order.priority or "-").upper(),
                "status": str(order.status or "-").upper(),
                "order_received_date": self._format_date(order.order_received_date),
                "system_can_receive_datetime": self._format_datetime(order.system_can_receive_datetime),
                "manager_confirmed_receive_date": self._format_date(order.manager_confirmed_receive_date),
                "manager_note": str(order.manager_note or "-"),
                "items": items,
            }

        return order_data

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

