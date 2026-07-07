from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
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

from app.database import engine


def _to_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value == "":
                return default
        return int(float(value))
    except Exception:
        return default


class ShipmentDialog(QDialog):
    def __init__(self, parent=None, shipment: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Shipment Header")
        self.setMinimumWidth(620)

        self.shipment_no_input = QLineEdit()
        self.shipment_no_input.setPlaceholderText("Shipment ID / shipment name")

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer / destination")

        self.order_date_input = QDateEdit()
        self.order_date_input.setCalendarPopup(True)
        self.order_date_input.setDate(QDate.currentDate())

        self.status_input = QComboBox()
        self.status_input.addItems(["Planned", "In Progress", "Completed", "On Hold", "Cancelled"])

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Shipment note / remarks")
        self.note_input.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Shipment Header")
        title.setStyleSheet("font-size:18pt; font-weight:950; color:#0f172a;")
        layout.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Shipment ID / Name"), 0, 0)
        form.addWidget(self.shipment_no_input, 1, 0)
        form.addWidget(QLabel("Customer / Destination"), 0, 1)
        form.addWidget(self.customer_input, 1, 1)
        form.addWidget(QLabel("Order / Priority Date"), 2, 0)
        form.addWidget(self.order_date_input, 3, 0)
        form.addWidget(QLabel("Status"), 2, 1)
        form.addWidget(self.status_input, 3, 1)
        form.addWidget(QLabel("Note"), 4, 0, 1, 2)
        form.addWidget(self.note_input, 5, 0, 1, 2)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if shipment:
            self.shipment_no_input.setText(str(shipment.get("shipment_no") or ""))
            self.customer_input.setText(str(shipment.get("customer_name") or ""))
            order_date = shipment.get("manager_order_date") or shipment.get("shipment_date") or shipment.get("created_at")
            if hasattr(order_date, "year"):
                self.order_date_input.setDate(QDate(order_date.year, order_date.month, order_date.day))
            status = str(shipment.get("status") or "Planned")
            index = self.status_input.findText(status)
            if index >= 0:
                self.status_input.setCurrentIndex(index)
            self.note_input.setPlainText(str(shipment.get("note") or ""))

    def get_data(self) -> dict:
        order_date = self.order_date_input.date().toPython()
        return {
            "shipment_no": self.shipment_no_input.text().strip(),
            "shipment_name": self.shipment_no_input.text().strip(),
            "customer_name": self.customer_input.text().strip(),
            "manager_order_date": order_date,
            "shipment_date": order_date,
            "status": self.status_input.currentText(),
            "note": self.note_input.toPlainText().strip(),
        }


class ShipmentItemDialog(QDialog):
    def __init__(self, parent=None, base_date=None, item: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Shipment Item")
        self.setMinimumWidth(720)
        self.master_items = self.load_master_items()

        self.sap_input = QComboBox()
        self.sap_input.setEditable(True)
        self.sap_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.sap_input.addItem("Select approved SMDS item", None)
        for master_item in self.master_items:
            self.sap_input.addItem(
                f"{master_item['sap_code']} - {master_item['tyre_description']}",
                master_item,
            )
        self.sap_input.currentIndexChanged.connect(self.update_description_from_master)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Item description")

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 999999999)
        self.quantity_input.setValue(1)

        self.receive_date_input = QDateEdit()
        self.receive_date_input.setCalendarPopup(True)
        qdate = QDate.currentDate()
        if hasattr(base_date, "year"):
            qdate = QDate(base_date.year, base_date.month, base_date.day)
        self.receive_date_input.setDate(qdate)

        self.status_input = QComboBox()
        self.status_input.addItems(["Pending", "In Production", "Completed", "On Hold", "Cancelled"])

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Item note / schedule reason")
        self.note_input.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        title = QLabel("Shipment Item")
        title.setStyleSheet("font-size:18pt; font-weight:950; color:#0f172a;")
        layout.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Approved SMDS Item"), 0, 0, 1, 2)
        form.addWidget(self.sap_input, 1, 0, 1, 2)
        form.addWidget(QLabel("Description"), 2, 0, 1, 2)
        form.addWidget(self.description_input, 3, 0, 1, 2)
        form.addWidget(QLabel("Quantity"), 4, 0)
        form.addWidget(self.quantity_input, 5, 0)
        form.addWidget(QLabel("Item Receive Date"), 4, 1)
        form.addWidget(self.receive_date_input, 5, 1)
        form.addWidget(QLabel("Status"), 6, 0)
        form.addWidget(self.status_input, 7, 0)
        form.addWidget(QLabel("Reason / Note"), 8, 0, 1, 2)
        form.addWidget(self.note_input, 9, 0, 1, 2)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if item:
            self.populate_item(item)

    def load_master_items(self) -> list[dict]:
        # Preferred source: approved SMDS rows.
        try:
            with engine.begin() as connection:
                rows = connection.execute(text("""
                    SELECT sap_code,
                           COALESCE(material_description, tyre_description, '') AS tyre_description
                    FROM smds
                    WHERE COALESCE(planning_manager_approval_status, 'Pending') = 'Approved'
                      AND sap_code IS NOT NULL
                      AND TRIM(sap_code) <> ''
                    ORDER BY sap_code ASC;
                """)).mappings().all()
            result = [dict(row) for row in rows]
            if result:
                return result
        except Exception:
            pass

        # Fallback for older databases.
        try:
            with engine.begin() as connection:
                rows = connection.execute(text("""
                    SELECT sap_code, tyre_description
                    FROM mpps_sap_stock_items
                    WHERE is_active = TRUE
                    ORDER BY sap_code ASC;
                """)).mappings().all()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def populate_item(self, item: dict) -> None:
        sap_code = str(item.get("sap_code") or "")
        for index in range(self.sap_input.count()):
            data = self.sap_input.itemData(index)
            if isinstance(data, dict) and str(data.get("sap_code")) == sap_code:
                self.sap_input.setCurrentIndex(index)
                break
        else:
            self.sap_input.setEditText(sap_code)
        self.description_input.setText(str(item.get("item_description") or ""))
        self.quantity_input.setValue(_to_int(item.get("quantity"), 1))
        receive_date = item.get("item_receive_date") or item.get("end_date") or item.get("start_date")
        if hasattr(receive_date, "year"):
            self.receive_date_input.setDate(QDate(receive_date.year, receive_date.month, receive_date.day))
        status = str(item.get("item_status") or "Pending")
        index = self.status_input.findText(status)
        if index >= 0:
            self.status_input.setCurrentIndex(index)
        self.note_input.setPlainText(str(item.get("schedule_reason") or item.get("note") or ""))

    def update_description_from_master(self) -> None:
        data = self.sap_input.currentData()
        if isinstance(data, dict):
            self.description_input.setText(str(data.get("tyre_description") or ""))

    def get_data(self) -> dict:
        data = self.sap_input.currentData()
        if isinstance(data, dict):
            sap_code = str(data.get("sap_code") or "").strip()
            description = str(data.get("tyre_description") or "").strip()
        else:
            text_value = self.sap_input.currentText().strip()
            sap_code = text_value.split(" - ", 1)[0].strip()
            description = self.description_input.text().strip()
        if self.description_input.text().strip():
            description = self.description_input.text().strip()
        receive_date = self.receive_date_input.date().toPython()
        return {
            "sap_code": sap_code,
            "item_description": description,
            "quantity": self.quantity_input.value(),
            "start_date": receive_date,
            "end_date": receive_date,
            "item_receive_date": receive_date,
            "item_status": self.status_input.currentText(),
            "note": self.note_input.toPlainText().strip(),
            "schedule_reason": self.note_input.toPlainText().strip(),
        }


class ShipmentOrdersPage(QWidget):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.selected_shipment_id: int | None = None
        self.current_shipment_id: int | None = None
        self.selected_item_id: int | None = None

        self._apply_styles()
        self.ensure_tables()

        self.stack = QStackedWidget()
        self.list_page = QWidget()
        self.detail_page = QWidget()
        self.stack.addWidget(self.list_page)
        self.stack.addWidget(self.detail_page)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)

        self._build_list_page()
        self._build_detail_page()
        self.refresh_list()

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; }
            QFrame#Card, QFrame#HeaderCard, QFrame#MetricCard {
                background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;
            }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#SectionTitle { color:#0f172a; font-size:16pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#InfoLabel { color:#334155; font-size:10pt; font-weight:750; }
            QLabel#MetricValue { color:#0f172a; font-size:24pt; font-weight:950; }
            QLabel#MetricLabel { color:#64748b; font-size:9pt; font-weight:850; }
            QLineEdit, QDateEdit, QComboBox, QTextEdit, QSpinBox {
                background:#ffffff; color:#0f172a; border:1px solid #cbd5e1;
                border-radius:10px; padding:9px 12px; font-size:10pt; font-weight:650; min-height:24px;
            }
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {
                border:1px solid #2563eb;
            }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:none; border-radius:10px; padding:10px 18px; font-weight:950; min-height:26px; }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:none; border-radius:10px; padding:10px 18px; font-weight:950; min-height:26px; }
            QPushButton#SecondaryButton:hover { background:#cbd5e1; }
            QPushButton#DangerButton { background:#fee2e2; color:#991b1b; border:none; border-radius:10px; padding:10px 18px; font-weight:950; min-height:26px; }
            QPushButton#DangerButton:hover { background:#fecaca; }
            QTableWidget { background:#ffffff; color:#0f172a; border:1px solid #e2e8f0; border-radius:12px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QTableWidget::item { padding:8px 10px; border:none; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:none; border-right:1px solid #e2e8f0; border-bottom:1px solid #e2e8f0; padding:10px; font-weight:950; }
        """)

    def _build_list_page(self) -> None:
        layout = QVBoxLayout(self.list_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = self._card("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(12)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Shipment Details")
        title.setObjectName("PageTitle")
        hint = QLabel("Review saved shipments by manager order/priority date and calculated factory-out date.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        self.new_btn = QPushButton("+ New Shipment")
        self.new_btn.setObjectName("PrimaryButton")
        self.new_btn.clicked.connect(self.create_shipment)
        self.edit_btn = QPushButton("Edit Shipment")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.clicked.connect(self.edit_selected_shipment)
        self.move_back_btn = QPushButton("← Order Date -1")
        self.move_back_btn.setObjectName("SecondaryButton")
        self.move_back_btn.clicked.connect(lambda: self.move_selected_shipment_date(-1))
        self.move_forward_btn = QPushButton("Order Date +1 →")
        self.move_forward_btn.setObjectName("SecondaryButton")
        self.move_forward_btn.clicked.connect(lambda: self.move_selected_shipment_date(1))
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_list)
        top.addLayout(title_box, 1)
        top.addWidget(self.new_btn)
        top.addWidget(self.edit_btn)
        top.addWidget(self.move_back_btn)
        top.addWidget(self.move_forward_btn)
        top.addWidget(self.refresh_btn)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search shipment ID, customer, status, note or SAP code...")
        self.search_input.textChanged.connect(self.refresh_list)
        header_layout.addLayout(top)
        header_layout.addWidget(self.search_input)
        layout.addWidget(header)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.total_shipments_value = QLabel("0")
        self.total_items_value = QLabel("0")
        self.total_qty_value = QLabel("0")
        self.next_shipment_value = QLabel("-")
        stats.addWidget(self._metric_card(self.total_shipments_value, "Total Shipments"))
        stats.addWidget(self._metric_card(self.total_items_value, "Total Items"))
        stats.addWidget(self._metric_card(self.total_qty_value, "Total Quantity"))
        stats.addWidget(self._metric_card(self.next_shipment_value, "Next Factory Out"))
        layout.addLayout(stats)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)
        table_title = QLabel("All Shipments")
        table_title.setObjectName("SectionTitle")
        table_hint = QLabel("Double-click a shipment row to open full item-level factory-out details.")
        table_hint.setObjectName("Hint")
        self.list_table = QTableWidget(0, 8)
        self.list_table.setHorizontalHeaderLabels([
            "Order / Priority Date", "Factory Out Date", "Shipment ID", "Customer",
            "Items", "Total Qty", "Status", "Note"
        ])
        self._setup_list_table()
        table_layout.addWidget(table_title)
        table_layout.addWidget(table_hint)
        table_layout.addWidget(self.list_table, 1)
        layout.addWidget(table_card, 1)

    def _build_detail_page(self) -> None:
        layout = QVBoxLayout(self.detail_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = self._card("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(14)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        self.detail_title = QLabel("Shipment")
        self.detail_title.setObjectName("PageTitle")
        self.detail_subtitle = QLabel("Full shipment details and item-level planning dates")
        self.detail_subtitle.setObjectName("Hint")
        title_box.addWidget(self.detail_title)
        title_box.addWidget(self.detail_subtitle)
        self.back_btn = QPushButton("← Back to Shipments")
        self.back_btn.setObjectName("SecondaryButton")
        self.back_btn.clicked.connect(self.back_to_list)
        self.edit_header_btn = QPushButton("Edit Header")
        self.edit_header_btn.setObjectName("SecondaryButton")
        self.edit_header_btn.clicked.connect(self.edit_current_shipment_header)
        self.add_item_btn = QPushButton("+ Add Item")
        self.add_item_btn.setObjectName("PrimaryButton")
        self.add_item_btn.clicked.connect(self.add_item)
        self.edit_item_btn = QPushButton("Edit Item")
        self.edit_item_btn.setObjectName("SecondaryButton")
        self.edit_item_btn.clicked.connect(self.edit_selected_item)
        self.delete_item_btn = QPushButton("Delete Item")
        self.delete_item_btn.setObjectName("DangerButton")
        self.delete_item_btn.clicked.connect(self.delete_selected_item)
        top.addLayout(title_box, 1)
        top.addWidget(self.back_btn)
        top.addWidget(self.edit_header_btn)
        top.addWidget(self.add_item_btn)
        top.addWidget(self.edit_item_btn)
        top.addWidget(self.delete_item_btn)

        info = QGridLayout()
        info.setHorizontalSpacing(16)
        info.setVerticalSpacing(8)
        self.info_customer = QLabel("Customer: -")
        self.info_order_date = QLabel("Order / Priority Date: -")
        self.info_factory_out = QLabel("Factory Out Date: -")
        self.info_status = QLabel("Status: -")
        self.info_note = QLabel("Note: -")
        for label in [self.info_customer, self.info_order_date, self.info_factory_out, self.info_status, self.info_note]:
            label.setObjectName("InfoLabel")
            label.setWordWrap(True)
        info.addWidget(self.info_customer, 0, 0)
        info.addWidget(self.info_order_date, 0, 1)
        info.addWidget(self.info_factory_out, 1, 0)
        info.addWidget(self.info_status, 1, 1)
        info.addWidget(self.info_note, 2, 0, 1, 2)
        header_layout.addLayout(top)
        header_layout.addLayout(info)
        layout.addWidget(header)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.detail_items_value = QLabel("0")
        self.detail_qty_value = QLabel("0")
        self.detail_first_value = QLabel("-")
        self.detail_factory_out_value = QLabel("-")
        stats.addWidget(self._metric_card(self.detail_items_value, "Items"))
        stats.addWidget(self._metric_card(self.detail_qty_value, "Total Quantity"))
        stats.addWidget(self._metric_card(self.detail_first_value, "First Item Date"))
        stats.addWidget(self._metric_card(self.detail_factory_out_value, "Factory Out Date"))
        layout.addLayout(stats)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)
        table_title = QLabel("Shipment Item Details")
        table_title.setObjectName("SectionTitle")
        table_hint = QLabel("Select a row before editing or deleting. Item Receive Date is saved in the database.")
        table_hint.setObjectName("Hint")
        self.detail_table = QTableWidget(0, 10)
        self.detail_table.setHorizontalHeaderLabels([
            "SAP Code", "Item Description", "Qty", "Stock Allocated", "Production Qty",
            "Cavities", "Production Days", "Item Receive Date", "Reason", "Item ID"
        ])
        self._setup_detail_table()
        table_layout.addWidget(table_title)
        table_layout.addWidget(table_hint)
        table_layout.addWidget(self.detail_table, 1)
        layout.addWidget(table_card, 1)

    def _card(self, name: str = "Card") -> QFrame:
        card = QFrame()
        card.setObjectName(name)
        return card

    def _metric_card(self, value_label: QLabel, label_text: str) -> QFrame:
        card = self._card("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        value_label.setObjectName("MetricValue")
        label = QLabel(label_text)
        label.setObjectName("MetricLabel")
        layout.addWidget(value_label)
        layout.addWidget(label)
        return card

    def _setup_list_table(self) -> None:
        self.list_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_table.setAlternatingRowColors(True)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.verticalHeader().setDefaultSectionSize(42)
        self.list_table.itemSelectionChanged.connect(self.on_list_selection_changed)
        self.list_table.itemDoubleClicked.connect(lambda *_: self.open_selected_shipment())
        header = self.list_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.list_table.setColumnWidth(0, 155)
        self.list_table.setColumnWidth(1, 150)
        self.list_table.setColumnWidth(2, 170)
        self.list_table.setColumnWidth(4, 80)
        self.list_table.setColumnWidth(5, 110)
        self.list_table.setColumnWidth(6, 115)

    def _setup_detail_table(self) -> None:
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.verticalHeader().setDefaultSectionSize(42)
        self.detail_table.itemSelectionChanged.connect(self.on_detail_selection_changed)
        self.detail_table.itemDoubleClicked.connect(lambda *_: self.edit_selected_item())
        header = self.detail_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.detail_table.setColumnWidth(0, 115)
        self.detail_table.setColumnWidth(2, 90)
        self.detail_table.setColumnWidth(3, 120)
        self.detail_table.setColumnWidth(4, 115)
        self.detail_table.setColumnWidth(5, 90)
        self.detail_table.setColumnWidth(6, 115)
        self.detail_table.setColumnWidth(7, 135)
        self.detail_table.setColumnHidden(9, True)

    def ensure_tables(self) -> None:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_shipments (
                    id SERIAL PRIMARY KEY,
                    shipment_no VARCHAR(100) NOT NULL UNIQUE,
                    customer_name VARCHAR(255) NOT NULL,
                    shipment_date DATE NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'Planned',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_shipment_items (
                    id SERIAL PRIMARY KEY,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    sap_code VARCHAR(100) NOT NULL,
                    item_description TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    start_date DATE,
                    end_date DATE,
                    item_status VARCHAR(50) NOT NULL DEFAULT 'Pending',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for sql in [
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS shipment_name VARCHAR(255) NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS manager_order_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_date DATE",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS stock_allocated_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_required_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS allocated_cavity_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_days INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS item_receive_date DATE",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS schedule_reason TEXT NOT NULL DEFAULT ''",
            ]:
                connection.execute(text(sql))
            connection.execute(text("""
                UPDATE mpps_shipments
                SET manager_order_date = COALESCE(manager_order_date, created_at::date, shipment_date, CURRENT_DATE)
                WHERE manager_order_date IS NULL
            """))
            connection.execute(text("""
                UPDATE mpps_shipment_items
                SET item_receive_date = COALESCE(item_receive_date, end_date, start_date)
                WHERE item_receive_date IS NULL
            """))
            self._recalculate_all_factory_out_dates(connection)

    def _recalculate_all_factory_out_dates(self, connection) -> None:
        connection.execute(text("""
            UPDATE mpps_shipments s
            SET factory_out_date = COALESCE(
                (SELECT MAX(COALESCE(i.item_receive_date, i.end_date, i.start_date)) FROM mpps_shipment_items i WHERE i.shipment_id = s.id),
                s.manager_order_date,
                s.shipment_date,
                CURRENT_DATE
            )
        """))

    def recalculate_shipment_factory_out_date(self, shipment_id: int) -> None:
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE mpps_shipments s
                SET factory_out_date = COALESCE(
                    (SELECT MAX(COALESCE(i.item_receive_date, i.end_date, i.start_date)) FROM mpps_shipment_items i WHERE i.shipment_id = s.id),
                    s.manager_order_date,
                    s.shipment_date,
                    CURRENT_DATE
                ),
                updated_at = CURRENT_TIMESTAMP
                WHERE s.id = :shipment_id
            """), {"shipment_id": shipment_id})

    def refresh_list(self) -> None:
        search = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        params = {"search": f"%{search}%"}
        where = ""
        if search:
            where = """
                WHERE s.shipment_no ILIKE :search
                   OR COALESCE(s.shipment_name, '') ILIKE :search
                   OR s.customer_name ILIKE :search
                   OR COALESCE(s.status, '') ILIKE :search
                   OR COALESCE(s.note, '') ILIKE :search
                   OR COALESCE(i.sap_code, '') ILIKE :search
                   OR COALESCE(i.item_description, '') ILIKE :search
            """
        with engine.begin() as connection:
            summary = connection.execute(text(f"""
                SELECT COUNT(DISTINCT s.id) AS shipments,
                       COUNT(i.id) AS items,
                       COALESCE(SUM(i.quantity), 0) AS qty,
                       MIN(s.factory_out_date) FILTER (WHERE s.factory_out_date >= CURRENT_DATE) AS next_date
                FROM mpps_shipments s
                LEFT JOIN mpps_shipment_items i ON i.shipment_id = s.id
                {where};
            """), params).mappings().first()
            rows = connection.execute(text(f"""
                SELECT s.id AS shipment_id,
                       s.shipment_no,
                       COALESCE(NULLIF(s.shipment_name, ''), s.shipment_no) AS shipment_name,
                       s.customer_name,
                       COALESCE(s.manager_order_date, s.created_at::date, s.shipment_date) AS manager_order_date,
                       COALESCE(s.factory_out_date, MAX(COALESCE(i.item_receive_date, i.end_date, i.start_date)), s.shipment_date) AS factory_out_date,
                       s.status AS shipment_status,
                       s.note AS shipment_note,
                       COUNT(i.id) AS item_count,
                       COALESCE(SUM(i.quantity), 0) AS total_qty
                FROM mpps_shipments s
                LEFT JOIN mpps_shipment_items i ON i.shipment_id = s.id
                {where}
                GROUP BY s.id, s.shipment_no, s.shipment_name, s.customer_name, s.manager_order_date,
                         s.created_at, s.shipment_date, s.factory_out_date, s.status, s.note
                ORDER BY factory_out_date ASC NULLS LAST, manager_order_date ASC NULLS LAST, s.id ASC;
            """), params).mappings().all()
        self.total_shipments_value.setText(self._format_int(summary["shipments"] if summary else 0))
        self.total_items_value.setText(self._format_int(summary["items"] if summary else 0))
        self.total_qty_value.setText(self._format_int(summary["qty"] if summary else 0))
        self.next_shipment_value.setText(self._fmt_date(summary["next_date"] if summary else None))
        self.list_table.setRowCount(0)
        self.selected_shipment_id = None
        for row_index, row in enumerate(rows):
            self.list_table.insertRow(row_index)
            values = [
                self._fmt_date(row["manager_order_date"]),
                self._fmt_date(row["factory_out_date"]),
                row["shipment_no"],
                row["customer_name"],
                self._format_int(row["item_count"]),
                self._format_int(row["total_qty"]),
                row["shipment_status"],
                row["shipment_note"] or "",
            ]
            for col, value in enumerate(values):
                item = self._readonly_item(str(value))
                if col in {0, 1, 4, 5, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 2:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["shipment_id"]))
                if col == 6:
                    self._style_status(item, str(value))
                self.list_table.setItem(row_index, col, item)
        self.list_table.resizeRowsToContents()

    def on_list_selection_changed(self) -> None:
        selected = self.list_table.selectedItems()
        if not selected:
            self.selected_shipment_id = None
            return
        row = selected[0].row()
        item = self.list_table.item(row, 2)
        self.selected_shipment_id = item.data(Qt.ItemDataRole.UserRole) if item else None

    def open_selected_shipment(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if self.selected_shipment_id:
            self.open_shipment_detail(int(self.selected_shipment_id))

    def open_shipment_detail(self, shipment_id: int) -> None:
        self.recalculate_shipment_factory_out_date(shipment_id)
        shipment = self.get_shipment(shipment_id)
        if not shipment:
            return
        self.current_shipment_id = shipment_id
        self.selected_item_id = None
        order_date = shipment.get("manager_order_date") or shipment.get("shipment_date")
        factory_out = shipment.get("factory_out_date") or shipment.get("shipment_date")
        self.detail_title.setText(f"Shipment {shipment['shipment_no']}")
        self.detail_subtitle.setText("Saved shipment with database-connected order date and factory-out date")
        self.info_customer.setText(f"Customer: {shipment['customer_name']}")
        self.info_order_date.setText(f"Order / Priority Date: {self._fmt_date(order_date)}")
        self.info_factory_out.setText(f"Factory Out Date: {self._fmt_date(factory_out)}")
        self.info_status.setText(f"Status: {shipment['status']}")
        self.info_note.setText(f"Note: {shipment['note'] or '-'}")
        with engine.begin() as connection:
            stats = connection.execute(text("""
                SELECT COUNT(id) AS items,
                       COALESCE(SUM(quantity), 0) AS qty,
                       MIN(COALESCE(item_receive_date, end_date, start_date)) AS first_item_date,
                       MAX(COALESCE(item_receive_date, end_date, start_date)) AS factory_out_date
                FROM mpps_shipment_items
                WHERE shipment_id = :shipment_id;
            """), {"shipment_id": shipment_id}).mappings().first()
            rows = connection.execute(text("""
                SELECT id, sap_code, item_description, quantity,
                       stock_allocated_qty, production_required_qty, allocated_cavity_count,
                       production_days,
                       COALESCE(item_receive_date, end_date, start_date) AS item_receive_date,
                       COALESCE(NULLIF(schedule_reason, ''), note, '') AS schedule_reason,
                       item_status
                FROM mpps_shipment_items
                WHERE shipment_id = :shipment_id
                ORDER BY item_receive_date ASC NULLS LAST, sap_code ASC, id ASC;
            """), {"shipment_id": shipment_id}).mappings().all()
        self.detail_items_value.setText(self._format_int(stats["items"] if stats else 0))
        self.detail_qty_value.setText(self._format_int(stats["qty"] if stats else 0))
        self.detail_first_value.setText(self._fmt_date(stats["first_item_date"] if stats else None))
        self.detail_factory_out_value.setText(self._fmt_date(factory_out or (stats["factory_out_date"] if stats else None)))
        self.detail_table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.detail_table.insertRow(row_index)
            values = [
                row["sap_code"],
                row["item_description"],
                self._format_int(row["quantity"]),
                self._format_int(row["stock_allocated_qty"]),
                self._format_int(row["production_required_qty"]),
                self._format_int(row["allocated_cavity_count"]),
                self._format_int(row["production_days"]),
                self._fmt_date(row["item_receive_date"]),
                row["schedule_reason"] or row["item_status"] or "",
                row["id"],
            ]
            for col, value in enumerate(values):
                item = self._readonly_item(str(value))
                if col in {0, 2, 3, 4, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 9:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.detail_table.setItem(row_index, col, item)
        self.detail_table.resizeRowsToContents()
        self.stack.setCurrentWidget(self.detail_page)

    def back_to_list(self) -> None:
        self.refresh_list()
        self.stack.setCurrentWidget(self.list_page)

    def on_detail_selection_changed(self) -> None:
        row = self.detail_table.currentRow()
        self.selected_item_id = None
        if row < 0:
            return
        item = self.detail_table.item(row, 9)
        if item is not None:
            self.selected_item_id = item.data(Qt.ItemDataRole.UserRole)

    def create_shipment(self) -> None:
        dialog = ShipmentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        if not data["shipment_no"]:
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment ID / name.")
            return
        if not data["customer_name"]:
            data["customer_name"] = data["shipment_no"]
        try:
            with engine.begin() as connection:
                shipment_id = connection.execute(text("""
                    INSERT INTO mpps_shipments
                        (shipment_no, shipment_name, customer_name, shipment_date, manager_order_date, factory_out_date, status, note, updated_at)
                    VALUES
                        (:shipment_no, :shipment_name, :customer_name, :shipment_date, :manager_order_date, :manager_order_date, :status, :note, CURRENT_TIMESTAMP)
                    RETURNING id;
                """), data).scalar_one()
            self.refresh_list()
            self.open_shipment_detail(int(shipment_id))
        except Exception as exc:
            QMessageBox.critical(self, "Create Failed", str(exc))

    def edit_selected_shipment(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if not self.selected_shipment_id:
            QMessageBox.information(self, "Select Shipment", "Please select a shipment row first.")
            return
        self._edit_shipment_header(int(self.selected_shipment_id))

    def edit_current_shipment_header(self) -> None:
        if self.current_shipment_id:
            self._edit_shipment_header(int(self.current_shipment_id))
            self.open_shipment_detail(int(self.current_shipment_id))

    def _edit_shipment_header(self, shipment_id: int) -> None:
        shipment = self.get_shipment(shipment_id)
        if not shipment:
            return
        dialog = ShipmentDialog(self, dict(shipment))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        data["id"] = shipment_id
        if not data["shipment_no"]:
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment ID / name.")
            return
        if not data["customer_name"]:
            data["customer_name"] = data["shipment_no"]
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    UPDATE mpps_shipments
                    SET shipment_no = :shipment_no,
                        shipment_name = :shipment_name,
                        customer_name = :customer_name,
                        shipment_date = :shipment_date,
                        manager_order_date = :manager_order_date,
                        status = :status,
                        note = :note,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id;
                """), data)
            self.recalculate_shipment_factory_out_date(shipment_id)
            self.refresh_list()
        except Exception as exc:
            QMessageBox.critical(self, "Edit Failed", str(exc))

    def move_selected_shipment_date(self, delta_days: int) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if not self.selected_shipment_id:
            QMessageBox.information(self, "Select Shipment", "Please select a shipment row first.")
            return
        shipment_id = int(self.selected_shipment_id)
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    UPDATE mpps_shipments
                    SET manager_order_date = COALESCE(manager_order_date, shipment_date, CURRENT_DATE) + (:delta_days * INTERVAL '1 day'),
                        shipment_date = COALESCE(manager_order_date, shipment_date, CURRENT_DATE) + (:delta_days * INTERVAL '1 day'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :shipment_id;
                """), {"shipment_id": shipment_id, "delta_days": delta_days})
            self.recalculate_shipment_factory_out_date(shipment_id)
            self.refresh_list()
        except Exception as exc:
            QMessageBox.critical(self, "Move Date Failed", str(exc))

    def add_item(self) -> None:
        if not self.current_shipment_id:
            return
        shipment = self.get_shipment(self.current_shipment_id)
        base_date = shipment["factory_out_date"] or shipment["manager_order_date"] or shipment["shipment_date"] if shipment else None
        dialog = ShipmentItemDialog(self, base_date=base_date)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        if not data["sap_code"] or not data["item_description"]:
            QMessageBox.warning(self, "Item Required", "Please select a valid approved item.")
            return
        data["shipment_id"] = self.current_shipment_id
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO mpps_shipment_items
                        (shipment_id, sap_code, item_description, quantity, start_date, end_date,
                         item_receive_date, item_status, note, schedule_reason, updated_at)
                    VALUES
                        (:shipment_id, :sap_code, :item_description, :quantity, :start_date, :end_date,
                         :item_receive_date, :item_status, :note, :schedule_reason, CURRENT_TIMESTAMP);
                """), data)
            self.recalculate_shipment_factory_out_date(int(self.current_shipment_id))
            self.open_shipment_detail(int(self.current_shipment_id))
        except Exception as exc:
            QMessageBox.critical(self, "Add Item Failed", str(exc))

    def edit_selected_item(self) -> None:
        if not self.selected_item_id:
            self.on_detail_selection_changed()
        if not self.selected_item_id:
            QMessageBox.information(self, "Select Item", "Please select an item row first.")
            return
        item = self.get_shipment_item(int(self.selected_item_id))
        if not item:
            return
        shipment = self.get_shipment(self.current_shipment_id)
        base_date = shipment["factory_out_date"] if shipment else None
        dialog = ShipmentItemDialog(self, base_date=base_date, item=dict(item))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        data["id"] = int(self.selected_item_id)
        if not data["sap_code"] or not data["item_description"]:
            QMessageBox.warning(self, "Item Required", "Please select a valid item.")
            return
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    UPDATE mpps_shipment_items
                    SET sap_code = :sap_code,
                        item_description = :item_description,
                        quantity = :quantity,
                        start_date = :start_date,
                        end_date = :end_date,
                        item_receive_date = :item_receive_date,
                        item_status = :item_status,
                        note = :note,
                        schedule_reason = :schedule_reason,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id;
                """), data)
            self.recalculate_shipment_factory_out_date(int(self.current_shipment_id))
            self.open_shipment_detail(int(self.current_shipment_id))
        except Exception as exc:
            QMessageBox.critical(self, "Edit Item Failed", str(exc))

    def delete_selected_item(self) -> None:
        if not self.selected_item_id:
            self.on_detail_selection_changed()
        if not self.selected_item_id:
            QMessageBox.information(self, "Select Item", "Please select an item row to delete.")
            return
        item_id = int(self.selected_item_id)
        answer = QMessageBox.question(
            self,
            "Delete Shipment Item",
            "Delete the selected shipment item from this order?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM mpps_shipment_items WHERE id = :id;"), {"id": item_id})
            if self.current_shipment_id:
                self.recalculate_shipment_factory_out_date(int(self.current_shipment_id))
                self.open_shipment_detail(int(self.current_shipment_id))
        except Exception as exc:
            QMessageBox.critical(self, "Delete Item Failed", str(exc))

    def get_shipment(self, shipment_id: int | None):
        if not shipment_id:
            return None
        with engine.begin() as connection:
            return connection.execute(text("SELECT * FROM mpps_shipments WHERE id = :id LIMIT 1;"), {"id": shipment_id}).mappings().first()

    def get_shipment_item(self, item_id: int | None):
        if not item_id:
            return None
        with engine.begin() as connection:
            return connection.execute(text("SELECT * FROM mpps_shipment_items WHERE id = :id LIMIT 1;"), {"id": item_id}).mappings().first()

    def _readonly_item(self, value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _style_status(self, item: QTableWidgetItem, status: str) -> None:
        font = QFont("Segoe UI")
        font.setBold(True)
        item.setFont(font)
        if status in {"Completed"}:
            item.setForeground(QColor("#047857"))
            item.setBackground(QColor("#dcfce7"))
        elif status in {"Cancelled", "On Hold"}:
            item.setForeground(QColor("#b45309"))
            item.setBackground(QColor("#fef3c7"))
        elif status in {"In Progress", "In Production"}:
            item.setForeground(QColor("#1d4ed8"))
            item.setBackground(QColor("#dbeafe"))
        else:
            item.setForeground(QColor("#334155"))

    def _fmt_date(self, value) -> str:
        if value is None:
            return "-"
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        text_value = str(value)
        if " " in text_value:
            return text_value.split(" ", 1)[0]
        return text_value

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"


class ShipmentDetailsPage(ShipmentOrdersPage):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user=current_user)
