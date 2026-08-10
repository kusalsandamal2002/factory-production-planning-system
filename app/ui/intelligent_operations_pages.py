from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text



class _OperationsPage(QWidget):
    title_text = "Operations"
    subtitle_text = ""

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 18, 22, 20)
        self.root.setSpacing(12)
        self._build_header()

    def _build_header(self) -> None:
        row = QHBoxLayout()
        text_box = QVBoxLayout()
        title = QLabel(self.title_text)
        title.setStyleSheet("font-size:26px;font-weight:950;color:#0f172a;")
        subtitle = QLabel(self.subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#64748b;font-size:12px;")
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        row.addLayout(text_box, 1)
        refresh = QPushButton("Refresh Live Data")
        refresh.setMinimumHeight(38)
        refresh.setStyleSheet("font-weight:900;")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        self.root.addLayout(row)

    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet(
            "QTableWidget{border:1px solid #dbe4ef;background:white;gridline-color:#e2e8f0;}"
            "QHeaderView::section{background:#f8fafc;color:#334155;font-weight:900;"
            "border:0;border-bottom:1px solid #cbd5e1;padding:7px;}"
        )
        return table

    def _metric(self, caption: str, value: Any) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:white;border:1px solid #dbe4ef;border-radius:10px;}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        value_label = QLabel(_display(value))
        value_label.setStyleSheet("font-size:20px;font-weight:950;color:#0f172a;")
        caption_label = QLabel(caption)
        caption_label.setStyleSheet("color:#64748b;font-size:10px;font-weight:800;")
        caption_label.setWordWrap(True)
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        return card

    def _fill(self, table: QTableWidget, rows: list[list[Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(_display(value))
                if isinstance(value, (int, float)):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                table.setItem(row, column, item)
        table.setSortingEnabled(True)

    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with _get_session() as session:
            return [
                dict(row)
                for row in session.execute(text(sql), params or {}).mappings().all()
            ]

    def _scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        with _get_session() as session:
            return session.execute(text(sql), params or {}).scalar()

    def refresh(self) -> None:
        raise NotImplementedError

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()


# DELIVERY DATE INTEGRITY V6.3
class DeliveryDateControlPage(_OperationsPage):
    title_text = "Delivery Date Control Center"
    subtitle_text = (
        "Live manual/Excel targets and automatic earliest-feasible Factory Can Out "
        "targets, with cumulative planning status, progress and delivery risk."
    )

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user, *args, **kwargs)
        self.table = self._table(
            [
                "Priority",
                "Shipment",
                "Customer",
                "Status",
                "Target Date",
                "Target Source",
                "Factory Receive",
                "Factory Out",
                "Total Qty",
                "Completed",
                "Progress %",
                "Delay Days",
                "Planning Status",
                "Decision / Reason",
            ]
        )
        self.root.addWidget(self.table, 1)

    def refresh(self) -> None:
        try:
            rows = self._query(
                """
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY
                            CASE WHEN target_date_is_manual THEN 0 ELSE 1 END,
                            COALESCE(target_date, factory_can_receive_date, shipment_date),
                            created_at,
                            id
                    ) AS priority,
                    COALESCE(NULLIF(shipment_name, ''), shipment_no) AS shipment_name,
                    customer_name,
                    status,
                    CASE
                        WHEN LOWER(COALESCE(status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(COALESCE(planning_status, ''))
                            = 'review required'
                        THEN NULL
                        ELSE target_date
                    END AS target_date,
                    COALESCE(
                        NULLIF(target_date_source, ''),
                        'Auto Earliest Feasible Factory Out'
                    ) AS target_date_source,
                    CASE
                        WHEN LOWER(COALESCE(status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(COALESCE(planning_status, ''))
                            = 'review required'
                        THEN NULL
                        ELSE factory_can_receive_date
                    END AS factory_can_receive_date,
                    CASE
                        WHEN LOWER(COALESCE(status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(COALESCE(planning_status, ''))
                            = 'review required'
                        THEN NULL
                        ELSE factory_out_date
                    END AS factory_out_date,
                    total_qty,
                    completed_qty,
                    progress_pct,
                    delay_days,
                    planning_status,
                    COALESCE(NULLIF(planning_note, ''), NULLIF(factory_out_note, ''), note, '') AS decision
                FROM mpps_shipments
                ORDER BY priority
                """
            )
            self._fill(
                self.table,
                [
                    [
                        r["priority"],
                        r["shipment_name"],
                        r["customer_name"],
                        r["status"],
                        r["target_date"],
                        r["target_date_source"],
                        r["factory_can_receive_date"],
                        r["factory_out_date"],
                        r["total_qty"],
                        r["completed_qty"],
                        r["progress_pct"],
                        r["delay_days"],
                        r["planning_status"],
                        r["decision"],
                    ]
                    for r in rows
                ],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Delivery Date Data", str(exc))


class DailyProductionPlanPage(_OperationsPage):
    title_text = "Daily Production Plan"
    subtitle_text = (
        "Saved cavity-level production plan combined with imported Excel oven plans. "
        "The latest saved planner run remains the live execution source."
    )

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user, *args, **kwargs)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Plan Date"))
        self.date_filter = QComboBox()
        self.date_filter.currentIndexChanged.connect(self._refresh_tables)
        filter_row.addWidget(self.date_filter)
        filter_row.addStretch()
        self.root.addLayout(filter_row)

        self.tabs = QTabWidget()
        self.cavity_table = self._table(
            [
                "Date",
                "Line",
                "Cavity",
                "Oven",
                "Shift",
                "SAP",
                "Description",
                "Day Qty",
                "Night Qty",
                "Total",
                "Balance",
                "Status",
                "Risk / Reason",
            ]
        )
        self.imported_table = self._table(
            [
                "Date",
                "Oven / Cavity",
                "Shift",
                "SAP",
                "Description",
                "Qty",
                "Weight Kg",
                "Status",
                "Source",
            ]
        )
        self.tabs.addTab(self.cavity_table, "Live Cavity Plan")
        self.tabs.addTab(self.imported_table, "Imported Oven Plan")
        self.root.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        try:
            dates = self._query(
                """
                SELECT DISTINCT plan_date
                FROM (
                    SELECT plan_date FROM mpps_cavity_plan_rows
                    UNION
                    SELECT plan_date FROM mpps_oven_plan
                ) dates
                WHERE plan_date IS NOT NULL
                ORDER BY plan_date DESC
                LIMIT 180
                """
            )
            selected = self.date_filter.currentText()
            self.date_filter.blockSignals(True)
            self.date_filter.clear()
            self.date_filter.addItems([str(r["plan_date"]) for r in dates])
            if selected:
                index = self.date_filter.findText(selected)
                if index >= 0:
                    self.date_filter.setCurrentIndex(index)
            self.date_filter.blockSignals(False)
            self._refresh_tables()
        except Exception as exc:
            QMessageBox.critical(self, "Daily Plan Data", str(exc))

    def _refresh_tables(self) -> None:
        selected = self.date_filter.currentText()
        if not selected:
            self.cavity_table.setRowCount(0)
            self.imported_table.setRowCount(0)
            return
        try:
            cavity_rows = self._query(
                """
                SELECT
                    plan_date,
                    line_name,
                    cavity_no,
                    oven_no,
                    shift_name,
                    tyre_code,
                    description,
                    day_plan_pcs,
                    night_plan_pcs,
                    total_plan,
                    balance,
                    allocation_status,
                    risk_reason
                FROM mpps_cavity_plan_rows
                WHERE plan_date = CAST(:plan_date AS DATE)
                ORDER BY line_name, cavity_no, sequence_no
                """,
                {"plan_date": selected},
            )
            self._fill(
                self.cavity_table,
                [
                    [
                        r["plan_date"],
                        r["line_name"],
                        r["cavity_no"],
                        r["oven_no"],
                        r["shift_name"],
                        r["tyre_code"],
                        r["description"],
                        r["day_plan_pcs"],
                        r["night_plan_pcs"],
                        r["total_plan"],
                        r["balance"],
                        r["allocation_status"],
                        r["risk_reason"],
                    ]
                    for r in cavity_rows
                ],
            )
            imported = self._query(
                """
                SELECT
                    plan_date,
                    oven_code,
                    shift_name,
                    material_code,
                    item_description,
                    planned_qty,
                    planned_weight_kg,
                    plan_status,
                    CONCAT(COALESCE(source_workbook, ''), ' / ', COALESCE(source_sheet, '')) AS source
                FROM mpps_oven_plan
                WHERE plan_date = CAST(:plan_date AS DATE)
                ORDER BY oven_code, shift_name, material_code
                """,
                {"plan_date": selected},
            )
            self._fill(
                self.imported_table,
                [
                    [
                        r["plan_date"],
                        r["oven_code"],
                        r["shift_name"],
                        r["material_code"],
                        r["item_description"],
                        r["planned_qty"],
                        r["planned_weight_kg"],
                        r["plan_status"],
                        r["source"],
                    ]
                    for r in imported
                ],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Daily Plan Data", str(exc))


class ShiftPlanPage(_OperationsPage):
    title_text = "Day / Night Shift Control"
    subtitle_text = (
        "Shift totals, oven/cavity allocations, planned weight and source traceability "
        "for the selected production date."
    )

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user, *args, **kwargs)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Plan Date"))
        self.date_filter = QComboBox()
        self.date_filter.currentIndexChanged.connect(self._load_selected)
        filter_row.addWidget(self.date_filter)
        filter_row.addStretch()
        self.root.addLayout(filter_row)
        self.metrics = QGridLayout()
        self.root.addLayout(self.metrics)
        self.table = self._table(
            [
                "Shift",
                "Line / Oven",
                "SAP",
                "Description",
                "Qty",
                "Weight Kg",
                "Source",
            ]
        )
        self.root.addWidget(self.table, 1)

    def refresh(self) -> None:
        try:
            dates = self._query(
                """
                SELECT DISTINCT plan_date
                FROM mpps_oven_plan
                WHERE plan_date IS NOT NULL
                ORDER BY plan_date DESC
                LIMIT 180
                """
            )
            selected = self.date_filter.currentText()
            self.date_filter.blockSignals(True)
            self.date_filter.clear()
            self.date_filter.addItems([str(r["plan_date"]) for r in dates])
            if selected:
                index = self.date_filter.findText(selected)
                if index >= 0:
                    self.date_filter.setCurrentIndex(index)
            self.date_filter.blockSignals(False)
            self._load_selected()
        except Exception as exc:
            QMessageBox.critical(self, "Shift Plan Data", str(exc))

    def _load_selected(self) -> None:
        selected = self.date_filter.currentText()
        if not selected:
            return
        try:
            summary = self._query(
                """
                SELECT
                    COALESCE(NULLIF(shift_name, ''), 'UNSPECIFIED') AS shift_name,
                    COUNT(*) AS allocation_rows,
                    SUM(planned_qty) AS planned_qty,
                    SUM(planned_weight_kg) AS planned_weight_kg,
                    COUNT(DISTINCT oven_code) AS ovens
                FROM mpps_oven_plan
                WHERE plan_date = CAST(:plan_date AS DATE)
                GROUP BY COALESCE(NULLIF(shift_name, ''), 'UNSPECIFIED')
                ORDER BY shift_name
                """,
                {"plan_date": selected},
            )
            while self.metrics.count():
                item = self.metrics.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for index, row in enumerate(summary):
                self.metrics.addWidget(
                    self._metric(
                        f"{row['shift_name']} — {row['ovens']} ovens / {row['allocation_rows']} rows",
                        f"{int(row['planned_qty'] or 0):,} pcs | {float(row['planned_weight_kg'] or 0):,.2f} kg",
                    ),
                    0,
                    index,
                )
            rows = self._query(
                """
                SELECT
                    shift_name,
                    oven_code,
                    material_code,
                    item_description,
                    planned_qty,
                    planned_weight_kg,
                    CONCAT(COALESCE(source_workbook, ''), ' / ', COALESCE(source_sheet, '')) AS source
                FROM mpps_oven_plan
                WHERE plan_date = CAST(:plan_date AS DATE)
                ORDER BY shift_name, oven_code, material_code
                """,
                {"plan_date": selected},
            )
            self._fill(
                self.table,
                [
                    [
                        r["shift_name"],
                        r["oven_code"],
                        r["material_code"],
                        r["item_description"],
                        r["planned_qty"],
                        r["planned_weight_kg"],
                        r["source"],
                    ]
                    for r in rows
                ],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Shift Plan Data", str(exc))


class OperationsReportsPage(_OperationsPage):
    title_text = "Operations Reports"
    subtitle_text = (
        "Live management view of stock, shipments, production plans, material plans, "
        "intelligent Excel imports and open data-quality issues."
    )

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user, *args, **kwargs)
        self.metric_layout = QGridLayout()
        self.metric_layout.setSpacing(10)
        self.root.addLayout(self.metric_layout)
        self.tabs = QTabWidget()
        self.shipment_table = self._table(
            ["Shipment", "Customer", "Target", "Qty", "Completed", "Progress %", "Status", "Planning"]
        )
        self.stock_table = self._table(
            ["SAP", "Description", "FG", "QC", "Scrap", "Blocked", "Net Available", "Weight Kg"]
        )
        self.material_table = self._table(
            ["Plan Date", "Type", "Material", "Day", "Night", "Total", "Stock", "Next Day", "Source"]
        )
        self.import_table = self._table(
            ["Run", "Workbook", "Plan Date", "Confidence", "Status", "Warnings", "Started", "Rollback"]
        )
        self.tabs.addTab(self.shipment_table, "Shipment Portfolio")
        self.tabs.addTab(self.stock_table, "Stock Portfolio")
        self.tabs.addTab(self.material_table, "Material Plans")
        self.tabs.addTab(self.import_table, "Excel Import Audit")
        self.root.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        try:
            metrics = self._query(
                """
                SELECT
                    (SELECT COUNT(*) FROM mpps_shipments) AS shipments,
                    (SELECT COALESCE(SUM(total_qty), 0) FROM mpps_shipments) AS shipment_qty,
                    (SELECT COALESCE(SUM(fg_stock), 0) FROM mpps_sap_stock_items WHERE is_active) AS fg_stock,
                    (SELECT COALESCE(SUM(scrap_stock), 0) FROM mpps_sap_stock_items WHERE is_active) AS scrap_stock,
                    (SELECT COUNT(*) FROM production_line_cavities WHERE is_active) AS active_cavities,
                    (SELECT COUNT(*) FROM production_line_cavities WHERE LOWER(COALESCE(status, '')) IN ('breakdown','broken','maintenance','inactive')) AS breakdown_cavities,
                    (SELECT COALESCE(SUM(planned_qty), 0) FROM mpps_oven_plan WHERE plan_date = CURRENT_DATE) AS today_plan,
                    (SELECT COUNT(*) FROM excel_import_runs WHERE status LIKE 'COMMITTED%') AS committed_imports
                """
            )[0]
            while self.metric_layout.count():
                item = self.metric_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            specs = [
                ("Shipments", metrics["shipments"]),
                ("Shipment Quantity", metrics["shipment_qty"]),
                ("Current FG Stock", metrics["fg_stock"]),
                ("Scrap Stock", metrics["scrap_stock"]),
                ("Active Cavities", metrics["active_cavities"]),
                ("Breakdown Cavities", metrics["breakdown_cavities"]),
                ("Today's Imported Plan", metrics["today_plan"]),
                ("Committed Excel Imports", metrics["committed_imports"]),
            ]
            for index, (caption, value) in enumerate(specs):
                self.metric_layout.addWidget(self._metric(caption, value), index // 4, index % 4)

            shipments = self._query(
                """
                SELECT
                    COALESCE(NULLIF(shipment_name, ''), shipment_no) AS shipment,
                    customer_name,
                    CASE
                        WHEN LOWER(COALESCE(status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(COALESCE(planning_status, ''))
                            = 'review required'
                        THEN NULL
                        ELSE target_date
                    END AS target_date,
                    total_qty,
                    completed_qty,
                    progress_pct,
                    status,
                    planning_status
                FROM mpps_shipments
                ORDER BY COALESCE(target_date, shipment_date), id
                """
            )
            self._fill(
                self.shipment_table,
                [[r["shipment"], r["customer_name"], r["target_date"], r["total_qty"], r["completed_qty"], r["progress_pct"], r["status"], r["planning_status"]] for r in shipments],
            )
            stock = self._query(
                """
                SELECT
                    s.sap_code,
                    COALESCE(NULLIF(s.item_description, ''), s.tyre_description) AS description,
                    s.fg_stock,
                    s.qc_stock,
                    s.scrap_stock,
                    s.blocked_stock,
                    GREATEST(0, s.fg_stock + s.qc_stock - s.scrap_stock - s.blocked_stock) AS net_available,
                    p.average_weight
                FROM mpps_sap_stock_items s
                LEFT JOIN mpps_stock_items p ON p.material_code = s.sap_code
                WHERE s.is_active
                ORDER BY s.sap_code
                """
            )
            self._fill(
                self.stock_table,
                [[r["sap_code"], r["description"], r["fg_stock"], r["qc_stock"], r["scrap_stock"], r["blocked_stock"], r["net_available"], r["average_weight"]] for r in stock],
            )
            materials = self._query(
                """
                SELECT
                    plan_date,
                    material_type,
                    material_key,
                    day_qty,
                    night_qty,
                    total_qty,
                    stock_qty,
                    next_day_qty,
                    CONCAT(source_sheet, ':', source_row) AS source
                FROM excel_import_material_plans
                ORDER BY plan_date DESC, material_type, material_key
                LIMIT 5000
                """
            )
            self._fill(
                self.material_table,
                [[r["plan_date"], r["material_type"], r["material_key"], r["day_qty"], r["night_qty"], r["total_qty"], r["stock_qty"], r["next_day_qty"], r["source"]] for r in materials],
            )
            imports = self._query(
                """
                SELECT
                    r.id,
                    r.workbook_name,
                    r.plan_date,
                    r.confidence_score,
                    r.status,
                    COUNT(i.id) FILTER (WHERE i.severity IN ('BLOCKER','WARNING')) AS warnings,
                    r.started_at,
                    r.rollback_at
                FROM excel_import_runs r
                LEFT JOIN excel_import_issues i ON i.run_id = r.id
                GROUP BY r.id
                ORDER BY r.id DESC
                LIMIT 200
                """
            )
            self._fill(
                self.import_table,
                [[r["id"], r["workbook_name"], r["plan_date"], f"{float(r['confidence_score'] or 0) * 100:.1f}%", r["status"], r["warnings"], r["started_at"], r["rollback_at"]] for r in imports],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Operations Reports", str(exc))


def _get_session():
    from app.database import get_session

    return get_session()


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.3f}".rstrip("0").rstrip(".")
    return str(value)
