from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, QTimer, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDateEdit,
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
    QStackedWidget,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app.core.events import EventBus
from app.core.task_manager import TaskManager


def _date_text(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _num(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(float(value)):,}"
    except Exception:
        return str(value)


def _priority_text(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        return str(int(value))
    except Exception:
        return str(value)


def _stock_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return str(value)


def _status_text(value: Any) -> str:
    mapping = {
        "CLOSURE_REVIEW": "Closure Review",
        "NOT_PLANNED": "Not Planned",
        "PLANNED": "Planned",
        "IN_PRODUCTION": "In Production",
        "READY_FOR_DISPATCH": "Ready for Dispatch",
        "HOLD": "On Hold",
        "SHIPPED": "Shipped",
        "CANCELLED": "Cancelled",
    }
    key = str(value or "").upper()
    return mapping.get(key, str(value or "—"))


class _DictModel(QAbstractTableModel):
    def __init__(self, columns: list[tuple[str, str, Any]], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = list(rows or [])
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

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
        _label, key, formatter = self.columns[index.column()]
        value = row.get(key)

        if role == Qt.ItemDataRole.DisplayRole:
            return formatter(value) if formatter else ("—" if value in (None, "") else str(value))

        if role == Qt.ItemDataRole.ToolTipRole:
            if key == "priority_no" and row.get("priority_no") is not None:
                return "Priority basis: " + str(row.get("priority_reason") or "active shipment priority")
            if key == "operational_status" and bool(row.get("needs_attention")):
                drivers = row.get("risk_drivers") or []
                if isinstance(drivers, (list, tuple)) and drivers:
                    return "Needs attention: " + "; ".join(str(item) for item in drivers)
                return "This shipment currently needs operational attention."

        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "priority_no" and row.get("priority_no") is not None:
                return QColor("#1d4ed8")
            if key == "operational_status":
                status = str(value or "").upper()
                if status in {"SHIPPED", "READY_FOR_DISPATCH"}:
                    return QColor("#047857")
                if status in {"CANCELLED", "CLOSURE_REVIEW"}:
                    return QColor("#b91c1c")
                if status in {"HOLD", "NOT_PLANNED"}:
                    return QColor("#b45309")
                if status == "IN_PRODUCTION":
                    return QColor("#1d4ed8")

        if role == Qt.ItemDataRole.FontRole and key == "priority_no" and row.get("priority_no") is not None:
            if self.parent() is not None:
                font = QFont(self.parent().font())
                font.setBold(True)
                return font

        if role == Qt.ItemDataRole.TextAlignmentRole and key in {
            "priority_no",
            "target_date",
            "factory_can_receive_date",
            "total_quantity",
            "stock_progress_pct",
            "production_gap",
        }:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return None

    def row_at(self, index: QModelIndex) -> dict[str, Any] | None:
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        return self.rows[index.row()]


PORTFOLIO_COLUMNS = [
    ("Priority No.", "priority_no", _priority_text),
    ("Shipment", "shipment_name", None),
    ("Target Date", "target_date", _date_text),
    ("Factory Can Out", "factory_can_receive_date", _date_text),
    ("Qty", "total_quantity", _num),
    ("Stock %", "stock_progress_pct", _stock_pct),
    ("Production Gap", "production_gap", _num),
    ("Status", "operational_status", _status_text),
]

REVIEW_COLUMNS = [
    ("Shipment", "shipment_name", None),
    ("Target Date", "target_date", _date_text),
    ("Factory Can Out", "factory_can_receive_date", _date_text),
    ("Qty", "total_quantity", _num),
    ("Stock %", "stock_progress_pct", _stock_pct),
    ("Status", "operational_status", _status_text),
]

DETAIL_COLUMNS = [
    ("SAP", "sap_code", None),
    ("Description", "item_description", None),
    ("Order Qty", "quantity", _num),
    ("Stock Allocated", "stock_allocated_qty", _num),
    ("Production Gap", "production_required_qty", _num),
    ("Produced", "produced_qty", _num),
    ("Remaining", "remaining_qty", _num),
    ("Production Start", "production_start", _date_text),
    ("Expected Finish", "expected_finish", _date_text),
    ("State", "item_status", None),
]

ALL_FILTERS = (
    ("All", "ALL"),
    ("Needs Attention", "NEEDS_ATTENTION"),
    ("Closure Review", "CLOSURE_REVIEW"),
    ("Not Planned", "NOT_PLANNED"),
    ("Planned", "PLANNED"),
    ("In Production", "IN_PRODUCTION"),
    ("Ready", "READY_FOR_DISPATCH"),
    ("Hold", "HOLD"),
    ("Shipped", "SHIPPED"),
    ("Cancelled", "CANCELLED"),
)

ACTIVE_STATUSES = {
    "NOT_PLANNED",
    "PLANNED",
    "IN_PRODUCTION",
    "READY_FOR_DISPATCH",
}


class ShipmentDetailsProPage(QWidget):
    TASK_PREFIX = "shipment-details-pro:"

    def __init__(self, current_user=None, on_new_shipment=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.on_new_shipment = on_new_shipment
        self.task_manager = TaskManager.instance()
        self.event_bus = EventBus.instance()
        self.current_shipment_id: int | None = None
        self._all_rows: list[dict[str, Any]] = []
        self._all_filter_key = "ALL"

        self.active_model = _DictModel(PORTFOLIO_COLUMNS, self)
        self.all_model = _DictModel(PORTFOLIO_COLUMNS, self)
        self.review_model = _DictModel(REVIEW_COLUMNS, self)
        self.detail_model = _DictModel(DETAIL_COLUMNS, self)
        self.detail_page: QWidget | None = None

        self._build_ui()
        QTimer.singleShot(30, self.refresh)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget{font-family:'Segoe UI';}
            QFrame#Header,QFrame#Panel,QFrame#Metric{background:#fff;border:1px solid #dbe4ef;border-radius:15px;}
            QLabel#Title{color:#0f172a;font-size:23pt;font-weight:950;}
            QLabel#Sub{color:#64748b;font-size:9pt;font-weight:650;}
            QLabel#Section{color:#0f172a;font-size:14pt;font-weight:950;}
            QLabel#MetricValue{color:#0f172a;font-size:18pt;font-weight:950;}
            QLabel#MetricTitle{color:#64748b;font-size:8pt;font-weight:850;}
            QLabel#Review{background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:10px;padding:8px 10px;font-weight:900;}
            QPushButton{background:#e2e8f0;color:#0f172a;border:none;border-radius:9px;padding:8px 12px;font-weight:900;}
            QPushButton#Primary{background:#2563eb;color:#fff;}
            QPushButton#Danger{background:#fee2e2;color:#b91c1c;}
            QPushButton#Good{background:#dcfce7;color:#047857;}
            QPushButton#FilterChip{background:#f1f5f9;color:#475569;border:1px solid #dbe4ef;border-radius:9px;padding:7px 10px;font-weight:850;}
            QPushButton#FilterChip:checked{background:#2563eb;color:#fff;border-color:#2563eb;}
            QLineEdit{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:7px 9px;}
            QTableView{background:#fff;alternate-background-color:#f8fafc;border:1px solid #dbe4ef;gridline-color:#e2e8f0;selection-background-color:#dbeafe;selection-color:#0f172a;}
            QHeaderView::section{background:#edf3f9;color:#1e293b;border:none;border-right:1px solid #dbe4ef;border-bottom:1px solid #dbe4ef;padding:8px;font-weight:950;}
            QTabWidget::pane{border:0;background:transparent;}
            QTabBar::tab{background:#f1f5f9;color:#475569;padding:9px 18px;margin-right:3px;border-top-left-radius:8px;border-top-right-radius:8px;font-weight:900;}
            QTabBar::tab:selected{background:#2563eb;color:#fff;}
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.list_page = self._build_list_page()
        self.pages.addWidget(self.list_page)

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 12, 18, 12)
        left = QVBoxLayout()
        title = QLabel("Shipment Details")
        title.setObjectName("Title")
        sub = QLabel(
            "Priority-based active shipment control, full lifecycle history and closure review. "
            "Database work runs in background."
        )
        sub.setObjectName("Sub")
        left.addWidget(title)
        left.addWidget(sub)
        hl.addLayout(left, 1)
        self.new_btn = QPushButton("New Shipment")
        self.new_btn.setObjectName("Primary")
        if callable(self.on_new_shipment):
            self.new_btn.clicked.connect(self.on_new_shipment)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(self.new_btn)
        hl.addWidget(self.refresh_btn)
        root.addWidget(header)

        search_panel = QFrame()
        search_panel.setObjectName("Panel")
        search_layout = QHBoxLayout(search_panel)
        search_layout.setContentsMargins(10, 8, 10, 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search shipment, customer or SAP...")
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search.textChanged.connect(lambda _text: self.search_timer.start())
        self.search_timer.timeout.connect(self._apply_local_filters)
        search_layout.addWidget(QLabel("Search"))
        search_layout.addWidget(self.search, 1)
        root.addWidget(search_panel)

        metrics = QGridLayout()
        self.metric_labels: dict[str, QLabel] = {}
        for i, (key, caption) in enumerate(
            (
                ("active", "Active Planning"),
                ("attention", "Needs Attention"),
                ("ready", "Ready for Dispatch"),
                ("review", "Closure Review"),
            )
        ):
            card = QFrame()
            card.setObjectName("Metric")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            value = QLabel("—")
            value.setObjectName("MetricValue")
            label = QLabel(caption)
            label.setObjectName("MetricTitle")
            cl.addWidget(value)
            cl.addWidget(label)
            metrics.addWidget(card, 0, i)
            self.metric_labels[key] = value
        root.addLayout(metrics)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.addTab(self._build_active_tab(), "Active Shipments")
        self.workspace_tabs.addTab(self._build_all_tab(), "All Shipments")
        root.addWidget(self.workspace_tabs, 1)

        self.status = QLabel("Loading shipment portfolio in background...")
        self.status.setObjectName("Sub")
        root.addWidget(self.status)
        return page

    def _build_active_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(8)

        self.review_panel = QFrame()
        self.review_panel.setObjectName("Panel")
        rl = QVBoxLayout(self.review_panel)
        rl.setContentsMargins(12, 10, 12, 10)
        self.review_label = QLabel("NEEDS CLOSURE REVIEW")
        self.review_label.setObjectName("Review")
        rl.addWidget(self.review_label)
        self.review_table = self._table(self.review_model)
        self.review_table.setMaximumHeight(180)
        self.review_table.doubleClicked.connect(self._open_review_index)
        rl.addWidget(self.review_table)
        root.addWidget(self.review_panel)

        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 8, 10, 10)
        section = QLabel("Active Planning Queue")
        section.setObjectName("Section")
        pl.addWidget(section)
        self.active_table = self._table(self.active_model)
        self.active_table.doubleClicked.connect(self._open_active_index)
        pl.addWidget(self.active_table)
        root.addWidget(panel, 1)
        return page

    def _build_all_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(8)

        filter_panel = QFrame()
        filter_panel.setObjectName("Panel")
        fl = QHBoxLayout(filter_panel)
        fl.setContentsMargins(10, 8, 10, 8)
        self.all_filter_group = QButtonGroup(self)
        self.all_filter_group.setExclusive(True)
        self.all_filter_buttons: dict[str, QPushButton] = {}
        for label, key in ALL_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=key: self._set_all_filter(value))
            self.all_filter_group.addButton(button)
            self.all_filter_buttons[key] = button
            fl.addWidget(button)
        fl.addStretch()
        self.all_filter_buttons["ALL"].setChecked(True)
        root.addWidget(filter_panel)

        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 8, 10, 10)
        self.all_section = QLabel("All Shipment History")
        self.all_section.setObjectName("Section")
        pl.addWidget(self.all_section)
        self.all_table = self._table(self.all_model)
        self.all_table.doubleClicked.connect(self._open_all_index)
        pl.addWidget(self.all_table)
        root.addWidget(panel, 1)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 16, 12)
        self.back_btn = QPushButton("← Shipments")
        self.back_btn.clicked.connect(lambda: self.pages.setCurrentWidget(self.list_page))
        hl.addWidget(self.back_btn)

        title_box = QVBoxLayout()
        self.detail_title = QLabel("Shipment")
        self.detail_title.setObjectName("Title")
        self.detail_sub = QLabel("")
        self.detail_sub.setObjectName("Sub")
        title_box.addWidget(self.detail_title)
        title_box.addWidget(self.detail_sub)
        hl.addLayout(title_box, 1)

        self.ship_btn = QPushButton("Mark Shipped")
        self.ship_btn.setObjectName("Good")
        self.ship_btn.clicked.connect(self._mark_shipped)
        self.hold_btn = QPushButton("Hold")
        self.hold_btn.clicked.connect(self._hold)
        self.restore_btn = QPushButton("Restore Active")
        self.restore_btn.clicked.connect(self._restore)
        self.cancel_btn = QPushButton("Cancel Shipment")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.clicked.connect(self._cancel)
        hl.addWidget(self.ship_btn)
        hl.addWidget(self.hold_btn)
        hl.addWidget(self.restore_btn)
        hl.addWidget(self.cancel_btn)
        root.addWidget(header)

        self.detail_status = QLabel("Loading...")
        self.detail_status.setObjectName("Review")
        root.addWidget(self.detail_status)

        grid = QGridLayout()
        self.detail_metrics: dict[str, QLabel] = {}
        for i, (key, caption) in enumerate(
            (
                ("target", "Target Date"),
                ("factory", "Factory Can Out"),
                ("variance", "Delivery Variance"),
                ("qty", "Order Qty"),
                ("stock", "Stock Covered"),
                ("gap", "Production Gap"),
                ("ready", "Ready Qty"),
                ("coverage", "Coverage"),
            )
        ):
            card = QFrame()
            card.setObjectName("Metric")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            value = QLabel("—")
            value.setObjectName("MetricValue")
            label = QLabel(caption)
            label.setObjectName("MetricTitle")
            cl.addWidget(value)
            cl.addWidget(label)
            grid.addWidget(card, i // 4, i % 4)
            self.detail_metrics[key] = value
        root.addLayout(grid)

        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 8, 10, 10)
        section = QLabel("Item Stock & Production Schedule")
        section.setObjectName("Section")
        pl.addWidget(section)
        self.detail_table = self._table(self.detail_model)
        pl.addWidget(self.detail_table)
        root.addWidget(panel, 1)
        return page

    def _table(self, model: _DictModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.status.setText("Refreshing shipment portfolio in background...")

        def load_portfolio_job():
            from app.services.shipment_lifecycle_service import load_portfolio

            return load_portfolio({})

        self.task_manager.submit(
            self.TASK_PREFIX + "portfolio",
            load_portfolio_job,
            on_result=self._portfolio_loaded,
            on_error=self._load_error,
            replace=True,
        )

    refresh_page = refresh
    load_data = refresh

    def _portfolio_loaded(self, payload: dict[str, Any]) -> None:
        self.refresh_btn.setEnabled(True)
        self._all_rows = list(payload.get("rows") or [])
        reviews = [
            row for row in self._all_rows if row.get("operational_status") == "CLOSURE_REVIEW"
        ]
        self.review_model.set_rows(reviews[:20])
        self.review_panel.setVisible(bool(reviews))
        self.review_label.setText(
            f"NEEDS CLOSURE REVIEW • {len(reviews)} shipment(s) missing/review-required in latest authority"
        )

        status_counts = dict(payload.get("status_counts") or {})
        active_count = sum(int(status_counts.get(key) or 0) for key in ACTIVE_STATUSES)
        self.metric_labels["active"].setText(_num(active_count))
        self.metric_labels["attention"].setText(_num(payload.get("needs_attention_count") or 0))
        self.metric_labels["ready"].setText(_num(status_counts.get("READY_FOR_DISPATCH") or 0))
        self.metric_labels["review"].setText(_num(len(reviews)))

        self._apply_local_filters()
        self.status.setText(
            f"{len(self._all_rows):,} shipment(s) loaded. "
            "Active rows use dynamic Priority No.; closure/hold/shipped/cancelled rows do not."
        )

    def _load_error(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.status.setText(
            "Shipment background load failed: "
            + (message.splitlines()[-1] if message else "unknown error")
        )

    def _matches_search(self, row: dict[str, Any], query: str) -> bool:
        if not query:
            return True
        haystack = " ".join(
            str(row.get(key) or "")
            for key in (
                "shipment_name",
                "shipment_no",
                "customer_name",
                "item_search_text",
                "operational_status",
            )
        ).lower()
        return query in haystack

    def _apply_local_filters(self) -> None:
        query = self.search.text().strip().lower()

        active_rows = [
            row
            for row in self._all_rows
            if row.get("operational_status") in ACTIVE_STATUSES
            and self._matches_search(row, query)
        ]
        active_rows.sort(
            key=lambda row: (
                row.get("priority_no") if row.get("priority_no") is not None else 10**9,
                row.get("target_date") or date.max,
                int(row.get("shipment_pk") or 0),
            )
        )
        self.active_model.set_rows(active_rows)

        all_rows = [row for row in self._all_rows if self._matches_search(row, query)]
        if self._all_filter_key == "NEEDS_ATTENTION":
            all_rows = [row for row in all_rows if bool(row.get("needs_attention"))]
        elif self._all_filter_key != "ALL":
            all_rows = [
                row
                for row in all_rows
                if row.get("operational_status") == self._all_filter_key
            ]
        self.all_model.set_rows(all_rows)

        label = next(
            (caption for caption, key in ALL_FILTERS if key == self._all_filter_key),
            self._all_filter_key,
        )
        if self._all_filter_key == "ALL":
            self.all_section.setText(f"All Shipment History • {len(all_rows):,}")
        else:
            self.all_section.setText(f"{label} • {len(all_rows):,}")

    def _set_all_filter(self, key: str) -> None:
        self._all_filter_key = str(key or "ALL")
        self._apply_local_filters()

    def _open_active_index(self, index: QModelIndex) -> None:
        row = self.active_model.row_at(index)
        if row:
            self.open_shipment_detail(int(row.get("shipment_pk") or 0))

    def _open_all_index(self, index: QModelIndex) -> None:
        row = self.all_model.row_at(index)
        if row:
            self.open_shipment_detail(int(row.get("shipment_pk") or 0))

    def _open_review_index(self, index: QModelIndex) -> None:
        row = self.review_model.row_at(index)
        if row:
            self.open_shipment_detail(int(row.get("shipment_pk") or 0))

    def open_shipment_detail(self, shipment_id: int) -> None:
        if not shipment_id:
            return
        if self.detail_page is None:
            self.detail_page = self._build_detail_page()
            self.pages.addWidget(self.detail_page)
        self.current_shipment_id = int(shipment_id)
        self.pages.setCurrentWidget(self.detail_page)
        self.detail_title.setText("Loading shipment...")
        self.detail_status.setText("Reading detail snapshot in background...")

        def load_detail_job():
            from app.services.shipment_lifecycle_service import load_detail

            return load_detail(shipment_id)

        self.task_manager.submit(
            self.TASK_PREFIX + "detail",
            load_detail_job,
            on_result=self._detail_loaded,
            on_error=lambda msg: self.detail_status.setText(
                "Detail load failed: " + (msg.splitlines()[-1] if msg else "error")
            ),
            replace=True,
        )

    def _detail_loaded(self, payload: dict[str, Any]) -> None:
        shipment = dict(payload.get("shipment") or {})
        metrics = dict(payload.get("metrics") or {})
        self.current_shipment_id = int(shipment.get("id") or 0)
        lifecycle = str(shipment.get("lifecycle") or "ACTIVE")
        operational = _status_text(shipment.get("operational_status"))

        self.detail_title.setText(
            str(shipment.get("display_name") or shipment.get("shipment_no") or "Shipment")
        )
        self.detail_sub.setText(
            f"{shipment.get('shipment_no') or '-'} • {shipment.get('customer_name') or '-'}"
        )
        delivery = str(shipment.get("delivery_status") or "")
        self.detail_status.setText(
            f"Status: {operational}  •  Lifecycle: {lifecycle}  •  Delivery: {delivery or '—'}"
        )

        self.detail_metrics["target"].setText(_date_text(shipment.get("target_date")))
        factory = (
            shipment.get("actual_factory_out_date")
            or shipment.get("factory_out_date")
            or shipment.get("factory_can_receive_date")
        )
        self.detail_metrics["factory"].setText(_date_text(factory))
        variance = metrics.get("delivery_variance_days")
        self.detail_metrics["variance"].setText(
            "—"
            if variance is None
            else (
                f"{abs(int(variance))} days late"
                if int(variance) > 0
                else (f"{abs(int(variance))} days early" if int(variance) < 0 else "On target")
            )
        )
        self.detail_metrics["qty"].setText(_num(metrics.get("order_qty")))
        self.detail_metrics["stock"].setText(_num(metrics.get("stock_covered")))
        self.detail_metrics["gap"].setText(_num(metrics.get("production_gap")))
        self.detail_metrics["ready"].setText(_num(metrics.get("ready_qty")))
        coverage = metrics.get("coverage_pct")
        self.detail_metrics["coverage"].setText(
            "—" if coverage is None else f"{float(coverage):.1f}%"
        )
        self.detail_model.set_rows(list(payload.get("items") or []))

        closed = lifecycle in {"SHIPPED", "CANCELLED"}
        self.ship_btn.setEnabled(not closed)
        self.cancel_btn.setEnabled(not closed)
        self.hold_btn.setEnabled(lifecycle not in {"SHIPPED", "CANCELLED", "HOLD"})
        self.restore_btn.setEnabled(lifecycle in {"HOLD", "CLOSURE_REVIEW"})

    def _user_id(self):
        value = getattr(self.current_user, "id", None)
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    def _mark_shipped(self) -> None:
        if not self.current_shipment_id:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Mark Shipment Shipped")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Actual Factory Out Date"))
        picker = QDateEdit(QDate.currentDate())
        picker.setCalendarPopup(True)
        picker.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(picker)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_lifecycle("SHIPPED", actual_date=picker.date().toPython())

    def _cancel(self) -> None:
        if not self.current_shipment_id:
            return
        reason, ok = QInputDialog.getText(self, "Cancel Shipment", "Cancellation reason:")
        if ok and reason.strip():
            self._run_lifecycle("CANCELLED", reason=reason.strip())

    def _hold(self) -> None:
        if not self.current_shipment_id:
            return
        reason, ok = QInputDialog.getText(self, "Put Shipment On Hold", "Hold reason:")
        if ok:
            self._run_lifecycle("HOLD", reason=reason.strip())

    def _restore(self) -> None:
        if not self.current_shipment_id:
            return
        if (
            QMessageBox.question(
                self,
                "Restore Shipment",
                "Restore this shipment to the active planning queue?",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._run_lifecycle("ACTIVE", reason="Restored by user")

    def _run_lifecycle(
        self,
        lifecycle: str,
        *,
        reason: str = "",
        actual_date: date | None = None,
    ) -> None:
        shipment_id = int(self.current_shipment_id or 0)
        user_id = self._user_id()
        self.detail_status.setText(f"Applying {lifecycle} in background...")

        def lifecycle_job():
            from app.services.shipment_lifecycle_service import set_lifecycle

            return set_lifecycle(
                shipment_id,
                lifecycle,
                user_id=user_id,
                reason=reason,
                actual_factory_out_date=actual_date,
            )

        self.task_manager.submit(
            self.TASK_PREFIX + "lifecycle",
            lifecycle_job,
            on_result=lambda payload: self._lifecycle_done(lifecycle, payload),
            on_error=lambda msg: QMessageBox.warning(
                self,
                "Shipment Lifecycle",
                msg.splitlines()[-1] if msg else "Action failed",
            ),
            replace=True,
        )

    def _lifecycle_done(self, lifecycle: str, payload: dict[str, Any]) -> None:
        event_name = {
            "SHIPPED": "ShipmentShipped",
            "CANCELLED": "ShipmentCancelled",
            "HOLD": "ShipmentUpdated",
            "ACTIVE": "ShipmentUpdated",
        }.get(lifecycle, "ShipmentUpdated")
        self.event_bus.publish(
            event_name,
            shipment_id=self.current_shipment_id,
            lifecycle=lifecycle,
        )
        self._detail_loaded(payload)
        self.refresh()

    def handle_domain_event(self, event) -> None:
        if getattr(event, "name", "") in {
            "SourceCommitted",
            "ShipmentCreated",
            "ShipmentUpdated",
            "ShipmentCancelled",
            "ShipmentShipped",
            "StockChanged",
            "PlanGenerated",
        }:
            self.refresh()

    def closeEvent(self, event) -> None:
        self.task_manager.cancel_prefix(self.TASK_PREFIX)
        super().closeEvent(event)
