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
    QDialog,
    QDialogButtonBox,
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
    def __init__(self, current_user=None, on_shipment_saved=None, *args, **kwargs):
        super().__init__()
        self.on_shipment_saved = on_shipment_saved
        self.current_user = current_user
        self.current_items: list[dict] = []
        self.master_items: list[dict] = []
        self.planner = FactoryPlanningEngine(start_date=date.today())
        self.current_shipment_id: int | None = None
        self.smds_columns: SmdsColumnMap | None = None

        self.shipment_name_input = QLineEdit()
        self.shipment_name_input.setPlaceholderText("Type shipment name")
        self.shipment_name_input.textChanged.connect(self.load_previous_shipments)

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer / destination / note")

        self.remarks_input = QTextEdit()
        self.remarks_input.setPlaceholderText("Remarks / special instructions")
        self.remarks_input.setMinimumHeight(74)

        self.item_search_input = QLineEdit()
        self.item_search_input.setPlaceholderText("Search SAP code or tyre description from SMDS...")
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

        self.refresh_btn = QPushButton("Refresh SMDS")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_master_items)

        self.preview_code_label = QLabel("No item selected.")
        self.preview_desc_label = QLabel("Search SAP code or tyre description to preview item details.")
        self.preview_available_label = QLabel("")
        self.preview_planning_label = QLabel("")

        self.items_table = QTableWidget(0, 9)
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

        self.previous_table = QTableWidget(0, 4)
        self.previous_table.setHorizontalHeaderLabels(["Shipment ID", "Name", "Items", "Factory Out"])

        self.summary_items_value = QLabel("0")
        self.summary_qty_value = QLabel("0")
        self.summary_factory_out_value = QLabel("Pending")
        self.summary_shipment_label = QLabel("Shipment: -")

        self._apply_styles()
        self._build_ui()
        self._setup_tables()
        self.ensure_tables()
        self.refresh_master_items(show_warning=False)
        self.load_previous_shipments()
        self.update_summary()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-family: "Segoe UI"; }
            QFrame#HeaderCard, QFrame#FormCard, QFrame#TableCard, QFrame#SummaryCard, QFrame#PreviewCard {
                background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;
            }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#PageHint, QLabel#Hint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#SectionTitle { color:#0f172a; font-size:16pt; font-weight:950; }
            QLabel#FieldLabel { color:#334155; font-size:9pt; font-weight:850; }
            QLabel#PreviewTitle { color:#0f172a; font-size:11pt; font-weight:950; }
            QLabel#PreviewText { color:#475569; font-size:9.2pt; font-weight:650; }
            QLabel#MetricValue { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#MetricLabel { color:#64748b; font-size:8.8pt; font-weight:850; }
            QLineEdit, QTextEdit, QSpinBox {
                background:#ffffff; color:#0f172a; border:1px solid #cbd5e1; border-radius:10px;
                padding:8px 11px; font-size:9.5pt; font-weight:650; min-height:24px;
            }
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus { border:1px solid #2563eb; }
            QPushButton#PrimaryButton {
                background:#2563eb; color:#ffffff; border:none; border-radius:10px;
                padding:10px 18px; font-weight:950; min-height:26px;
            }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QPushButton#SecondaryButton {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:10px;
                padding:10px 18px; font-weight:950; min-height:26px;
            }
            QPushButton#DangerButton {
                background:#fee2e2; color:#991b1b; border:none; border-radius:9px;
                padding:7px 10px; font-weight:950;
            }
            QPushButton#SmallButton {
                background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:8px;
                padding:7px 10px; font-weight:900;
            }
            QTableWidget {
                background:#ffffff; color:#0f172a; border:1px solid #e2e8f0; border-radius:12px;
                gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe;
            }
            QTableWidget::item { padding:7px 8px; border:none; }
            QHeaderView::section {
                background:#f1f5f9; color:#1e293b; border:none; border-right:1px solid #e2e8f0;
                border-bottom:1px solid #e2e8f0; padding:8px; font-weight:950;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._header_card())
        root.addWidget(self._shipment_form_card())

        middle = QHBoxLayout()
        middle.setSpacing(16)
        middle.addWidget(self._add_item_card(), 2)
        middle.addWidget(self._previous_shipments_card(), 1)
        root.addLayout(middle)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(self._items_card(), 3)
        bottom.addWidget(self._summary_card(), 1)
        root.addLayout(bottom, 1)

    def _header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        title_box = QVBoxLayout()
        title = QLabel("Shipment Entry")
        title.setObjectName("PageTitle")
        hint = QLabel("Create shipments from SMDS-approved tyre items. Item receive dates are calculated before final shipment save.")
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
        layout.setVerticalSpacing(10)
        self._add_field(layout, 0, 0, "Shipment Name", self.shipment_name_input)
        self._add_field(layout, 0, 1, "Customer / Destination", self.customer_input)
        remarks_label = QLabel("Remarks")
        remarks_label.setObjectName("FieldLabel")
        layout.addWidget(remarks_label, 2, 0)
        layout.addWidget(self.remarks_input, 3, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        return card

    def _add_item_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("FormCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        title = QLabel("Add Shipment Item")
        title.setObjectName("SectionTitle")
        hint = QLabel("Search from SMDS. Only approved items can enter the cart.")
        hint.setObjectName("Hint")
        layout.addWidget(title)
        layout.addWidget(hint)
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
        title = QLabel("Shipment Cart")
        title.setObjectName("SectionTitle")
        hint = QLabel("Item receive date is calculated when quantity is saved into the cart.")
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
        layout.setSpacing(14)
        title = QLabel("Shipment Summary")
        title.setObjectName("SectionTitle")
        self.summary_shipment_label.setObjectName("Hint")
        layout.addWidget(title)
        layout.addWidget(self.summary_shipment_label)
        layout.addWidget(self._metric_box(self.summary_items_value, "Total Items"))
        layout.addWidget(self._metric_box(self.summary_qty_value, "Total Qty"))
        layout.addWidget(self._metric_box(self.summary_factory_out_value, "Factory Out Date"))
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
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setAlternatingRowColors(True)
        self.items_table.setWordWrap(True)
        header = self.items_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, 9):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.setColumnWidth(0, 105)
        self.items_table.setColumnWidth(7, 220)

        self.previous_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.previous_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.previous_table.verticalHeader().setVisible(False)
        self.previous_table.setAlternatingRowColors(True)
        self.previous_table.itemDoubleClicked.connect(lambda *_: self.load_selected_previous_shipment())
        prev_header = self.previous_table.horizontalHeader()
        prev_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        prev_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        prev_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        prev_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.previous_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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

        if str(item.get("approval_status", "")).strip().lower() != "approved":
            dialog = ShipmentApprovalDialog(self, item)
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.approved:
                QMessageBox.warning(self, "Approval Required", "This item was not added to the cart because it is not approved.")
                return
            self.save_item_approval_to_smds(item)
            self.refresh_master_items(show_warning=False)

        qty = int(self.quantity_input.value())
        sap_code = str(item["sap_code"])
        for existing in self.current_items:
            if existing["sap_code"] == sap_code:
                existing["quantity"] += qty
                self.recalculate_item(existing)
                self.refresh_items_table()
                self.item_search_input.clear()
                self.quantity_input.setValue(1)
                return

        cart_item = {
            "sap_code": sap_code,
            "item_description": str(item["tyre_description"]),
            "quantity": qty,
            "smds": item,
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

    def recalculate_item(self, item: dict) -> None:
        self.planner.ensure_schema()
        qty = int(item.get("quantity") or 0)
        smds = item.get("smds") or self.find_master_item(item.get("sap_code", "")) or {}
        item["smds"] = smds

        if not item.get("sap_code"):
            self._set_pending(item, "SAP code is required")
            return

        try:
            preview_items = [{
                "sap_code": item.get("sap_code", ""),
                "item_description": item.get("item_description", ""),
                "quantity": qty,
            }]
            result = self.planner.calculate_cart_items(preview_items)[0]
            item["stock_allocated_qty"] = int(result.get("stock_allocated_qty") or 0)
            item["production_required_qty"] = int(result.get("production_required_qty") or 0)
            item["allocated_cavity_count"] = int(result.get("allocated_cavity_count") or 0)
            item["production_days"] = int(result.get("production_days") or 0)
            item["item_receive_date"] = result.get("receive_date") or result.get("item_receive_date")
            item["schedule_reason"] = result.get("reason") or result.get("schedule_reason") or ""
            item["item_description"] = result.get("item_description") or item.get("item_description", "")
            item["quantity"] = int(result.get("quantity") or qty)
            item["status"] = result.get("status", "")
            return
        except Exception:
            pass

        stock_allocated = min(qty, self.get_unallocated_stock(item["sap_code"]))
        balance_qty = max(0, qty - stock_allocated)
        item["stock_allocated_qty"] = stock_allocated
        item["production_required_qty"] = balance_qty

        if balance_qty <= 0:
            item["allocated_cavity_count"] = 0
            item["production_days"] = 0
            item["item_receive_date"] = date.today()
            item["schedule_reason"] = "Covered by unallocated stock"
            return

        total_plan = _to_int(smds.get("total_plan"))
        if total_plan <= 0:
            self._set_pending(item, "SMDS Total Plan missing")
            return

        mold_count = self.get_available_mold_count(smds.get("key_code", ""))
        if mold_count <= 0:
            self._set_pending(item, "Mold not available")
            return

        casing_type = _clean(smds.get("casing_type", ""))
        casing_required = casing_type and casing_type.lower() not in {"no casing", "-", "n/a", "na"}
        casing_count = 999999 if not casing_required else self.get_available_casing_count(casing_type)
        if casing_required and casing_count <= 0:
            self._set_pending(item, "Casing not available")
            return

        line_count = self.get_available_line_cavity_count(smds.get("line", ""))
        if line_count <= 0:
            self._set_pending(item, "No free line/cavity")
            return

        allocated_cavities = max(0, min(mold_count, casing_count, line_count))
        if allocated_cavities <= 0:
            self._set_pending(item, "No allocatable cavity")
            return

        daily_capacity = total_plan * allocated_cavities
        if daily_capacity <= 0:
            self._set_pending(item, "Daily capacity is zero")
            return

        production_days = max(1, int(math.ceil(balance_qty / daily_capacity)))
        receive_date = date.today() + timedelta(days=production_days - 1)
        item["allocated_cavity_count"] = allocated_cavities
        item["production_days"] = production_days
        item["item_receive_date"] = receive_date
        item["schedule_reason"] = "Stock {stock}; production {prod}; {cap}/day using {cav} cavity".format(
            stock=stock_allocated,
            prod=balance_qty,
            cap=daily_capacity,
            cav=allocated_cavities,
        )

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
                    SELECT COALESCE(MAX(fg_stock + qc_stock - scrap_stock - blocked_stock), 0)
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
        for item in self.current_items:
            self.recalculate_item(item)
        self.refresh_items_table()

    def update_summary(self) -> None:
        shipment_name = self.shipment_name_input.text().strip() or "-"
        total_items = len(self.current_items)
        total_qty = sum(int(item.get("quantity") or 0) for item in self.current_items)
        dates = [item.get("item_receive_date") for item in self.current_items if item.get("item_receive_date") is not None]
        final_date = self.planner.final_shipment_date(self.current_items)
        self.summary_shipment_label.setText("Shipment: " + shipment_name)
        self.summary_items_value.setText(_format_int(total_items))
        self.summary_qty_value.setText(_format_int(total_qty))
        self.summary_factory_out_value.setText(_fmt_date(final_date))

    def get_factory_out_date(self):
        return self.planner.final_shipment_date(self.current_items)

    def load_previous_shipments(self) -> None:
        self.update_summary()
        search = self.shipment_name_input.text().strip()
        params = {"search": f"%{search}%"}
        where = ""
        if search:
            where = """
                WHERE s.shipment_no ILIKE :search
                   OR COALESCE(s.shipment_name, '') ILIKE :search
                   OR s.customer_name ILIKE :search
                   OR COALESCE(s.note, '') ILIKE :search
            """
        sql = """
            SELECT s.id, s.shipment_no, COALESCE(NULLIF(s.shipment_name, ''), s.customer_name) AS shipment_name,
                   s.factory_out_date, COUNT(i.id) AS item_count
            FROM mpps_shipments s
            LEFT JOIN mpps_shipment_items i ON s.id = i.shipment_id
            {where}
            GROUP BY s.id, s.shipment_no, s.shipment_name, s.customer_name, s.factory_out_date
            ORDER BY s.id DESC
            LIMIT 30
        """.format(where=where)
        try:
            with engine.begin() as connection:
                rows = connection.execute(text(sql), params).mappings().all()
        except Exception:
            rows = []
        self.previous_table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.previous_table.insertRow(row_index)
            values = [row["shipment_no"], row["shipment_name"], _format_int(row["item_count"]), _fmt_date(row["factory_out_date"])]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col in {0, 2, 3}:
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
        if shipment_id:
            self.load_shipment(int(shipment_id))

    def load_shipment(self, shipment_id: int) -> None:
        with engine.begin() as connection:
            shipment = connection.execute(text("SELECT * FROM mpps_shipments WHERE id = :id LIMIT 1"), {"id": shipment_id}).mappings().first()
            items = connection.execute(text("""
                SELECT sap_code, item_description, quantity, stock_allocated_qty, production_required_qty,
                       allocated_cavity_count, production_days, item_receive_date, schedule_reason
                FROM mpps_shipment_items
                WHERE shipment_id = :id
                ORDER BY id ASC
            """), {"id": shipment_id}).mappings().all()
        if not shipment:
            return
        self.current_shipment_id = int(shipment["id"])
        self.shipment_name_input.setText(str(shipment.get("shipment_name") or shipment.get("shipment_no") or ""))
        self.customer_input.setText(str(shipment.get("customer_name") or ""))
        self.remarks_input.setPlainText(str(shipment.get("note") or ""))
        self.current_items = []
        for row in items:
            smds = self.find_master_item(str(row["sap_code"])) or {}
            self.current_items.append({
                "sap_code": str(row["sap_code"]),
                "item_description": str(row["item_description"]),
                "quantity": int(row["quantity"] or 0),
                "stock_allocated_qty": int(row["stock_allocated_qty"] or 0),
                "production_required_qty": int(row["production_required_qty"] or 0),
                "allocated_cavity_count": int(row["allocated_cavity_count"] or 0),
                "production_days": int(row["production_days"] or 0),
                "item_receive_date": row["item_receive_date"],
                "schedule_reason": str(row["schedule_reason"] or ""),
                "smds": smds,
            })
        self.refresh_items_table()

    def generate_shipment_no(self) -> str:
        prefix = "SHP-" + date.today().strftime("%Y%m%d") + "-"
        with engine.begin() as connection:
            existing = int(connection.execute(text("SELECT COUNT(*) FROM mpps_shipments WHERE shipment_no LIKE :prefix"), {"prefix": prefix + "%"}).scalar() or 0)
        return prefix + f"{existing + 1:04d}"

    def save_shipment(self) -> None:
        shipment_name = self.shipment_name_input.text().strip()
        customer = self.customer_input.text().strip() or shipment_name
        note = self.remarks_input.toPlainText().strip()
        if not shipment_name:
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment name.")
            self.shipment_name_input.setFocus()
            return
        if not self.current_items:
            QMessageBox.warning(self, "Items Required", "Please add at least one approved SMDS item.")
            self.item_search_input.setFocus()
            return
        for item in self.current_items:
            self.recalculate_item(item)
        factory_out_date = self.get_factory_out_date()
        if factory_out_date is None:
            answer = QMessageBox.question(
                self,
                "Factory Out Date Pending",
                "One or more items cannot calculate a receive date. Save shipment anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        shipment_date = factory_out_date or date.today()
        try:
            with engine.begin() as connection:
                if self.current_shipment_id:
                    shipment_id = self.current_shipment_id
                    connection.execute(text("""
                        UPDATE mpps_shipments
                        SET shipment_name = :shipment_name,
                            customer_name = :customer_name,
                            shipment_date = :shipment_date,
                            factory_out_date = :factory_out_date,
                            status = 'Planned',
                            note = :note,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """), {
                        "id": shipment_id,
                        "shipment_name": shipment_name,
                        "customer_name": customer,
                        "shipment_date": shipment_date,
                        "factory_out_date": factory_out_date,
                        "note": note,
                    })
                    connection.execute(text("DELETE FROM mpps_shipment_items WHERE shipment_id = :id"), {"id": shipment_id})
                else:
                    shipment_no = self.generate_shipment_no()
                    shipment_id = int(connection.execute(text("""
                        INSERT INTO mpps_shipments
                            (shipment_no, shipment_name, customer_name, shipment_date, factory_out_date, status, note, updated_at)
                        VALUES
                            (:shipment_no, :shipment_name, :customer_name, :shipment_date, :factory_out_date, 'Planned', :note, CURRENT_TIMESTAMP)
                        RETURNING id
                    """), {
                        "shipment_no": shipment_no,
                        "shipment_name": shipment_name,
                        "customer_name": customer,
                        "shipment_date": shipment_date,
                        "factory_out_date": factory_out_date,
                        "note": note,
                    }).scalar_one())

                for item in self.current_items:
                    connection.execute(text("""
                        INSERT INTO mpps_shipment_items
                            (shipment_id, sap_code, item_description, quantity, start_date, end_date,
                             item_status, note, stock_allocated_qty, production_required_qty,
                             allocated_cavity_count, production_days, item_receive_date, schedule_reason, updated_at)
                        VALUES
                            (:shipment_id, :sap_code, :item_description, :quantity, :start_date, :end_date,
                             'Pending', '', :stock_allocated_qty, :production_required_qty,
                             :allocated_cavity_count, :production_days, :item_receive_date, :schedule_reason, CURRENT_TIMESTAMP)
                    """), {
                        "shipment_id": shipment_id,
                        "sap_code": item["sap_code"],
                        "item_description": item["item_description"],
                        "quantity": int(item.get("quantity") or 0),
                        "start_date": date.today(),
                        "end_date": item.get("item_receive_date") or date.today(),
                        "stock_allocated_qty": int(item.get("stock_allocated_qty") or 0),
                        "production_required_qty": int(item.get("production_required_qty") or 0),
                        "allocated_cavity_count": int(item.get("allocated_cavity_count") or 0),
                        "production_days": int(item.get("production_days") or 0),
                        "item_receive_date": item.get("item_receive_date"),
                        "schedule_reason": item.get("schedule_reason", ""),
                    })
            QMessageBox.information(self, "Shipment Saved", "Shipment saved successfully with factory out date: " + _fmt_date(factory_out_date))
            self.clear_after_successful_save()
            if callable(self.on_shipment_saved):
                self.on_shipment_saved(shipment_id)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))

    def clear_form(self) -> None:
        self.current_shipment_id = None
        self.shipment_name_input.clear()
        self.customer_input.clear()
        self.remarks_input.clear()
        self.item_search_input.clear()
        self.quantity_input.setValue(1)
        self.current_items.clear()
        self.refresh_items_table()
        self.load_previous_shipments()

    def clear_after_successful_save(self) -> None:
        self.current_shipment_id = None
        self.shipment_name_input.blockSignals(True)
        self.shipment_name_input.clear()
        self.shipment_name_input.blockSignals(False)
        self.customer_input.clear()
        self.remarks_input.clear()
        self.item_search_input.clear()
        self.quantity_input.setValue(1)
        self.current_items.clear()
        self.refresh_items_table()
        self.load_previous_shipments()
        self.shipment_name_input.setFocus()


class ShipmentDemandPage(OrderEntryPage):
    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user=current_user)
