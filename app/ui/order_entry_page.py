from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QDate, QObject, Qt, QThread, QTimer, Signal, QStringListModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from app.database import get_session
from app.models import Customer, TireType
from app.services.order_service import (
    create_confirmed_order,
    generate_next_order_no,
    preview_order_capacity,
)
from app.services.scheduler import OrderLineInput, SchedulePreviewResult
from app.utils.formatters import fmt_datetime


@dataclass
class InquiryItem:
    tire_type_id: int
    tire_text: str
    quantity: int


class CapacityPreviewWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, order_lines: list[OrderLineInput]):
        super().__init__()
        self.order_lines = order_lines

    def run(self) -> None:
        try:
            with get_session() as session:
                preview = preview_order_capacity(session, self.order_lines)

            self.finished.emit(preview)

        except Exception as exc:
            self.failed.emit(str(exc))


class OrderEntryPage(QWidget):
    def __init__(self, current_user_id: int | None):
        super().__init__()

        self.current_user_id = current_user_id
        self.current_preview: SchedulePreviewResult | None = None

        self.preview_thread: QThread | None = None
        self.preview_worker: CapacityPreviewWorker | None = None

        self.progress_value = 0
        self.is_rebuilding_table = False
        self.pending_recalculate = False

        self.inquiry_items: list[InquiryItem] = []
        self.tire_options: list[dict] = []
        self.customer_options: list[dict] = []

        self.tire_combo = QComboBox()
        self.tire_combo.setEditable(True)
        self.tire_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.tire_combo.setMinimumHeight(42)
        self.tire_combo.setMaxVisibleItems(12)
        self.tire_combo.lineEdit().setPlaceholderText(
            "Search tire type by code or name..."
        )

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 100000)
        self.qty_spin.setValue(10)
        self.qty_spin.setMinimumHeight(42)

        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.customer_combo.setMinimumHeight(42)
        self.customer_combo.setMaxVisibleItems(12)
        self.customer_combo.lineEdit().setPlaceholderText(
            "Type or search customer name after customer accepts the date"
        )

        self.order_no_label = QLabel("-")
        self.order_no_label.setObjectName("InfoPill")
        self.order_no_label.setMinimumHeight(38)

        self.confirmed_date = QDateEdit()
        self.confirmed_date.setCalendarPopup(True)
        self.confirmed_date.setDate(QDate.currentDate())
        self.confirmed_date.setMinimumHeight(42)

        self.note = QTextEdit()
        self.note.setPlaceholderText(
            "Manager note / customer agreement / production remark"
        )
        self.note.setMinimumHeight(92)

        self.can_receive_label = QLabel("Add tire items to calculate")
        self.can_receive_label.setObjectName("MetricValue")
        self.can_receive_label.setWordWrap(True)
        self.can_receive_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.calculation_status_label = QLabel("Ready for live capacity calculation")
        self.calculation_status_label.setObjectName("SectionHint")
        self.calculation_status_label.setWordWrap(True)

        self.calculation_progress = QProgressBar()
        self.calculation_progress.setRange(0, 100)
        self.calculation_progress.setValue(0)
        self.calculation_progress.setTextVisible(True)
        self.calculation_progress.setFormat("0%")
        self.calculation_progress.setMinimumHeight(22)
        self.calculation_progress.setVisible(False)

        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(70)
        self.progress_timer.timeout.connect(self._advance_progress)

        self.table_change_timer = QTimer(self)
        self.table_change_timer.setSingleShot(True)
        self.table_change_timer.setInterval(600)
        self.table_change_timer.timeout.connect(self.recalculate_preview)

        self.items_table = QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(
            ["Tire Type", "Qty", "Action", "Tire ID"]
        )
        self.items_table.setColumnHidden(3, True)
        self.items_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.items_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.verticalHeader().setDefaultSectionSize(46)
        self.items_table.horizontalHeader().setStretchLastSection(False)
        self.items_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.items_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed
        )
        self.items_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed
        )
        self.items_table.setColumnWidth(1, 110)
        self.items_table.setColumnWidth(2, 110)
        self.items_table.setMinimumHeight(330)
        self.items_table.itemChanged.connect(self._on_table_item_changed)

        self.add_btn = QPushButton("Add Tire Item")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setMinimumHeight(44)
        self.add_btn.clicked.connect(self.add_item)

        self.confirm_btn = QPushButton("Confirm & Save Customer Order")
        self.confirm_btn.setObjectName("PrimaryButton")
        self.confirm_btn.setMinimumHeight(44)
        self.confirm_btn.clicked.connect(self.confirm_order)
        self.confirm_btn.setEnabled(False)

        self._apply_input_styles()
        self._build_ui()
        self.load_master_data()
        self.refresh_order_no()
        self.recalculate_preview()

    def _apply_input_styles(self) -> None:
        combo_popup_style = """
            QListView {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px;
                outline: 0;
            }

            QListView::item {
                padding: 9px 10px;
                border-radius: 6px;
                min-height: 28px;
            }

            QListView::item:selected {
                background: #dbeafe;
                color: #1e40af;
            }

            QListView::item:hover {
                background: #eff6ff;
                color: #1e40af;
            }
        """

        self.tire_combo.view().setStyleSheet(combo_popup_style)
        self.customer_combo.view().setStyleSheet(combo_popup_style)

        clean_input_style = """
            QComboBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 600;
            }

            QComboBox:focus {
                border: 1px solid #2563eb;
            }

            QComboBox::drop-down {
                border: none;
                width: 28px;
            }

            QComboBox QLineEdit {
                background: transparent;
                color: #0f172a;
                border: none;
                padding: 4px;
                font-weight: 600;
            }

            QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 700;
            }

            QSpinBox:focus {
                border: 1px solid #2563eb;
            }

            QDateEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 700;
            }

            QTextEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 10px;
            }

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                selection-background-color: #eff6ff;
                selection-color: #0f172a;
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
                font-weight: 900;
            }

            QProgressBar {
                background: #e2e8f0;
                border: none;
                border-radius: 8px;
                height: 22px;
                text-align: center;
                color: #0f172a;
                font-size: 8.5pt;
                font-weight: 900;
            }

            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 8px;
            }
        """

        self.tire_combo.setStyleSheet(clean_input_style)
        self.customer_combo.setStyleSheet(clean_input_style)
        self.qty_spin.setStyleSheet(clean_input_style)
        self.confirmed_date.setStyleSheet(clean_input_style)
        self.note.setStyleSheet(clean_input_style)
        self.calculation_progress.setStyleSheet(clean_input_style)
        self.items_table.setStyleSheet(clean_input_style)

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_workflow_header())

        page_grid = QGridLayout()
        page_grid.setHorizontalSpacing(16)
        page_grid.setVerticalSpacing(16)
        page_grid.setColumnStretch(0, 5)
        page_grid.setColumnStretch(1, 5)

        page_grid.addWidget(self._build_enquiry_card(), 0, 0, 2, 1)
        page_grid.addWidget(self._build_live_result_card(), 0, 1)
        page_grid.addWidget(self._build_confirmation_card(), 1, 1)

        root.addLayout(page_grid, 1)

        scroll.setWidget(page)
        outer_layout.addWidget(scroll)

    def _build_workflow_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelCard")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        title = QLabel("Order Enquiry to Confirmation Workflow")
        title.setObjectName("CardTitle")
        title.setStyleSheet(
            "font-size: 13pt; font-weight: 900; color: #0f172a;"
        )

        hint = QLabel(
            "First calculate the live Company Can Receive Date without customer details. "
            "When the customer accepts the date, add customer details and confirm the order."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        return frame

    def _build_enquiry_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("1. Live Order Enquiry")
        title.setObjectName("CardTitle")
        title.setStyleSheet(
            "font-size: 12pt; font-weight: 900; color: #0f172a;"
        )

        hint = QLabel(
            "Use this during a customer call. Search tire type by code or name, enter quantity, then add it to the enquiry."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        input_frame = QFrame()
        input_frame.setObjectName("PanelCard")

        input_layout = QGridLayout(input_frame)
        input_layout.setContentsMargins(16, 14, 16, 14)
        input_layout.setHorizontalSpacing(14)
        input_layout.setVerticalSpacing(12)
        input_layout.setColumnStretch(0, 1)
        input_layout.setColumnStretch(1, 3)

        input_layout.addWidget(self._form_label("Tire Type"), 0, 0)
        input_layout.addWidget(self.tire_combo, 0, 1)

        input_layout.addWidget(self._form_label("Quantity"), 1, 0)
        input_layout.addWidget(self.qty_spin, 1, 1)

        input_layout.addWidget(self.add_btn, 2, 0, 1, 2)

        layout.addWidget(input_frame)

        items_title = QLabel("Inquiry Items")
        items_title.setObjectName("CardTitle")
        items_title.setStyleSheet(
            "font-size: 11pt; font-weight: 900; color: #0f172a;"
        )

        table_hint = QLabel(
            "Click the Qty cell and type a new quantity like Excel. Use Delete to remove a tire item."
        )
        table_hint.setObjectName("SectionHint")
        table_hint.setWordWrap(True)

        layout.addWidget(items_title)
        layout.addWidget(table_hint)
        layout.addWidget(self.items_table, 1)

        return card

    def _build_live_result_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("2. Live Capacity Result")
        title.setObjectName("CardTitle")
        title.setStyleSheet(
            "font-size: 12pt; font-weight: 900; color: #0f172a;"
        )

        hint = QLabel(
            "Earliest possible receive date based on current oven capacity and existing confirmed orders."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        result_box = QFrame()
        result_box.setObjectName("PanelCard")
        result_box.setMinimumHeight(180)

        result_layout = QVBoxLayout(result_box)
        result_layout.setContentsMargins(18, 18, 18, 18)
        result_layout.setSpacing(10)

        receive_title = QLabel("Company Can Receive Date")
        receive_title.setObjectName("MetricLabel")
        receive_title.setStyleSheet("font-weight: 900; color: #334155;")

        self.can_receive_label.setStyleSheet(
            "font-size: 24pt; font-weight: 900; color: #0f172a; background: transparent;"
        )

        result_layout.addWidget(receive_title)
        result_layout.addWidget(self.can_receive_label)
        result_layout.addWidget(self.calculation_status_label)
        result_layout.addWidget(self.calculation_progress)
        result_layout.addStretch()

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(result_box)
        layout.addStretch()

        return card

    def _build_confirmation_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("3. Confirm Customer Order")
        title.setObjectName("CardTitle")
        title.setStyleSheet(
            "font-size: 12pt; font-weight: 900; color: #0f172a;"
        )

        hint = QLabel(
            "Fill this section only after the customer accepts the calculated receive date."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        form_frame = QFrame()
        form_frame.setObjectName("PanelCard")

        form = QGridLayout(form_frame)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 3)

        form.addWidget(self._form_label("Customer Name"), 0, 0)
        form.addWidget(self.customer_combo, 0, 1)

        form.addWidget(self._form_label("Order No"), 1, 0)
        form.addWidget(self.order_no_label, 1, 1)

        form.addWidget(self._form_label("Confirmed Receive Date"), 2, 0)
        form.addWidget(self.confirmed_date, 2, 1)

        layout.addWidget(form_frame)
        layout.addWidget(self.note)
        layout.addWidget(self.confirm_btn)

        return card

    def _form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MetricLabel")
        label.setStyleSheet("font-weight: 800; color: #334155;")
        return label

    def _set_entry_controls_enabled(self, enabled: bool) -> None:
        self.tire_combo.setEnabled(enabled)
        self.qty_spin.setEnabled(enabled)
        self.add_btn.setEnabled(enabled)
        self.items_table.setEnabled(enabled)

    def _start_calculation_progress(self) -> None:
        self.progress_value = 0
        self.calculation_progress.setVisible(True)
        self.calculation_progress.setValue(0)
        self.calculation_progress.setFormat("0%")
        self.calculation_status_label.setText("Calculating oven capacity... 0%")
        self.progress_timer.start()

    def _advance_progress(self) -> None:
        if self.progress_value < 75:
            self.progress_value += 5
        elif self.progress_value < 92:
            self.progress_value += 2
        elif self.progress_value < 96:
            self.progress_value += 1

        self.progress_value = min(self.progress_value, 96)
        self.calculation_progress.setValue(self.progress_value)
        self.calculation_progress.setFormat(f"{self.progress_value}%")
        self.calculation_status_label.setText(
            f"Calculating oven capacity... {self.progress_value}%"
        )

    def _finish_calculation_progress(self) -> None:
        self.progress_timer.stop()
        self.progress_value = 100
        self.calculation_progress.setVisible(True)
        self.calculation_progress.setValue(100)
        self.calculation_progress.setFormat("100%")
        self.calculation_status_label.setText("Calculation completed • 100%")

    def _reset_calculation_progress(self) -> None:
        self.progress_timer.stop()
        self.progress_value = 0
        self.calculation_progress.setVisible(False)
        self.calculation_progress.setValue(0)
        self.calculation_progress.setFormat("0%")
        self.calculation_status_label.setText("Ready for live capacity calculation")

    def load_master_data(self) -> None:
        with get_session() as session:
            customers = session.scalars(
                select(Customer)
                .where(Customer.is_active.is_(True))
                .order_by(Customer.customer_code)
            ).all()

            tires = session.scalars(
                select(TireType)
                .where(TireType.is_active.is_(True))
                .order_by(TireType.tire_code)
            ).all()

        self.customer_combo.clear()
        self.customer_options.clear()

        customer_search_texts: list[str] = []

        for customer in customers:
            display_text = f"{customer.customer_code} - {customer.customer_name}"

            self.customer_combo.addItem(display_text, customer.id)

            self.customer_options.append(
                {
                    "id": customer.id,
                    "code": customer.customer_code,
                    "name": customer.customer_name,
                    "display": display_text,
                    "search_text": f"{customer.customer_code} {customer.customer_name}".lower(),
                }
            )

            customer_search_texts.append(display_text)

        customer_completer_model = QStringListModel(customer_search_texts, self)
        self.customer_completer = QCompleter(customer_completer_model, self)
        self.customer_completer.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.customer_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.customer_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self.customer_completer.popup().setStyleSheet(self.tire_combo.view().styleSheet())

        self.customer_combo.setCompleter(self.customer_completer)
        self.customer_combo.setCurrentIndex(-1)
        self.customer_combo.setEditText("")

        self.tire_combo.clear()
        self.tire_options.clear()

        tire_search_texts: list[str] = []

        for tire in tires:
            display_text = (
                f"{tire.tire_code} - {tire.tire_name} "
                f"({tire.curing_minutes} min)"
            )
            table_text = f"{tire.tire_code} - {tire.tire_name}"

            self.tire_combo.addItem(display_text, tire.id)

            self.tire_options.append(
                {
                    "id": tire.id,
                    "code": tire.tire_code,
                    "name": tire.tire_name,
                    "display": display_text,
                    "table_text": table_text,
                    "search_text": f"{tire.tire_code} {tire.tire_name} {display_text}".lower(),
                }
            )

            tire_search_texts.append(display_text)

        tire_completer_model = QStringListModel(tire_search_texts, self)
        self.tire_completer = QCompleter(tire_completer_model, self)
        self.tire_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tire_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.tire_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self.tire_completer.popup().setStyleSheet(self.tire_combo.view().styleSheet())

        self.tire_combo.setCompleter(self.tire_completer)
        self.tire_combo.setCurrentIndex(-1)
        self.tire_combo.setEditText("")

    def refresh_order_no(self) -> None:
        with get_session() as session:
            self.order_no_label.setText(generate_next_order_no(session))

    def _resolve_tire_from_search_text(self) -> dict:
        current_text = self.tire_combo.currentText().strip()
        current_index = self.tire_combo.currentIndex()
        current_data = self.tire_combo.currentData()

        if current_data is not None and current_index >= 0:
            selected_display = self.tire_combo.itemText(current_index)

            if current_text == selected_display:
                for option in self.tire_options:
                    if int(option["id"]) == int(current_data):
                        return option

        if not current_text:
            raise ValueError("Please type or select a tire type.")

        search_value = current_text.lower()

        exact_matches = [
            option
            for option in self.tire_options
            if search_value == option["display"].lower()
            or search_value == option["code"].lower()
            or search_value == option["name"].lower()
            or search_value == option["table_text"].lower()
        ]

        if len(exact_matches) == 1:
            return exact_matches[0]

        contains_matches = [
            option
            for option in self.tire_options
            if search_value in option["search_text"]
        ]

        if len(contains_matches) == 1:
            return contains_matches[0]

        if len(contains_matches) > 1:
            match_names = "\n".join(
                f"- {option['table_text']}" for option in contains_matches[:8]
            )

            raise ValueError(
                "More than one tire type matched your search.\n\n"
                "Please type more specific tire code/name or select from the dropdown.\n\n"
                f"Matches:\n{match_names}"
            )

        raise ValueError(
            "No tire type found for your search.\n\n"
            "Please check the tire code/name and try again."
        )

    def add_item(self) -> None:
        try:
            tire_option = self._resolve_tire_from_search_text()
        except ValueError as exc:
            QMessageBox.warning(self, "Tire Type Search", str(exc))
            return

        tire_id = int(tire_option["id"])
        tire_text = tire_option["table_text"]
        qty = self.qty_spin.value()

        for item in self.inquiry_items:
            if item.tire_type_id == tire_id:
                item.quantity += qty
                self.tire_combo.setCurrentIndex(-1)
                self.tire_combo.setEditText("")
                self._refresh_items_table()
                self.recalculate_preview()
                return

        self.inquiry_items.append(
            InquiryItem(
                tire_type_id=tire_id,
                tire_text=tire_text,
                quantity=qty,
            )
        )

        self.tire_combo.setCurrentIndex(-1)
        self.tire_combo.setEditText("")

        self._refresh_items_table()
        self.recalculate_preview()

    def _refresh_items_table(self) -> None:
        self.is_rebuilding_table = True
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(0)

        for row, item in enumerate(self.inquiry_items):
            self.items_table.insertRow(row)

            tire_item = QTableWidgetItem(item.tire_text)
            tire_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            tire_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )

            qty_item = QTableWidgetItem(str(item.quantity))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsEditable
            )
            qty_item.setData(Qt.ItemDataRole.UserRole, item.quantity)

            tire_id_item = QTableWidgetItem(str(item.tire_type_id))
            tire_id_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )

            delete_btn = QPushButton("Delete")
            delete_btn.setMinimumHeight(32)
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.setStyleSheet(
                """
                QPushButton {
                    background: #fee2e2;
                    color: #991b1b;
                    border: 1px solid #fecaca;
                    border-radius: 8px;
                    padding: 5px 14px;
                    font-weight: 900;
                }

                QPushButton:hover {
                    background: #fecaca;
                    color: #7f1d1d;
                }

                QPushButton:pressed {
                    background: #fca5a5;
                }
                """
            )
            delete_btn.clicked.connect(
                lambda checked=False, tire_id=item.tire_type_id: self.delete_inquiry_item(
                    tire_id
                )
            )

            self.items_table.setItem(row, 0, tire_item)
            self.items_table.setItem(row, 1, qty_item)
            self.items_table.setCellWidget(row, 2, delete_btn)
            self.items_table.setItem(row, 3, tire_id_item)

        self.items_table.setColumnWidth(1, 110)
        self.items_table.setColumnWidth(2, 110)
        self.items_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

        self.items_table.blockSignals(False)
        self.is_rebuilding_table = False

    def _on_table_item_changed(self, changed_item: QTableWidgetItem) -> None:
        if self.is_rebuilding_table:
            return

        if changed_item.column() != 1:
            return

        row = changed_item.row()
        old_quantity = int(changed_item.data(Qt.ItemDataRole.UserRole) or 1)

        tire_id_item = self.items_table.item(row, 3)

        if tire_id_item is None:
            return

        tire_type_id = int(tire_id_item.text())
        entered_text = changed_item.text().strip().replace(",", "")

        try:
            new_quantity = int(entered_text)
        except ValueError:
            self._restore_qty_cell(changed_item, old_quantity)
            QMessageBox.warning(
                self,
                "Invalid Quantity",
                "Please enter a valid whole number quantity.",
            )
            return

        if new_quantity <= 0:
            self._restore_qty_cell(changed_item, old_quantity)
            QMessageBox.warning(
                self,
                "Invalid Quantity",
                "Quantity must be greater than zero.",
            )
            return

        if new_quantity > 100000:
            self._restore_qty_cell(changed_item, old_quantity)
            QMessageBox.warning(
                self,
                "Invalid Quantity",
                "Quantity cannot be greater than 100000.",
            )
            return

        changed_item.setData(Qt.ItemDataRole.UserRole, new_quantity)

        if changed_item.text() != str(new_quantity):
            self.items_table.blockSignals(True)
            changed_item.setText(str(new_quantity))
            self.items_table.blockSignals(False)

        for inquiry_item in self.inquiry_items:
            if inquiry_item.tire_type_id == tire_type_id:
                inquiry_item.quantity = new_quantity
                break

        self.table_change_timer.start()

    def _restore_qty_cell(
        self,
        changed_item: QTableWidgetItem,
        old_quantity: int,
    ) -> None:
        self.items_table.blockSignals(True)
        changed_item.setText(str(old_quantity))
        changed_item.setData(Qt.ItemDataRole.UserRole, old_quantity)
        self.items_table.blockSignals(False)

    def delete_inquiry_item(self, tire_type_id: int) -> None:
        if self.preview_thread is not None and self.preview_thread.isRunning():
            QMessageBox.information(
                self,
                "Calculation Running",
                "Please wait until the current live capacity calculation is finished.",
            )
            return

        self.inquiry_items = [
            item for item in self.inquiry_items if item.tire_type_id != tire_type_id
        ]

        self._refresh_items_table()
        self.recalculate_preview()

    def collect_order_lines(self) -> list[OrderLineInput]:
        return [
            OrderLineInput(
                tire_type_id=item.tire_type_id,
                quantity=item.quantity,
            )
            for item in self.inquiry_items
            if item.quantity > 0
        ]

    def recalculate_preview(self) -> None:
        lines = self.collect_order_lines()

        if not lines:
            self.current_preview = None
            self.can_receive_label.setText("Add tire items to calculate")
            self.confirm_btn.setEnabled(False)
            self.confirmed_date.setMinimumDate(QDate.currentDate())
            self.confirmed_date.setDate(QDate.currentDate())
            self._reset_calculation_progress()
            return

        if self.preview_thread is not None and self.preview_thread.isRunning():
            self.pending_recalculate = True
            self.calculation_status_label.setText(
                "Calculation running. Latest table change will recalculate after this finishes."
            )
            return

        self.pending_recalculate = False
        self.current_preview = None
        self.confirm_btn.setEnabled(False)
        self.can_receive_label.setText("Calculating...")
        self._set_entry_controls_enabled(False)
        self._start_calculation_progress()

        self.preview_thread = QThread(self)
        self.preview_worker = CapacityPreviewWorker(lines)
        self.preview_worker.moveToThread(self.preview_thread)

        self.preview_thread.started.connect(self.preview_worker.run)

        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.failed.connect(self._on_preview_failed)

        self.preview_worker.finished.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(self.preview_thread.quit)

        self.preview_worker.finished.connect(self.preview_worker.deleteLater)
        self.preview_worker.failed.connect(self.preview_worker.deleteLater)

        self.preview_thread.finished.connect(self.preview_thread.deleteLater)
        self.preview_thread.finished.connect(self._clear_preview_thread)

        self.preview_thread.start()

    def _on_preview_finished(self, preview: SchedulePreviewResult) -> None:
        self.current_preview = preview

        min_date = preview.can_receive_datetime.date()

        self.can_receive_label.setText(fmt_datetime(preview.can_receive_datetime))

        self.confirmed_date.setMinimumDate(
            QDate(min_date.year, min_date.month, min_date.day)
        )
        self.confirmed_date.setDate(QDate(min_date.year, min_date.month, min_date.day))

        self.confirm_btn.setEnabled(True)
        self._set_entry_controls_enabled(True)
        self._finish_calculation_progress()

        if self.pending_recalculate:
            self.pending_recalculate = False
            QTimer.singleShot(150, self.recalculate_preview)

    def _on_preview_failed(self, error_message: str) -> None:
        self.current_preview = None
        self.confirm_btn.setEnabled(False)
        self.can_receive_label.setText("Calculation failed")
        self._set_entry_controls_enabled(True)
        self._reset_calculation_progress()

        QMessageBox.critical(self, "Preview Error", error_message)

    def _clear_preview_thread(self) -> None:
        self.preview_thread = None
        self.preview_worker = None

    def _generate_next_customer_code(self, session) -> str:
        next_no = (session.scalar(select(func.count(Customer.id))) or 0) + 1

        while True:
            customer_code = f"CUS-{next_no:03d}"
            exists = session.scalar(
                select(Customer.id).where(Customer.customer_code == customer_code)
            )

            if not exists:
                return customer_code

            next_no += 1

    def _resolve_customer_id_for_confirmation(self, session) -> int:
        customer_text = self.customer_combo.currentText().strip()
        selected_customer_id = self.customer_combo.currentData()
        current_index = self.customer_combo.currentIndex()

        if selected_customer_id is not None and current_index >= 0:
            selected_display_text = self.customer_combo.itemText(current_index)

            if customer_text == selected_display_text:
                return int(selected_customer_id)

        if not customer_text:
            raise ValueError(
                "Customer name is required only when confirming the order. "
                "Please type/select the customer name after the customer accepts the receive date."
            )

        existing_customer = session.scalar(
            select(Customer).where(
                func.lower(Customer.customer_name) == customer_text.lower()
            )
        )

        if existing_customer is not None:
            return existing_customer.id

        customer_code = self._generate_next_customer_code(session)

        customer = Customer(
            customer_code=customer_code,
            customer_name=customer_text,
            is_active=True,
        )

        session.add(customer)
        session.flush()

        return customer.id

    def confirm_order(self) -> None:
        lines = self.collect_order_lines()

        if not lines:
            QMessageBox.warning(
                self,
                "Missing Items",
                "Please add tire items first and calculate the live receive date.",
            )
            return

        if self.current_preview is None:
            QMessageBox.warning(
                self,
                "Preview Required",
                "Please calculate the live receive date before confirming the order.",
            )
            return

        manager_date = self.confirmed_date.date().toPython()
        received_date = QDate.currentDate().toPython()
        system_date = self.current_preview.can_receive_datetime.date()

        if manager_date < system_date:
            QMessageBox.warning(
                self,
                "Invalid Confirmed Date",
                "Manager confirmed receive date cannot be earlier than the system calculated Company Can Receive Date.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Customer Order",
            "Customer accepted the receive date. Do you want to confirm and save this order?",
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_session() as session:
                customer_id = self._resolve_customer_id_for_confirmation(session)

                order = create_confirmed_order(
                    session,
                    customer_id=customer_id,
                    order_received_date=received_date,
                    order_lines=lines,
                    manager_confirmed_receive_date=manager_date,
                    priority="NORMAL",
                    manager_note=self.note.toPlainText().strip(),
                    user_id=self.current_user_id,
                )

                order_no = order.order_no

        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return

        QMessageBox.information(
            self,
            "Order Confirmed",
            f"Order {order_no} confirmed and scheduled successfully.",
        )

        self.reset_form_after_save()

    def reset_form_after_save(self) -> None:
        self.inquiry_items.clear()
        self._refresh_items_table()
        self.note.clear()

        self.customer_combo.setCurrentIndex(-1)
        self.customer_combo.setEditText("")

        self.tire_combo.setCurrentIndex(-1)
        self.tire_combo.setEditText("")

        self.current_preview = None
        self.can_receive_label.setText("Add tire items to calculate")

        self.confirm_btn.setEnabled(False)
        self.confirmed_date.setMinimumDate(QDate.currentDate())
        self.confirmed_date.setDate(QDate.currentDate())

        self._set_entry_controls_enabled(True)
        self._reset_calculation_progress()

        self.refresh_order_no()
        self.load_master_data()

