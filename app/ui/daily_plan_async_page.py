from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.core.task_manager import TaskManager
from app.services.daily_plan_async_service import list_plan_dates, load_daily_plan


def _display(value: Any) -> str:
    if value in (None, ""):
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


class _PlanModel(QAbstractTableModel):
    def __init__(self, columns: tuple[tuple[str, str], ...], parent=None):
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
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.columns[index.column()][1]
        value = row.get(key)
        if role == Qt.ItemDataRole.DisplayRole:
            if key == "confidence_score" and value not in (None, ""):
                try:
                    return f"{float(value) * 100:.1f}%"
                except Exception:
                    pass
            if key == "priority_score" and value not in (None, ""):
                try:
                    return f"{float(value):.1f}"
                except Exception:
                    pass
            return _display(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class DailyPlanAsyncPage(QWidget):
    TASK_PREFIX = "daily-plan-r5:"

    CAVITY_COLUMNS = (
        ("Date", "plan_date"),
        ("Line", "line_name"),
        ("Cavity", "cavity_no"),
        ("Oven", "oven_no"),
        ("Shift", "shift_name"),
        ("Priority", "priority_no"),
        ("SAP", "tyre_code"),
        ("Description", "description"),
        ("Day Qty", "day_plan_pcs"),
        ("Night Qty", "night_plan_pcs"),
        ("Total", "total_plan"),
        ("Balance", "balance"),
        ("Status", "allocation_status"),
        ("Risk / Reason", "risk_reason"),
    )
    IMPORTED_COLUMNS = (
        ("Date", "plan_date"),
        ("Oven / Cavity", "oven_code"),
        ("Shift", "shift_name"),
        ("SAP", "material_code"),
        ("Description", "item_description"),
        ("Qty", "planned_qty"),
        ("Weight Kg", "planned_weight_kg"),
        ("Status", "plan_status"),
        ("Source", "source"),
    )
    AI_COLUMNS = (
        ("Date", "plan_date"),
        ("Priority", "priority_score"),
        ("SAP", "sap_code"),
        ("Description", "item_description"),
        ("Shipment Demand", "shipment_demand_qty"),
        ("Planning Stock", "current_stock_qty"),
        ("Net Requirement", "net_requirement_qty"),
        ("AI Day", "recommended_day_qty"),
        ("AI Night", "recommended_night_qty"),
        ("AI Total", "recommended_total_qty"),
        ("Expected Actual", "expected_actual_qty"),
        ("Confidence", "confidence_score"),
        ("Status", "status"),
        ("Reason", "explanation"),
    )

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.tasks = TaskManager.instance()
        self._loaded_dates = False
        self._load_generation = 0
        self.cavity_model = _PlanModel(self.CAVITY_COLUMNS, self)
        self.imported_model = _PlanModel(self.IMPORTED_COLUMNS, self)
        self.ai_model = _PlanModel(self.AI_COLUMNS, self)
        self._build_ui()
        QTimer.singleShot(30, self.refresh)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Header,QFrame#Control,QFrame#Panel{background:#fff;border:1px solid #dbe4ef;border-radius:15px;}
            QLabel#Title{color:#0f172a;font-size:23pt;font-weight:950;}
            QLabel#Sub{color:#64748b;font-size:9pt;font-weight:650;}
            QLabel#Status{color:#475569;font-size:8.5pt;font-weight:800;}
            QPushButton{background:#e2e8f0;color:#0f172a;border:none;border-radius:9px;padding:8px 12px;font-weight:900;}
            QPushButton#Primary{background:#2563eb;color:#fff;}
            QComboBox{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:7px 9px;min-width:150px;}
            QTableView{background:#fff;alternate-background-color:#f8fafc;border:1px solid #dbe4ef;selection-background-color:#dbeafe;selection-color:#0f172a;}
            QHeaderView::section{background:#edf3f9;color:#1e293b;border:none;border-right:1px solid #dbe4ef;border-bottom:1px solid #dbe4ef;padding:8px;font-weight:950;}
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        header = QFrame(); header.setObjectName("Header")
        row = QHBoxLayout(header); row.setContentsMargins(18, 12, 18, 12)
        left = QVBoxLayout()
        title = QLabel("Daily Production Plan"); title.setObjectName("Title")
        sub = QLabel(
            "Live cavity planning, imported OVEN final plan and AI candidate. "
            "All database work runs in the shared background task pool."
        ); sub.setObjectName("Sub"); sub.setWordWrap(True)
        left.addWidget(title); left.addWidget(sub); row.addLayout(left, 1)
        self.refresh_btn = QPushButton("Refresh"); self.refresh_btn.setObjectName("Primary")
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)
        root.addWidget(header)

        control = QFrame(); control.setObjectName("Control")
        cr = QHBoxLayout(control); cr.setContentsMargins(12, 8, 12, 8)
        cr.addWidget(QLabel("Plan Date"))
        self.date_filter = QComboBox()
        self.date_filter.currentIndexChanged.connect(self._date_changed)
        cr.addWidget(self.date_filter)
        self.status = QLabel("Preparing daily plan..."); self.status.setObjectName("Status")
        cr.addWidget(self.status, 1)
        root.addWidget(control)

        self.tabs = QTabWidget()
        self.cavity_table = self._table(self.cavity_model)
        self.imported_table = self._table(self.imported_model)
        self.ai_table = self._table(self.ai_model)
        self.tabs.addTab(self.cavity_table, "Live Cavity Plan")
        self.tabs.addTab(self.imported_table, "Imported Oven Plan - FINAL")
        self.tabs.addTab(self.ai_table, "AI Candidate - SHADOW")
        root.addWidget(self.tabs, 1)

    @staticmethod
    def _table(model: _PlanModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.status.setText("Loading available plan dates in background...")
        self.tasks.submit(
            self.TASK_PREFIX + "dates",
            list_plan_dates,
            on_result=self._dates_loaded,
            on_error=self._error,
            replace=True,
        )

    refresh_page = refresh
    load_data = refresh

    def _dates_loaded(self, dates: list[str]) -> None:
        previous = self.date_filter.currentText()
        self.date_filter.blockSignals(True)
        self.date_filter.clear()
        self.date_filter.addItems(list(dates or []))
        if previous:
            index = self.date_filter.findText(previous)
            if index >= 0:
                self.date_filter.setCurrentIndex(index)
        self.date_filter.blockSignals(False)
        self._loaded_dates = True
        self.refresh_btn.setEnabled(True)
        self._load_selected()

    def _date_changed(self, _index: int) -> None:
        if self._loaded_dates:
            QTimer.singleShot(0, self._load_selected)

    def _load_selected(self) -> None:
        selected = self.date_filter.currentText().strip()
        if not selected:
            self.cavity_model.set_rows([])
            self.imported_model.set_rows([])
            self.ai_model.set_rows([])
            self.status.setText("No daily plan date is available.")
            return

        self._load_generation += 1
        generation = self._load_generation
        self.status.setText(f"Loading {selected} in background...")
        self.tasks.submit(
            self.TASK_PREFIX + "date",
            lambda day=selected: load_daily_plan(day),
            on_result=lambda payload, gen=generation: self._plan_loaded(gen, payload),
            on_error=self._error,
            replace=True,
        )

    def _plan_loaded(self, generation: int, payload: dict[str, Any]) -> None:
        if generation != self._load_generation:
            return
        cavity = list(payload.get("cavity") or [])
        imported = list(payload.get("imported") or [])
        ai = list(payload.get("ai") or [])
        self.cavity_model.set_rows(cavity)
        self.imported_model.set_rows(imported)
        self.ai_model.set_rows(ai)
        self.status.setText(
            f"{payload.get('plan_date') or '—'}  •  "
            f"{len(cavity):,} cavity rows  •  {len(imported):,} final OVEN rows  •  {len(ai):,} AI rows"
        )

    def _error(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.status.setText("Daily plan load failed: " + (message.splitlines()[-1] if message else "unknown error"))

    def handle_domain_event(self, event) -> None:
        if getattr(event, "name", "") in {"SourceCommitted", "PlanGenerated", "ShipmentUpdated", "StockChanged"}:
            QTimer.singleShot(120, self.refresh)
