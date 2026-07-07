from __future__ import annotations

from datetime import timedelta

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


class ShipmentDialog(QDialog):
    def __init__(self, parent=None, shipment: dict | None = None):
        super().__init__(parent)

        self.setWindowTitle("Shipment")
        self.setMinimumWidth(560)

        self.shipment_no_input = QLineEdit()
        self.shipment_no_input.setPlaceholderText("Shipment number / shipment name")

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer / destination")

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())

        self.status_input = QComboBox()
        self.status_input.addItems(["Planned", "In Progress", "Completed", "On Hold", "Cancelled"])

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Shipment note / remarks")
        self.note_input.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Shipment No"), 0, 0)
        form.addWidget(self.shipment_no_input, 1, 0)

        form.addWidget(QLabel("Customer"), 0, 1)
        form.addWidget(self.customer_input, 1, 1)

        form.addWidget(QLabel("Shipment Date"), 2, 0)
        form.addWidget(self.date_input, 3, 0)

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

            shipment_date = shipment.get("shipment_date")
            if hasattr(shipment_date, "year"):
                self.date_input.setDate(QDate(shipment_date.year, shipment_date.month, shipment_date.day))

            status = str(shipment.get("status") or "Planned")
            index = self.status_input.findText(status)
            if index >= 0:
                self.status_input.setCurrentIndex(index)

            self.note_input.setPlainText(str(shipment.get("note") or ""))

    def get_data(self) -> dict:
        return {
            "shipment_no": self.shipment_no_input.text().strip(),
            "customer_name": self.customer_input.text().strip(),
            "shipment_date": self.date_input.date().toPython(),
            "status": self.status_input.currentText(),
            "note": self.note_input.toPlainText().strip(),
        }


class ShipmentItemDialog(QDialog):
    def __init__(self, parent=None, shipment_date=None, item: dict | None = None):
        super().__init__(parent)

        self.setWindowTitle("Shipment Item")
        self.setMinimumWidth(680)

        self.master_items = self.load_master_items()

        self.sap_input = QComboBox()
        self.sap_input.setEditable(True)
        self.sap_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.sap_input.addItem("Select SAP item from master data", None)

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

        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)

        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)

        base_date = QDate.currentDate()
        if hasattr(shipment_date, "year"):
            base_date = QDate(shipment_date.year, shipment_date.month, shipment_date.day)

        self.start_date_input.setDate(base_date)
        self.end_date_input.setDate(base_date)

        self.status_input = QComboBox()
        self.status_input.addItems(["Pending", "In Production", "Completed", "On Hold", "Cancelled"])

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Item note")
        self.note_input.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("SAP Code / Master Item"), 0, 0, 1, 2)
        form.addWidget(self.sap_input, 1, 0, 1, 2)

        form.addWidget(QLabel("Description"), 2, 0, 1, 2)
        form.addWidget(self.description_input, 3, 0, 1, 2)

        form.addWidget(QLabel("Quantity"), 4, 0)
        form.addWidget(self.quantity_input, 5, 0)

        form.addWidget(QLabel("Status"), 4, 1)
        form.addWidget(self.status_input, 5, 1)

        form.addWidget(QLabel("Start Date"), 6, 0)
        form.addWidget(self.start_date_input, 7, 0)

        form.addWidget(QLabel("End Date"), 6, 1)
        form.addWidget(self.end_date_input, 7, 1)

        form.addWidget(QLabel("Note"), 8, 0, 1, 2)
        form.addWidget(self.note_input, 9, 0, 1, 2)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if item:
            self.populate_item(item)

    def load_master_items(self) -> list[dict]:
        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT sap_code, tyre_description
                        FROM mpps_sap_stock_items
                        WHERE is_active = TRUE
                        ORDER BY sap_code ASC;
                        """
                    )
                ).mappings().all()

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
        self.quantity_input.setValue(int(item.get("quantity") or 1))

        start_date = item.get("start_date")
        if hasattr(start_date, "year"):
            self.start_date_input.setDate(QDate(start_date.year, start_date.month, start_date.day))

        end_date = item.get("end_date")
        if hasattr(end_date, "year"):
            self.end_date_input.setDate(QDate(end_date.year, end_date.month, end_date.day))

        status = str(item.get("item_status") or "Pending")
        index = self.status_input.findText(status)
        if index >= 0:
            self.status_input.setCurrentIndex(index)

        self.note_input.setPlainText(str(item.get("note") or ""))

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

        return {
            "sap_code": sap_code,
            "item_description": description,
            "quantity": self.quantity_input.value(),
            "start_date": self.start_date_input.date().toPython(),
            "end_date": self.end_date_input.date().toPython(),
            "item_status": self.status_input.currentText(),
            "note": self.note_input.toPlainText().strip(),
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
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI";
            }

            QFrame#Card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 16pt;
                font-weight: 950;
            }

            QLabel#Hint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#MetricLabel {
                color: #64748b;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#InfoLabel {
                color: #334155;
                font-size: 10pt;
                font-weight: 750;
            }

            QLineEdit, QDateEdit, QComboBox, QTextEdit, QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 10pt;
                font-weight: 650;
                min-height: 24px;
            }

            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {
                border: 1px solid #2563eb;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QPushButton#DangerButton {
                background: #fee2e2;
                color: #991b1b;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#DangerButton:hover {
                background: #fecaca;
            }

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                alternate-background-color: #f8fafc;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 8px 10px;
                border: none;
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

    def _build_list_page(self) -> None:
        layout = QVBoxLayout(self.list_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = self._card()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(12)

        top = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Shipment Details")
        title.setObjectName("PageTitle")

        hint = QLabel("Review saved shipments, adjust shipment dates, and manage item-wise quantity/start/end dates.")
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

        self.move_back_btn = QPushButton("← Move Date -1")
        self.move_back_btn.setObjectName("SecondaryButton")
        self.move_back_btn.clicked.connect(lambda: self.move_selected_shipment_date(-1))

        self.move_forward_btn = QPushButton("Move Date +1 →")
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
        self.search_input.setPlaceholderText("Search shipment no, customer, status, note or SAP code...")
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
        stats.addWidget(self._metric_card(self.next_shipment_value, "Next Shipment"))

        layout.addLayout(stats)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("All Shipment Details")
        table_title.setObjectName("SectionTitle")

        table_hint = QLabel("Double-click a shipment row to open full shipment details. List is sorted by shipment date.")
        table_hint.setObjectName("Hint")

        self.list_table = QTableWidget(0, 8)
        self.list_table.setHorizontalHeaderLabels(
            ["Shipment Date", "Shipment No", "Customer", "Items", "Total Qty", "Status", "Note", "Created At"]
        )
        self._setup_list_table()

        table_layout.addWidget(table_title)
        table_layout.addWidget(table_hint)
        table_layout.addWidget(self.list_table, 1)

        layout.addWidget(table_card, 1)

    def _build_detail_page(self) -> None:
        layout = QVBoxLayout(self.detail_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = self._card()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(12)

        top = QHBoxLayout()

        title_box = QVBoxLayout()
        self.detail_title = QLabel("Shipment")
        self.detail_title.setObjectName("PageTitle")

        self.detail_subtitle = QLabel("Full shipment detail")
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
        self.info_date = QLabel("Shipment Date: -")
        self.info_status = QLabel("Status: -")
        self.info_note = QLabel("Note: -")

        for label in [self.info_customer, self.info_date, self.info_status, self.info_note]:
            label.setObjectName("InfoLabel")
            label.setWordWrap(True)

        info.addWidget(self.info_customer, 0, 0)
        info.addWidget(self.info_date, 0, 1)
        info.addWidget(self.info_status, 1, 0)
        info.addWidget(self.info_note, 1, 1)

        header_layout.addLayout(top)
        header_layout.addLayout(info)

        layout.addWidget(header)

        stats = QHBoxLayout()
        stats.setSpacing(12)

        self.detail_items_value = QLabel("0")
        self.detail_qty_value = QLabel("0")
        self.detail_start_value = QLabel("-")
        self.detail_end_value = QLabel("-")

        stats.addWidget(self._metric_card(self.detail_items_value, "Items"))
        stats.addWidget(self._metric_card(self.detail_qty_value, "Total Quantity"))
        stats.addWidget(self._metric_card(self.detail_start_value, "Earliest Start"))
        stats.addWidget(self._metric_card(self.detail_end_value, "Latest End"))

        layout.addLayout(stats)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Shipment Item Details")
        table_title.setObjectName("SectionTitle")

        table_hint = QLabel("Double-click an item row to edit quantity, start date, end date, status and note.")
        table_hint.setObjectName("Hint")

        self.detail_table = QTableWidget(0, 8)
        self.detail_table.setHorizontalHeaderLabels(
            ["SAP Code", "Item Description", "Quantity", "Start Date", "End Date", "Status", "Note", "Item ID"]
        )
        self._setup_detail_table()

        table_layout.addWidget(table_title)
        table_layout.addWidget(table_hint)
        table_layout.addWidget(self.detail_table, 1)

        layout.addWidget(table_card, 1)

    def _card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def _metric_card(self, value_label: QLabel, label_text: str) -> QFrame:
        card = self._card()
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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.list_table.setColumnWidth(0, 130)
        self.list_table.setColumnWidth(1, 150)
        self.list_table.setColumnWidth(3, 80)
        self.list_table.setColumnWidth(4, 110)
        self.list_table.setColumnWidth(5, 120)
        self.list_table.setColumnWidth(7, 145)

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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.detail_table.setColumnWidth(0, 120)
        self.detail_table.setColumnWidth(2, 100)
        self.detail_table.setColumnWidth(3, 120)
        self.detail_table.setColumnWidth(4, 120)
        self.detail_table.setColumnWidth(5, 130)
        self.detail_table.setColumnHidden(7, True)

    def ensure_tables(self) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS mpps_shipments (
                        id SERIAL PRIMARY KEY,
                        shipment_no VARCHAR(100) NOT NULL UNIQUE,
                        customer_name VARCHAR(255) NOT NULL,
                        shipment_date DATE NOT NULL,
                        status VARCHAR(50) NOT NULL DEFAULT 'Planned',
                        note TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )

            connection.execute(
                text(
                    """
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
                    );
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS mpps_shipment_entry_details (
                        id SERIAL PRIMARY KEY,
                        shipment_id INTEGER NOT NULL,
                        shipment_item_id INTEGER,
                        shipment_no VARCHAR(100) NOT NULL,
                        customer_name VARCHAR(255) NOT NULL,
                        shipment_date DATE NOT NULL,
                        actual_receive_date DATE,
                        shipment_status VARCHAR(50),
                        shipment_note TEXT,
                        sap_code VARCHAR(100),
                        item_description TEXT,
                        quantity INTEGER NOT NULL DEFAULT 0,
                        item_start_date DATE,
                        item_end_date DATE,
                        item_status VARCHAR(50),
                        item_note TEXT,
                        source_table VARCHAR(100) NOT NULL DEFAULT 'shipment_entry',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )

    def sync_entry_details(self, shipment_id: int | None = None) -> None:
        with engine.begin() as connection:
            if shipment_id is None:
                connection.execute(text("DELETE FROM mpps_shipment_entry_details;"))
                params = {}
                where = ""
            else:
                connection.execute(
                    text("DELETE FROM mpps_shipment_entry_details WHERE shipment_id = :shipment_id;"),
                    {"shipment_id": shipment_id},
                )
                params = {"shipment_id": shipment_id}
                where = "WHERE s.id = :shipment_id"

            connection.execute(
                text(
                    f"""
                    INSERT INTO mpps_shipment_entry_details (
                        shipment_id,
                        shipment_item_id,
                        shipment_no,
                        customer_name,
                        shipment_date,
                        actual_receive_date,
                        shipment_status,
                        shipment_note,
                        sap_code,
                        item_description,
                        quantity,
                        item_start_date,
                        item_end_date,
                        item_status,
                        item_note,
                        source_table,
                        created_at,
                        updated_at
                    )
                    SELECT
                        s.id,
                        i.id,
                        s.shipment_no,
                        s.customer_name,
                        s.shipment_date,
                        NULL,
                        s.status,
                        s.note,
                        i.sap_code,
                        i.item_description,
                        i.quantity,
                        i.start_date,
                        i.end_date,
                        i.item_status,
                        i.note,
                        'mpps_shipments + mpps_shipment_items',
                        s.created_at,
                        CURRENT_TIMESTAMP
                    FROM mpps_shipments s
                    JOIN mpps_shipment_items i
                        ON i.shipment_id = s.id
                    {where};
                    """
                ),
                params,
            )

            connection.execute(
                text(
                    f"""
                    INSERT INTO mpps_shipment_entry_details (
                        shipment_id,
                        shipment_item_id,
                        shipment_no,
                        customer_name,
                        shipment_date,
                        actual_receive_date,
                        shipment_status,
                        shipment_note,
                        sap_code,
                        item_description,
                        quantity,
                        item_start_date,
                        item_end_date,
                        item_status,
                        item_note,
                        source_table,
                        created_at,
                        updated_at
                    )
                    SELECT
                        s.id,
                        NULL,
                        s.shipment_no,
                        s.customer_name,
                        s.shipment_date,
                        NULL,
                        s.status,
                        s.note,
                        NULL,
                        NULL,
                        0,
                        NULL,
                        NULL,
                        NULL,
                        NULL,
                        'mpps_shipments',
                        s.created_at,
                        CURRENT_TIMESTAMP
                    FROM mpps_shipments s
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM mpps_shipment_items i
                        WHERE i.shipment_id = s.id
                    )
                    {"AND s.id = :shipment_id" if shipment_id is not None else ""};
                    """
                ),
                params,
            )

    def refresh_list(self) -> None:
        self.sync_entry_details()

        search = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        params = {"search": f"%{search}%"}
        where = ""

        if search:
            where = """
                WHERE shipment_no ILIKE :search
                   OR customer_name ILIKE :search
                   OR COALESCE(shipment_status, '') ILIKE :search
                   OR COALESCE(shipment_note, '') ILIKE :search
                   OR COALESCE(sap_code, '') ILIKE :search
                   OR COALESCE(item_description, '') ILIKE :search
            """

        with engine.begin() as connection:
            summary = connection.execute(
                text(
                    f"""
                    SELECT
                        COUNT(DISTINCT shipment_id) AS shipments,
                        COUNT(shipment_item_id) AS items,
                        COALESCE(SUM(quantity), 0) AS qty,
                        MIN(shipment_date) FILTER (WHERE shipment_date >= CURRENT_DATE) AS next_date
                    FROM mpps_shipment_entry_details
                    {where};
                    """
                ),
                params,
            ).mappings().first()

            rows = connection.execute(
                text(
                    f"""
                    SELECT
                        shipment_id,
                        shipment_no,
                        customer_name,
                        shipment_date,
                        shipment_status,
                        shipment_note,
                        COUNT(shipment_item_id) AS item_count,
                        COALESCE(SUM(quantity), 0) AS total_qty,
                        MIN(created_at) AS created_at
                    FROM mpps_shipment_entry_details
                    {where}
                    GROUP BY
                        shipment_id,
                        shipment_no,
                        customer_name,
                        shipment_date,
                        shipment_status,
                        shipment_note
                    ORDER BY shipment_date ASC, shipment_id ASC;
                    """
                ),
                params,
            ).mappings().all()

        self.total_shipments_value.setText(self._format_int(summary["shipments"] if summary else 0))
        self.total_items_value.setText(self._format_int(summary["items"] if summary else 0))
        self.total_qty_value.setText(self._format_int(summary["qty"] if summary else 0))
        self.next_shipment_value.setText(self._fmt_date(summary["next_date"] if summary else None))

        self.list_table.setRowCount(0)
        self.selected_shipment_id = None

        for row_index, row in enumerate(rows):
            self.list_table.insertRow(row_index)

            values = [
                self._fmt_date(row["shipment_date"]),
                row["shipment_no"],
                row["customer_name"],
                self._format_int(row["item_count"]),
                self._format_int(row["total_qty"]),
                row["shipment_status"],
                row["shipment_note"] or "",
                self._fmt_datetime(row["created_at"]),
            ]

            for col, value in enumerate(values):
                item = self._readonly_item(str(value))

                if col in {0, 3, 4, 5, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 1:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["shipment_id"]))

                if col == 5:
                    self._style_status(item, str(value))

                self.list_table.setItem(row_index, col, item)

        self.list_table.resizeRowsToContents()

    def on_list_selection_changed(self) -> None:
        selected = self.list_table.selectedItems()
        if not selected:
            self.selected_shipment_id = None
            return

        row = selected[0].row()
        item = self.list_table.item(row, 1)
        self.selected_shipment_id = item.data(Qt.ItemDataRole.UserRole) if item else None

    def open_selected_shipment(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()

        if self.selected_shipment_id:
            self.open_shipment_detail(int(self.selected_shipment_id))

    def open_shipment_detail(self, shipment_id: int) -> None:
        self.sync_entry_details(shipment_id)
        shipment = self.get_shipment(shipment_id)

        if not shipment:
            return

        self.current_shipment_id = shipment_id
        self.selected_item_id = None

        self.detail_title.setText(f"Shipment {shipment['shipment_no']}")
        self.detail_subtitle.setText("Full shipment details and item-level planning dates")
        self.info_customer.setText(f"Customer: {shipment['customer_name']}")
        self.info_date.setText(f"Shipment Date: {self._fmt_date(shipment['shipment_date'])}")
        self.info_status.setText(f"Status: {shipment['status']}")
        self.info_note.setText(f"Note: {shipment['note'] or '-'}")

        with engine.begin() as connection:
            stats = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(shipment_item_id) AS items,
                        COALESCE(SUM(quantity), 0) AS qty,
                        MIN(item_start_date) AS start_date,
                        MAX(item_end_date) AS end_date
                    FROM mpps_shipment_entry_details
                    WHERE shipment_id = :shipment_id
                      AND shipment_item_id IS NOT NULL;
                    """
                ),
                {"shipment_id": shipment_id},
            ).mappings().first()

            rows = connection.execute(
                text(
                    """
                    SELECT
                        shipment_item_id AS id,
                        sap_code,
                        item_description,
                        quantity,
                        item_start_date AS start_date,
                        item_end_date AS end_date,
                        item_status,
                        item_note AS note
                    FROM mpps_shipment_entry_details
                    WHERE shipment_id = :shipment_id
                      AND shipment_item_id IS NOT NULL
                    ORDER BY item_start_date ASC NULLS LAST, item_end_date ASC NULLS LAST, sap_code ASC;
                    """
                ),
                {"shipment_id": shipment_id},
            ).mappings().all()

        self.detail_items_value.setText(self._format_int(stats["items"] if stats else 0))
        self.detail_qty_value.setText(self._format_int(stats["qty"] if stats else 0))
        self.detail_start_value.setText(self._fmt_date(stats["start_date"] if stats else None))
        self.detail_end_value.setText(self._fmt_date(stats["end_date"] if stats else None))

        self.detail_table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.detail_table.insertRow(row_index)

            values = [
                row["sap_code"],
                row["item_description"],
                self._format_int(row["quantity"]),
                self._fmt_date(row["start_date"]),
                self._fmt_date(row["end_date"]),
                row["item_status"],
                row["note"] or "",
                row["id"],
            ]

            for col, value in enumerate(values):
                item = self._readonly_item(str(value))

                if col in {0, 2, 3, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 7:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                if col == 5:
                    self._style_status(item, str(value))

                self.detail_table.setItem(row_index, col, item)

        self.detail_table.resizeRowsToContents()
        self.stack.setCurrentWidget(self.detail_page)

    def back_to_list(self) -> None:
        self.refresh_list()
        self.stack.setCurrentWidget(self.list_page)

    def on_detail_selection_changed(self) -> None:
        selected = self.detail_table.selectedItems()
        if not selected:
            self.selected_item_id = None
            return

        row = selected[0].row()
        item = self.detail_table.item(row, 7)
        self.selected_item_id = item.data(Qt.ItemDataRole.UserRole) if item else None

    def create_shipment(self) -> None:
        dialog = ShipmentDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()

        if not data["shipment_no"]:
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment number.")
            return

        if not data["customer_name"]:
            data["customer_name"] = data["shipment_no"]

        try:
            with engine.begin() as connection:
                shipment_id = connection.execute(
                    text(
                        """
                        INSERT INTO mpps_shipments
                            (shipment_no, customer_name, shipment_date, status, note, updated_at)
                        VALUES
                            (:shipment_no, :customer_name, :shipment_date, :status, :note, CURRENT_TIMESTAMP)
                        RETURNING id;
                        """
                    ),
                    data,
                ).scalar_one()

            self.sync_entry_details(int(shipment_id))
            self.refresh_list()
            self.open_shipment_detail(int(shipment_id))

        except Exception as exc:
            QMessageBox.critical(self, "Create Failed", str(exc))

    def edit_selected_shipment(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()

        if not self.selected_shipment_id:
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
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment number.")
            return

        if not data["customer_name"]:
            data["customer_name"] = data["shipment_no"]

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            shipment_no = :shipment_no,
                            customer_name = :customer_name,
                            shipment_date = :shipment_date,
                            status = :status,
                            note = :note,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    data,
                )

            self.sync_entry_details(shipment_id)
            self.refresh_list()

        except Exception as exc:
            QMessageBox.critical(self, "Edit Failed", str(exc))

    def move_selected_shipment_date(self, delta_days: int) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()

        if not self.selected_shipment_id:
            return

        shipment_id = int(self.selected_shipment_id)

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            shipment_date = shipment_date + (:delta_days * INTERVAL '1 day'),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :shipment_id;
                        """
                    ),
                    {"shipment_id": shipment_id, "delta_days": delta_days},
                )

            self.sync_entry_details(shipment_id)
            self.refresh_list()

        except Exception as exc:
            QMessageBox.critical(self, "Move Date Failed", str(exc))

    def add_item(self) -> None:
        if not self.current_shipment_id:
            return

        shipment = self.get_shipment(self.current_shipment_id)
        dialog = ShipmentItemDialog(self, shipment_date=shipment["shipment_date"] if shipment else None)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()

        if not data["sap_code"] or not data["item_description"]:
            QMessageBox.warning(self, "Item Required", "Please select a valid SAP item.")
            return

        data["shipment_id"] = self.current_shipment_id

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_shipment_items
                            (
                                shipment_id,
                                sap_code,
                                item_description,
                                quantity,
                                start_date,
                                end_date,
                                item_status,
                                note,
                                updated_at
                            )
                        VALUES
                            (
                                :shipment_id,
                                :sap_code,
                                :item_description,
                                :quantity,
                                :start_date,
                                :end_date,
                                :item_status,
                                :note,
                                CURRENT_TIMESTAMP
                            );
                        """
                    ),
                    data,
                )

            self.open_shipment_detail(int(self.current_shipment_id))

        except Exception as exc:
            QMessageBox.critical(self, "Add Item Failed", str(exc))

    def edit_selected_item(self) -> None:
        if not self.selected_item_id:
            self.on_detail_selection_changed()

        if not self.selected_item_id:
            return

        item = self.get_shipment_item(int(self.selected_item_id))
        shipment = self.get_shipment(self.current_shipment_id)

        if not item:
            return

        dialog = ShipmentItemDialog(
            self,
            shipment_date=shipment["shipment_date"] if shipment else None,
            item=dict(item),
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        data["id"] = int(self.selected_item_id)

        if not data["sap_code"] or not data["item_description"]:
            QMessageBox.warning(self, "Item Required", "Please select a valid SAP item.")
            return

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipment_items
                        SET
                            sap_code = :sap_code,
                            item_description = :item_description,
                            quantity = :quantity,
                            start_date = :start_date,
                            end_date = :end_date,
                            item_status = :item_status,
                            note = :note,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    data,
                )

            self.open_shipment_detail(int(self.current_shipment_id))

        except Exception as exc:
            QMessageBox.critical(self, "Edit Item Failed", str(exc))

    def delete_selected_item(self) -> None:
        if not self.selected_item_id:
            self.on_detail_selection_changed()

        if not self.selected_item_id:
            return

        answer = QMessageBox.question(
            self,
            "Delete Shipment Item",
            "Are you sure you want to delete the selected shipment item?",
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM mpps_shipment_items WHERE id = :id;"),
                    {"id": int(self.selected_item_id)},
                )

            self.open_shipment_detail(int(self.current_shipment_id))

        except Exception as exc:
            QMessageBox.critical(self, "Delete Item Failed", str(exc))

    def get_shipment(self, shipment_id: int | None):
        if not shipment_id:
            return None

        with engine.begin() as connection:
            return connection.execute(
                text("SELECT * FROM mpps_shipments WHERE id = :id LIMIT 1;"),
                {"id": shipment_id},
            ).mappings().first()

    def get_shipment_item(self, item_id: int | None):
        if not item_id:
            return None

        with engine.begin() as connection:
            return connection.execute(
                text("SELECT * FROM mpps_shipment_items WHERE id = :id LIMIT 1;"),
                {"id": item_id},
            ).mappings().first()

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

        return str(value)

    def _fmt_datetime(self, value) -> str:
        if value is None:
            return "-"

        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M")

        return str(value)

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"


class ShipmentDetailsPage(ShipmentOrdersPage):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user=current_user)
