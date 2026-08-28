from __future__ import annotations

from dataclasses import asdict
from datetime import date
import time
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QTimer,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.core.task_manager import TaskManager
from app.services.material_requirement_service import (
    DEMAND_BASIS_OVEN,
    DEMAND_BASIS_SHORTAGE,
    PlanningAssumptions,
    build_material_requirements,
    consolidate_material_requirements,
    latest_material_planning_date,
    load_excel_material_plan_snapshot,
    load_material_demands,
)
from app.utils.reports_export import export_to_csv


def _fmt(value, unit="", decimals=2):
    if value is None:
        return "—"
    try:
        number = float(value)
        if decimals == 0:
            return f"{number:,.0f}{unit}"
        return f"{number:,.{decimals}f}{unit}"
    except Exception:
        return str(value)


class _RowsModel(QAbstractTableModel):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.rows = []

    def set_rows(self, rows):
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
        label, key, formatter = self.columns[index.column()]
        value = row.get(key)

        if role == Qt.ItemDataRole.DisplayRole:
            return formatter(value) if formatter else ("—" if value in (None, "") else str(value))

        if role == Qt.ItemDataRole.TextAlignmentRole and key not in {
            "material_name",
            "finished_item_description",
            "warning",
            "status",
        }:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "status":
                text = str(value or "").upper()
                if text in {"READY", "OK", "MATCH"}:
                    return QColor("#047857")
                if "WARNING" in text or "CHECK" in text or "SHORT" in text:
                    return QColor("#b45309")
            if key == "warning" and value:
                return QColor("#b91c1c")

        return None


def _load_mrp_payload(planning_date, basis):
    with get_session() as session:
        if planning_date is None:
            planning_date = latest_material_planning_date(session)

        if planning_date is None:
            return {
                "planning_date": None,
                "detail": [],
                "summary": [],
                "excel": [],
                "snapshot_date": None,
                "snapshot_workbook": "",
                "demand_count": 0,
            }

        demand_rows = load_material_demands(
            session,
            planning_date=planning_date,
            basis=basis,
        )
        detail = build_material_requirements(
            session,
            demand_rows=demand_rows,
            assumptions=PlanningAssumptions(),
        )
        excel_rows, snapshot_date, snapshot_workbook = (
            load_excel_material_plan_snapshot(
                session,
                planning_date=planning_date,
            )
        )
        reconcile = (
            excel_rows
            if basis == DEMAND_BASIS_OVEN
            and snapshot_date == planning_date
            else []
        )
        summary = consolidate_material_requirements(detail, reconcile)

    return {
        "planning_date": planning_date,
        "detail": [asdict(row) for row in detail],
        "summary": [asdict(row) for row in summary],
        "excel": [asdict(row) for row in excel_rows],
        "snapshot_date": snapshot_date,
        "snapshot_workbook": snapshot_workbook,
        "demand_count": len(demand_rows),
    }


class MaterialRequirementProPage(QWidget):
    CACHE_SECONDS = 45.0

    SUMMARY_COLUMNS = (
        ("Type", "component_type", None),
        ("Material Code", "material_code", None),
        ("Material", "material_name", None),
        ("Unit", "unit", None),
        ("Required Qty", "calculated_required_qty", lambda v: _fmt(v, "", 2)),
        ("Available Stock", "excel_stock_qty", lambda v: _fmt(v, "", 2)),
        ("Prepared / Produced", "excel_produced_qty", lambda v: _fmt(v, "", 2)),
        ("Net To Prepare", "net_to_prepare_qty", lambda v: _fmt(v, "", 2)),
        ("Next Day", "excel_next_day_qty", lambda v: _fmt(v, "", 2)),
        ("Variance", "variance_qty", lambda v: _fmt(v, "", 2)),
        ("Status", "status", None),
    )

    DETAIL_COLUMNS = (
        ("SAP", "finished_item_code", None),
        ("Description", "finished_item_description", None),
        ("Plan Qty", "production_required_qty", lambda v: _fmt(v, "", 0)),
        ("Day", "day_production_qty", lambda v: _fmt(v, "", 0)),
        ("Night", "night_production_qty", lambda v: _fmt(v, "", 0)),
        ("Type", "component_type", None),
        ("Material Code", "raw_material_code", None),
        ("Material", "raw_material_name", None),
        ("Usage / Tyre", "usage_per_unit", lambda v: _fmt(v, "", 4)),
        ("Required", "required_qty", lambda v: _fmt(v, "", 2)),
        ("Warning", "warning", None),
    )

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.tasks = TaskManager.instance()
        self._refresh_running = False
        self._cache = {}
        self._latest_payload = None

        self.summary_model = _RowsModel(self.SUMMARY_COLUMNS, self)
        self.detail_model = _RowsModel(self.DETAIL_COLUMNS, self)

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60000)
        self._refresh_timer.timeout.connect(self._refresh_if_visible)
        self._refresh_timer.start()

        QTimer.singleShot(0, lambda: self.refresh_async(use_latest=True))

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget { font-family:"Segoe UI"; }
            QFrame#Header, QFrame#Metric, QFrame#Panel {
                background:#ffffff; border:1px solid #dbe4ef; border-radius:15px;
            }
            QLabel#Title { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#Sub { color:#64748b; font-size:9pt; font-weight:650; }
            QLabel#MetricValue { color:#0f172a; font-size:18pt; font-weight:950; }
            QLabel#MetricTitle { color:#64748b; font-size:8.4pt; font-weight:850; }
            QLabel#Status {
                background:#f8fafc; color:#475569; border:1px solid #e2e8f0;
                border-radius:8px; padding:7px 10px; font-weight:750;
            }
            QPushButton#Primary {
                background:#2563eb; color:white; border:none; border-radius:9px;
                padding:9px 14px; font-weight:950;
            }
            QPushButton#Secondary {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:9px;
                padding:9px 13px; font-weight:900;
            }
            QLineEdit, QComboBox, QDateEdit {
                background:white; border:1px solid #cbd5e1; border-radius:8px;
                padding:7px 10px;
            }
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
            QTabBar::tab {
                background:#f1f5f9; color:#475569; padding:9px 15px;
                margin-right:3px; font-weight:850;
            }
            QTabBar::tab:selected { background:#2563eb; color:white; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 13, 18, 13)

        left = QVBoxLayout()
        title = QLabel("Material Requirement Planning")
        title.setObjectName("Title")
        sub = QLabel(
            "Automatic MRP from the approved production plan, canonical stock authority and tyre material mappings. Excel remains an import/history source, not a manual calculation step."
        )
        sub.setObjectName("Sub")
        left.addWidget(title)
        left.addWidget(sub)
        hl.addLayout(left, 1)

        self.latest_btn = QPushButton("Latest Plan")
        self.latest_btn.setObjectName("Secondary")
        self.latest_btn.clicked.connect(lambda: self.refresh_async(use_latest=True, force=True))
        hl.addWidget(self.latest_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("Secondary")
        self.refresh_btn.clicked.connect(lambda: self.refresh_async(force=True))
        hl.addWidget(self.refresh_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("Primary")
        self.export_btn.clicked.connect(self.export_current_view)
        hl.addWidget(self.export_btn)

        root.addWidget(header)

        self.metrics = {}
        metric_grid = QGridLayout()
        metric_grid.setSpacing(10)
        for i, (key, caption) in enumerate(
            (
                ("items", "Finished Tyres"),
                ("compound", "Compound Required"),
                ("band", "Band Required"),
                ("bead", "Bead Required"),
                ("core", "Core Required"),
                ("exceptions", "Material Exceptions"),
            )
        ):
            metric_grid.addWidget(self._metric_card(key, caption), i // 3, i % 3)
        root.addLayout(metric_grid)

        controls = QFrame()
        controls.setObjectName("Panel")
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(12, 10, 12, 10)

        cl.addWidget(QLabel("Planning Date"))
        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.dateChanged.connect(lambda _d: self.refresh_async(force=True))
        cl.addWidget(self.plan_date)

        cl.addWidget(QLabel("Demand"))
        self.basis_combo = QComboBox()
        self.basis_combo.addItem("Approved Production Plan", DEMAND_BASIS_OVEN)
        self.basis_combo.addItem("Shipment Production Gap", DEMAND_BASIS_SHORTAGE)
        self.basis_combo.currentIndexChanged.connect(lambda _i: self.refresh_async(force=True))
        cl.addWidget(self.basis_combo)

        cl.addWidget(QLabel("Search"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search material, SAP, description or status...")
        self.search.textChanged.connect(self.apply_filter)
        cl.addWidget(self.search, 1)

        self.source_status = QLabel("Awaiting latest committed plan")
        self.source_status.setObjectName("Status")
        self.source_status.setWordWrap(True)
        root.addWidget(controls)
        root.addWidget(self.source_status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        self.progress.hide()
        root.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.summary_table = self._table(self.summary_model)
        self.detail_table = self._table(self.detail_model)
        self.tabs.addTab(self.summary_table, "Material Plan")
        self.tabs.addTab(self.detail_table, "Finished Item Breakdown")
        root.addWidget(self.tabs, 1)

    def _metric_card(self, key, caption):
        card = QFrame()
        card.setObjectName("Metric")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        value = QLabel("—")
        value.setObjectName("MetricValue")
        title = QLabel(caption)
        title.setObjectName("MetricTitle")
        self.metrics[key] = value
        layout.addWidget(value)
        layout.addWidget(title)
        return card

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if model is self.summary_model:
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        else:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        return table

    def _refresh_if_visible(self):
        if self.isVisible():
            self.refresh_async(force=False)

    def _cache_key(self, planning_date, basis):
        return (str(planning_date or "LATEST"), str(basis))

    def refresh_async(self, use_latest=False, force=False):
        if self._refresh_running:
            return

        planning_date = None if use_latest else self.plan_date.date().toPython()
        basis = str(self.basis_combo.currentData() or DEMAND_BASIS_OVEN)
        key = self._cache_key(planning_date, basis)

        cached = self._cache.get(key)
        if (
            not force
            and cached is not None
            and time.monotonic() - cached[0] < self.CACHE_SECONDS
        ):
            self._apply_payload(cached[1])
            return

        self._refresh_running = True
        self.progress.show()
        self.refresh_btn.setEnabled(False)
        self.latest_btn.setEnabled(False)
        self.tasks.submit(
            "material-r6:calculate",
            lambda day=planning_date, demand_basis=basis: _load_mrp_payload(day, demand_basis),
            on_result=lambda payload, cache_key=key: self._loaded(cache_key, payload),
            on_error=self._failed,
            replace=True,
            priority=1,
        )

    def _loaded(self, cache_key, payload):
        self._refresh_running = False
        self.progress.hide()
        self.refresh_btn.setEnabled(True)
        self.latest_btn.setEnabled(True)
        payload = dict(payload or {})
        self._cache[cache_key] = (time.monotonic(), payload)
        self._latest_payload = payload
        self._apply_payload(payload)

    def _failed(self, message):
        self._refresh_running = False
        self.progress.hide()
        self.refresh_btn.setEnabled(True)
        self.latest_btn.setEnabled(True)
        self.source_status.setText(f"MRP background calculation failed: {message}")

    def _apply_payload(self, payload):
        planning_date = payload.get("planning_date")
        if planning_date is not None:
            self.plan_date.blockSignals(True)
            self.plan_date.setDate(QDate(planning_date.year, planning_date.month, planning_date.day))
            self.plan_date.blockSignals(False)

        summary = list(payload.get("summary") or [])
        detail = list(payload.get("detail") or [])
        self._all_summary = summary
        self._all_detail = detail
        self.apply_filter()

        if not summary and not detail:
            self.source_status.setText("No material demand is available for the selected/latest committed plan.")
            for label in self.metrics.values():
                label.setText("—")
            return

        excel_rows = list(payload.get("excel") or [])
        snapshot_date = payload.get("snapshot_date")
        workbook = str(payload.get("snapshot_workbook") or "")
        self.source_status.setText(
            "Planning date: "
            + (planning_date.isoformat() if planning_date else "—")
            + " • Operational source: "
            + (snapshot_date.isoformat() if hasattr(snapshot_date, "isoformat") else "database")
            + (" • " + workbook if workbook else "")
        )

        totals = {}
        for row in summary:
            totals[row.get("component_type")] = totals.get(row.get("component_type"), 0.0) + float(row.get("calculated_required_qty") or 0.0)

        core = sum(
            float(row.get("total_qty") or 0.0)
            for row in excel_rows
            if str(row.get("material_type") or "").upper() == "CORE"
        )
        exceptions = sum(
            1
            for row in summary
            if str(row.get("status") or "").upper() not in {"", "OK", "READY", "MATCH"}
        ) + sum(1 for row in detail if row.get("warning"))

        self.metrics["items"].setText(f"{int(payload.get('demand_count') or 0):,}")
        self.metrics["compound"].setText(_fmt(totals.get("COMPOUND"), " kg", 2))
        self.metrics["band"].setText(_fmt(totals.get("BAND"), " pcs", 0))
        self.metrics["bead"].setText(_fmt(totals.get("BEAD"), " pcs", 0))
        self.metrics["core"].setText(_fmt(core if core else None, " pcs", 0))
        self.metrics["exceptions"].setText(f"{exceptions:,}")

    def apply_filter(self):
        query = self.search.text().strip().lower()
        summary = list(getattr(self, "_all_summary", []))
        detail = list(getattr(self, "_all_detail", []))

        if query:
            summary = [
                row for row in summary
                if query in " ".join(str(v or "") for v in row.values()).lower()
            ]
            detail = [
                row for row in detail
                if query in " ".join(str(v or "") for v in row.values()).lower()
            ]

        self.summary_model.set_rows(summary)
        self.detail_model.set_rows(detail)

    def export_current_view(self):
        rows = self.summary_model.rows if self.tabs.currentIndex() == 0 else self.detail_model.rows
        if not rows:
            self.source_status.setText("Nothing to export in the current view.")
            return
        try:
            if self.tabs.currentIndex() == 0:
                export_rows = [
                    [row.get(key) for _label, key, _formatter in self.SUMMARY_COLUMNS]
                    for row in rows
                ]
                headers = [label for label, _key, _formatter in self.SUMMARY_COLUMNS]
                filename = "material_plan.csv"
            else:
                export_rows = [
                    [row.get(key) for _label, key, _formatter in self.DETAIL_COLUMNS]
                    for row in rows
                ]
                headers = [label for label, _key, _formatter in self.DETAIL_COLUMNS]
                filename = "finished_item_breakdown.csv"
            export_to_csv(headers, export_rows, filename)
        except TypeError:
            # Keep compatibility with older export helper signature.
            export_to_csv(filename, headers, export_rows)
        except Exception as exc:
            self.source_status.setText(f"Export failed: {exc}")

    def notify_source_changed(self, *args, **kwargs):
        self._cache.clear()
        self.refresh_async(use_latest=True, force=True)

    def refresh(self):
        self.refresh_async(force=True)

    refresh_page = refresh
    load_data = refresh


MaterialRequirementPage = MaterialRequirementProPage
MaterialRequirementsPage = MaterialRequirementProPage
