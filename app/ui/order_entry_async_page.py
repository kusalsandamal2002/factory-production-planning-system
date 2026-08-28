from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.events import EventBus
from app.core.task_manager import TaskManager
from app.services.shipment_order_async_service import (
    calculate_cart_plan,
    get_unallocated_stock,
    load_previous_shipments,
    replan_open_shipments,
    save_shipment,
    search_master_items,
)


def _fmt_date(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "—")


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value or 0)):,}"
    except Exception:
        return "0"


class _DictTableModel(QAbstractTableModel):
    def __init__(self, columns: tuple[tuple[str, str], ...], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]] | None) -> None:
        self.beginResetModel()
        self.rows = list(rows or [])
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.columns)
        ):
            return self.columns[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.columns[index.column()][1]
        value = row.get(key)

        if role == Qt.ItemDataRole.DisplayRole:
            if key in {
                "quantity",
                "stock_allocated_qty",
                "production_required_qty",
                "allocated_cavity_count",
                "daily_capacity",
                "production_days",
                "item_count",
            }:
                return _fmt_int(value)
            if key in {"item_receive_date", "target_date", "factory_receive_date"}:
                return _fmt_date(value)
            return str(value or "—")

        if role == Qt.ItemDataRole.ForegroundRole:
            if key in {"production_required_qty"} and int(row.get(key) or 0) > 0:
                return QColor("#b45309")
            if key == "item_status":
                state = str(value or "").lower()
                if "stock" in state or "ready" in state:
                    return QColor("#047857")
                if "pending" in state or "calculat" in state:
                    return QColor("#b45309")
                if "block" in state or "fail" in state or "error" in state:
                    return QColor("#b91c1c")

        if role == Qt.ItemDataRole.ToolTipRole:
            if key == "item_status":
                return str(row.get("schedule_reason") or value or "")
            if key == "tyre_description":
                line = row.get("line") or "—"
                casing = row.get("casing_type") or "—"
                mold = row.get("key_code") or "—"
                return f"Line: {line}\nMold/Key: {mold}\nCasing: {casing}"

        return None

    def row_dict(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self.rows):
            return self.rows[row]
        return None


class ShipmentOrderAsyncPage(QWidget):
    """R3 true zero-freeze shipment entry.

    This page does not inherit the legacy OrderEntryPage, does not preload the whole
    tyre master, uses QTableView models, and sends every DB/planning/save operation
    through the shared TaskManager.
    """

    TASK_PREFIX = "shipment-order-r3:"

    SEARCH_COLUMNS = (
        ("SAP", "sap_code"),
        ("Tyre Description", "tyre_description"),
        ("Line", "line"),
        ("Mold / Key", "key_code"),
        ("Casing", "casing_type"),
        ("Approval", "approval_status"),
    )
    CART_COLUMNS = (
        ("SAP", "sap_code"),
        ("Description", "item_description"),
        ("Qty", "quantity"),
        ("Stock", "stock_allocated_qty"),
        ("Production", "production_required_qty"),
        ("Cavities", "allocated_cavity_count"),
        ("Daily Capacity", "daily_capacity"),
        ("Factory Can Out", "item_receive_date"),
        ("Status", "item_status"),
    )
    HISTORY_COLUMNS = (
        ("Shipment", "shipment_name"),
        ("No.", "shipment_no"),
        ("Target", "target_date"),
        ("Factory Can Out", "factory_receive_date"),
        ("Items", "item_count"),
    )

    def __init__(self, current_user=None, on_shipment_saved=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.on_shipment_saved = on_shipment_saved
        self.task_manager = TaskManager.instance()
        self.event_bus = EventBus.instance()
        self.current_items: list[dict[str, Any]] = []
        self.selected_master_item: dict[str, Any] | None = None
        self._planning_busy = False
        self._saving = False
        self._pending_stock_sap = ""

        self.search_model = _DictTableModel(self.SEARCH_COLUMNS, self)
        self.cart_model = _DictTableModel(self.CART_COLUMNS, self)
        self.history_model = _DictTableModel(self.HISTORY_COLUMNS, self)

        self._build_ui()
        self._connect_timers()

        # R3: no full tyre-master load on page open. Only the small recent-shipment
        # query starts after the page has painted.
        QTimer.singleShot(650, self._load_recent_shipments)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-family:'Segoe UI'; color:#0f172a; }
            QFrame#Card, QFrame#Header {
                background:#ffffff; border:1px solid #dbe4ef; border-radius:16px;
            }
            QLabel#Title { font-size:24pt; font-weight:950; }
            QLabel#Section { font-size:14pt; font-weight:950; }
            QLabel#Sub { color:#64748b; font-weight:650; }
            QLabel#Status {
                background:#fffbeb; color:#92400e; border:1px solid #fde68a;
                border-radius:9px; padding:8px 11px; font-weight:800;
            }
            QLabel#GoodStatus {
                background:#ecfdf5; color:#047857; border:1px solid #a7f3d0;
                border-radius:9px; padding:8px 11px; font-weight:850;
            }
            QLineEdit, QDateEdit, QSpinBox, QTextEdit {
                background:white; border:1px solid #cbd5e1; border-radius:8px;
                padding:7px 9px;
            }
            QPushButton {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:9px;
                padding:9px 13px; font-weight:900;
            }
            QPushButton#Primary { background:#2563eb; color:white; }
            QPushButton#Danger { background:#fee2e2; color:#991b1b; }
            QTableView {
                background:white; alternate-background-color:#f8fafc;
                border:1px solid #dbe4ef; gridline-color:#e2e8f0;
                selection-background-color:#dbeafe; selection-color:#0f172a;
            }
            QHeaderView::section {
                background:#edf3f9; color:#1e293b; border:none;
                border-right:1px solid #dbe4ef; border-bottom:1px solid #dbe4ef;
                padding:8px; font-weight:950;
            }
            QProgressBar {
                border:none; background:#e2e8f0; border-radius:5px;
                min-height:8px; max-height:8px;
            }
            QProgressBar::chunk { background:#2563eb; border-radius:5px; }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 14, 18, 14)
        left = QVBoxLayout()
        title = QLabel("Shipment Order Entry")
        title.setObjectName("Title")
        sub = QLabel(
            "Create a shipment without blocking the UI. Tyre search, stock, planning and save run in background."
        )
        sub.setObjectName("Sub")
        sub.setWordWrap(True)
        left.addWidget(title)
        left.addWidget(sub)
        hl.addLayout(left, 1)
        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.clicked.connect(self.clear_form)
        self.save_btn = QPushButton("Save Shipment")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self.save_shipment)
        hl.addWidget(self.clear_btn)
        hl.addWidget(self.save_btn)
        root.addWidget(header)

        info = QFrame()
        info.setObjectName("Card")
        ig = QGridLayout(info)
        ig.setContentsMargins(16, 13, 16, 14)
        section = QLabel("Shipment Information")
        section.setObjectName("Section")
        ig.addWidget(section, 0, 0, 1, 4)

        ig.addWidget(QLabel("Shipment Name"), 1, 0)
        self.shipment_name_input = QLineEdit()
        self.shipment_name_input.setPlaceholderText("Shipment name / reference")
        ig.addWidget(self.shipment_name_input, 2, 0, 1, 2)

        ig.addWidget(QLabel("Customer / Destination"), 1, 2)
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer, destination or delivery point")
        ig.addWidget(self.customer_input, 2, 2, 1, 2)

        self.target_date_checkbox = QCheckBox("Use a specific target date")
        self.target_date_checkbox.toggled.connect(self._target_mode_changed)
        ig.addWidget(self.target_date_checkbox, 3, 0)
        self.target_date_input = QDateEdit()
        self.target_date_input.setCalendarPopup(True)
        self.target_date_input.setDisplayFormat("yyyy-MM-dd")
        self.target_date_input.setDate(QDate.currentDate())
        self.target_date_input.setEnabled(False)
        self.target_date_input.dateChanged.connect(lambda _d: self._schedule_replan())
        ig.addWidget(self.target_date_input, 3, 1)

        target_rule = QLabel("Automatic mode saves the calculated Factory Can Out date as the Target Date.")
        target_rule.setObjectName("Sub")
        target_rule.setWordWrap(True)
        ig.addWidget(target_rule, 3, 2, 1, 2)

        ig.addWidget(QLabel("Remarks / Delivery Instructions"), 4, 0, 1, 4)
        self.remarks_input = QTextEdit()
        self.remarks_input.setPlaceholderText("Optional planning notes")
        self.remarks_input.setMaximumHeight(72)
        ig.addWidget(self.remarks_input, 5, 0, 1, 4)
        root.addWidget(info)

        item_card = QFrame()
        item_card.setObjectName("Card")
        il = QVBoxLayout(item_card)
        il.setContentsMargins(16, 13, 16, 14)
        item_title = QLabel("Add Shipment Item")
        item_title.setObjectName("Section")
        il.addWidget(item_title)

        search_row = QHBoxLayout()
        self.item_search_input = QLineEdit()
        self.item_search_input.setPlaceholderText("Type at least 2 characters of SAP or tyre description...")
        self.item_search_input.textChanged.connect(lambda _text: self._search_timer.start())
        search_row.addWidget(self.item_search_input, 1)
        self.search_state = QLabel("Type to search")
        self.search_state.setObjectName("Sub")
        search_row.addWidget(self.search_state)
        il.addLayout(search_row)

        self.search_table = self._table(self.search_model)
        self.search_table.setMaximumHeight(185)
        self.search_table.clicked.connect(self._select_search_row)
        self.search_table.doubleClicked.connect(lambda _index: self._select_search_row(_index))
        self.search_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        il.addWidget(self.search_table)

        selected_row = QHBoxLayout()
        self.selected_label = QLabel("No tyre selected")
        self.selected_label.setObjectName("Sub")
        self.selected_label.setWordWrap(True)
        selected_row.addWidget(self.selected_label, 1)
        selected_row.addWidget(QLabel("Qty"))
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 1_000_000)
        self.quantity_input.setValue(1)
        selected_row.addWidget(self.quantity_input)
        self.add_btn = QPushButton("Add Item")
        self.add_btn.setObjectName("Primary")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add_item)
        selected_row.addWidget(self.add_btn)
        il.addLayout(selected_row)
        root.addWidget(item_card)

        cart_card = QFrame()
        cart_card.setObjectName("Card")
        cl = QVBoxLayout(cart_card)
        cl.setContentsMargins(16, 13, 16, 14)
        cart_head = QHBoxLayout()
        cart_title = QLabel("Shipment Items & Feasible Plan")
        cart_title.setObjectName("Section")
        cart_head.addWidget(cart_title, 1)
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.clicked.connect(self.remove_selected_item)
        cart_head.addWidget(self.remove_btn)
        cl.addLayout(cart_head)

        self.cart_table = self._table(self.cart_model)
        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cart_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.cart_table.setMinimumHeight(190)
        cl.addWidget(self.cart_table)

        self.plan_progress = QProgressBar()
        self.plan_progress.setRange(0, 0)
        self.plan_progress.hide()
        cl.addWidget(self.plan_progress)

        self.summary_label = QLabel("Add a tyre item to calculate stock coverage and Factory Can Out.")
        self.summary_label.setObjectName("GoodStatus")
        self.summary_label.setWordWrap(True)
        cl.addWidget(self.summary_label)
        root.addWidget(cart_card)

        recent_card = QFrame()
        recent_card.setObjectName("Card")
        rl = QVBoxLayout(recent_card)
        rl.setContentsMargins(16, 13, 16, 14)
        recent_head = QHBoxLayout()
        recent_title = QLabel("Recent Shipments")
        recent_title.setObjectName("Section")
        recent_head.addWidget(recent_title, 1)
        self.history_refresh_btn = QPushButton("Refresh")
        self.history_refresh_btn.clicked.connect(self._load_recent_shipments)
        recent_head.addWidget(self.history_refresh_btn)
        rl.addLayout(recent_head)
        self.history_table = self._table(self.history_model)
        self.history_table.setMaximumHeight(180)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rl.addWidget(self.history_table)
        root.addWidget(recent_card)

        self.page_status = QLabel("Ready. Tyre master is searched on demand; no full-master UI load runs on page open.")
        self.page_status.setObjectName("Status")
        self.page_status.setWordWrap(True)
        root.addWidget(self.page_status)

    def _table(self, model: _DictTableModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _connect_timers(self) -> None:
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(280)
        self._search_timer.timeout.connect(self._search_now)

        self._plan_timer = QTimer(self)
        self._plan_timer.setSingleShot(True)
        self._plan_timer.setInterval(180)
        self._plan_timer.timeout.connect(self._replan_now)

    # ------------------------------------------------------------------ tyre search
    def _search_now(self) -> None:
        query = self.item_search_input.text().strip()
        self.selected_master_item = None
        self.add_btn.setEnabled(False)
        self.selected_label.setText("No tyre selected")
        self.task_manager.cancel(self.TASK_PREFIX + "search")
        if len(query) < 2:
            self.search_model.set_rows([])
            self.search_state.setText("Type at least 2 characters")
            return

        self.search_state.setText("Searching...")
        self.task_manager.submit(
            self.TASK_PREFIX + "search",
            lambda q=query: search_master_items(q, limit=40),
            on_result=self._apply_search_results,
            on_error=self._search_error,
            priority=3,
            replace=True,
        )

    def _apply_search_results(self, rows: list[dict[str, Any]]) -> None:
        self.search_model.set_rows(rows)
        self.search_state.setText(f"{len(rows):,} match(es)")
        if not rows:
            self.selected_label.setText("No matching approved/master tyre found.")

    def _search_error(self, message: str) -> None:
        self.search_model.set_rows([])
        self.search_state.setText("Search unavailable")
        self.page_status.setText("Tyre search failed: " + (message.splitlines()[-1] if message else "Unknown error"))

    def _select_search_row(self, index: QModelIndex) -> None:
        item = self.search_model.row_dict(index.row())
        if not item:
            return
        self.selected_master_item = dict(item)
        sap = str(item.get("sap_code") or "")
        self._pending_stock_sap = sap
        self.add_btn.setEnabled(False)
        self.selected_label.setText(
            f"SAP {sap} • {item.get('tyre_description') or '—'} • "
            f"Line {item.get('line') or '—'} • Stock loading..."
        )
        self.task_manager.submit(
            self.TASK_PREFIX + "stock",
            lambda s=sap: (s, get_unallocated_stock(s)),
            on_result=self._apply_selected_stock,
            on_error=lambda _msg: self._selected_stock_failed(),
            priority=4,
            replace=True,
        )

    def _apply_selected_stock(self, payload) -> None:
        sap, stock = payload
        if not self.selected_master_item or str(sap) != str(self.selected_master_item.get("sap_code") or ""):
            return
        self.selected_master_item["unallocated_stock"] = int(stock or 0)
        self.selected_label.setText(
            f"SAP {sap} • {self.selected_master_item.get('tyre_description') or '—'} • "
            f"Unallocated Stock {_fmt_int(stock)} • Line {self.selected_master_item.get('line') or '—'}"
        )
        self.add_btn.setEnabled(True)

    def _selected_stock_failed(self) -> None:
        if self.selected_master_item:
            self.selected_master_item["unallocated_stock"] = 0
            self.selected_label.setText(
                f"SAP {self.selected_master_item.get('sap_code')} • stock unavailable; item can still be planned."
            )
            self.add_btn.setEnabled(True)

    # ------------------------------------------------------------------ cart/planning
    def add_item(self) -> None:
        item = self.selected_master_item
        if not item:
            return
        sap = str(item.get("sap_code") or "").strip()
        qty = int(self.quantity_input.value())
        if not sap or qty <= 0:
            return

        existing = next((row for row in self.current_items if row.get("sap_code") == sap), None)
        if existing is not None:
            existing["quantity"] = int(existing.get("quantity") or 0) + qty
        else:
            self.current_items.append(
                {
                    "sap_code": sap,
                    "item_description": str(item.get("tyre_description") or ""),
                    "quantity": qty,
                    "stock_allocated_qty": min(qty, int(item.get("unallocated_stock") or 0)),
                    "production_required_qty": max(qty - int(item.get("unallocated_stock") or 0), 0),
                    "allocated_cavity_count": 0,
                    "daily_capacity": 0,
                    "production_days": 0,
                    "item_receive_date": None,
                    "item_status": "Planning...",
                    "schedule_reason": "Queued for background feasibility planning.",
                }
            )

        self.cart_model.set_rows(self.current_items)
        self.quantity_input.setValue(1)
        self._schedule_replan()

    def remove_selected_item(self) -> None:
        selection = self.cart_table.selectionModel().selectedRows()
        if not selection:
            return
        row = selection[0].row()
        if 0 <= row < len(self.current_items):
            self.current_items.pop(row)
            self.cart_model.set_rows(self.current_items)
            self._schedule_replan()

    def _target_mode_changed(self, checked: bool) -> None:
        self.target_date_input.setEnabled(bool(checked))
        self._schedule_replan()

    def _schedule_replan(self) -> None:
        self.task_manager.cancel(self.TASK_PREFIX + "cart-plan")
        if not self.current_items:
            self._planning_busy = False
            self.plan_progress.hide()
            self.save_btn.setEnabled(True)
            self.summary_label.setText("Add a tyre item to calculate stock coverage and Factory Can Out.")
            return
        self._plan_timer.start()

    def _manual_target(self) -> date | None:
        if not self.target_date_checkbox.isChecked():
            return None
        return self.target_date_input.date().toPython()

    def _replan_now(self) -> None:
        if not self.current_items:
            return
        preview = [
            {
                "sap_code": str(item.get("sap_code") or ""),
                "item_description": str(item.get("item_description") or ""),
                "quantity": int(item.get("quantity") or 0),
                "produced_qty": int(item.get("produced_qty") or 0),
            }
            for item in self.current_items
        ]
        target = self._manual_target()
        self._planning_busy = True
        self.save_btn.setEnabled(False)
        self.plan_progress.show()
        self.summary_label.setText("Calculating feasible stock allocation, production and Factory Can Out in background...")
        self.task_manager.submit(
            self.TASK_PREFIX + "cart-plan",
            lambda: calculate_cart_plan(
                preview,
                target_date=target,
                target_date_is_manual=self.target_date_checkbox.isChecked(),
            ),
            on_result=self._apply_plan,
            on_error=self._plan_error,
            priority=1,
            replace=True,
        )

    def _apply_plan(self, results: list[dict[str, Any]]) -> None:
        if len(results or []) != len(self.current_items):
            self._plan_error("Planner returned an incomplete result set.")
            return
        for item, result in zip(self.current_items, results):
            item["stock_allocated_qty"] = int(result.get("stock_allocated_qty") or 0)
            item["production_required_qty"] = int(result.get("production_required_qty") or result.get("remaining_qty") or 0)
            item["allocated_cavity_count"] = int(result.get("allocated_cavity_count") or 0)
            item["daily_capacity"] = int(result.get("daily_capacity") or 0)
            item["production_days"] = int(result.get("production_days") or 0)
            item["item_receive_date"] = result.get("receive_date") or result.get("item_receive_date")
            item["item_status"] = str(result.get("status") or result.get("item_status") or "Planned")
            item["schedule_reason"] = str(result.get("reason") or result.get("schedule_reason") or "")

        self._planning_busy = False
        self.plan_progress.hide()
        self.save_btn.setEnabled(not self._saving)
        self.cart_model.set_rows(self.current_items)
        self._update_summary()

    def _plan_error(self, message: str) -> None:
        reason = (message.splitlines()[-1] if message else "Planning failed")[:260]
        for item in self.current_items:
            item["item_status"] = "Planning Failed"
            item["schedule_reason"] = reason
        self._planning_busy = False
        self.plan_progress.hide()
        self.save_btn.setEnabled(False)
        self.cart_model.set_rows(self.current_items)
        self.summary_label.setText("Planning failed: " + reason)

    def _update_summary(self) -> None:
        total = sum(int(item.get("quantity") or 0) for item in self.current_items)
        stock = sum(int(item.get("stock_allocated_qty") or 0) for item in self.current_items)
        production = sum(int(item.get("production_required_qty") or 0) for item in self.current_items)
        dates = [item.get("item_receive_date") for item in self.current_items if item.get("item_receive_date")]
        factory_out = max(dates) if dates else None
        coverage = (stock / total * 100.0) if total else 0.0
        self.summary_label.setText(
            f"Order Qty {_fmt_int(total)} • Stock Covered {_fmt_int(stock)} ({coverage:.1f}%) • "
            f"Production Required {_fmt_int(production)} • Factory Can Out {_fmt_date(factory_out)}"
        )

    # ------------------------------------------------------------------ save
    def save_shipment(self) -> None:
        if self._saving:
            return
        if self._planning_busy:
            QMessageBox.information(self, "Planning In Progress", "Background planning is still running.")
            return
        shipment_name = self.shipment_name_input.text().strip()
        if not shipment_name:
            QMessageBox.warning(self, "Shipment Required", "Please enter a shipment name.")
            self.shipment_name_input.setFocus()
            return
        if not self.current_items:
            QMessageBox.warning(self, "Items Required", "Please add at least one shipment item.")
            return
        if any(item.get("item_receive_date") is None for item in self.current_items):
            QMessageBox.warning(
                self,
                "Plan Required",
                "One or more items do not have a feasible Factory Can Out date. Resolve planning before saving.",
            )
            return

        payload = {
            "shipment_name": shipment_name,
            "customer": self.customer_input.text().strip(),
            "note": self.remarks_input.toPlainText().strip(),
            "target_date_is_manual": self.target_date_checkbox.isChecked(),
            "target_date": self._manual_target(),
            "items": [dict(item) for item in self.current_items],
        }
        self._saving = True
        self.save_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.plan_progress.show()
        self.page_status.setText("Saving shipment in background...")
        self.task_manager.submit(
            self.TASK_PREFIX + "save",
            lambda: save_shipment(payload),
            on_result=self._save_done,
            on_error=self._save_error,
            priority=2,
            replace=True,
        )

    def _save_done(self, result: dict[str, Any]) -> None:
        self._saving = False
        self.plan_progress.hide()
        self.clear_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        shipment_id = int(result.get("shipment_id") or 0)
        self.page_status.setText(
            f"Shipment saved • {result.get('shipment_no') or ''} • "
            f"Factory Can Out {_fmt_date(result.get('factory_receive_date'))} • {result.get('promise') or ''}"
        )
        self.event_bus.publish("ShipmentCreated", shipment_id=shipment_id)

        callback = self.on_shipment_saved
        self.clear_form()

        # Full cumulative replan is deliberately separated from the short save
        # transaction and runs at low priority under a global planning key. It is
        # not cancelled when this shipment-entry page is cleared or navigated away.
        self.task_manager.submit(
            "planning:shipment-entry-replan",
            lambda sid=shipment_id: replan_open_shipments(f"shipment_entry_r3_save_{sid}"),
            on_result=lambda _payload: self.event_bus.publish("PlanGenerated", shipment_id=shipment_id),
            on_error=lambda msg: print("[MPPS R3 REPLAN WARNING] " + (msg.splitlines()[-1] if msg else "failed"), flush=True),
            priority=-2,
            replace=True,
        )

        self._load_recent_shipments()
        if callable(callback):
            callback(shipment_id)

    def _save_error(self, message: str) -> None:
        self._saving = False
        self.plan_progress.hide()
        self.clear_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        reason = message.splitlines()[-1] if message else "Save failed"
        self.page_status.setText("Save failed: " + reason)
        QMessageBox.critical(self, "Save Failed", reason)

    # ------------------------------------------------------------------ history
    def _load_recent_shipments(self) -> None:
        self.history_refresh_btn.setEnabled(False)
        self.task_manager.submit(
            self.TASK_PREFIX + "history",
            lambda: load_previous_shipments("", limit=20),
            on_result=self._apply_history,
            on_error=lambda _msg: self._apply_history([]),
            priority=0,
            replace=True,
        )

    def _apply_history(self, rows: list[dict[str, Any]]) -> None:
        self.history_model.set_rows(rows)
        self.history_refresh_btn.setEnabled(True)

    # ------------------------------------------------------------------ external API
    def clear_form(self) -> None:
        self.task_manager.cancel_prefix(self.TASK_PREFIX)
        self._planning_busy = False
        self._saving = False
        self.shipment_name_input.clear()
        self.customer_input.clear()
        self.remarks_input.clear()
        self.target_date_checkbox.setChecked(False)
        self.target_date_input.setDate(QDate.currentDate())
        self.item_search_input.clear()
        self.search_model.set_rows([])
        self.selected_master_item = None
        self.selected_label.setText("No tyre selected")
        self.add_btn.setEnabled(False)
        self.current_items.clear()
        self.cart_model.set_rows([])
        self.plan_progress.hide()
        self.clear_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.summary_label.setText("Add a tyre item to calculate stock coverage and Factory Can Out.")
        self.page_status.setText("Ready. Tyre master is searched on demand; no full-master UI load runs on page open.")
        self.shipment_name_input.setFocus()

    def handle_domain_event(self, event) -> None:
        name = getattr(event, "name", "")
        if name in {"StockChanged", "MasterDataChanged", "SourceCommitted"} and self.current_items:
            self._schedule_replan()
        if name in {"ShipmentCreated", "ShipmentUpdated", "ShipmentCancelled", "ShipmentShipped"}:
            self._load_recent_shipments()

    def closeEvent(self, event) -> None:
        self.task_manager.cancel_prefix(self.TASK_PREFIX)
        super().closeEvent(event)
