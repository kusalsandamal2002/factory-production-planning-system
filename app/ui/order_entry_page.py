from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine
from app.services.shipment_entry_sync_service import ensure_shipment_entry_detail_table


class OrderEntryPage(QWidget):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()

        self.current_user = current_user
        self.current_items: list[dict] = []
        self.master_items: list[dict] = []
        self.current_shipment_id: int | None = None

        self.shipment_name_input = QLineEdit()
        self.shipment_name_input.setPlaceholderText("Type shipment name / shipment no")
        self.shipment_name_input.textChanged.connect(self.load_previous_shipments)

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer / destination / note")

        self.plan_date_input = QDateEdit()
        self.plan_date_input.setCalendarPopup(True)
        self.plan_date_input.setDate(QDate.currentDate().addDays(7))
        self.plan_date_input.dateChanged.connect(self.recalculate_actual_date)

        self.actual_date_input = QLineEdit()
        self.actual_date_input.setReadOnly(True)
        self.actual_date_input.setText("Pending")

        self.remarks_input = QTextEdit()
        self.remarks_input.setPlaceholderText("Remarks / special instructions")
        self.remarks_input.setMinimumHeight(72)

        self.item_search_input = QLineEdit()
        self.item_search_input.setPlaceholderText("Search SAP code or tyre description from master data...")
        self.item_search_input.textChanged.connect(self.update_item_preview)

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 999999999)
        self.quantity_input.setValue(1)

        self.add_item_btn = QPushButton("Add Item")
        self.add_item_btn.setObjectName("PrimaryButton")
        self.add_item_btn.clicked.connect(self.add_item)

        self.save_btn = QPushButton("Save Shipment")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_shipment)

        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setObjectName("SecondaryButton")
        self.clear_btn.clicked.connect(self.clear_form)

        self.refresh_btn = QPushButton("Refresh Master Data")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_master_items)

        self.preview_code_label = QLabel("No item selected.")
        self.preview_desc_label = QLabel("Search SAP code or tyre description to preview item details.")
        self.preview_available_label = QLabel("")

        self.items_table = QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(["SAP Code", "Description", "Qty", "Action"])

        self.previous_table = QTableWidget(0, 4)
        self.previous_table.setHorizontalHeaderLabels(["Shipment No", "Date", "Items", "Status"])

        self.summary_items_value = QLabel("0")
        self.summary_qty_value = QLabel("0")
        self.summary_shipment_label = QLabel("Shipment: -")
        self.summary_plan_date_label = QLabel("Plan To Receive Date: -")
        self.summary_actual_date_label = QLabel("Shipment Can Receive Actual Date: Pending")

        self._apply_styles()
        self._build_ui()
        self._setup_tables()

        self.ensure_tables()
        ensure_shipment_entry_detail_table()
        self.refresh_master_items()
        self.load_previous_shipments()
        self.recalculate_actual_date()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI";
            }

            QFrame#HeaderCard,
            QFrame#FormCard,
            QFrame#TableCard,
            QFrame#SummaryCard,
            QFrame#PreviewCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#PageHint,
            QLabel#Hint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 17pt;
                font-weight: 950;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#PreviewTitle {
                color: #0f172a;
                font-size: 11pt;
                font-weight: 950;
            }

            QLabel#PreviewText {
                color: #475569;
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

            QLineEdit, QDateEdit, QTextEdit, QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 10pt;
                font-weight: 650;
                min-height: 24px;
            }

            QLineEdit:focus, QDateEdit:focus, QTextEdit:focus, QSpinBox:focus {
                border: 1px solid #2563eb;
            }

            QLineEdit:read-only {
                background: #f8fafc;
                color: #1d4ed8;
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
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 950;
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

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._header_card())
        root.addWidget(self._shipment_form_card())

        middle = QHBoxLayout()
        middle.setSpacing(16)
        middle.addWidget(self._add_item_card(), 2)
        middle.addWidget(self._previous_shipments_card(), 1)
        root.addLayout(middle)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(self._items_card(), 2)
        bottom.addWidget(self._summary_card(), 1)
        root.addLayout(bottom, 1)

    def _header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(5)

        title = QLabel("Shipment Entry")
        title.setObjectName("PageTitle")

        hint = QLabel(
            "Enter shipment details and add tyre items directly from Master Data / SAP Stock Master. No dummy tyre data is used."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        layout.addLayout(title_box, 1)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.clear_btn)
        layout.addWidget(self.save_btn)

        return card

    def _shipment_form_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("FormCard")

        layout = QGridLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(12)

        self._add_field(layout, 0, 0, "Shipment Name", self.shipment_name_input)
        self._add_field(layout, 0, 1, "Customer / Destination", self.customer_input)
        self._add_field(layout, 0, 2, "Plan To Receive Date", self.plan_date_input)
        self._add_field(layout, 0, 3, "Shipment Can Receive Actual Date", self.actual_date_input)

        remarks_label = QLabel("Remarks")
        remarks_label.setObjectName("FieldLabel")
        layout.addWidget(remarks_label, 2, 0)
        layout.addWidget(self.remarks_input, 3, 0, 1, 4)

        for col in range(4):
            layout.setColumnStretch(col, 1)

        return card

    def _add_item_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("FormCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Add Shipment Item")
        title.setObjectName("SectionTitle")

        hint = QLabel("Items are loaded from Master Data. Search using SAP code or tyre description.")
        hint.setObjectName("Hint")

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        item_label = QLabel("Item Code / Description")
        item_label.setObjectName("FieldLabel")

        qty_label = QLabel("Quantity")
        qty_label.setObjectName("FieldLabel")

        form.addWidget(item_label, 0, 0)
        form.addWidget(qty_label, 0, 1)
        form.addWidget(self.item_search_input, 1, 0)
        form.addWidget(self.quantity_input, 1, 1)
        form.addWidget(self.add_item_btn, 1, 2)

        form.setColumnStretch(0, 1)

        layout.addLayout(form)
        layout.addWidget(self._preview_card())

        return card

    def _preview_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PreviewCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        title = QLabel("Selected Item Preview")
        title.setObjectName("PreviewTitle")

        self.preview_code_label.setObjectName("PreviewText")
        self.preview_desc_label.setObjectName("PreviewText")
        self.preview_available_label.setObjectName("PreviewText")

        layout.addWidget(title)
        layout.addWidget(self.preview_code_label)
        layout.addWidget(self.preview_desc_label)
        layout.addWidget(self.preview_available_label)

        return card

    def _previous_shipments_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Previous Shipments")
        title.setObjectName("SectionTitle")

        hint = QLabel("Saved shipments from database. Double-click to load the shipment into this entry form.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.previous_table, 1)

        return card

    def _items_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Shipment Items")
        title.setObjectName("SectionTitle")

        hint = QLabel("Items selected for this shipment. Remove and re-add if you need to correct an item before saving.")
        hint.setObjectName("Hint")

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.items_table, 1)

        return card

    def _summary_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("SummaryCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(16)

        title = QLabel("Shipment Summary")
        title.setObjectName("SectionTitle")

        self.summary_shipment_label.setObjectName("Hint")

        metrics = QHBoxLayout()
        metrics.setSpacing(12)

        metrics.addWidget(self._metric_box(self.summary_items_value, "Total Items"))
        metrics.addWidget(self._metric_box(self.summary_qty_value, "Total Qty"))

        result_title = QLabel("Calculated Planning Result")
        result_title.setObjectName("SectionTitle")

        self.summary_plan_date_label.setObjectName("Hint")
        self.summary_actual_date_label.setObjectName("Hint")

        layout.addWidget(title)
        layout.addWidget(self.summary_shipment_label)
        layout.addLayout(metrics)
        layout.addWidget(result_title)
        layout.addWidget(self.summary_plan_date_label)
        layout.addWidget(self.summary_actual_date_label)
        layout.addStretch()

        return card

    def _metric_box(self, value_label: QLabel, label_text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("PreviewCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)

        value_label.setObjectName("MetricValue")

        label = QLabel(label_text)
        label.setObjectName("MetricLabel")

        layout.addWidget(value_label)
        layout.addWidget(label)

        return card

    def _add_field(self, grid: QGridLayout, row: int, col: int, label_text: str, widget: QWidget) -> None:
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        grid.addWidget(label, row * 2, col)
        grid.addWidget(widget, row * 2 + 1, col)

    def _setup_tables(self) -> None:
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.verticalHeader().setDefaultSectionSize(44)
        self.items_table.setAlternatingRowColors(True)

        items_header = self.items_table.horizontalHeader()
        items_header.setSectionResizeMode(0, items_header.ResizeMode.Fixed)
        items_header.setSectionResizeMode(1, items_header.ResizeMode.Stretch)
        items_header.setSectionResizeMode(2, items_header.ResizeMode.Fixed)
        items_header.setSectionResizeMode(3, items_header.ResizeMode.Fixed)

        self.items_table.setColumnWidth(0, 150)
        self.items_table.setColumnWidth(2, 110)
        self.items_table.setColumnWidth(3, 130)

        self.previous_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.previous_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.previous_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.previous_table.verticalHeader().setVisible(False)
        self.previous_table.verticalHeader().setDefaultSectionSize(40)
        self.previous_table.setAlternatingRowColors(True)
        self.previous_table.itemDoubleClicked.connect(lambda *_: self.load_selected_previous_shipment())

        previous_header = self.previous_table.horizontalHeader()
        previous_header.setSectionResizeMode(0, previous_header.ResizeMode.Stretch)
        previous_header.setSectionResizeMode(1, previous_header.ResizeMode.Fixed)
        previous_header.setSectionResizeMode(2, previous_header.ResizeMode.Fixed)
        previous_header.setSectionResizeMode(3, previous_header.ResizeMode.Fixed)

        self.previous_table.setColumnWidth(1, 105)
        self.previous_table.setColumnWidth(2, 70)
        self.previous_table.setColumnWidth(3, 100)

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

    def refresh_master_items(self) -> None:
        self.master_items = self.load_master_items()

        completer_values = [
            f"{item['sap_code']} - {item['tyre_description']}"
            for item in self.master_items
        ]

        completer = QCompleter(completer_values)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item_search_input.setCompleter(completer)

        if not self.master_items:
            QMessageBox.warning(
                self,
                "Master Data Missing",
                "No tyre items were found in mpps_sap_stock_items.\n\n"
                "Open Master Data > Stock Master > Final Tyre Stock and sync tyres from master first.",
            )

    def load_master_items(self) -> list[dict]:
        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                            sap_code,
                            tyre_description,
                            fg_stock,
                            qc_stock,
                            scrap_stock,
                            blocked_stock,
                            (fg_stock + qc_stock - scrap_stock - blocked_stock) AS available_stock
                        FROM mpps_sap_stock_items
                        WHERE is_active = TRUE
                        ORDER BY sap_code ASC;
                        """
                    )
                ).mappings().all()

            return [dict(row) for row in rows]

        except Exception:
            return []

    def update_item_preview(self) -> None:
        item = self.find_master_item(self.item_search_input.text().strip())

        if not item:
            self.preview_code_label.setText("No item selected.")
            self.preview_desc_label.setText("Search SAP code or tyre description to preview item details.")
            self.preview_available_label.setText("")
            return

        self.preview_code_label.setText(f"SAP Code: {item['sap_code']}")
        self.preview_desc_label.setText(f"Description: {item['tyre_description']}")
        self.preview_available_label.setText(f"Available Stock: {self._format_int(item.get('available_stock'))}")

    def find_master_item(self, value: str) -> dict | None:
        if not value:
            return None

        search = value.strip().lower()
        sap_from_combo = value.split(" - ", 1)[0].strip().lower()

        for item in self.master_items:
            sap_code = str(item["sap_code"]).lower()
            desc = str(item["tyre_description"]).lower()

            if sap_code == sap_from_combo or sap_code == search:
                return item

        for item in self.master_items:
            sap_code = str(item["sap_code"]).lower()
            desc = str(item["tyre_description"]).lower()

            if search in sap_code or search in desc:
                return item

        return None

    def add_item(self) -> None:
        item = self.find_master_item(self.item_search_input.text().strip())

        if not item:
            QMessageBox.warning(self, "Item Not Found", "Please select a valid SAP tyre item from master data.")
            self.item_search_input.setFocus()
            return

        qty = self.quantity_input.value()
        sap_code = str(item["sap_code"])

        for existing in self.current_items:
            if existing["sap_code"] == sap_code:
                existing["quantity"] += qty
                self.refresh_items_table()
                self.recalculate_actual_date()
                self.item_search_input.clear()
                self.quantity_input.setValue(1)
                return

        self.current_items.append(
            {
                "sap_code": sap_code,
                "item_description": str(item["tyre_description"]),
                "quantity": qty,
            }
        )

        self.refresh_items_table()
        self.recalculate_actual_date()
        self.item_search_input.clear()
        self.quantity_input.setValue(1)

    def refresh_items_table(self) -> None:
        self.items_table.setRowCount(0)

        for row_index, item in enumerate(self.current_items):
            self.items_table.insertRow(row_index)

            values = [
                item["sap_code"],
                item["item_description"],
                self._format_int(item["quantity"]),
            ]

            for col, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

                if col in {0, 2}:
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 2:
                    font = QFont("Segoe UI")
                    font.setBold(True)
                    table_item.setFont(font)

                self.items_table.setItem(row_index, col, table_item)

            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("DangerButton")
            remove_btn.clicked.connect(lambda checked=False, code=item["sap_code"]: self.remove_item(code))
            self.items_table.setCellWidget(row_index, 3, remove_btn)

        self.items_table.resizeRowsToContents()
        self.update_summary()

    def remove_item(self, sap_code: str) -> None:
        self.current_items = [item for item in self.current_items if item["sap_code"] != sap_code]
        self.refresh_items_table()
        self.recalculate_actual_date()

    def recalculate_actual_date(self) -> None:
        if not self.current_items:
            self.actual_date_input.setText("Pending")
        else:
            self.actual_date_input.setText(self.plan_date_input.date().toString("yyyy-MM-dd"))

        self.update_summary()

    def update_summary(self) -> None:
        shipment_name = self.shipment_name_input.text().strip() or "-"
        total_items = len(self.current_items)
        total_qty = sum(int(item["quantity"] or 0) for item in self.current_items)

        self.summary_shipment_label.setText(f"Shipment: {shipment_name}")
        self.summary_items_value.setText(self._format_int(total_items))
        self.summary_qty_value.setText(self._format_int(total_qty))
        self.summary_plan_date_label.setText(f"Plan To Receive Date: {self.plan_date_input.date().toString('yyyy-MM-dd')}")
        self.summary_actual_date_label.setText(f"Shipment Can Receive Actual Date: {self.actual_date_input.text()}")

    def load_previous_shipments(self) -> None:
        self.update_summary()

        search = self.shipment_name_input.text().strip()

        params = {"search": f"%{search}%"}
        where = ""

        if search:
            where = """
                WHERE s.shipment_no ILIKE :search
                   OR s.customer_name ILIKE :search
                   OR COALESCE(s.note, '') ILIKE :search
            """

        sql = f"""
            SELECT
                s.id,
                s.shipment_no,
                s.shipment_date,
                s.status,
                COUNT(i.id) AS item_count
            FROM mpps_shipments s
            LEFT JOIN mpps_shipment_items i ON s.id = i.shipment_id
            {where}
            GROUP BY s.id, s.shipment_no, s.shipment_date, s.status
            ORDER BY s.shipment_date DESC, s.id DESC
            LIMIT 30;
        """

        try:
            with engine.begin() as connection:
                rows = connection.execute(text(sql), params).mappings().all()
        except Exception:
            rows = []

        self.previous_table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.previous_table.insertRow(row_index)

            values = [
                row["shipment_no"],
                self._fmt_date(row["shipment_date"]),
                self._format_int(row["item_count"]),
                row["status"],
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

                if col in {1, 2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                self.previous_table.setItem(row_index, col, item)

        self.previous_table.resizeRowsToContents()

    def load_selected_previous_shipment(self) -> None:
        selected = self.previous_table.selectedItems()

        if not selected:
            return

        row = selected[0].row()
        id_item = self.previous_table.item(row, 0)

        if id_item is None:
            return

        shipment_id = id_item.data(Qt.ItemDataRole.UserRole)

        if not shipment_id:
            return

        self.load_shipment(int(shipment_id))

    def load_shipment(self, shipment_id: int) -> None:
        with engine.begin() as connection:
            shipment = connection.execute(
                text("SELECT * FROM mpps_shipments WHERE id = :id LIMIT 1;"),
                {"id": shipment_id},
            ).mappings().first()

            items = connection.execute(
                text(
                    """
                    SELECT sap_code, item_description, quantity
                    FROM mpps_shipment_items
                    WHERE shipment_id = :id
                    ORDER BY id ASC;
                    """
                ),
                {"id": shipment_id},
            ).mappings().all()

        if not shipment:
            return

        self.current_shipment_id = int(shipment["id"])
        self.shipment_name_input.setText(str(shipment["shipment_no"]))
        self.customer_input.setText(str(shipment["customer_name"] or ""))

        shipment_date = shipment["shipment_date"]

        if hasattr(shipment_date, "year"):
            self.plan_date_input.setDate(QDate(shipment_date.year, shipment_date.month, shipment_date.day))

        self.remarks_input.setPlainText(str(shipment["note"] or ""))

        self.current_items = [
            {
                "sap_code": str(row["sap_code"]),
                "item_description": str(row["item_description"]),
                "quantity": int(row["quantity"] or 0),
            }
            for row in items
        ]

        self.refresh_items_table()
        self.recalculate_actual_date()

    def save_shipment(self) -> None:
        shipment_no = self.shipment_name_input.text().strip()
        customer = self.customer_input.text().strip() or shipment_no
        plan_date = self.plan_date_input.date().toPython()
        note = self.remarks_input.toPlainText().strip()

        if not shipment_no:
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment name / shipment no.")
            self.shipment_name_input.setFocus()
            return

        if not self.current_items:
            QMessageBox.warning(self, "Items Required", "Please add at least one tyre item from master data.")
            self.item_search_input.setFocus()
            return

        try:
            with engine.begin() as connection:
                existing_id = connection.execute(
                    text("SELECT id FROM mpps_shipments WHERE shipment_no = :shipment_no LIMIT 1;"),
                    {"shipment_no": shipment_no},
                ).scalar()

                if existing_id:
                    shipment_id = int(existing_id)
                    connection.execute(
                        text(
                            """
                            UPDATE mpps_shipments
                            SET
                                customer_name = :customer_name,
                                shipment_date = :shipment_date,
                                status = 'Planned',
                                note = :note,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id;
                            """
                        ),
                        {
                            "id": shipment_id,
                            "customer_name": customer,
                            "shipment_date": plan_date,
                            "note": note,
                        },
                    )

                    connection.execute(
                        text("DELETE FROM mpps_shipment_items WHERE shipment_id = :id;"),
                        {"id": shipment_id},
                    )
                else:
                    shipment_id = int(
                        connection.execute(
                            text(
                                """
                                INSERT INTO mpps_shipments
                                    (shipment_no, customer_name, shipment_date, status, note, updated_at)
                                VALUES
                                    (:shipment_no, :customer_name, :shipment_date, 'Planned', :note, CURRENT_TIMESTAMP)
                                RETURNING id;
                                """
                            ),
                            {
                                "shipment_no": shipment_no,
                                "customer_name": customer,
                                "shipment_date": plan_date,
                                "note": note,
                            },
                        ).scalar_one()
                    )

                for item in self.current_items:
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
                                    'Pending',
                                    '',
                                    CURRENT_TIMESTAMP
                                );
                            """
                        ),
                        {
                            "shipment_id": shipment_id,
                            "sap_code": item["sap_code"],
                            "item_description": item["item_description"],
                            "quantity": item["quantity"],
                            "start_date": plan_date,
                            "end_date": plan_date,
                        },
                    )

            self.current_shipment_id = shipment_id

            QMessageBox.information(
                self,
                "Shipment Saved",
                "Shipment saved successfully. The entry form is now ready for the next shipment.",
            )

            self.clear_after_successful_save()

        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))

    def clear_form(self) -> None:
        self.current_shipment_id = None
        self.shipment_name_input.clear()
        self.customer_input.clear()
        self.plan_date_input.setDate(QDate.currentDate().addDays(7))
        self.actual_date_input.setText("Pending")
        self.remarks_input.clear()
        self.item_search_input.clear()
        self.quantity_input.setValue(1)
        self.current_items.clear()
        self.refresh_items_table()
        self.load_previous_shipments()
        self.recalculate_actual_date()

    def clear_after_successful_save(self) -> None:
        """
        Professional post-save reset.

        Saved data remains in database and Previous Shipments.
        Entry fields and the unsaved item table are cleared for the next shipment.
        """

        self.current_shipment_id = None

        self.shipment_name_input.blockSignals(True)
        self.shipment_name_input.clear()
        self.shipment_name_input.blockSignals(False)

        self.customer_input.clear()
        self.plan_date_input.setDate(QDate.currentDate().addDays(7))
        self.actual_date_input.setText("Pending")
        self.remarks_input.clear()

        self.item_search_input.clear()
        self.quantity_input.setValue(1)

        self.current_items.clear()
        self.refresh_items_table()

        self.load_previous_shipments()
        self.recalculate_actual_date()

        self.shipment_name_input.setFocus()

    def _fmt_date(self, value) -> str:
        if value is None:
            return "-"

        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")

        return str(value)

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"


class ShipmentDemandPage(OrderEntryPage):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user=current_user)
