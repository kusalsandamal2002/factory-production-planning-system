from __future__ import annotations

from datetime import date, timedelta
import math
import re

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCompleter,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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
    QInputDialog,
)
from sqlalchemy import text

from app.database import engine
from app.services.factory_planning_engine import FactoryPlanningEngine


LINE_DISPLAY_NAMES = [
    "Line-400",
    "Line-800",
    "Press-LINE",
    "NANCY PRESS",
    "400 T PRESS",
    "T 600 -01 PRESS",
    "T 600 -02 PRESS",
    "L-PRESS-1250",
    "L-PRESS-1500",
    "L-PRESS-1800",
    "ORING-PRESS",
    "NEW PRESS",
]

LINE_COLUMN_CANDIDATES = {
    "Line-400": ["line_400", "line-400", "line400"],
    "Line-800": ["line_800", "line-800", "line800"],
    "Press-LINE": ["press_line", "press-line", "press line", "press -line", "press - line"],
    "NANCY PRESS": ["nancy_press", "nancy press"],
    "400 T PRESS": ["400_t_press", "_400_t_press", "400 t press"],
    "T 600 -01 PRESS": ["t_600_01_press", "t 600 -01 press", "t 600 01 press"],
    "T 600 -02 PRESS": ["t_600_02_press", "t 600 -02 press", "t 600 02 press"],
    "L-PRESS-1250": ["l_press_1250", "l-press-1250", "l press 1250"],
    "L-PRESS-1500": ["l_press_1500", "l-press-1500", "l press 1500"],
    "L-PRESS-1800": ["l_press_1800", "l-press-1800", "l press 1800"],
    "ORING-PRESS": ["oring_press", "oring-press", "o_ring_press"],
    "NEW PRESS": ["new_press", "new press"],
}


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _clean(value) -> str:
    text_value = str(value or "").strip()
    text_value = re.sub(r"\s+", " ", text_value)
    return text_value


def _quote_ident(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


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


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value == "":
                return default
        return float(value)
    except Exception:
        return default


def _fmt_date(value) -> str:
    if value is None:
        return "Pending"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _format_int(value) -> str:
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return "0"


class SmdsColumnMap:
    def __init__(self, columns: list[str]):
        self.columns = columns
        self.norm_map: dict[str, str] = {}
        for col in columns:
            self.norm_map.setdefault(_norm_name(col), col)

    def find(self, *candidates: str) -> str | None:
        for candidate in candidates:
            norm = _norm_name(candidate)
            if norm in self.norm_map:
                return self.norm_map[norm]
        return None

    def require(self, *candidates: str) -> str:
        col = self.find(*candidates)
        if not col:
            raise RuntimeError("SMDS column missing: " + ", ".join(candidates))
        return col


class ShipmentApprovalDialog(QDialog):
    def __init__(self, parent: QWidget, item: dict):
        super().__init__(parent)
        self.setWindowTitle("Planning Manager Approval")
        self.setMinimumWidth(760)
        self.item = item
        self.approved = False

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("Planning Manager Approval Required")
        title.setObjectName("DialogTitle")
        title.setStyleSheet("font-size: 20pt; font-weight: 950; color: #0f172a;")
        root.addWidget(title)

        warning = QLabel(
            "This item is not approved for shipment planning yet. Review the SMDS planning data, correct it if needed, then approve."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff7ed; color:#c2410c; border:1px solid #fed7aa; "
            "border-radius:12px; padding:12px; font-weight:850;"
        )
        root.addWidget(warning)

        summary = QLabel(
            "SAP Code: {sap}\nDescription: {desc}\nCurrent Status: {status}".format(
                sap=item.get("sap_code", "-"),
                desc=item.get("tyre_description", "-"),
                status=item.get("approval_status", "Pending"),
            )
        )
        summary.setStyleSheet("font-weight:850; color:#334155;")
        root.addWidget(summary)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        root.addLayout(form)

        self.key_code_input = self._line(item.get("key_code"))
        self.casing_type_input = self._line(item.get("casing_type"))
        self.curing_text_input = self._line(item.get("curing_time_text"))
        self.curing_minutes_input = self._line(item.get("curing_minutes"))
        self.handling_minutes_input = self._line(item.get("handling_minutes"))
        self.day_plan_input = self._line(item.get("day_plan"))
        self.night_plan_input = self._line(item.get("night_plan"))
        self.total_plan_input = self._line(item.get("total_plan"))
        self.line_input = self._line(item.get("line"))

        fields = [
            ("Mold Key Code", self.key_code_input),
            ("Casing Type", self.casing_type_input),
            ("Curing Time Text", self.curing_text_input),
            ("Curing Minutes", self.curing_minutes_input),
            ("Handling Minutes", self.handling_minutes_input),
            ("Day Shift Qty", self.day_plan_input),
            ("Night Shift Qty", self.night_plan_input),
            ("Total Shift Qty", self.total_plan_input),
            ("Production Lines", self.line_input),
        ]
        for index, (label_text, widget) in enumerate(fields):
            label = QLabel(label_text)
            label.setStyleSheet("font-weight:800; color:#334155;")
            form.addWidget(label, index, 0)
            form.addWidget(widget, index, 1)

        buttons = QDialogButtonBox()
        self.approve_btn = buttons.addButton("Approve & Add Item", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.approve_btn.setStyleSheet(
            "background:#2563eb; color:white; border:none; border-radius:10px; "
            "padding:10px 18px; font-weight:950;"
        )
        self.cancel_btn.setStyleSheet(
            "background:#e2e8f0; color:#0f172a; border:none; border-radius:10px; "
            "padding:10px 18px; font-weight:950;"
        )
        buttons.accepted.connect(self._approve)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _line(self, value) -> QLineEdit:
        widget = QLineEdit(str(value or ""))
        widget.setMinimumHeight(36)
        return widget

    def _approve(self) -> None:
        self.approved = True
        self.item["key_code"] = self.key_code_input.text().strip()
        self.item["casing_type"] = self.casing_type_input.text().strip()
        self.item["curing_time_text"] = self.curing_text_input.text().strip()
        self.item["curing_minutes"] = _to_float(self.curing_minutes_input.text())
        self.item["handling_minutes"] = _to_float(self.handling_minutes_input.text())
        self.item["day_plan"] = _to_int(self.day_plan_input.text())
        self.item["night_plan"] = _to_int(self.night_plan_input.text())
        self.item["total_plan"] = _to_int(self.total_plan_input.text())
        self.item["line"] = self.line_input.text().strip()
        self.item["approval_status"] = "Approved"
        self.accept()


class OrderEntryPage(QWidget):
    def __init__(
        self,
        current_user=None,
        on_shipment_saved=None,
        *args,
        **kwargs,
    ):
        super().__init__()
        self.on_shipment_saved = on_shipment_saved
        self.current_user = current_user
        self.current_items: list[dict] = []
        self.master_items: list[dict] = []
        self.planner = FactoryPlanningEngine(
            start_date=date.today()
        )
        self.current_shipment_id: int | None = None
        self.existing_item_add_mode = False
        self.existing_shipment_context: dict = {}
        self.existing_saved_items: list[dict] = []
        self.smds_columns: SmdsColumnMap | None = None

        self.shipment_name_input = QLineEdit()
        self.shipment_name_input.setPlaceholderText(
            "Enter a clear shipment name"
        )
        self.shipment_name_input.textChanged.connect(
            self.load_previous_shipments
        )

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText(
            "Customer, destination or delivery point"
        )

        self.target_date_checkbox = QCheckBox(
            "Use a specific target date"
        )
        self.target_date_checkbox.setObjectName(
            "TargetDateCheck"
        )
        self.target_date_checkbox.setToolTip(
            "Enable this only when the manager has "
            "specified a required delivery target date."
        )

        self.target_date_input = QDateEdit()
        self.target_date_input.setCalendarPopup(True)
        self.target_date_input.setDisplayFormat(
            "yyyy-MM-dd"
        )
        self.target_date_input.setDate(
            QDate.currentDate()
        )
        self.target_date_input.setEnabled(False)
        self.target_date_input.setMinimumWidth(150)

        self.target_date_mode_label = QLabel(
            "Automatic: Factory Can Receive Date will "
            "be saved as the Target Date."
        )
        self.target_date_mode_label.setObjectName(
            "TargetRule"
        )
        self.target_date_mode_label.setWordWrap(True)

        self.target_preview_label = QLabel(
            "Add shipment items to calculate the "
            "delivery promise."
        )
        self.target_preview_label.setObjectName(
            "PromiseBanner"
        )
        self.target_preview_label.setWordWrap(True)

        self.target_date_checkbox.toggled.connect(
            self._on_target_mode_changed
        )
        self.target_date_input.dateChanged.connect(
            self.update_summary
        )
        self.target_date_checkbox.toggled.connect(
            self._replan_cart_after_target_change
        )
        self.target_date_input.dateChanged.connect(
            self._replan_cart_after_target_change
        )

        self.remarks_input = QTextEdit()
        self.remarks_input.setPlaceholderText(
            "Remarks, delivery instructions or "
            "planning notes"
        )
        self.remarks_input.setMinimumHeight(92)

        self.item_search_input = QLineEdit()
        self.item_search_input.setPlaceholderText(
            "Search approved SAP code or tyre "
            "description from SMDS..."
        )
        self.item_search_input.textChanged.connect(
            self.update_item_preview
        )

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(
            1,
            999999999,
        )
        self.quantity_input.setValue(1)

        self.add_item_btn = QPushButton(
            "Add Item"
        )
        self.add_item_btn.setObjectName(
            "PrimaryButton"
        )
        self.add_item_btn.clicked.connect(
            self.add_item
        )

        self.save_btn = QPushButton(
            "Save Shipment"
        )
        self.save_btn.setObjectName(
            "PrimaryButton"
        )
        self.save_btn.clicked.connect(
            self.save_shipment
        )

        self.clear_btn = QPushButton(
            "Clear Form"
        )
        self.clear_btn.setObjectName(
            "SecondaryButton"
        )
        self.clear_btn.clicked.connect(
            self.clear_form
        )

        self.refresh_btn = QPushButton(
            "Refresh SMDS"
        )
        self.refresh_btn.setObjectName(
            "SecondaryButton"
        )
        self.refresh_btn.clicked.connect(
            self.refresh_master_items
        )

        self.back_to_shipment_btn = QPushButton(
            "← Back to Shipment Details"
        )
        self.back_to_shipment_btn.setObjectName(
            "SecondaryButton"
        )
        self.back_to_shipment_btn.setVisible(False)
        self.back_to_shipment_btn.clicked.connect(
            self.return_to_shipment_details
        )

        self.preview_code_label = QLabel(
            "No item selected."
        )
        self.preview_desc_label = QLabel(
            "Search SAP code or tyre description "
            "to preview item details."
        )
        self.preview_available_label = QLabel("")
        self.preview_planning_label = QLabel("")

        self.items_table = QTableWidget(
            0,
            9,
        )
        self.items_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Qty",
            "Stock",
            "Prod Qty",
            "Cavities",
            "Item Receive Date",
            "Reason",
            "Action",
        ])

        self.existing_saved_items_table = QTableWidget(
            0,
            12,
        )
        self.existing_saved_items_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Order Qty",
            "Stock",
            "Production Required",
            "Produced",
            "Completed",
            "Remaining",
            "Cavities",
            "Daily Capacity",
            "Receive Date",
            "Status",
        ])

        self.previous_table = QTableWidget(
            0,
            6,
        )
        self.previous_table.setHorizontalHeaderLabels([
            "Shipment Name",
            "Shipment ID",
            "Target",
            "Factory Receive",
            "Items",
            "Promise",
        ])

        self.summary_items_value = QLabel("0")
        self.summary_qty_value = QLabel("0")
        self.summary_stock_value = QLabel("0")
        self.summary_stock_coverage_value = QLabel(
            "0.0%"
        )
        self.summary_factory_out_value = QLabel(
            "Pending"
        )
        self.summary_target_value = QLabel(
            "Pending"
        )
        self.summary_shipment_label = QLabel(
            "Shipment: -"
        )
        self.summary_target_source_label = QLabel(
            "Target source: Automatic"
        )
        self.summary_promise_value = QLabel(
            "PENDING CALCULATION"
        )
        self.summary_promise_value.setObjectName(
            "PromiseSummary"
        )
        self.summary_promise_value.setWordWrap(True)
        self.summary_promise_value.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self._apply_styles()
        self._build_ui()
        self._setup_tables()
        self.ensure_tables()
        self.refresh_master_items(
            show_warning=False
        )
        self.load_previous_shipments()
        self._on_target_mode_changed(False)
        self.update_summary()

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
                background:#ffffff;
                border:1px solid #e2e8f0;
                border-radius:16px;
            }

            QLabel#PageTitle {
                color:#0f172a;
                font-size:22pt;
                font-weight:950;
            }

            QLabel#PageHint,
            QLabel#Hint {
                color:#64748b;
                font-size:9.5pt;
                font-weight:650;
            }

            QLabel#SectionTitle {
                color:#0f172a;
                font-size:16pt;
                font-weight:950;
            }

            QLabel#FieldLabel {
                color:#334155;
                font-size:9pt;
                font-weight:850;
            }

            QLabel#PreviewTitle {
                color:#0f172a;
                font-size:11pt;
                font-weight:950;
            }

            QLabel#PreviewText {
                color:#475569;
                font-size:9.2pt;
                font-weight:650;
            }

            QLabel#MetricValue {
                color:#0f172a;
                font-size:18pt;
                font-weight:950;
            }

            QLabel#MetricLabel {
                color:#64748b;
                font-size:8.5pt;
                font-weight:850;
            }

            QLabel#TargetRule {
                background:#eff6ff;
                color:#1d4ed8;
                border:1px solid #bfdbfe;
                border-radius:10px;
                padding:10px 12px;
                font-size:9pt;
                font-weight:800;
            }

            QLabel#PromiseBanner,
            QLabel#PromiseSummary {
                background:#fef3c7;
                color:#92400e;
                border:1px solid #fde68a;
                border-radius:10px;
                padding:10px 12px;
                font-size:9.2pt;
                font-weight:950;
            }

            QLabel#HeaderBadgeBlue {
                background:#dbeafe;
                color:#1d4ed8;
                border:1px solid #bfdbfe;
                border-radius:8px;
                padding:6px 10px;
                font-size:8.5pt;
                font-weight:950;
            }

            QLabel#HeaderBadgeGreen {
                background:#dcfce7;
                color:#047857;
                border:1px solid #bbf7d0;
                border-radius:8px;
                padding:6px 10px;
                font-size:8.5pt;
                font-weight:950;
            }

            QLabel#ExistingShipmentContext {
                background:#eff6ff;
                color:#1e3a8a;
                border:1px solid #bfdbfe;
                border-radius:10px;
                padding:10px 12px;
                font-size:9.2pt;
                font-weight:850;
            }

            QLineEdit[existingLocked="true"],
            QTextEdit[existingLocked="true"] {
                background:#f8fafc;
                color:#334155;
                border:1px solid #dbe4f0;
            }

            QLineEdit,
            QTextEdit,
            QSpinBox,
            QDateEdit {
                background:#ffffff;
                color:#0f172a;
                border:1px solid #cbd5e1;
                border-radius:10px;
                padding:8px 11px;
                font-size:9.5pt;
                font-weight:650;
                min-height:24px;
            }

            QLineEdit:focus,
            QTextEdit:focus,
            QSpinBox:focus,
            QDateEdit:focus {
                border:1px solid #2563eb;
            }

            QDateEdit:disabled {
                background:#f1f5f9;
                color:#94a3b8;
            }

            QCheckBox#TargetDateCheck {
                color:#0f172a;
                font-size:9.5pt;
                font-weight:850;
                spacing:8px;
            }

            QCheckBox#TargetDateCheck::indicator {
                width:18px;
                height:18px;
            }

            QPushButton#PrimaryButton {
                background:#2563eb;
                color:#ffffff;
                border:none;
                border-radius:10px;
                padding:10px 18px;
                font-weight:950;
                min-height:26px;
            }

            QPushButton#PrimaryButton:hover {
                background:#1d4ed8;
            }

            QPushButton#SecondaryButton {
                background:#e2e8f0;
                color:#0f172a;
                border:none;
                border-radius:10px;
                padding:10px 18px;
                font-weight:950;
                min-height:26px;
            }

            QPushButton#SecondaryButton:hover {
                background:#cbd5e1;
            }

            QPushButton#DangerButton {
                background:#fee2e2;
                color:#991b1b;
                border:none;
                border-radius:9px;
                padding:7px 10px;
                font-weight:950;
            }

            QPushButton#SmallButton {
                background:#eff6ff;
                color:#1d4ed8;
                border:1px solid #bfdbfe;
                border-radius:8px;
                padding:7px 10px;
                font-weight:900;
            }

            QTableWidget {
                background:#ffffff;
                color:#0f172a;
                border:1px solid #e2e8f0;
                border-radius:12px;
                gridline-color:#e2e8f0;
                alternate-background-color:#f8fafc;
                selection-background-color:#dbeafe;
            }

            QTableWidget::item {
                padding:7px 8px;
                border:none;
            }

            QHeaderView::section {
                background:#f1f5f9;
                color:#1e293b;
                border:none;
                border-right:1px solid #e2e8f0;
                border-bottom:1px solid #e2e8f0;
                padding:8px;
                font-weight:950;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._header_card())
        root.addWidget(self._shipment_form_card())
        item_and_readiness = QHBoxLayout()
        item_and_readiness.setSpacing(16)
        item_and_readiness.addWidget(self._add_item_card(), 3)
        item_and_readiness.addWidget(self._summary_card(), 1)
        root.addLayout(item_and_readiness)
        root.addWidget(self._items_card(), 1)

        self.existing_saved_items_card = (
            self._existing_saved_items_card()
        )
        self.existing_saved_items_card.setVisible(False)
        root.addWidget(
            self.existing_saved_items_card,
            1,
        )

    def _header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(
            22,
            18,
            22,
            18,
        )
        layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(5)

        self.page_title_label = QLabel(
            "Shipment Order Entry"
        )
        self.page_title_label.setObjectName(
            "PageTitle"
        )

        self.page_hint_label = QLabel(
            "Create a production-ready shipment from "
            "manager-approved SMDS items. Factory "
            "receive dates, stock coverage and delivery "
            "promise are calculated before saving."
        )
        self.page_hint_label.setObjectName(
            "PageHint"
        )
        self.page_hint_label.setWordWrap(True)

        badges = QHBoxLayout()
        badges.setSpacing(8)

        self.approved_badge_label = QLabel(
            "APPROVED SMDS ITEMS ONLY"
        )
        self.approved_badge_label.setObjectName(
            "HeaderBadgeGreen"
        )

        self.target_badge_label = QLabel(
            "TARGET DATE OPTIONAL"
        )
        self.target_badge_label.setObjectName(
            "HeaderBadgeBlue"
        )

        badges.addWidget(
            self.approved_badge_label
        )
        badges.addWidget(
            self.target_badge_label
        )
        badges.addStretch(1)

        self.existing_context_label = QLabel("")
        self.existing_context_label.setObjectName(
            "ExistingShipmentContext"
        )
        self.existing_context_label.setWordWrap(True)
        self.existing_context_label.setVisible(False)

        title_box.addWidget(
            self.page_title_label
        )
        title_box.addWidget(
            self.page_hint_label
        )
        title_box.addLayout(badges)
        title_box.addWidget(
            self.existing_context_label
        )

        layout.addLayout(title_box, 1)
        layout.addWidget(
            self.back_to_shipment_btn
        )
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.clear_btn)
        layout.addWidget(self.save_btn)

        return card

    def _shipment_form_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("FormCard")

        layout = QGridLayout(card)
        layout.setContentsMargins(
            18,
            16,
            18,
            18,
        )
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        self.shipment_form_title = QLabel(
            "Shipment Information"
        )
        self.shipment_form_title.setObjectName(
            "SectionTitle"
        )

        self.shipment_form_hint = QLabel(
            "Set a target date only when the manager "
            "has confirmed one. When it is not set, "
            "the calculated Factory Can Receive Date "
            "becomes the Target Date automatically."
        )
        self.shipment_form_hint.setObjectName(
            "Hint"
        )
        self.shipment_form_hint.setWordWrap(True)

        layout.addWidget(
            self.shipment_form_title,
            0,
            0,
            1,
            2,
        )
        layout.addWidget(
            self.shipment_form_hint,
            1,
            0,
            1,
            2,
        )

        name_label = QLabel(
            "Shipment Name"
        )
        name_label.setObjectName(
            "FieldLabel"
        )
        customer_label = QLabel(
            "Customer / Destination"
        )
        customer_label.setObjectName(
            "FieldLabel"
        )

        layout.addWidget(
            name_label,
            2,
            0,
        )
        layout.addWidget(
            customer_label,
            2,
            1,
        )
        layout.addWidget(
            self.shipment_name_input,
            3,
            0,
        )
        layout.addWidget(
            self.customer_input,
            3,
            1,
        )

        target_label = QLabel(
            "Target Date"
        )
        target_label.setObjectName(
            "FieldLabel"
        )
        rule_label = QLabel(
            "Target Date Rule"
        )
        rule_label.setObjectName(
            "FieldLabel"
        )

        layout.addWidget(
            target_label,
            4,
            0,
        )
        layout.addWidget(
            rule_label,
            4,
            1,
        )

        target_controls = QWidget()
        target_controls_layout = QHBoxLayout(
            target_controls
        )
        target_controls_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        target_controls_layout.setSpacing(10)
        target_controls_layout.addWidget(
            self.target_date_checkbox
        )
        target_controls_layout.addWidget(
            self.target_date_input
        )
        target_controls_layout.addStretch(1)

        layout.addWidget(
            target_controls,
            5,
            0,
        )
        layout.addWidget(
            self.target_date_mode_label,
            5,
            1,
        )

        layout.addWidget(
            self.target_preview_label,
            6,
            0,
            1,
            2,
        )

        remarks_label = QLabel(
            "Remarks / Delivery Instructions"
        )
        remarks_label.setObjectName(
            "FieldLabel"
        )
        layout.addWidget(
            remarks_label,
            7,
            0,
            1,
            2,
        )
        layout.addWidget(
            self.remarks_input,
            8,
            0,
            1,
            2,
        )

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        return card

    def _add_item_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("FormCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        self.add_item_section_title = QLabel(
            "Add Shipment Item"
        )
        self.add_item_section_title.setObjectName(
            "SectionTitle"
        )
        self.add_item_section_hint = QLabel(
            "Search from SMDS. Only approved items "
            "can enter the cart."
        )
        self.add_item_section_hint.setObjectName(
            "Hint"
        )
        self.add_item_section_hint.setWordWrap(True)
        layout.addWidget(
            self.add_item_section_title
        )
        layout.addWidget(
            self.add_item_section_hint
        )
        form = QGridLayout()
        form.setHorizontalSpacing(12)
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
        layout.setSpacing(4)
        title = QLabel("Selected Item Preview")
        title.setObjectName("PreviewTitle")
        for label in [self.preview_code_label, self.preview_desc_label, self.preview_available_label, self.preview_planning_label]:
            label.setObjectName("PreviewText")
            label.setWordWrap(True)
            layout.addWidget(label) if label is not self.preview_code_label else None
        layout.insertWidget(0, title)
        return card

    def _previous_shipments_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("Previous Shipments")
        title.setObjectName("SectionTitle")
        hint = QLabel("Saved shipments from database. Double-click to load.")
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
        layout.setSpacing(10)
        self.items_section_title = QLabel(
            "Shipment Cart"
        )
        self.items_section_title.setObjectName(
            "SectionTitle"
        )
        self.items_section_hint = QLabel(
            "Item receive date is calculated when "
            "quantity is saved into the cart."
        )
        self.items_section_hint.setObjectName(
            "Hint"
        )
        self.items_section_hint.setWordWrap(True)
        layout.addWidget(
            self.items_section_title
        )
        layout.addWidget(
            self.items_section_hint
        )
        layout.addWidget(self.items_table, 1)
        return card

    def _existing_saved_items_card(
        self,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            18,
            16,
            18,
            18,
        )
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel(
            "Already Saved Shipment Items"
        )
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "These items are already saved in the shipment. "
            "They are shown for reference only and will not "
            "be duplicated or rewritten when new items are added."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        self.existing_saved_items_badge = QLabel(
            "0 saved items"
        )
        self.existing_saved_items_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.existing_saved_items_badge.setStyleSheet(
            "background:#dcfce7; color:#047857; "
            "border:1px solid #bbf7d0; "
            "border-radius:10px; padding:7px 12px; "
            "font-weight:950;"
        )

        title_row.addLayout(title_box, 1)
        title_row.addWidget(
            self.existing_saved_items_badge
        )

        layout.addLayout(title_row)
        layout.addWidget(
            self.existing_saved_items_table,
            1,
        )
        return card

    def _summary_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("SummaryCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            18,
            16,
            18,
            18,
        )
        layout.setSpacing(12)

        title = QLabel(
            "Shipment Readiness"
        )
        title.setObjectName("SectionTitle")

        self.summary_shipment_label.setObjectName(
            "Hint"
        )
        self.summary_target_source_label.setObjectName(
            "Hint"
        )

        layout.addWidget(title)
        layout.addWidget(
            self.summary_shipment_label
        )
        layout.addWidget(
            self.summary_target_source_label
        )

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)

        metrics.addWidget(
            self._metric_box(
                self.summary_items_value,
                "Total Items",
            ),
            0,
            0,
        )
        metrics.addWidget(
            self._metric_box(
                self.summary_qty_value,
                "Total Qty",
            ),
            0,
            1,
        )
        metrics.addWidget(
            self._metric_box(
                self.summary_stock_value,
                "Stock Allocated",
            ),
            1,
            0,
        )
        metrics.addWidget(
            self._metric_box(
                self.summary_stock_coverage_value,
                "Stock Coverage",
            ),
            1,
            1,
        )
        metrics.addWidget(
            self._metric_box(
                self.summary_factory_out_value,
                "Factory Can Receive",
            ),
            2,
            0,
        )
        metrics.addWidget(
            self._metric_box(
                self.summary_target_value,
                "Target Date",
            ),
            2,
            1,
        )

        layout.addLayout(metrics)
        layout.addWidget(
            self.summary_promise_value
        )
        layout.addStretch(1)

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
        self.items_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.items_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.items_table.verticalHeader().setVisible(
            False
        )
        self.items_table.setAlternatingRowColors(True)
        self.items_table.setWordWrap(True)

        header = self.items_table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Fixed,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )

        for col in range(2, 9):
            header.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        self.items_table.setColumnWidth(
            0,
            105,
        )
        self.items_table.setColumnWidth(
            7,
            220,
        )

        saved_table = (
            self.existing_saved_items_table
        )
        saved_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        saved_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        saved_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        saved_table.verticalHeader().setVisible(
            False
        )
        saved_table.setAlternatingRowColors(True)
        saved_table.setWordWrap(False)
        saved_table.setSortingEnabled(True)
        saved_table.verticalHeader().setDefaultSectionSize(
            42
        )

        saved_header = (
            saved_table.horizontalHeader()
        )
        saved_header.setStretchLastSection(False)

        saved_widths = {
            0: 105,
            1: 300,
            2: 86,
            3: 78,
            4: 125,
            5: 82,
            6: 88,
            7: 88,
            8: 78,
            9: 105,
            10: 118,
            11: 110,
        }

        for column in range(
            saved_table.columnCount()
        ):
            saved_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )
            saved_table.setColumnWidth(
                column,
                saved_widths[column],
            )

        self.previous_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.previous_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.previous_table.verticalHeader().setVisible(
            False
        )
        self.previous_table.setAlternatingRowColors(
            True
        )
        self.previous_table.setWordWrap(True)
        self.previous_table.itemDoubleClicked.connect(
            lambda *_: self.load_selected_previous_shipment()
        )

        prev_header = (
            self.previous_table.horizontalHeader()
        )
        prev_header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        prev_header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )

        for col in range(2, 6):
            prev_header.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        self.previous_table.setColumnWidth(
            5,
            180,
        )
        self.previous_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

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
                    shipment_id INTEGER NOT NULL
                        REFERENCES mpps_shipments(id)
                        ON DELETE CASCADE,
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
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "shipment_name VARCHAR(255) "
                    "NOT NULL DEFAULT ''"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "manager_order_date DATE"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "target_date DATE"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "plan_date DATE"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "factory_out_date DATE"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "factory_can_receive_date DATE"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "delivery_status VARCHAR(80) "
                    "NOT NULL DEFAULT ''"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "delay_days INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "early_days INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "total_qty INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "completed_qty INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "progress_pct NUMERIC(6,2) "
                    "NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "planning_status VARCHAR(80) "
                    "NOT NULL DEFAULT ''"
                ),
                (
                    "ALTER TABLE mpps_shipments "
                    "ADD COLUMN IF NOT EXISTS "
                    "planning_note TEXT NOT NULL DEFAULT ''"
                ),
                (
                    "ALTER TABLE mpps_shipment_items "
                    "ADD COLUMN IF NOT EXISTS "
                    "stock_allocated_qty INTEGER "
                    "NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipment_items "
                    "ADD COLUMN IF NOT EXISTS "
                    "production_required_qty INTEGER "
                    "NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipment_items "
                    "ADD COLUMN IF NOT EXISTS "
                    "allocated_cavity_count INTEGER "
                    "NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipment_items "
                    "ADD COLUMN IF NOT EXISTS "
                    "production_days INTEGER "
                    "NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mpps_shipment_items "
                    "ADD COLUMN IF NOT EXISTS "
                    "item_receive_date DATE"
                ),
                (
                    "ALTER TABLE mpps_shipment_items "
                    "ADD COLUMN IF NOT EXISTS "
                    "schedule_reason TEXT "
                    "NOT NULL DEFAULT ''"
                ),
            ]:
                connection.execute(text(sql))

            connection.execute(text("""
                UPDATE mpps_shipments
                SET
                    factory_can_receive_date = COALESCE(
                        factory_can_receive_date,
                        factory_out_date
                    ),
                    target_date = COALESCE(
                        target_date,
                        plan_date,
                        manager_order_date,
                        factory_out_date
                    ),
                    plan_date = COALESCE(
                        plan_date,
                        target_date,
                        manager_order_date,
                        factory_out_date
                    ),
                    manager_order_date = COALESCE(
                        manager_order_date,
                        target_date,
                        plan_date,
                        factory_out_date
                    )
                WHERE
                    factory_can_receive_date IS NULL
                    OR target_date IS NULL
                    OR plan_date IS NULL
                    OR manager_order_date IS NULL
            """))

    def _get_smds_columns(self) -> SmdsColumnMap:
        with engine.connect() as connection:
            columns = [
                str(row[0])
                for row in connection.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'smds'
                    ORDER BY ordinal_position
                """)).all()
            ]
        if not columns:
            raise RuntimeError("SMDS table was not found or has no columns.")
        self.smds_columns = SmdsColumnMap(columns)
        return self.smds_columns

    def refresh_master_items(self, show_warning: bool = True) -> None:
        try:
            self.master_items = self.load_master_items()
        except Exception as exc:
            self.master_items = []
            if show_warning:
                QMessageBox.critical(self, "SMDS Load Failed", str(exc))

        values = ["{sap} - {desc}".format(sap=item["sap_code"], desc=item["tyre_description"]) for item in self.master_items]
        completer = QCompleter(values)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item_search_input.setCompleter(completer)

        if show_warning and not self.master_items:
            QMessageBox.warning(self, "SMDS Missing", "No tyre items were found in the SMDS table.")

    def load_master_items(self) -> list[dict]:
        columns = self._get_smds_columns()
        sap_col = columns.require("sap_code", "sap code", "sap")
        desc_col = columns.find("material_description", "material description", "tyre_description", "description")
        if not desc_col:
            desc_col = sap_col

        query = "SELECT * FROM smds WHERE {sap} IS NOT NULL AND TRIM({sap}::text) <> '' ORDER BY {sap} ASC".format(
            sap=_quote_ident(sap_col)
        )
        with engine.connect() as connection:
            rows = connection.execute(text(query)).mappings().all()

        result: list[dict] = []
        for row in rows:
            item = self._map_smds_row(dict(row), columns, sap_col, desc_col)
            if item["sap_code"]:
                result.append(item)
        return result

    def _map_smds_row(self, row: dict, columns: SmdsColumnMap, sap_col: str, desc_col: str) -> dict:
        def get(*names, default=""):
            col = columns.find(*names)
            if not col:
                return default
            return row.get(col, default)

        line_text = _clean(get("line"))
        detected_lines = []
        for display_name, candidates in LINE_COLUMN_CANDIDATES.items():
            col = columns.find(*candidates)
            if not col:
                continue
            value = _clean(row.get(col, ""))
            if value.lower() in {"ok", "yes", "y", "1", "true", "x"}:
                detected_lines.append(display_name)
        if detected_lines:
            line_text = ", ".join(detected_lines)

        approval = _clean(get("planning_manager_approval_status", "approval_status", default="Pending")) or "Pending"
        return {
            "sap_code": _clean(row.get(sap_col, "")),
            "tyre_description": _clean(row.get(desc_col, "")),
            "key_code": _clean(get("key_code", "key code", "mold_key_code")),
            "casing_type": _clean(get("casing_type", "casing type")),
            "line": line_text,
            "day_plan": _to_int(get("day_plan", "day plan")),
            "night_plan": _to_int(get("night_plan", "night plan")),
            "total_plan": _to_int(get("total_plan", "total plan")),
            "curing_time_text": _clean(get("normal_curing_time_text", "curing_cycle", "curing cycle")),
            "curing_minutes": _to_float(get("normal_curing_minutes", "curing_minutes", "curing minutes")),
            "handling_minutes": _to_float(get("handling_minutes", "handling_time", "handling time")),
            "approval_status": approval,
        }

    def update_item_preview(self) -> None:
        item = self.find_master_item(self.item_search_input.text().strip())
        if not item:
            self.preview_code_label.setText("No item selected.")
            self.preview_desc_label.setText("Search SAP code or tyre description to preview item details.")
            self.preview_available_label.setText("")
            self.preview_planning_label.setText("")
            return
        available_stock = self.get_unallocated_stock(item["sap_code"])
        self.preview_code_label.setText("SAP Code: {sap} | Status: {status}".format(sap=item["sap_code"], status=item.get("approval_status", "Pending")))
        self.preview_desc_label.setText("Description: " + item.get("tyre_description", ""))
        self.preview_available_label.setText("Unallocated Stock: " + _format_int(available_stock))
        self.preview_planning_label.setText(
            "Line: {line} | Mold: {mold} | Casing: {casing} | Total Plan: {plan}".format(
                line=item.get("line") or "-",
                mold=item.get("key_code") or "-",
                casing=item.get("casing_type") or "-",
                plan=_format_int(item.get("total_plan")),
            )
        )

    def find_master_item(self, value: str) -> dict | None:
        if not value:
            return None
        search = value.strip().lower()
        sap_from_combo = value.split(" - ", 1)[0].strip().lower()
        for item in self.master_items:
            if str(item["sap_code"]).lower() in {search, sap_from_combo}:
                return dict(item)
        for item in self.master_items:
            if search in str(item["sap_code"]).lower() or search in str(item["tyre_description"]).lower():
                return dict(item)
        return None

    def add_item(self) -> None:
        item = self.find_master_item(self.item_search_input.text().strip())
        if not item:
            QMessageBox.warning(self, "Item Not Found", "Please select a valid SMDS tyre item.")
            self.item_search_input.setFocus()
            return

        # V10.4: planning-manager approval is retained as audit metadata only;
        # it no longer blocks shipment entry or downstream planning.

        qty = int(self.quantity_input.value())
        sap_code = str(item["sap_code"])
        for existing in self.current_items:
            if (
                existing["sap_code"] == sap_code
                and (
                    not self.existing_item_add_mode
                    or existing.get(
                        "_new_addition"
                    )
                )
            ):
                existing["quantity"] += qty
                self.recalculate_item(existing)
                self.refresh_items_table()
                self.item_search_input.clear()
                self.quantity_input.setValue(1)
                return

        cart_item = {
            "sap_code": sap_code,
            "item_description": str(
                item["tyre_description"]
            ),
            "quantity": qty,
            "produced_qty": 0,
            "smds": item,
            "_new_addition": (
                self.existing_item_add_mode
            ),
        }
        self.recalculate_item(cart_item)
        self.current_items.append(cart_item)
        self.refresh_items_table()
        self.item_search_input.clear()
        self.quantity_input.setValue(1)

    def save_item_approval_to_smds(self, item: dict) -> None:
        columns = self._get_smds_columns()
        sap_col = columns.require("sap_code", "sap code", "sap")
        assignments = []
        params = {"sap_code": item["sap_code"]}
        update_map = [
            (("planning_manager_approval_status", "approval_status"), "approval_status", "Approved"),
            (("key_code", "key code"), "key_code", item.get("key_code", "")),
            (("casing_type", "casing type"), "casing_type", item.get("casing_type", "")),
            (("line",), "line", item.get("line", "")),
            (("normal_curing_time_text", "curing_cycle", "curing cycle"), "curing_text", item.get("curing_time_text", "")),
            (("normal_curing_minutes", "curing_minutes"), "curing_minutes", item.get("curing_minutes", 0)),
            (("handling_minutes", "handling_time", "handling time"), "handling_minutes", item.get("handling_minutes", 0)),
            (("day_plan", "day plan"), "day_plan", item.get("day_plan", 0)),
            (("night_plan", "night plan"), "night_plan", item.get("night_plan", 0)),
            (("total_plan", "total plan"), "total_plan", item.get("total_plan", 0)),
        ]
        for candidates, param_name, value in update_map:
            col = columns.find(*candidates)
            if col:
                assignments.append("{col} = :{param}".format(col=_quote_ident(col), param=param_name))
                params[param_name] = value
        if not assignments:
            return
        sql = "UPDATE smds SET {assignments} WHERE {sap_col}::text = :sap_code".format(
            assignments=", ".join(assignments),
            sap_col=_quote_ident(sap_col),
        )
        with engine.begin() as connection:
            connection.execute(text(sql), params)

    def _manual_preview_target_date(self):
        if self.target_date_checkbox.isChecked():
            return self.target_date_input.date().toPython()
        return None

    def recalculate_current_cart(
        self,
        extra_item: dict | None = None,
    ) -> None:
        plan_items = list(
            self.current_items
        )

        if (
            extra_item is not None
            and not any(
                candidate is extra_item
                for candidate in plan_items
            )
        ):
            plan_items.append(extra_item)

        if not plan_items:
            return

        preview_items = [
            {
                "sap_code": str(
                    item.get("sap_code")
                    or ""
                ).strip(),
                "item_description": str(
                    item.get(
                        "item_description"
                    )
                    or ""
                ),
                "quantity": int(
                    item.get("quantity")
                    or 0
                ),
                "produced_qty": int(
                    item.get("produced_qty")
                    or 0
                ),
            }
            for item in plan_items
        ]

        manual_target_date = (
            self._manual_preview_target_date()
        )

        exclude_shipment_id = (
            self.current_shipment_id
            if not self.existing_item_add_mode
            else None
        )
        draft_created_at = (
            self.existing_shipment_context.get(
                "created_at"
            )
            if self.existing_item_add_mode
            else None
        )
        target_is_manual = (
            bool(
                self.existing_shipment_context.get(
                    "target_date_is_manual"
                )
            )
            if self.existing_item_add_mode
            else (
                manual_target_date is not None
            )
        )

        try:
            self.planner = FactoryPlanningEngine(
                start_date=date.today()
            )
            results = (
                self.planner.calculate_cart_items(
                    preview_items,
                    target_date=manual_target_date,
                    exclude_shipment_id=(
                        exclude_shipment_id
                    ),
                    target_date_is_manual=(
                        target_is_manual
                    ),
                    draft_created_at=(
                        draft_created_at
                    ),
                )
            )
        except Exception as exc:
            for item in plan_items:
                self._set_pending(
                    item,
                    (
                        "Cumulative priority preview "
                        f"failed: {exc}"
                    ),
                )
            return

        for item, result in zip(
            plan_items,
            results,
        ):
            item["stock_allocated_qty"] = int(
                result.get(
                    "stock_allocated_qty"
                )
                or 0
            )
            item["production_required_qty"] = int(
                result.get(
                    "production_required_qty"
                )
                or 0
            )
            item["allocated_cavity_count"] = int(
                result.get(
                    "allocated_cavity_count"
                )
                or 0
            )
            item["daily_capacity"] = int(
                result.get("daily_capacity")
                or 0
            )
            item["production_days"] = int(
                result.get("production_days")
                or 0
            )
            item["item_receive_date"] = (
                result.get("receive_date")
                or result.get(
                    "item_receive_date"
                )
            )
            item["item_status"] = str(
                result.get("status")
                or result.get("item_status")
                or ""
            )
            reason = str(
                result.get("reason")
                or result.get(
                    "schedule_reason"
                )
                or ""
            )
            item["schedule_reason"] = (
                "Priority queue: "
                + reason
            )


    def recalculate_item(
        self,
        item: dict,
    ) -> None:
        self.recalculate_current_cart(
            extra_item=item
        )

    def _replan_cart_after_target_change(
        self,
        *_args,
    ) -> None:
        if not self.current_items:
            self.update_summary()
            return

        self.recalculate_current_cart()
        self.refresh_items_table()

    def _set_pending(self, item: dict, reason: str) -> None:
        item["allocated_cavity_count"] = 0
        item["production_days"] = 0
        item["item_receive_date"] = None
        item["schedule_reason"] = reason

    def get_unallocated_stock(self, sap_code: str) -> int:
        available = 0
        allocated = 0
        try:
            with engine.connect() as connection:
                available = int(connection.execute(text("""
                    SELECT COALESCE(MAX(GREATEST(fg_stock, 0) + GREATEST(qc_stock, 0)), 0)
                    FROM mpps_sap_stock_items
                    WHERE sap_code = :sap_code
                """), {"sap_code": sap_code}).scalar() or 0)
        except Exception:
            available = 0
        try:
            with engine.connect() as connection:
                allocated = int(connection.execute(text("""
                    SELECT COALESCE(SUM(i.stock_allocated_qty), 0)
                    FROM mpps_shipment_items i
                    JOIN mpps_shipments s ON s.id = i.shipment_id
                    WHERE i.sap_code = :sap_code
                      AND COALESCE(s.status, 'Planned') IN ('Planned', 'Pending', 'Open')
                """), {"sap_code": sap_code}).scalar() or 0)
        except Exception:
            allocated = 0
        return max(0, available - allocated)

    def get_available_mold_count(self, key_code: str) -> int:
        key_code = _clean(key_code)
        if not key_code:
            return 0
        try:
            with engine.connect() as connection:
                return int(connection.execute(text("""
                    SELECT COALESCE(SUM(mold_count), 0)
                    FROM mold_master
                    WHERE LOWER(TRIM(mold_key_code)) = LOWER(TRIM(:key_code))
                      AND LOWER(COALESCE(status, 'Active')) = 'active'
                """), {"key_code": key_code}).scalar() or 0)
        except Exception:
            return 0

    def get_available_casing_count(self, casing_type: str) -> int:
        casing_type = _clean(casing_type)
        if not casing_type:
            return 0
        try:
            with engine.connect() as connection:
                count = int(connection.execute(text("""
                    SELECT COALESCE(COUNT(*), 0)
                    FROM casing_units
                    WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                      AND LOWER(COALESCE(condition_status, 'Active')) = 'active'
                      AND LOWER(COALESCE(stock_status, 'Free')) = 'free'
                """), {"casing_type": casing_type}).scalar() or 0)
                if count > 0:
                    return count
        except Exception:
            pass
        try:
            with engine.connect() as connection:
                return int(connection.execute(text("""
                    SELECT COALESCE(SUM(available_casing_count), 0)
                    FROM casing_master
                    WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                """), {"casing_type": casing_type}).scalar() or 0)
        except Exception:
            return 0

    def get_available_line_cavity_count(self, line_text: str) -> int:
        lines = [part.strip() for part in re.split(r"[,/;|]+", str(line_text or "")) if part.strip()]
        if not lines:
            return 0
        total = 0
        for line_name in lines:
            try:
                with engine.connect() as connection:
                    total += int(connection.execute(text("""
                        SELECT COALESCE(COUNT(*), 0)
                        FROM production_line_cavities
                        WHERE LOWER(TRIM(line_name)) = LOWER(TRIM(:line_name))
                          AND LOWER(COALESCE(status, 'Active')) = 'active'
                          AND TRIM(COALESCE(assigned_tyre_item, '')) = ''
                    """), {"line_name": line_name}).scalar() or 0)
            except Exception:
                pass
        return total

    def load_existing_saved_items(
        self,
        shipment_id: int,
    ) -> None:
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        sap_code,
                        item_description,
                        quantity,
                        COALESCE(
                            stock_allocated_qty,
                            0
                        ) AS stock_allocated_qty,
                        COALESCE(
                            production_required_qty,
                            0
                        ) AS production_required_qty,
                        COALESCE(
                            produced_qty,
                            0
                        ) AS produced_qty,
                        COALESCE(
                            completed_qty,
                            0
                        ) AS completed_qty,
                        COALESCE(
                            remaining_qty,
                            0
                        ) AS remaining_qty,
                        COALESCE(
                            allocated_cavity_count,
                            allocated_cavities,
                            0
                        ) AS cavity_count,
                        COALESCE(
                            daily_capacity,
                            0
                        ) AS daily_capacity,
                        COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date,
                            start_date
                        ) AS item_receive_date,
                        COALESCE(
                            NULLIF(item_status, ''),
                            'Pending'
                        ) AS item_status
                    FROM mpps_shipment_items
                    WHERE shipment_id =
                        :shipment_id
                    ORDER BY
                        item_receive_date
                            ASC NULLS LAST,
                        sap_code ASC,
                        id ASC
                    """
                ),
                {
                    "shipment_id": shipment_id
                },
            ).mappings().all()

        self.existing_saved_items = [
            dict(row)
            for row in rows
        ]
        self.refresh_existing_saved_items_table()

    def refresh_existing_saved_items_table(
        self,
    ) -> None:
        table = self.existing_saved_items_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        for row_index, item in enumerate(
            self.existing_saved_items
        ):
            table.insertRow(row_index)

            values = [
                item.get("sap_code") or "-",
                item.get(
                    "item_description"
                ) or "-",
                _format_int(
                    item.get("quantity")
                ),
                _format_int(
                    item.get(
                        "stock_allocated_qty"
                    )
                ),
                _format_int(
                    item.get(
                        "production_required_qty"
                    )
                ),
                _format_int(
                    item.get("produced_qty")
                ),
                _format_int(
                    item.get("completed_qty")
                ),
                _format_int(
                    item.get("remaining_qty")
                ),
                _format_int(
                    item.get("cavity_count")
                ),
                _format_int(
                    item.get("daily_capacity")
                ),
                _fmt_date(
                    item.get("item_receive_date")
                ),
                str(
                    item.get("item_status")
                    or "Pending"
                ),
            ]

            for column, value in enumerate(
                values
            ):
                cell = QTableWidgetItem(
                    str(value)
                )
                cell.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )

                if column in {
                    0,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                }:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column in {1, 11}:
                    cell.setToolTip(
                        str(value)
                    )

                if column in {
                    2,
                    10,
                }:
                    font = QFont("Segoe UI")
                    font.setBold(True)
                    cell.setFont(font)

                table.setItem(
                    row_index,
                    column,
                    cell,
                )

        count = len(
            self.existing_saved_items
        )
        self.existing_saved_items_badge.setText(
            f"{count} saved "
            f"{'item' if count == 1 else 'items'}"
        )

        table.setSortingEnabled(True)
        table.resizeRowsToContents()

    def refresh_items_table(self) -> None:
        self.items_table.setRowCount(0)
        for row_index, item in enumerate(self.current_items):
            self.items_table.insertRow(row_index)
            values = [
                item.get("sap_code", ""),
                item.get("item_description", ""),
                _format_int(item.get("quantity")),
                _format_int(item.get("stock_allocated_qty")),
                _format_int(item.get("production_required_qty")),
                _format_int(item.get("allocated_cavity_count")),
                _fmt_date(item.get("item_receive_date")),
                item.get("schedule_reason", ""),
            ]
            for col, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col in {0, 2, 3, 4, 5, 6}:
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col in {2, 6}:
                    font = QFont("Segoe UI")
                    font.setBold(True)
                    table_item.setFont(font)
                self.items_table.setItem(row_index, col, table_item)

            action_box = QWidget()
            action_layout = QHBoxLayout(action_box)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(4)
            qty_btn = QPushButton("Qty")
            qty_btn.setObjectName("SmallButton")
            qty_btn.clicked.connect(lambda checked=False, code=item["sap_code"]: self.edit_item_quantity(code))
            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("DangerButton")
            remove_btn.clicked.connect(lambda checked=False, code=item["sap_code"]: self.remove_item(code))
            action_layout.addWidget(qty_btn)
            action_layout.addWidget(remove_btn)
            self.items_table.setCellWidget(row_index, 8, action_box)

        self.items_table.resizeRowsToContents()
        self.update_summary()

    def edit_item_quantity(self, sap_code: str) -> None:
        for item in self.current_items:
            if item["sap_code"] != sap_code:
                continue
            qty, ok = QInputDialog.getInt(self, "Change Quantity", "Quantity:", int(item.get("quantity") or 1), 1, 999999999)
            if ok:
                item["quantity"] = qty
                self.recalculate_item(item)
                self.refresh_items_table()
            return

    def remove_item(self, sap_code: str) -> None:
        self.current_items = [item for item in self.current_items if item["sap_code"] != sap_code]
        self.recalculate_current_cart()
        self.refresh_items_table()

    def _on_target_mode_changed(
        self,
        checked: bool,
    ) -> None:
        checked = bool(checked)
        self.target_date_input.setEnabled(
            checked
        )

        if checked:
            self.target_date_mode_label.setText(
                "Manual target: this date will be "
                "used to rank the shipment priority."
            )
        else:
            self.target_date_mode_label.setText(
                "Automatic: Factory Can Receive Date "
                "will be saved as the Target Date."
            )

        self.update_summary()

    def _resolved_target_date(
        self,
        factory_receive_date=None,
    ):
        if self.target_date_checkbox.isChecked():
            return (
                self.target_date_input
                .date()
                .toPython()
            )

        if factory_receive_date is not None:
            return factory_receive_date

        return self.get_factory_out_date()

    def _delivery_promise(
        self,
        target_date,
        factory_receive_date,
    ) -> tuple[str, str, int, int]:
        if (
            target_date is None
            or factory_receive_date is None
        ):
            return (
                "pending",
                "PENDING CALCULATION",
                0,
                0,
            )

        variance_days = (
            factory_receive_date - target_date
        ).days

        if variance_days > 0:
            suffix = (
                "DAY"
                if variance_days == 1
                else "DAYS"
            )
            return (
                "late",
                (
                    "CANNOT DELIVER "
                    f"-{variance_days} {suffix} LATE"
                ),
                variance_days,
                0,
            )

        early_days = abs(variance_days)

        if early_days > 0:
            suffix = (
                "DAY"
                if early_days == 1
                else "DAYS"
            )
            return (
                "early",
                (
                    "CAN DELIVER "
                    f"+{early_days} {suffix} EARLY"
                ),
                0,
                early_days,
            )

        return (
            "on_time",
            "CAN DELIVER ON TARGET",
            0,
            0,
        )

    def _apply_promise_style(
        self,
        state: str,
        message: str,
    ) -> None:
        if state in {
            "early",
            "on_time",
        }:
            style = (
                "background:#dcfce7; color:#047857; "
                "border:1px solid #bbf7d0; "
                "border-radius:10px; padding:10px 12px; "
                "font-size:9.2pt; font-weight:950;"
            )
        elif state in {"late", "blocked"}:
            style = (
                "background:#fee2e2; color:#b91c1c; "
                "border:1px solid #fecaca; "
                "border-radius:10px; padding:10px 12px; "
                "font-size:9.2pt; font-weight:950;"
            )
        else:
            style = (
                "background:#fef3c7; color:#92400e; "
                "border:1px solid #fde68a; "
                "border-radius:10px; padding:10px 12px; "
                "font-size:9.2pt; font-weight:950;"
            )

        self.summary_promise_value.setText(
            message
        )
        self.summary_promise_value.setStyleSheet(
            style
        )
        self.target_preview_label.setText(
            "Delivery Promise: " + message
        )
        self.target_preview_label.setStyleSheet(
            style
        )

    def update_summary(self) -> None:
        shipment_name = (
            self.shipment_name_input.text().strip()
            or "-"
        )
        total_items = len(
            self.current_items
        )
        total_qty = sum(
            int(item.get("quantity") or 0)
            for item in self.current_items
        )
        stock_allocated = sum(
            int(
                item.get(
                    "stock_allocated_qty"
                )
                or 0
            )
            for item in self.current_items
        )
        stock_coverage = (
            (
                stock_allocated
                / total_qty
            ) * 100
            if total_qty > 0
            else 0.0
        )

        blocked_items = (
            self._get_unplannable_items()
        )

        if blocked_items:
            factory_receive_date = None
            target_date = (
                self.target_date_input
                .date()
                .toPython()
                if self.target_date_checkbox
                .isChecked()
                else None
            )
            promise_state = "blocked"
            promise_message = (
                "SHIPMENT NOT READY — "
                f"{len(blocked_items)} "
                "ITEM"
                f"{'S' if len(blocked_items) != 1 else ''} "
                "CANNOT BE PLANNED"
            )
        else:
            factory_receive_date = (
                self.planner.final_shipment_date(
                    self.current_items
                )
            )
            target_date = (
                self._resolved_target_date(
                    factory_receive_date
                )
            )

            (
                promise_state,
                promise_message,
                _delay_days,
                _early_days,
            ) = self._delivery_promise(
                target_date,
                factory_receive_date,
            )

        target_source = (
            "Manual manager target"
            if self.target_date_checkbox.isChecked()
            else "Automatic from Factory Can Receive Date"
        )

        self.summary_shipment_label.setText(
            "Shipment: " + shipment_name
        )
        self.summary_target_source_label.setText(
            "Target source: " + target_source
        )
        self.summary_items_value.setText(
            _format_int(total_items)
        )
        self.summary_qty_value.setText(
            _format_int(total_qty)
        )
        self.summary_stock_value.setText(
            _format_int(stock_allocated)
        )
        self.summary_stock_coverage_value.setText(
            f"{stock_coverage:.1f}%"
        )
        self.summary_factory_out_value.setText(
            _fmt_date(factory_receive_date)
        )
        self.summary_target_value.setText(
            _fmt_date(target_date)
        )

        self._apply_promise_style(
            promise_state,
            promise_message,
        )

    def get_factory_out_date(self):
        return self.planner.final_shipment_date(self.current_items)

    def load_previous_shipments(self) -> None:
        self.update_summary()

        search = (
            self.shipment_name_input.text().strip()
        )
        params = {
            "search": f"%{search}%"
        }
        where = ""

        if search:
            where = """
                WHERE
                    s.shipment_no ILIKE :search
                    OR COALESCE(
                        s.shipment_name,
                        ''
                    ) ILIKE :search
                    OR s.customer_name ILIKE :search
                    OR COALESCE(
                        s.note,
                        ''
                    ) ILIKE :search
            """

        sql = """
            SELECT
                s.id,
                s.shipment_no,
                COALESCE(
                    NULLIF(
                        s.shipment_name,
                        ''
                    ),
                    s.customer_name
                ) AS shipment_name,
                COALESCE(
                    s.target_date,
                    s.plan_date,
                    s.manager_order_date,
                    s.factory_out_date
                ) AS target_date,
                COALESCE(
                    MAX(i.item_receive_date),
                    s.factory_can_receive_date,
                    s.factory_out_date
                ) AS factory_receive_date,
                COUNT(i.id) AS item_count
            FROM mpps_shipments s
            LEFT JOIN mpps_shipment_items i
                ON s.id = i.shipment_id
            {where}
            GROUP BY
                s.id,
                s.shipment_no,
                s.shipment_name,
                s.customer_name,
                s.target_date,
                s.plan_date,
                s.manager_order_date,
                s.factory_can_receive_date,
                s.factory_out_date
            ORDER BY
                target_date ASC NULLS LAST,
                s.id DESC
            LIMIT 30
        """.format(
            where=where
        )

        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text(sql),
                    params,
                ).mappings().all()
        except Exception:
            rows = []

        self.previous_table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.previous_table.insertRow(
                row_index
            )

            (
                promise_state,
                promise_message,
                _delay_days,
                _early_days,
            ) = self._delivery_promise(
                row["target_date"],
                row["factory_receive_date"],
            )

            values = [
                row["shipment_name"],
                row["shipment_no"],
                _fmt_date(
                    row["target_date"]
                ),
                _fmt_date(
                    row["factory_receive_date"]
                ),
                _format_int(
                    row["item_count"]
                ),
                promise_message,
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(
                    str(value)
                )
                item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    int(row["id"]),
                )

                if col in {
                    0,
                    2,
                    3,
                    4,
                }:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if col == 5:
                    font = QFont("Segoe UI")
                    font.setBold(True)
                    item.setFont(font)

                    if promise_state in {
                        "early",
                        "on_time",
                    }:
                        item.setForeground(
                            Qt.GlobalColor.darkGreen
                        )
                    elif promise_state == "late":
                        item.setForeground(
                            Qt.GlobalColor.red
                        )

                self.previous_table.setItem(
                    row_index,
                    col,
                    item,
                )

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
        if shipment_id:
            self.load_shipment(int(shipment_id))

    def load_shipment(
        self,
        shipment_id: int,
    ) -> None:
        self._restore_new_shipment_mode()

        with engine.begin() as connection:
            shipment = connection.execute(
                text(
                    """
                    SELECT *
                    FROM mpps_shipments
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": shipment_id},
            ).mappings().first()

            items = connection.execute(
                text(
                    """
                    SELECT
                        sap_code,
                        item_description,
                        quantity,
                        stock_allocated_qty,
                        production_required_qty,
                        allocated_cavity_count,
                        production_days,
                        item_receive_date,
                        schedule_reason
                    FROM mpps_shipment_items
                    WHERE shipment_id = :id
                    ORDER BY id ASC
                    """
                ),
                {"id": shipment_id},
            ).mappings().all()

        if not shipment:
            return

        self.current_shipment_id = int(
            shipment["id"]
        )
        self.shipment_name_input.setText(
            str(
                shipment.get("shipment_name")
                or shipment.get("shipment_no")
                or ""
            )
        )
        self.customer_input.setText(
            str(
                shipment.get("customer_name")
                or ""
            )
        )
        self.remarks_input.setPlainText(
            str(
                shipment.get("note")
                or ""
            )
        )

        stored_target = (
            shipment.get("target_date")
            or shipment.get("plan_date")
            or shipment.get(
                "manager_order_date"
            )
        )
        factory_receive = (
            shipment.get(
                "factory_can_receive_date"
            )
            or shipment.get("factory_out_date")
        )

        manual_target = bool(
            stored_target is not None
            and (
                factory_receive is None
                or stored_target != factory_receive
            )
        )

        self.target_date_checkbox.blockSignals(
            True
        )
        self.target_date_checkbox.setChecked(
            manual_target
        )
        self.target_date_checkbox.blockSignals(
            False
        )

        selected_date = (
            stored_target
            or factory_receive
            or date.today()
        )
        self.target_date_input.setDate(
            QDate(
                selected_date.year,
                selected_date.month,
                selected_date.day,
            )
        )
        self._on_target_mode_changed(
            manual_target
        )

        self.current_items = []

        for row in items:
            smds = (
                self.find_master_item(
                    str(row["sap_code"])
                )
                or {}
            )

            self.current_items.append({
                "sap_code": str(
                    row["sap_code"]
                ),
                "item_description": str(
                    row["item_description"]
                ),
                "quantity": int(
                    row["quantity"] or 0
                ),
                "stock_allocated_qty": int(
                    row["stock_allocated_qty"]
                    or 0
                ),
                "production_required_qty": int(
                    row[
                        "production_required_qty"
                    ]
                    or 0
                ),
                "allocated_cavity_count": int(
                    row[
                        "allocated_cavity_count"
                    ]
                    or 0
                ),
                "production_days": int(
                    row["production_days"]
                    or 0
                ),
                "item_receive_date": row[
                    "item_receive_date"
                ],
                "schedule_reason": str(
                    row["schedule_reason"]
                    or ""
                ),
                "smds": smds,
            })

        self.refresh_items_table()

    def generate_shipment_no(self) -> str:
        prefix = "SHP-" + date.today().strftime("%Y%m%d") + "-"
        with engine.begin() as connection:
            existing = int(connection.execute(text("SELECT COUNT(*) FROM mpps_shipments WHERE shipment_no LIKE :prefix"), {"prefix": prefix + "%"}).scalar() or 0)
        return prefix + f"{existing + 1:04d}"


    def _get_unplannable_items(
        self,
    ) -> list[dict]:
        blocked_items: list[dict] = []

        blocked_statuses = {
            "",
            "blocked",
            "pending",
            "unplanned",
            "failed",
            "error",
        }

        for item in self.current_items:
            production_required = max(
                0,
                int(
                    item.get(
                        "production_required_qty"
                    )
                    or 0
                ),
            )
            item_status = str(
                item.get("item_status")
                or ""
            ).strip().lower()
            receive_date = item.get(
                "item_receive_date"
            )

            is_unplannable = (
                production_required > 0
                and (
                    receive_date is None
                    or item_status
                    in blocked_statuses
                )
            )

            if is_unplannable:
                blocked_items.append(item)

        return blocked_items

    def _clean_planning_reason(
        self,
        item: dict,
    ) -> str:
        reason = str(
            item.get("schedule_reason")
            or (
                "Planning engine did not return "
                "a valid receive date."
            )
        ).strip()

        prefix = "Priority queue:"
        if reason.lower().startswith(
            prefix.lower()
        ):
            reason = reason[
                len(prefix):
            ].strip()

        return (
            reason
            or (
                "Planning engine did not return "
                "a valid receive date."
            )
        )

    def _build_save_block_warning(
        self,
        blocked_items: list[dict],
    ) -> str:
        count = len(blocked_items)

        lines = [
            (
                "This shipment cannot be saved because "
                f"{count} item"
                f"{'s' if count != 1 else ''} cannot "
                "be fully planned."
            ),
            "",
            (
                "No shipment data was created or updated. "
                "Correct the resource problem and "
                "recalculate the item before saving."
            ),
            "",
            "Blocked item details:",
        ]

        for index, item in enumerate(
            blocked_items,
            start=1,
        ):
            order_qty = int(
                item.get("quantity")
                or 0
            )
            stock_qty = int(
                item.get(
                    "stock_allocated_qty"
                )
                or 0
            )
            production_qty = int(
                item.get(
                    "production_required_qty"
                )
                or 0
            )
            description = str(
                item.get("item_description")
                or "-"
            ).strip()
            reason = self._clean_planning_reason(
                item
            )

            lines.extend([
                "",
                (
                    f"{index}. SAP Code: "
                    f"{item.get('sap_code') or '-'}"
                ),
                (
                    "   Description: "
                    f"{description}"
                ),
                (
                    "   Order Qty: "
                    f"{order_qty:,} | "
                    "Stock Allocated: "
                    f"{stock_qty:,} | "
                    "Production Required: "
                    f"{production_qty:,}"
                ),
                (
                    "   Exact reason: "
                    f"{reason}"
                ),
            ])

        lines.extend([
            "",
            (
                "Save remains blocked until every item "
                "has a valid Item Receive Date and a "
                "Planned or Stock Ready status."
            ),
        ])

        return "\n".join(lines)

    def open_existing_shipment_for_item_add(
        self,
        shipment_id: int,
    ) -> None:
        self.ensure_tables()
        self.refresh_master_items(
            show_warning=False
        )

        with engine.begin() as connection:
            shipment = connection.execute(
                text(
                    """
                    SELECT *
                    FROM mpps_shipments
                    WHERE id = :shipment_id
                    LIMIT 1
                    """
                ),
                {
                    "shipment_id": shipment_id
                },
            ).mappings().first()

            stats = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(id) AS item_count,
                        COALESCE(
                            SUM(quantity),
                            0
                        ) AS total_qty,
                        COALESCE(
                            SUM(stock_allocated_qty),
                            0
                        ) AS stock_qty,
                        COALESCE(
                            SUM(produced_qty),
                            0
                        ) AS produced_qty,
                        MAX(
                            COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                            )
                        ) AS factory_receive
                    FROM mpps_shipment_items
                    WHERE shipment_id =
                        :shipment_id
                    """
                ),
                {
                    "shipment_id": shipment_id
                },
            ).mappings().first()

        if not shipment:
            QMessageBox.warning(
                self,
                "Shipment Not Found",
                (
                    "The selected shipment could not "
                    "be loaded."
                ),
            )
            return

        shipment = dict(shipment)
        stats = dict(stats or {})

        self.load_existing_saved_items(
            int(shipment_id)
        )
        self.existing_saved_items_card.setVisible(
            True
        )

        self.existing_item_add_mode = True
        self.current_shipment_id = int(
            shipment_id
        )
        self.existing_shipment_context = {
            **shipment,
            **stats,
        }
        self.current_items = []

        shipment_name = str(
            shipment.get("shipment_name")
            or shipment.get("shipment_no")
            or ""
        )
        customer = str(
            shipment.get("customer_name")
            or ""
        )
        note = str(
            shipment.get("note")
            or ""
        )

        self.shipment_name_input.blockSignals(
            True
        )
        self.shipment_name_input.setText(
            shipment_name
        )
        self.shipment_name_input.blockSignals(
            False
        )
        self.customer_input.setText(
            customer
        )
        self.remarks_input.setPlainText(
            note
        )

        stored_target = (
            shipment.get("target_date")
            or shipment.get("plan_date")
            or shipment.get(
                "manager_order_date"
            )
        )
        factory_receive = (
            shipment.get(
                "factory_can_receive_date"
            )
            or stats.get(
                "factory_receive"
            )
            or shipment.get(
                "factory_out_date"
            )
        )
        target_is_manual = bool(
            shipment.get(
                "target_date_is_manual"
            )
        )

        self.target_date_checkbox.blockSignals(
            True
        )
        self.target_date_checkbox.setChecked(
            target_is_manual
        )
        self.target_date_checkbox.blockSignals(
            False
        )

        selected_date = (
            stored_target
            or factory_receive
            or date.today()
        )
        self.target_date_input.setDate(
            QDate(
                selected_date.year,
                selected_date.month,
                selected_date.day,
            )
        )
        self._on_target_mode_changed(
            target_is_manual
        )

        self._set_existing_mode_controls(
            True
        )

        shipment_no = str(
            shipment.get("shipment_no")
            or shipment_id
        )
        item_count = int(
            stats.get("item_count")
            or 0
        )
        total_qty = int(
            stats.get("total_qty")
            or 0
        )
        stock_qty = int(
            stats.get("stock_qty")
            or 0
        )

        self.page_title_label.setText(
            "Add Items to Existing Shipment"
        )
        self.page_hint_label.setText(
            "Use the full Shipment Order workspace "
            "to add one or more approved items. "
            "The existing shipment is never rewritten; "
            "only the new additions are saved."
        )
        self.approved_badge_label.setText(
            "EXISTING SHIPMENT"
        )
        self.target_badge_label.setText(
            "ADDITIVE UPDATE"
        )
        self.existing_context_label.setText(
            f"Shipment {shipment_no}  •  "
            f"{item_count} existing "
            f"{'item' if item_count == 1 else 'items'}  •  "
            f"{_format_int(total_qty)} existing qty  •  "
            f"{_format_int(stock_qty)} stock allocated  •  "
            "Factory Can Receive "
            f"{_fmt_date(factory_receive)}"
        )
        self.existing_context_label.setVisible(
            True
        )

        self.shipment_form_title.setText(
            "Existing Shipment Context"
        )
        self.shipment_form_hint.setText(
            "Shipment header and Target Date are locked "
            "in this workflow. Use Edit Header or Change "
            "Target Date from Shipment Details when those "
            "values must be changed."
        )
        self.add_item_section_title.setText(
            "Add New Shipment Items"
        )
        self.add_item_section_hint.setText(
            "Build a new-item cart for this shipment. "
            "Each addition is previewed against all active "
            "shipment priorities and available resources."
        )
        self.items_section_title.setText(
            "New Items to Add"
        )
        self.items_section_hint.setText(
            "Only items in this table will be added. "
            "Existing saved items remain unchanged. "
            "Receive dates are calculated automatically."
        )

        self.save_btn.setText(
            "Add Items & Replan"
        )
        self.clear_btn.setText(
            "Clear New Items"
        )
        self.back_to_shipment_btn.setVisible(
            True
        )

        self.item_search_input.clear()
        self.quantity_input.setValue(1)
        self.refresh_items_table()
        self.item_search_input.setFocus()

    def _set_existing_mode_controls(
        self,
        locked: bool,
    ) -> None:
        self.shipment_name_input.setReadOnly(
            locked
        )
        self.customer_input.setReadOnly(
            locked
        )
        self.remarks_input.setReadOnly(
            locked
        )
        self.target_date_checkbox.setEnabled(
            not locked
        )
        self.target_date_input.setEnabled(
            (
                not locked
                and self.target_date_checkbox
                .isChecked()
            )
        )

        for widget in (
            self.shipment_name_input,
            self.customer_input,
            self.remarks_input,
        ):
            widget.setProperty(
                "existingLocked",
                locked,
            )
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _restore_new_shipment_mode(
        self,
    ) -> None:
        self.existing_item_add_mode = False
        self.existing_shipment_context = {}
        self.existing_saved_items = []

        if hasattr(
            self,
            "existing_saved_items_table",
        ):
            self.existing_saved_items_table.setRowCount(
                0
            )

        if hasattr(
            self,
            "existing_saved_items_card",
        ):
            self.existing_saved_items_card.setVisible(
                False
            )

        self._set_existing_mode_controls(
            False
        )

        self.page_title_label.setText(
            "Shipment Order Entry"
        )
        self.page_hint_label.setText(
            "Create a production-ready shipment from "
            "manager-approved SMDS items. Factory "
            "receive dates, stock coverage and delivery "
            "promise are calculated before saving."
        )
        self.approved_badge_label.setText(
            "APPROVED SMDS ITEMS ONLY"
        )
        self.target_badge_label.setText(
            "TARGET DATE OPTIONAL"
        )
        self.existing_context_label.clear()
        self.existing_context_label.setVisible(
            False
        )

        self.shipment_form_title.setText(
            "Shipment Information"
        )
        self.shipment_form_hint.setText(
            "Set a target date only when the manager "
            "has confirmed one. When it is not set, "
            "the calculated Factory Can Receive Date "
            "becomes the Target Date automatically."
        )
        self.add_item_section_title.setText(
            "Add Shipment Item"
        )
        self.add_item_section_hint.setText(
            "Search from SMDS. Only approved items "
            "can enter the cart."
        )
        self.items_section_title.setText(
            "Shipment Cart"
        )
        self.items_section_hint.setText(
            "Item receive date is calculated when "
            "quantity is saved into the cart."
        )

        self.save_btn.setText(
            "Save Shipment"
        )
        self.clear_btn.setText(
            "Clear Form"
        )
        self.back_to_shipment_btn.setVisible(
            False
        )

    def return_to_shipment_details(
        self,
    ) -> None:
        shipment_id = (
            self.current_shipment_id
        )

        if not shipment_id:
            self.clear_form()
            return

        main_window = self.window()
        open_details = getattr(
            main_window,
            "open_shipment_details_page",
            None,
        )

        if callable(open_details):
            open_details(
                int(shipment_id)
            )
            return

        navigate = getattr(
            main_window,
            "navigate",
            None,
        )
        details_index = getattr(
            main_window,
            "SHIPMENT_DETAILS_INDEX",
            None,
        )

        if (
            callable(navigate)
            and details_index is not None
        ):
            navigate(details_index)
            details_page = getattr(
                main_window,
                "shipment_details_page",
                None,
            )
            if (
                details_page is not None
                and hasattr(
                    details_page,
                    "open_shipment_detail",
                )
            ):
                details_page.open_shipment_detail(
                    int(shipment_id)
                )
            return

        QMessageBox.warning(
            self,
            "Shipment Details Unavailable",
            (
                "The Shipment Details page could "
                "not be opened."
            ),
        )

    def _save_existing_item_additions(
        self,
    ) -> None:
        shipment_id = int(
            self.current_shipment_id
            or 0
        )

        if shipment_id <= 0:
            QMessageBox.warning(
                self,
                "Shipment Required",
                "Open an existing shipment first.",
            )
            return

        if not self.current_items:
            QMessageBox.warning(
                self,
                "New Items Required",
                (
                    "Add at least one new approved "
                    "SMDS item before saving."
                ),
            )
            self.item_search_input.setFocus()
            return

        self.recalculate_current_cart()
        self.refresh_items_table()

        blocked_items = (
            self._get_unplannable_items()
        )
        if blocked_items:
            QMessageBox.warning(
                self,
                "New Items Cannot Be Added",
                self._build_save_block_warning(
                    blocked_items
                ).replace(
                    "This shipment cannot be saved",
                    (
                        "These new items cannot be "
                        "added to the shipment"
                    ),
                    1,
                ),
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Add Items and Replan",
            (
                f"Add {len(self.current_items)} new "
                f"{'item' if len(self.current_items) == 1 else 'items'} "
                "to this shipment?\n\n"
                "All active shipments will be replanned "
                "in priority order. Existing shipment "
                "items and production progress will not "
                "be deleted or rewritten."
            ),
        )
        if (
            confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        inserted_ids: list[int] = []

        try:
            with engine.begin() as connection:
                for item in self.current_items:
                    inserted_id = int(
                        connection.execute(
                            text(
                                """
                                INSERT INTO
                                    mpps_shipment_items
                                (
                                    shipment_id,
                                    sap_code,
                                    item_description,
                                    quantity,
                                    start_date,
                                    end_date,
                                    receive_date,
                                    item_receive_date,
                                    item_status,
                                    note,
                                    stock_allocated_qty,
                                    production_required_qty,
                                    allocated_cavity_count,
                                    allocated_cavities,
                                    daily_capacity,
                                    production_days,
                                    produced_qty,
                                    completed_qty,
                                    remaining_qty,
                                    progress_pct,
                                    schedule_reason,
                                    updated_at
                                )
                                VALUES
                                (
                                    :shipment_id,
                                    :sap_code,
                                    :item_description,
                                    :quantity,
                                    :receive_date,
                                    :receive_date,
                                    :receive_date,
                                    :receive_date,
                                    :item_status,
                                    :note,
                                    :stock_allocated_qty,
                                    :production_required_qty,
                                    :allocated_cavity_count,
                                    :allocated_cavity_count,
                                    :daily_capacity,
                                    :production_days,
                                    0,
                                    :stock_allocated_qty,
                                    :remaining_qty,
                                    :progress_pct,
                                    :schedule_reason,
                                    CURRENT_TIMESTAMP
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "shipment_id": shipment_id,
                                "sap_code": item.get(
                                    "sap_code"
                                ),
                                "item_description": item.get(
                                    "item_description"
                                ),
                                "quantity": int(
                                    item.get("quantity")
                                    or 0
                                ),
                                "receive_date": item.get(
                                    "item_receive_date"
                                ),
                                "item_status": item.get(
                                    "item_status"
                                )
                                or "Planned",
                                "note": (
                                    "Added through existing "
                                    "shipment item workspace."
                                ),
                                "stock_allocated_qty": int(
                                    item.get(
                                        "stock_allocated_qty"
                                    )
                                    or 0
                                ),
                                "production_required_qty": int(
                                    item.get(
                                        "production_required_qty"
                                    )
                                    or 0
                                ),
                                "allocated_cavity_count": int(
                                    item.get(
                                        "allocated_cavity_count"
                                    )
                                    or 0
                                ),
                                "daily_capacity": int(
                                    item.get(
                                        "daily_capacity"
                                    )
                                    or 0
                                ),
                                "production_days": int(
                                    item.get(
                                        "production_days"
                                    )
                                    or 0
                                ),
                                "remaining_qty": int(
                                    item.get(
                                        "production_required_qty"
                                    )
                                    or 0
                                ),
                                "progress_pct": (
                                    round(
                                        (
                                            int(
                                                item.get(
                                                    "stock_allocated_qty"
                                                )
                                                or 0
                                            )
                                            /
                                            max(
                                                1,
                                                int(
                                                    item.get(
                                                        "quantity"
                                                    )
                                                    or 0
                                                ),
                                            )
                                            * 100
                                        ),
                                        2,
                                    )
                                ),
                                "schedule_reason": item.get(
                                    "schedule_reason"
                                )
                                or "",
                            },
                        ).scalar_one()
                    )
                    inserted_ids.append(
                        inserted_id
                    )

            self.planner.replan_all_open_shipments(
                trigger_reason=(
                    "existing_shipment_items_added_"
                    f"{shipment_id}"
                ),
                created_by=(
                    "shipment_order_workspace"
                ),
            )

        except Exception as exc:
            if inserted_ids:
                try:
                    with engine.begin() as connection:
                        connection.execute(
                            text(
                                """
                                DELETE FROM
                                    planning_resource_reservations
                                WHERE shipment_item_id =
                                    ANY(:item_ids)
                                """
                            ),
                            {
                                "item_ids": inserted_ids
                            },
                        )
                        connection.execute(
                            text(
                                """
                                DELETE FROM
                                    shipment_stock_allocations
                                WHERE shipment_item_id =
                                    ANY(:item_ids)
                                """
                            ),
                            {
                                "item_ids": inserted_ids
                            },
                        )
                        connection.execute(
                            text(
                                """
                                DELETE FROM
                                    mpps_shipment_items
                                WHERE id =
                                    ANY(:item_ids)
                                """
                            ),
                            {
                                "item_ids": inserted_ids
                            },
                        )

                    self.planner.replan_all_open_shipments(
                        trigger_reason=(
                            "rollback_failed_existing_"
                            "shipment_item_addition_"
                            f"{shipment_id}"
                        ),
                        created_by=(
                            "shipment_order_workspace"
                        ),
                    )
                except Exception:
                    pass

            QMessageBox.critical(
                self,
                "Add Items Failed",
                (
                    "The new items could not be added. "
                    "Existing shipment items were not "
                    "changed.\n\n"
                    f"Reason: {exc}"
                ),
            )
            return

        added_count = len(
            inserted_ids
        )
        self.current_items = []
        self.refresh_items_table()

        QMessageBox.information(
            self,
            "Shipment Updated",
            (
                f"{added_count} new "
                f"{'item was' if added_count == 1 else 'items were'} "
                "added successfully.\n\n"
                "All active shipments were replanned "
                "using the existing shipment priority."
            ),
        )
        self.return_to_shipment_details()

    def save_shipment(self) -> None:
        if self.existing_item_add_mode:
            self._save_existing_item_additions()
            return

        shipment_name = (
            self.shipment_name_input.text().strip()
        )
        customer = (
            self.customer_input.text().strip()
            or shipment_name
        )
        note = (
            self.remarks_input
            .toPlainText()
            .strip()
        )

        if not shipment_name:
            QMessageBox.warning(
                self,
                "Shipment Required",
                "Please enter shipment name.",
            )
            self.shipment_name_input.setFocus()
            return

        if not self.current_items:
            QMessageBox.warning(
                self,
                "Items Required",
                (
                    "Please add at least one approved "
                    "SMDS item."
                ),
            )
            self.item_search_input.setFocus()
            return

        self.recalculate_current_cart()
        self.refresh_items_table()

        blocked_items = (
            self._get_unplannable_items()
        )
        if blocked_items:
            QMessageBox.warning(
                self,
                "Shipment Cannot Be Saved",
                self._build_save_block_warning(
                    blocked_items
                ),
            )
            return

        factory_receive_date = (
            self.get_factory_out_date()
        )
        manual_target = (
            self.target_date_checkbox.isChecked()
        )
        target_date = self._resolved_target_date(
            factory_receive_date
        )

        if (
            factory_receive_date is None
            and not manual_target
        ):
            QMessageBox.warning(
                self,
                "Target Date Cannot Be Resolved",
                (
                    "The automatic Target Date uses the "
                    "Factory Can Receive Date, but one "
                    "or more items do not have a valid "
                    "receive date.\n\n"
                    "Correct the item planning data or "
                    "enable 'Use a specific target date'."
                ),
            )
            return

        if target_date is None:
            QMessageBox.warning(
                self,
                "Target Date Required",
                (
                    "Please select a Target Date or "
                    "calculate a Factory Can Receive Date."
                ),
            )
            return

        (
            promise_state,
            promise_message,
            delay_days,
            early_days,
        ) = self._delivery_promise(
            target_date,
            factory_receive_date,
        )

        if promise_state == "late":
            delivery_status = "Delayed"
            planning_status = "At Risk"
        elif promise_state == "early":
            delivery_status = "Can Deliver Early"
            planning_status = "Ready"
        elif promise_state == "on_time":
            delivery_status = "On Time"
            planning_status = "Ready"
        else:
            delivery_status = (
                "Pending Calculation"
            )
            planning_status = (
                "Pending Calculation"
            )

        total_qty = sum(
            int(item.get("quantity") or 0)
            for item in self.current_items
        )
        stock_allocated = sum(
            int(
                item.get(
                    "stock_allocated_qty"
                )
                or 0
            )
            for item in self.current_items
        )
        progress_pct = (
            min(
                100.0,
                (
                    stock_allocated
                    / total_qty
                ) * 100,
            )
            if total_qty > 0
            else 0.0
        )

        shipment_date = target_date

        try:
            with engine.begin() as connection:
                header_params = {
                    "shipment_name": shipment_name,
                    "customer_name": customer,
                    "shipment_date": shipment_date,
                    "manager_order_date": target_date,
                    "target_date": target_date,
                    "plan_date": target_date,
                    "factory_out_date": (
                        factory_receive_date
                    ),
                    "factory_can_receive_date": (
                        factory_receive_date
                    ),
                    "delivery_status": delivery_status,
                    "delay_days": delay_days,
                    "early_days": early_days,
                    "total_qty": total_qty,
                    "completed_qty": 0,
                    "progress_pct": progress_pct,
                    "planning_status": planning_status,
                    "planning_note": promise_message,
                    "note": note,
                }

                if self.current_shipment_id:
                    shipment_id = int(
                        self.current_shipment_id
                    )
                    header_params["id"] = shipment_id

                    connection.execute(
                        text(
                            """
                            UPDATE mpps_shipments
                            SET
                                shipment_name =
                                    :shipment_name,
                                customer_name =
                                    :customer_name,
                                shipment_date =
                                    :shipment_date,
                                manager_order_date =
                                    :manager_order_date,
                                target_date =
                                    :target_date,
                                plan_date =
                                    :plan_date,
                                factory_out_date =
                                    :factory_out_date,
                                factory_can_receive_date =
                                    :factory_can_receive_date,
                                delivery_status =
                                    :delivery_status,
                                delay_days =
                                    :delay_days,
                                early_days =
                                    :early_days,
                                total_qty =
                                    :total_qty,
                                completed_qty =
                                    :completed_qty,
                                progress_pct =
                                    :progress_pct,
                                planning_status =
                                    :planning_status,
                                planning_note =
                                    :planning_note,
                                status = 'Planned',
                                note = :note,
                                updated_at =
                                    CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        header_params,
                    )

                    connection.execute(
                        text(
                            """
                            DELETE FROM
                                mpps_shipment_items
                            WHERE shipment_id = :id
                            """
                        ),
                        {"id": shipment_id},
                    )

                else:
                    shipment_no = (
                        self.generate_shipment_no()
                    )
                    header_params[
                        "shipment_no"
                    ] = shipment_no

                    shipment_id = int(
                        connection.execute(
                            text(
                                """
                                INSERT INTO
                                    mpps_shipments
                                (
                                    shipment_no,
                                    shipment_name,
                                    customer_name,
                                    shipment_date,
                                    manager_order_date,
                                    target_date,
                                    plan_date,
                                    factory_out_date,
                                    factory_can_receive_date,
                                    delivery_status,
                                    delay_days,
                                    early_days,
                                    total_qty,
                                    completed_qty,
                                    progress_pct,
                                    planning_status,
                                    planning_note,
                                    status,
                                    note,
                                    updated_at
                                )
                                VALUES
                                (
                                    :shipment_no,
                                    :shipment_name,
                                    :customer_name,
                                    :shipment_date,
                                    :manager_order_date,
                                    :target_date,
                                    :plan_date,
                                    :factory_out_date,
                                    :factory_can_receive_date,
                                    :delivery_status,
                                    :delay_days,
                                    :early_days,
                                    :total_qty,
                                    :completed_qty,
                                    :progress_pct,
                                    :planning_status,
                                    :planning_note,
                                    'Planned',
                                    :note,
                                    CURRENT_TIMESTAMP
                                )
                                RETURNING id
                                """
                            ),
                            header_params,
                        ).scalar_one()
                    )

                for item in self.current_items:
                    connection.execute(
                        text(
                            """
                            INSERT INTO
                                mpps_shipment_items
                            (
                                shipment_id,
                                sap_code,
                                item_description,
                                quantity,
                                start_date,
                                end_date,
                                item_status,
                                note,
                                stock_allocated_qty,
                                production_required_qty,
                                allocated_cavity_count,
                                production_days,
                                item_receive_date,
                                schedule_reason,
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
                                :stock_allocated_qty,
                                :production_required_qty,
                                :allocated_cavity_count,
                                :production_days,
                                :item_receive_date,
                                :schedule_reason,
                                CURRENT_TIMESTAMP
                            )
                            """
                        ),
                        {
                            "shipment_id": shipment_id,
                            "sap_code": item[
                                "sap_code"
                            ],
                            "item_description": item[
                                "item_description"
                            ],
                            "quantity": int(
                                item.get("quantity")
                                or 0
                            ),
                            "start_date": date.today(),
                            "end_date": (
                                item.get(
                                    "item_receive_date"
                                )
                                or date.today()
                            ),
                            "stock_allocated_qty": int(
                                item.get(
                                    "stock_allocated_qty"
                                )
                                or 0
                            ),
                            "production_required_qty": int(
                                item.get(
                                    "production_required_qty"
                                )
                                or 0
                            ),
                            "allocated_cavity_count": int(
                                item.get(
                                    "allocated_cavity_count"
                                )
                                or 0
                            ),
                            "production_days": int(
                                item.get(
                                    "production_days"
                                )
                                or 0
                            ),
                            "item_receive_date": item.get(
                                "item_receive_date"
                            ),
                            "schedule_reason": item.get(
                                "schedule_reason",
                                "",
                            ),
                        },
                    )

            planning_warning = ""
            try:
                with engine.begin() as connection:
                    connection.execute(text("""
                        UPDATE mpps_shipments
                        SET target_date_is_manual = :target_date_is_manual,
                            target_date_source = :target_date_source,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :shipment_id
                    """), {
                        "shipment_id": shipment_id,
                        "target_date_is_manual": manual_target,
                        "target_date_source": (
                            "Manual" if manual_target
                            else "Automatic Factory Receive"
                        ),
                    })

                planning_run = self.planner.replan_all_open_shipments(
                    trigger_reason=f"shipment_entry_save_{shipment_id}",
                    created_by="shipment_entry",
                )
                saved_plan = next(
                    (
                        shipment
                        for shipment in planning_run.shipments
                        if shipment.shipment_id == shipment_id
                    ),
                    None,
                )
                if saved_plan is not None:
                    factory_receive_date = saved_plan.factory_can_receive_date
                    target_date = saved_plan.target_date
                    (
                        promise_state,
                        promise_message,
                        delay_days,
                        early_days,
                    ) = self._delivery_promise(target_date, factory_receive_date)
            except Exception as planning_exc:
                planning_warning = (
                    "\n\nWARNING: Shipment was saved, but cumulative "
                    f"replanning failed: {planning_exc}"
                )

            QMessageBox.information(
                self,
                "Shipment Saved",
                (
                    "Shipment saved successfully."
                    "\n\n"
                    f"Target Date: "
                    f"{_fmt_date(target_date)}"
                    "\n"
                    f"Factory Can Receive Date: "
                    f"{_fmt_date(factory_receive_date)}"
                    "\n"
                    f"Delivery Promise: "
                    f"{promise_message}"
                    f"{planning_warning}"
                ),
            )

            self.clear_after_successful_save()

            if callable(
                self.on_shipment_saved
            ):
                self.on_shipment_saved(
                    shipment_id
                )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                str(exc),
            )

    def clear_form(self) -> None:
        if self.existing_item_add_mode:
            self.current_items.clear()
            self.item_search_input.clear()
            self.quantity_input.setValue(1)
            self.refresh_items_table()
            self.item_search_input.setFocus()
            return

        self._restore_new_shipment_mode()
        self.current_shipment_id = None

        self.shipment_name_input.blockSignals(
            True
        )
        self.shipment_name_input.clear()
        self.shipment_name_input.blockSignals(
            False
        )

        self.customer_input.clear()
        self.remarks_input.clear()
        self.item_search_input.clear()
        self.quantity_input.setValue(1)

        self.target_date_checkbox.blockSignals(
            True
        )
        self.target_date_checkbox.setChecked(
            False
        )
        self.target_date_checkbox.blockSignals(
            False
        )
        self.target_date_input.setDate(
            QDate.currentDate()
        )
        self._on_target_mode_changed(False)

        self.current_items.clear()
        self.refresh_items_table()
        self.load_previous_shipments()
        self.shipment_name_input.setFocus()

    def clear_after_successful_save(self) -> None:
        self.clear_form()



class ShipmentDemandPage(OrderEntryPage):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user=current_user)
