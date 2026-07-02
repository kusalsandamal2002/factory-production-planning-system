from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from PySide6.QtCore import QDate, Qt, QStringListModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QCompleter,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
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


@dataclass(frozen=True)
class DemoItem:
    code: str
    description: str
    tyre_type: str
    line: str
    mold: str
    casing: str


class CustomerOrderEntryPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.order_items: list[dict[str, object]] = []
        self.plan_date_enabled = True

        self.shipments = {
            "ABC Tyres Shipment": [
                ("SHP-00021", "2026-07-12", "12 items", "Completed"),
                ("SHP-00018", "2026-06-29", "8 items", "Delivered"),
                ("SHP-00011", "2026-06-04", "15 items", "Completed"),
            ],
            "Lanka Industrial Shipment": [
                ("SHP-00034", "2026-07-20", "9 items", "In Planning"),
                ("SHP-00028", "2026-06-16", "11 items", "Delivered"),
            ],
            "Ceylon Forklift Shipment": [
                ("SHP-00041", "2026-07-25", "6 items", "Completed"),
                ("SHP-00030", "2026-06-21", "10 items", "Delivered"),
            ],
            "Global Material Handling Shipment": [
                ("SHP-00038", "2026-07-22", "14 items", "Completed"),
            ],
        }

        self.demo_items = [
            DemoItem("SAP00123", "6.00-9 Resilient Standard Quick 2L NM", "Resilient Tyre", "400T", "M-400-018", "B2"),
            DemoItem("SAP00124", "6.00-9 Resilient Standard Normal 2L Grey", "Resilient Tyre", "400T", "M-400-019", "B2"),
            DemoItem("SAP00125", "7.00-12 Resilient Ultima Quick 3L Black", "Resilient Tyre", "800T", "M-800-044", "B5"),
            DemoItem("SAP00388", "6.00-9 Press-On Standard NM", "Press-On Tyre", "200T", "M-200-012", "Mono"),
            DemoItem("SAP00410", "8.15-15 Press-On Ultima Black", "Press-On Tyre", "400T", "M-400-072", "B3"),
            DemoItem("SAP00520", "10x5x6.5 Cured-On NM", "Cured-On Tyre", "200T", "M-200-031", "Mono"),
            DemoItem("SAP00630", "SuperSolid Industrial Tyre Black", "SuperSolid", "SuperSolid", "Special", "No restriction"),
        ]

        self.item_lookup = {self._item_display(item): item for item in self.demo_items}

        self._build_styles()
        self._build_ui()
        self._setup_autocomplete()
        self._refresh_previous_shipments()
        self._refresh_summary()

    def _build_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard, QFrame#PanelCard, QFrame#SummaryCard, QFrame#PreviewCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle {
                color: #64748b;
                font-size: 10pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 14pt;
                font-weight: 950;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 900;
            }

            QLabel#HintText {
                color: #64748b;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#PreviewTitle {
                color: #0f172a;
                font-size: 11.5pt;
                font-weight: 950;
            }

            QLabel#PreviewLine {
                color: #334155;
                font-size: 9pt;
                font-weight: 750;
            }

            QLabel#SummaryValue {
                color: #020617;
                font-size: 20pt;
                font-weight: 950;
            }

            QLabel#SummaryLabel {
                color: #64748b;
                font-size: 9pt;
                font-weight: 800;
            }

            QLabel#StatusBadge {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 12px;
                padding: 9px 12px;
                font-size: 9pt;
                font-weight: 900;
            }

            QLineEdit, QDateEdit, QSpinBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 10px;
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLineEdit:read-only {
                background: #f8fafc;
                color: #0f172a;
            }

            QLineEdit:focus, QDateEdit:focus, QSpinBox:focus, QTextEdit:focus {
                border: 1px solid #2563eb;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 10px 18px;
                font-size: 9.5pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SoftButton {
                background: #dbeafe;
                color: #1d4ed8;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 9pt;
                font-weight: 900;
            }

            QPushButton#SoftButton:hover {
                background: #bfdbfe;
            }

            QPushButton#DangerButton {
                background: #fee2e2;
                color: #b91c1c;
                border: none;
                border-radius: 9px;
                padding: 7px 10px;
                font-size: 8.5pt;
                font-weight: 900;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9pt;
                font-weight: 650;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 9px;
                font-size: 8.8pt;
                font-weight: 900;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        root.addWidget(self._build_header())
        root.addWidget(self._build_shipment_header())

        middle = QHBoxLayout()
        middle.setSpacing(14)
        middle.addWidget(self._build_add_item_panel(), 3)
        middle.addWidget(self._build_previous_shipments_panel(), 2)
        root.addLayout(middle)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(self._build_items_table_panel(), 4)
        bottom.addWidget(self._build_summary_panel(), 2)
        root.addLayout(bottom, 1)

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)

        title = QLabel("Shipment Entry")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Enter shipment details, add tyre items, and preview the actual date the shipment can be received."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def _build_shipment_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QGridLayout(card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(9)

        self.shipment_name_input = QLineEdit()
        self.shipment_name_input.setPlaceholderText("Type shipment name")

        self.plan_date_input = QDateEdit()
        self.plan_date_input.setCalendarPopup(True)
        self.plan_date_input.setDisplayFormat("yyyy-MM-dd")
        self.plan_date_input.setDate(QDate.currentDate().addDays(7))
        self.plan_date_input.setEnabled(True)
        self.plan_date_input.setCalendarWidget(self._build_calendar())

        self.auto_date_button = QPushButton("Auto Earliest")
        self.auto_date_button.setObjectName("SoftButton")
        self.auto_date_button.setToolTip(
            "Ignore plan to receive date and calculate the earliest possible actual receive date."
        )

        self.actual_receive_date_display = QLineEdit()
        self.actual_receive_date_display.setReadOnly(True)
        self.actual_receive_date_display.setPlaceholderText("Auto calculated")

        self.remarks_input = QTextEdit()
        self.remarks_input.setPlaceholderText("Remarks / special instructions")
        self.remarks_input.setFixedHeight(58)

        layout.addWidget(self._label("Shipment Name"), 0, 0)
        layout.addWidget(self.shipment_name_input, 1, 0)

        layout.addWidget(self._label("Plan To Receive Date"), 0, 1)

        plan_date_row = QHBoxLayout()
        plan_date_row.setSpacing(8)
        plan_date_row.addWidget(self.plan_date_input, 1)
        plan_date_row.addWidget(self.auto_date_button)
        layout.addLayout(plan_date_row, 1, 1)

        layout.addWidget(self._label("Shipment Can Receive Actual Date"), 0, 2)
        layout.addWidget(self.actual_receive_date_display, 1, 2)

        layout.addWidget(self._label("Remarks"), 2, 0)
        layout.addWidget(self.remarks_input, 3, 0, 1, 3)

        self.plan_date_input.dateChanged.connect(self._on_plan_date_changed)
        self.auto_date_button.clicked.connect(self._use_auto_earliest_date)

        return card

    def _build_calendar(self) -> QCalendarWidget:
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setStyleSheet(
            """
            QCalendarWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }

            QCalendarWidget QWidget {
                background: #ffffff;
                color: #0f172a;
            }

            QCalendarWidget QToolButton {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 8px;
                padding: 6px;
                font-weight: 900;
            }

            QCalendarWidget QToolButton:hover {
                background: #dbeafe;
            }

            QCalendarWidget QMenu {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
            }

            QCalendarWidget QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px;
            }

            QCalendarWidget QAbstractItemView {
                background: #ffffff;
                color: #0f172a;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: none;
                outline: none;
                font-weight: 800;
            }
            """
        )
        return calendar

    def _build_add_item_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Add Shipment Item")
        title.setObjectName("SectionTitle")

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.item_input = QLineEdit()
        self.item_input.setPlaceholderText("Type item code or description")

        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 1_000_000)
        self.qty_input.setValue(1)

        add_button = QPushButton("Add Item")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_item)

        form.addWidget(self._label("Item Code / Description"), 0, 0)
        form.addWidget(self._label("Quantity"), 0, 1)
        form.addWidget(self.item_input, 1, 0)
        form.addWidget(self.qty_input, 1, 1)
        form.addWidget(add_button, 1, 2)

        self.item_preview = QFrame()
        self.item_preview.setObjectName("PreviewCard")

        preview_layout = QVBoxLayout(self.item_preview)
        preview_layout.setContentsMargins(14, 12, 14, 12)
        preview_layout.setSpacing(5)

        preview_title = QLabel("Selected Item Preview")
        preview_title.setObjectName("PreviewTitle")

        self.preview_description = QLabel("No item selected.")
        self.preview_description.setObjectName("PreviewLine")
        self.preview_description.setWordWrap(True)

        self.preview_details = QLabel("Type an item code or description to preview item details.")
        self.preview_details.setObjectName("HintText")
        self.preview_details.setWordWrap(True)

        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview_description)
        preview_layout.addWidget(self.preview_details)

        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.item_preview)

        return card

    def _build_previous_shipments_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Previous Shipments")
        title.setObjectName("SectionTitle")

        self.previous_shipments_hint = QLabel("Type or select a shipment name to view previous shipments.")
        self.previous_shipments_hint.setObjectName("HintText")
        self.previous_shipments_hint.setWordWrap(True)

        self.previous_shipments_table = QTableWidget()
        self.previous_shipments_table.setColumnCount(4)
        self.previous_shipments_table.setHorizontalHeaderLabels(
            ["Shipment No", "Date", "Items", "Status"]
        )
        self.previous_shipments_table.verticalHeader().setVisible(False)
        self.previous_shipments_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.previous_shipments_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.previous_shipments_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.previous_shipments_table.setMinimumHeight(170)

        layout.addWidget(title)
        layout.addWidget(self.previous_shipments_hint)
        layout.addWidget(self.previous_shipments_table, 1)

        return card

    def _build_items_table_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Shipment Items")
        title.setObjectName("SectionTitle")

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(
            ["Item Code", "Description", "Qty", "Action"]
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        layout.addWidget(title)
        layout.addWidget(self.items_table, 1)

        return card

    def _build_summary_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("SummaryCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Shipment Summary")
        title.setObjectName("SectionTitle")

        self.shipment_summary_label = QLabel("Shipment: -")
        self.shipment_summary_label.setObjectName("HintText")
        self.shipment_summary_label.setWordWrap(True)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(12)

        self.total_items_box = self._summary_metric("0", "Total Items")
        self.total_qty_box = self._summary_metric("0", "Total Qty")

        metric_row.addWidget(self.total_items_box)
        metric_row.addWidget(self.total_qty_box)

        result_title = QLabel("Calculated Planning Result")
        result_title.setObjectName("PreviewTitle")

        self.priority_mode_label = QLabel("Priority Mode: Plan to receive date")
        self.priority_mode_label.setObjectName("PreviewLine")
        self.priority_mode_label.setWordWrap(True)

        self.plan_date_label = QLabel("Plan To Receive Date: -")
        self.plan_date_label.setObjectName("PreviewLine")
        self.plan_date_label.setWordWrap(True)

        self.actual_date_label = QLabel("Shipment Can Receive Actual Date: Pending")
        self.actual_date_label.setObjectName("PreviewLine")
        self.actual_date_label.setWordWrap(True)

        self.planning_status_label = QLabel("Planning Status: Add items to calculate actual receive date.")
        self.planning_status_label.setObjectName("StatusBadge")
        self.planning_status_label.setWordWrap(True)

        save_button = QPushButton("Save Shipment Draft")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self._save_draft_preview)

        clear_button = QPushButton("Clear Shipment")
        clear_button.setObjectName("SoftButton")
        clear_button.clicked.connect(self._clear_shipment)

        layout.addWidget(title)
        layout.addWidget(self.shipment_summary_label)
        layout.addLayout(metric_row)
        layout.addSpacing(8)
        layout.addWidget(result_title)
        layout.addWidget(self.priority_mode_label)
        layout.addWidget(self.plan_date_label)
        layout.addWidget(self.actual_date_label)
        layout.addWidget(self.planning_status_label)
        layout.addStretch()
        layout.addWidget(save_button)
        layout.addWidget(clear_button)

        return card

    def _summary_metric(self, value: str, label: str) -> QFrame:
        box = QFrame()
        box.setObjectName("PreviewCard")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        value_label = QLabel(value)
        value_label.setObjectName("SummaryValue")

        label_widget = QLabel(label)
        label_widget.setObjectName("SummaryLabel")

        if label == "Total Items":
            self.total_items_value = value_label
        if label == "Total Qty":
            self.total_qty_value = value_label

        layout.addWidget(value_label)
        layout.addWidget(label_widget)
        return box

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _setup_autocomplete(self) -> None:
        shipment_model = QStringListModel(sorted(self.shipments.keys()))
        self.shipment_completer = QCompleter(shipment_model, self)
        self.shipment_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.shipment_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.shipment_name_input.setCompleter(self.shipment_completer)

        self.shipment_completer.activated.connect(self._on_shipment_selected)
        self.shipment_name_input.textChanged.connect(self._on_shipment_text_changed)

        item_names = [self._item_display(item) for item in self.demo_items]
        item_model = QStringListModel(item_names)

        self.item_completer = QCompleter(item_model, self)
        self.item_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.item_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item_input.setCompleter(self.item_completer)

        self.item_completer.activated.connect(self._on_item_selected)
        self.item_input.textChanged.connect(self._on_item_text_changed)

    def _item_display(self, item: DemoItem) -> str:
        return f"{item.code} | {item.description}"

    def _on_plan_date_changed(self) -> None:
        self.plan_date_enabled = True
        self._refresh_summary()

    def _use_auto_earliest_date(self) -> None:
        self.plan_date_enabled = False
        self._refresh_summary()

    def _on_shipment_selected(self, name: str) -> None:
        self.shipment_name_input.setText(name)
        self._refresh_previous_shipments()
        self._refresh_summary()

    def _on_shipment_text_changed(self) -> None:
        self._refresh_previous_shipments()
        self._refresh_summary()

    def _on_item_selected(self, display_text: str) -> None:
        self.item_input.setText(display_text)
        self._refresh_item_preview()

    def _on_item_text_changed(self) -> None:
        self._refresh_item_preview()

    def _find_shipment_key(self) -> str | None:
        typed = self.shipment_name_input.text().strip().lower()
        if not typed:
            return None

        for shipment_name in self.shipments:
            if shipment_name.lower() == typed:
                return shipment_name

        for shipment_name in self.shipments:
            if typed in shipment_name.lower():
                return shipment_name

        return None

    def _refresh_previous_shipments(self) -> None:
        shipment_key = self._find_shipment_key()
        shipments = self.shipments.get(shipment_key, []) if shipment_key else []

        self.previous_shipments_table.setRowCount(len(shipments))

        for row, shipment in enumerate(shipments):
            for col, value in enumerate(shipment):
                self.previous_shipments_table.setItem(row, col, QTableWidgetItem(str(value)))

        if shipment_key:
            self.previous_shipments_hint.setText(f"Showing previous shipments for {shipment_key}.")
        elif self.shipment_name_input.text().strip():
            self.previous_shipments_hint.setText("No previous shipments found. This can be saved as a new shipment.")
        else:
            self.previous_shipments_hint.setText("Type or select a shipment name to view previous shipments.")

    def _find_item(self) -> DemoItem | None:
        typed = self.item_input.text().strip().lower()
        if not typed:
            return None

        exact = self.item_lookup.get(self.item_input.text().strip())
        if exact is not None:
            return exact

        for item in self.demo_items:
            display = self._item_display(item).lower()
            if typed == item.code.lower() or typed in display:
                return item

        return None

    def _refresh_item_preview(self) -> None:
        item = self._find_item()

        if item is None:
            self.preview_description.setText("No item selected.")
            self.preview_details.setText("Type an item code or description to preview item details.")
            return

        self.preview_description.setText(f"{item.code} | {item.description}")
        self.preview_details.setText(
            "Item selected. Final planning will check stock, line, mold, casing, cavity and schedule availability."
        )

    def _add_item(self) -> None:
        item = self._find_item()
        qty = int(self.qty_input.value())

        if not self.shipment_name_input.text().strip():
            QMessageBox.warning(self, "Shipment Name Required", "Please enter shipment name before adding items.")
            return

        if item is None:
            QMessageBox.warning(self, "Item Required", "Please select a valid item from the suggestions.")
            return

        for existing in self.order_items:
            if existing["code"] == item.code:
                existing["qty"] = int(existing["qty"]) + qty
                self._refresh_items_table()
                self._refresh_summary()
                self.item_input.clear()
                self.qty_input.setValue(1)
                return

        self.order_items.append(
            {
                "code": item.code,
                "description": item.description,
                "qty": qty,
            }
        )

        self._refresh_items_table()
        self._refresh_summary()
        self.item_input.clear()
        self.qty_input.setValue(1)

    def _refresh_items_table(self) -> None:
        self.items_table.setRowCount(len(self.order_items))

        for row, item in enumerate(self.order_items):
            values = [
                item["code"],
                item["description"],
                item["qty"],
            ]

            for col, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))

                if col == 2:
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                self.items_table.setItem(row, col, table_item)

            remove_button = QPushButton("Remove")
            remove_button.setObjectName("DangerButton")
            remove_button.clicked.connect(lambda checked=False, row_index=row: self._remove_item(row_index))
            self.items_table.setCellWidget(row, 3, remove_button)

        self.items_table.resizeRowsToContents()

    def _remove_item(self, row_index: int) -> None:
        if 0 <= row_index < len(self.order_items):
            self.order_items.pop(row_index)
            self._refresh_items_table()
            self._refresh_summary()

    def _refresh_summary(self) -> None:
        shipment_name = self.shipment_name_input.text().strip() or "-"
        total_items = len(self.order_items)
        total_qty = sum(int(item["qty"]) for item in self.order_items)

        self.shipment_summary_label.setText(f"Shipment: {shipment_name}")
        self.total_items_value.setText(f"{total_items:,}")
        self.total_qty_value.setText(f"{total_qty:,}")

        if total_items == 0:
            self.actual_receive_date_display.setText("Pending")
            self.priority_mode_label.setText(
                "Priority Mode: Plan to receive date" if self.plan_date_enabled else "Priority Mode: Auto earliest possible date"
            )
            self.plan_date_label.setText(
                f"Plan To Receive Date: {self._selected_plan_date().strftime('%Y-%m-%d')}"
                if self.plan_date_enabled
                else "Plan To Receive Date: Not provided"
            )
            self.actual_date_label.setText("Shipment Can Receive Actual Date: Pending")
            self.planning_status_label.setText("Planning Status: Add items to calculate actual receive date.")
            return

        plan_days = max(1, ceil(total_qty / 500))
        earliest_ready_date = date.today() + timedelta(days=plan_days)

        self.actual_receive_date_display.setText(earliest_ready_date.strftime("%Y-%m-%d"))
        self.actual_date_label.setText(
            f"Shipment Can Receive Actual Date: {earliest_ready_date.strftime('%Y-%m-%d')}"
        )

        if self.plan_date_enabled:
            plan_date = self._selected_plan_date()

            self.priority_mode_label.setText("Priority Mode: Plan to receive date")
            self.plan_date_label.setText(f"Plan To Receive Date: {plan_date.strftime('%Y-%m-%d')}")

            if earliest_ready_date <= plan_date:
                self.planning_status_label.setText(
                    "Planning Status: Plan to receive date can be achieved by current preview."
                )
            else:
                delay_days = (earliest_ready_date - plan_date).days
                self.planning_status_label.setText(
                    f"Planning Status: Plan to receive date needs review. Actual receive date is {delay_days} day(s) later."
                )
        else:
            self.priority_mode_label.setText("Priority Mode: Auto earliest possible date")
            self.plan_date_label.setText("Plan To Receive Date: Not provided")
            self.planning_status_label.setText(
                "Planning Status: No plan to receive date provided. System shows earliest possible actual receive date."
            )

    def _selected_plan_date(self) -> date:
        qdate = self.plan_date_input.date()
        return date(qdate.year(), qdate.month(), qdate.day())

    def _save_draft_preview(self) -> None:
        if not self.shipment_name_input.text().strip():
            QMessageBox.warning(self, "Shipment Name Required", "Please enter shipment name.")
            return

        if not self.order_items:
            QMessageBox.warning(self, "Shipment Items Required", "Please add at least one shipment item.")
            return

        QMessageBox.information(
            self,
            "Draft Ready",
            "Frontend shipment draft is ready. Database saving will be connected in the backend step.",
        )

    def _clear_shipment(self) -> None:
        self.shipment_name_input.clear()
        self.plan_date_enabled = True
        self.plan_date_input.setDate(QDate.currentDate().addDays(7))
        self.remarks_input.clear()
        self.item_input.clear()
        self.qty_input.setValue(1)
        self.order_items.clear()
        self._refresh_previous_shipments()
        self._refresh_items_table()
        self._refresh_summary()


OrderEntryPage = CustomerOrderEntryPage


class ShipmentDemandPage(CustomerOrderEntryPage):
    """Compatibility wrapper for old pages still importing ShipmentDemandPage."""

    def __init__(self, *args, **kwargs):
        current_user = kwargs.pop("current_user", None)
        super().__init__(current_user=current_user)
