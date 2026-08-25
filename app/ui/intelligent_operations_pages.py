from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.services.shift_daily_report_service import (
    LOSS_COLUMNS,
    LOSS_REASONS,
    TYRE_LINE_ORDER,
    ShiftDailyReportService,
    build_shift_report_html,
)
from app.services.ai_planning_service import AIPlanningService
from app.core.task_manager import TaskManager



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
        "Compare live cavity planning, the imported Excel/Oven FINAL plan and the "
        "AI next-day candidate. AI stays advisory while its plan-vs-actual accuracy learns."
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
        self.ai_table = self._table(
            [
                "Date",
                "Priority",
                "SAP",
                "Description",
                "Shipment Demand",
                "Planning Stock",
                "Net Requirement",
                "AI Day",
                "AI Night",
                "AI Total",
                "Expected Actual",
                "Confidence",
                "Status",
                "Reason",
            ]
        )
        self.tabs.addTab(self.cavity_table, "Live Cavity Plan")
        self.tabs.addTab(self.imported_table, "Imported Oven Plan - FINAL")
        self.tabs.addTab(self.ai_table, "AI Candidate - SHADOW")
        self.root.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        try:
            with _get_session() as session:
                AIPlanningService().ensure_schema(session)
            dates = self._query(
                """
                SELECT DISTINCT plan_date
                FROM (
                    SELECT plan_date FROM mpps_cavity_plan_rows
                    UNION
                    SELECT plan_date FROM mpps_oven_plan
                    UNION
                    SELECT plan_date FROM mpps_ai_plan_runs
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
            self.ai_table.setRowCount(0)
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
            ai_rows = self._query(
                """
                SELECT i.*
                FROM mpps_ai_plan_items i
                JOIN (
                    SELECT MAX(id) AS run_id
                    FROM mpps_ai_plan_runs
                    WHERE plan_date = CAST(:plan_date AS DATE)
                ) latest ON latest.run_id = i.run_id
                ORDER BY i.priority_score DESC, i.sap_code
                """,
                {"plan_date": selected},
            )
            self._fill(
                self.ai_table,
                [
                    [
                        r["plan_date"],
                        round(float(r["priority_score"] or 0), 1),
                        r["sap_code"],
                        r["item_description"],
                        r["shipment_demand_qty"],
                        r["current_stock_qty"],
                        r["net_requirement_qty"],
                        r["recommended_day_qty"],
                        r["recommended_night_qty"],
                        r["recommended_total_qty"],
                        r["expected_actual_qty"],
                        f"{float(r['confidence_score'] or 0) * 100:.1f}%",
                        r["status"],
                        r["explanation"],
                    ]
                    for r in ai_rows
                ],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Daily Plan Data", str(exc))


class _ShiftReportEditor(QWidget):
    def __init__(self, shift_name: str, current_user=None, parent=None):
        super().__init__(parent)
        self.shift_name = shift_name.upper()
        self.current_user = current_user
        self.report_date = ""
        self.target_summary: dict[str, Any] = {"lines": {}, "unmapped": []}
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        title = QLabel(f"{self.shift_name} — Daily Production Summary Report")
        title.setStyleSheet("font-size:16px;font-weight:950;color:#0f172a;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.save_button = QPushButton("Save Report")
        self.save_button.setMinimumHeight(34)
        self.save_button.setStyleSheet(
            "QPushButton{background:#2563eb;color:white;border:0;border-radius:7px;padding:7px 13px;font-weight:900;}"
            "QPushButton:hover{background:#1d4ed8;}"
        )
        self.save_button.clicked.connect(self.save_report)
        toolbar.addWidget(self.save_button)

        preview_button = QPushButton("Print / Preview")
        preview_button.setMinimumHeight(34)
        preview_button.setStyleSheet("font-weight:900;padding:7px 13px;")
        preview_button.clicked.connect(self.print_preview)
        toolbar.addWidget(preview_button)

        pdf_button = QPushButton("Save PDF")
        pdf_button.setMinimumHeight(34)
        pdf_button.setStyleSheet("font-weight:900;padding:7px 13px;")
        pdf_button.clicked.connect(self.save_pdf)
        toolbar.addWidget(pdf_button)
        outer.addLayout(toolbar)

        self.reconciliation_label = QLabel("")
        self.reconciliation_label.setWordWrap(True)
        self.reconciliation_label.setStyleSheet(
            "QLabel{background:#eff6ff;border:1px solid #bfdbfe;border-radius:7px;padding:7px;color:#1e3a8a;font-weight:800;}"
        )
        outer.addWidget(self.reconciliation_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:#f8fafc;border:0;}")
        body = QWidget()
        body.setStyleSheet("QWidget{background:#ffffff;}")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(10)

        header = QFrame()
        header.setStyleSheet("QFrame{border:1px solid #0f172a;background:white;}")
        header_layout = QGridLayout(header)
        company = QLabel("LAUGFS Corporation (Rubber) Ltd.")
        company.setStyleSheet("font-size:14px;font-weight:950;border:0;")
        report_title = QLabel("Daily Production Summary Report")
        report_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        report_title.setStyleSheet("font-size:15px;font-weight:950;border:0;")
        self.date_label = QLabel("Date: -")
        self.date_label.setStyleSheet("font-weight:900;border:0;")
        shift_label = QLabel(f"Shift: {self.shift_name}")
        shift_label.setStyleSheet("font-weight:900;border:0;")
        header_layout.addWidget(company, 0, 0)
        header_layout.addWidget(report_title, 0, 1, 1, 2)
        header_layout.addWidget(self.date_label, 1, 0)
        header_layout.addWidget(shift_label, 1, 2)
        body_layout.addWidget(header)

        top = QGridLayout()
        top.setHorizontalSpacing(10)
        top.setVerticalSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self._section_label("Production performance"))
        details_label = QLabel("Details For SAP")
        details_label.setStyleSheet("font-weight:900;")
        left.addWidget(details_label)
        self.production_notes = QTextEdit()
        self.production_notes.setPlaceholderText("Production performance / SAP details...")
        self.production_notes.setMaximumHeight(78)
        self.production_notes.setStyleSheet("QTextEdit{border:1px solid #94a3b8;padding:5px;}")
        left.addWidget(self.production_notes)

        left.addWidget(self._section_label("2nd Stage Compound Production"))
        self.compound_table = self._editable_table(
            ["Compound Type", "Target", "Actual", "Achievement (%)"], 7
        )
        self.compound_table.setMinimumHeight(214)
        left.addWidget(self.compound_table)

        left.addWidget(self._section_label("Quality Performance — Scrap Tyres"))
        self.scrap_tyre_table = self._editable_table(
            ["Tyre Size", "PCS", "Defect", "Responsible Operator"], 3
        )
        self.scrap_tyre_table.setMinimumHeight(126)
        left.addWidget(self.scrap_tyre_table)

        left.addWidget(self._section_label("Scrap Compound"))
        self.scrap_compound_table = self._editable_table(
            ["Compound Type", "Weights", "Defect", "Responsible Operator"], 3
        )
        self.scrap_compound_table.setMinimumHeight(126)
        left.addWidget(self.scrap_compound_table)

        metrics = QGridLayout()
        metrics.addWidget(QLabel("Used man hours"), 0, 0)
        self.used_man_hours = QLineEdit()
        self.used_man_hours.setPlaceholderText("0.00")
        self.used_man_hours.textChanged.connect(self._refresh_calculated_fields)
        metrics.addWidget(self.used_man_hours, 0, 1)
        metrics.addWidget(QLabel("Production (Kg)"), 1, 0)
        self.production_kg_label = QLabel("0.00")
        self.production_kg_label.setStyleSheet("font-weight:900;")
        metrics.addWidget(self.production_kg_label, 1, 1)
        metrics.addWidget(QLabel("Man hours (Kg)"), 2, 0)
        self.kg_per_hour_label = QLabel("0.00")
        self.kg_per_hour_label.setStyleSheet("font-weight:900;")
        metrics.addWidget(self.kg_per_hour_label, 2, 1)
        left.addLayout(metrics)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(self._section_label("Supervisor Name"))
        self.supervisor_name = QLineEdit()
        self.supervisor_name.setPlaceholderText("Supervisor name")
        right.addWidget(self.supervisor_name)
        right.addWidget(self._section_label("Tyre production"))
        self.tyre_table = self._editable_table(
            ["Line No", "Target (Kg)", "Actual (Kg)", "Target (pcs)", "Actual (Pcs)"],
            len(TYRE_LINE_ORDER) + 1,
        )
        self.tyre_table.setMinimumHeight(246)
        self.tyre_table.itemChanged.connect(self._on_tyre_item_changed)
        right.addWidget(self.tyre_table)
        right.addStretch()
        signature = QLabel("Supervisor:- ............................................................")
        signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        signature.setStyleSheet("font-weight:900;padding:18px 4px;")
        right.addWidget(signature)

        left_frame = QFrame()
        left_frame.setStyleSheet("QFrame{border:1px solid #cbd5e1;border-radius:6px;background:white;}")
        left_frame.setLayout(left)
        right_frame = QFrame()
        right_frame.setStyleSheet("QFrame{border:1px solid #cbd5e1;border-radius:6px;background:white;}")
        right_frame.setLayout(right)
        top.addWidget(left_frame, 0, 0)
        top.addWidget(right_frame, 0, 1)
        top.setColumnStretch(0, 1)
        top.setColumnStretch(1, 1)
        body_layout.addLayout(top)

        body_layout.addWidget(self._section_label("Loss Reasons"))
        self.loss_table = self._editable_table(
            [
                "Loss Reasons",
                "200 KG", "200 PCS",
                "600/400/Super KG", "600/400/Super PCS",
                "400 KG", "400 PCS",
                "800 KG", "800 PCS",
            ],
            len(LOSS_REASONS),
        )
        self.loss_table.setMinimumHeight(650)
        body_layout.addWidget(self.loss_table)

        footer = QLabel(
            "Doc #: LR-ST-PP-014     |     Issue #: 09     |     "
            "Issue Date: 02.09.2025     |     Print format: A4 Portrait / 2 pages"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color:#475569;font-size:10px;font-weight:800;padding:6px;")
        body_layout.addWidget(footer)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    @staticmethod
    def _section_label(text_value: str) -> QLabel:
        label = QLabel(text_value)
        label.setStyleSheet(
            "QLabel{background:#e2e8f0;border:1px solid #94a3b8;padding:5px;font-weight:950;color:#0f172a;}"
        )
        return label

    @staticmethod
    def _editable_table(headers: list[str], rows: int) -> QTableWidget:
        table = QTableWidget(rows, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(
            "QTableWidget{border:1px solid #94a3b8;background:white;gridline-color:#cbd5e1;}"
            "QHeaderView::section{background:#f1f5f9;color:#0f172a;font-weight:900;border:0;border-bottom:1px solid #94a3b8;padding:5px;}"
        )
        return table

    @staticmethod
    def _set_item(table: QTableWidget, row: int, column: int, value: Any, editable: bool = True) -> None:
        item = table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            table.setItem(row, column, item)
        item.setText("" if value is None else str(value))
        flags = item.flags()
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        else:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        if column > 0:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(str(value or "").replace(",", "").strip())
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _table_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item else ""

    def load(self, report_date: str) -> None:
        self.report_date = report_date
        self.date_label.setText(f"Date: {report_date or '-'}")
        if not report_date:
            return
        self._loading = True
        try:
            self.target_summary = ShiftDailyReportService.load_targets(report_date, self.shift_name)
            payload = ShiftDailyReportService.load_report(report_date, self.shift_name)
            self._load_payload(payload)
            self._load_targets()
            self._load_loss_reason_labels()
            self._update_reconciliation()
            self._refresh_calculated_fields()
        finally:
            self._loading = False

    def _load_targets(self) -> None:
        lines = self.target_summary.get("lines", {})
        actuals = self._current_payload_actuals_from_table()
        for row, line in enumerate(TYRE_LINE_ORDER):
            target = lines.get(line, {})
            self._set_item(self.tyre_table, row, 0, line, False)
            self._set_item(self.tyre_table, row, 1, f"{self._num(target.get('target_kg')):.2f}", False)
            self._set_item(self.tyre_table, row, 2, actuals.get(line, {}).get("kg", ""), True)
            self._set_item(self.tyre_table, row, 3, str(int(round(self._num(target.get('target_pcs'))))), False)
            self._set_item(self.tyre_table, row, 4, actuals.get(line, {}).get("pcs", ""), True)
        self._set_item(self.tyre_table, len(TYRE_LINE_ORDER), 0, "Total", False)
        for column in range(1, 5):
            self._set_item(self.tyre_table, len(TYRE_LINE_ORDER), column, "", False)
        self._refresh_tyre_totals()

    def _current_payload_actuals_from_table(self) -> dict[str, dict[str, str]]:
        result = {line: {"kg": "", "pcs": ""} for line in TYRE_LINE_ORDER}
        for row, line in enumerate(TYRE_LINE_ORDER):
            result[line] = {
                "kg": self._table_text(self.tyre_table, row, 2),
                "pcs": self._table_text(self.tyre_table, row, 4),
            }
        return result

    def _load_payload(self, payload: dict[str, Any]) -> None:
        self.supervisor_name.setText(str(payload.get("supervisor_name") or ""))
        self.production_notes.setPlainText(str(payload.get("production_notes") or ""))
        self.used_man_hours.setText(str(payload.get("used_man_hours") or ""))

        actuals = payload.get("tyre_actuals") or {}
        for row, line in enumerate(TYRE_LINE_ORDER):
            values = actuals.get(line) or {}
            self._set_item(self.tyre_table, row, 2, values.get("kg", ""), True)
            self._set_item(self.tyre_table, row, 4, values.get("pcs", ""), True)

        compound_rows = payload.get("compound_rows") or []
        for row in range(6):
            values = compound_rows[row] if row < len(compound_rows) else {}
            self._set_item(self.compound_table, row, 0, values.get("compound_type", ""), True)
            self._set_item(self.compound_table, row, 1, values.get("target", ""), True)
            self._set_item(self.compound_table, row, 2, values.get("actual", ""), True)
            self._set_item(self.compound_table, row, 3, "", False)
        self._set_item(self.compound_table, 6, 0, "Total", False)
        for column in range(1, 4):
            self._set_item(self.compound_table, 6, column, "", False)

        scrap_rows = payload.get("scrap_tyre_rows") or []
        scrap_keys = ("tyre_size", "pcs", "defect", "operator")
        for row in range(3):
            values = scrap_rows[row] if row < len(scrap_rows) else {}
            for column, key in enumerate(scrap_keys):
                self._set_item(self.scrap_tyre_table, row, column, values.get(key, ""), True)

        compound_scrap = payload.get("scrap_compound_rows") or []
        compound_scrap_keys = ("compound_type", "weight", "defect", "operator")
        for row in range(3):
            values = compound_scrap[row] if row < len(compound_scrap) else {}
            for column, key in enumerate(compound_scrap_keys):
                self._set_item(self.scrap_compound_table, row, column, values.get(key, ""), True)

        loss = payload.get("loss_reasons") or {}
        for row, reason in enumerate(LOSS_REASONS):
            values = loss.get(reason) or {}
            self._set_item(self.loss_table, row, 0, reason, False)
            for column, key in enumerate(LOSS_COLUMNS, start=1):
                self._set_item(self.loss_table, row, column, values.get(key, ""), True)

        self._refresh_compound_totals()

    def _load_loss_reason_labels(self) -> None:
        for row, reason in enumerate(LOSS_REASONS):
            self._set_item(self.loss_table, row, 0, reason, False)

    def _on_tyre_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        if item.column() in (2, 4):
            self._refresh_tyre_totals()
            self._refresh_calculated_fields()

    def _refresh_tyre_totals(self) -> None:
        target_kg = target_pcs = actual_kg = actual_pcs = 0.0
        for row in range(len(TYRE_LINE_ORDER)):
            target_kg += self._num(self._table_text(self.tyre_table, row, 1))
            actual_kg += self._num(self._table_text(self.tyre_table, row, 2))
            target_pcs += self._num(self._table_text(self.tyre_table, row, 3))
            actual_pcs += self._num(self._table_text(self.tyre_table, row, 4))
        total_row = len(TYRE_LINE_ORDER)
        previous = self.tyre_table.blockSignals(True)
        try:
            self._set_item(self.tyre_table, total_row, 1, f"{target_kg:.2f}", False)
            self._set_item(self.tyre_table, total_row, 2, f"{actual_kg:.2f}" if actual_kg else "", False)
            self._set_item(self.tyre_table, total_row, 3, str(int(round(target_pcs))), False)
            self._set_item(self.tyre_table, total_row, 4, str(int(round(actual_pcs))) if actual_pcs else "", False)
        finally:
            self.tyre_table.blockSignals(previous)

    def _refresh_compound_totals(self) -> None:
        target_total = actual_total = 0.0
        for row in range(6):
            target = self._num(self._table_text(self.compound_table, row, 1))
            actual = self._num(self._table_text(self.compound_table, row, 2))
            target_total += target
            actual_total += actual
            achievement = (actual / target * 100) if target else 0.0
            self._set_item(
                self.compound_table,
                row,
                3,
                f"{achievement:.1f}%" if target else "",
                False,
            )
        self._set_item(self.compound_table, 6, 1, f"{target_total:.2f}" if target_total else "", False)
        self._set_item(self.compound_table, 6, 2, f"{actual_total:.2f}" if actual_total else "", False)
        achievement = actual_total / target_total * 100 if target_total else 0.0
        self._set_item(self.compound_table, 6, 3, f"{achievement:.1f}%" if target_total else "", False)

    def _refresh_calculated_fields(self) -> None:
        actual_kg = sum(
            self._num(self._table_text(self.tyre_table, row, 2))
            for row in range(len(TYRE_LINE_ORDER))
        )
        man_hours = self._num(self.used_man_hours.text())
        self.production_kg_label.setText(f"{actual_kg:,.2f}" if actual_kg else "0.00")
        self.kg_per_hour_label.setText(
            f"{actual_kg / man_hours:,.2f}" if actual_kg and man_hours else "0.00"
        )
        if not self._loading:
            self._refresh_compound_totals()

    def _update_reconciliation(self) -> None:
        raw_pcs = int(self.target_summary.get("raw_total_pcs") or 0)
        mapped_pcs = int(self.target_summary.get("mapped_total_pcs") or 0)
        raw_kg = float(self.target_summary.get("raw_total_kg") or 0)
        mapped_kg = float(self.target_summary.get("mapped_total_kg") or 0)
        unmapped = self.target_summary.get("unmapped") or []
        if unmapped:
            names = ", ".join(str(row.get("line_name") or "") for row in unmapped[:6])
            self.reconciliation_label.setText(
                f"LIVE TARGET CHECK: {mapped_pcs:,}/{raw_pcs:,} pcs mapped | "
                f"{mapped_kg:,.2f}/{raw_kg:,.2f} kg mapped | UNMAPPED: {names}"
            )
            self.reconciliation_label.setStyleSheet(
                "QLabel{background:#fff7ed;border:1px solid #fdba74;border-radius:7px;padding:7px;color:#9a3412;font-weight:900;}"
            )
        else:
            self.reconciliation_label.setText(
                f"LIVE TARGET CHECK: {raw_pcs:,} pcs | {raw_kg:,.2f} kg | All imported OVEN lines reconciled to the Excel DAY/NIGHT report format."
            )
            self.reconciliation_label.setStyleSheet(
                "QLabel{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:7px;padding:7px;color:#065f46;font-weight:900;}"
            )

    def collect_payload(self) -> dict[str, Any]:
        self._refresh_compound_totals()
        compound_rows = []
        for row in range(6):
            compound_rows.append(
                {
                    "compound_type": self._table_text(self.compound_table, row, 0),
                    "target": self._table_text(self.compound_table, row, 1),
                    "actual": self._table_text(self.compound_table, row, 2),
                }
            )
        scrap_tyre_rows = []
        for row in range(3):
            scrap_tyre_rows.append(
                {
                    "tyre_size": self._table_text(self.scrap_tyre_table, row, 0),
                    "pcs": self._table_text(self.scrap_tyre_table, row, 1),
                    "defect": self._table_text(self.scrap_tyre_table, row, 2),
                    "operator": self._table_text(self.scrap_tyre_table, row, 3),
                }
            )
        scrap_compound_rows = []
        for row in range(3):
            scrap_compound_rows.append(
                {
                    "compound_type": self._table_text(self.scrap_compound_table, row, 0),
                    "weight": self._table_text(self.scrap_compound_table, row, 1),
                    "defect": self._table_text(self.scrap_compound_table, row, 2),
                    "operator": self._table_text(self.scrap_compound_table, row, 3),
                }
            )
        loss = {}
        for row, reason in enumerate(LOSS_REASONS):
            loss[reason] = {
                key: self._table_text(self.loss_table, row, column)
                for column, key in enumerate(LOSS_COLUMNS, start=1)
            }
        return {
            "supervisor_name": self.supervisor_name.text().strip(),
            "production_notes": self.production_notes.toPlainText().strip(),
            "tyre_actuals": self._current_payload_actuals_from_table(),
            "compound_rows": compound_rows,
            "scrap_tyre_rows": scrap_tyre_rows,
            "scrap_compound_rows": scrap_compound_rows,
            "used_man_hours": self.used_man_hours.text().strip(),
            "loss_reasons": loss,
        }

    def _user_label(self) -> str:
        user = self.current_user
        if isinstance(user, dict):
            for key in ("username", "full_name", "name", "email"):
                if user.get(key):
                    return str(user[key])
        for key in ("username", "full_name", "name", "email"):
            value = getattr(user, key, None)
            if value:
                return str(value)
        return ""

    def save_report(self) -> None:
        if not self.report_date:
            QMessageBox.warning(self, "Shift Report", "Select a plan date first.")
            return
        try:
            ShiftDailyReportService.save_report(
                self.report_date,
                self.shift_name,
                self.collect_payload(),
                self._user_label(),
            )
            QMessageBox.information(
                self,
                "Shift Report Saved",
                f"{self.shift_name} report for {self.report_date} was saved.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Shift Report Save", str(exc))

    def _document(self) -> QTextDocument:
        html = build_shift_report_html(
            self.report_date,
            self.shift_name,
            self.target_summary,
            self.collect_payload(),
        )
        document = QTextDocument(self)
        document.setHtml(html)
        return document

    @staticmethod
    def _configure_printer(printer: QPrinter) -> None:
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)

    def print_preview(self) -> None:
        if not self.report_date:
            QMessageBox.warning(self, "Shift Report", "Select a plan date first.")
            return
        document = self._document()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._configure_printer(printer)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(
            f"{self.shift_name} Daily Production Summary — {self.report_date}"
        )
        preview.paintRequested.connect(document.print_)
        preview.exec()

    def print_direct(self) -> None:
        if not self.report_date:
            return
        document = self._document()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._configure_printer(printer)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            document.print_(printer)

    def save_pdf(self) -> None:
        if not self.report_date:
            QMessageBox.warning(self, "Shift Report", "Select a plan date first.")
            return
        default_name = (
            f"Daily_Production_Summary_{self.report_date}_{self.shift_name.replace(' ', '_')}.pdf"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Shift Report PDF",
            default_name,
            "PDF Files (*.pdf)",
        )
        if not filename:
            return
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        try:
            document = self._document()
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            self._configure_printer(printer)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(filename)
            document.print_(printer)
            QMessageBox.information(self, "PDF Saved", f"Saved:\n{filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Save PDF", str(exc))


class ShiftPlanPage(_OperationsPage):
    title_text = "Day / Night Shift Control"
    subtitle_text = (
        "Saved production-plan DAY/NIGHT allocations are the operational authority. "
        "Imported OVEN allocations remain available only as historical/fallback evidence; "
        "actuals, quality and loss data are saved by date and shift."
    )
    TASK_PREFIX = "shift-plan-r5:"

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__(current_user, *args, **kwargs)
        self.tasks = TaskManager.instance()
        self._loaded_once = False
        self._load_generation = 0

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Plan Date"))
        self.date_filter = QComboBox()
        self.date_filter.currentIndexChanged.connect(self._load_selected_async)
        filter_row.addWidget(self.date_filter)
        self.status_label = QLabel("Preparing shift plan in background...")
        self.status_label.setStyleSheet("color:#64748b;font-weight:750;")
        filter_row.addWidget(self.status_label, 1)
        self.root.addLayout(filter_row)

        self.tabs = QTabWidget()
        live_tab = QWidget()
        live_layout = QVBoxLayout(live_tab)
        live_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics = QGridLayout()
        live_layout.addLayout(self.metrics)
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
        live_layout.addWidget(self.table, 1)

        self.day_report = _ShiftReportEditor("DAY", current_user, self)
        self.night_report = _ShiftReportEditor("NIGHT", current_user, self)
        self.tabs.addTab(live_tab, "Live Oven Allocations")
        self.tabs.addTab(self.day_report, "DAY Report / Print")
        self.tabs.addTab(self.night_report, "NIGHT Report / Print")
        self.root.addWidget(self.tabs, 1)

        QTimer.singleShot(40, self.refresh)

    def showEvent(self, event) -> None:
        QWidget.showEvent(self, event)
        if not self._loaded_once:
            QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        self.status_label.setText("Loading shift dates in background...")

        def load_dates_job():
            ShiftDailyReportService.ensure_schema()
            return ShiftDailyReportService.list_plan_dates(180)

        self.tasks.submit(
            self.TASK_PREFIX + "dates",
            load_dates_job,
            on_result=self._dates_loaded,
            on_error=self._async_error,
            replace=True,
        )

    def _dates_loaded(self, dates: list[str]) -> None:
        selected = self.date_filter.currentText()
        self.date_filter.blockSignals(True)
        self.date_filter.clear()
        self.date_filter.addItems(list(dates or []))
        if selected:
            index = self.date_filter.findText(selected)
            if index >= 0:
                self.date_filter.setCurrentIndex(index)
        self.date_filter.blockSignals(False)
        self._loaded_once = True
        self._load_selected_async()

    def _load_selected_async(self, *_args) -> None:
        selected = self.date_filter.currentText().strip()
        if not selected:
            self.table.setRowCount(0)
            self.status_label.setText("No shift-plan date is available.")
            return

        self._load_generation += 1
        generation = self._load_generation
        self.status_label.setText(f"Loading {selected} shift plan in background...")

        def load_selected_job():
            live = ShiftDailyReportService.load_live_plan(selected)
            live.update(
                {
                    "DAY": {
                        "plan_date": selected,
                        "targets": ShiftDailyReportService.load_targets(
                            selected,
                            "DAY",
                        ),
                        "report": ShiftDailyReportService.load_report(
                            selected,
                            "DAY",
                        ),
                    },
                    "NIGHT": {
                        "plan_date": selected,
                        "targets": ShiftDailyReportService.load_targets(
                            selected,
                            "NIGHT",
                        ),
                        "report": ShiftDailyReportService.load_report(
                            selected,
                            "NIGHT",
                        ),
                    },
                }
            )
            return live

        self.tasks.submit(
            self.TASK_PREFIX + "selected",
            load_selected_job,
            on_result=lambda payload, gen=generation: self._selected_loaded(gen, payload),
            on_error=self._async_error,
            replace=True,
        )

    def _selected_loaded(self, generation: int, payload: dict[str, Any]) -> None:
        if generation != self._load_generation:
            return

        summary = list(payload.get("summary") or [])
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

        rows = list(payload.get("rows") or [])
        self._fill(
            self.table,
            [
                [
                    row.get("shift_name"),
                    row.get("oven_code"),
                    row.get("material_code"),
                    row.get("item_description"),
                    row.get("planned_qty"),
                    row.get("planned_weight_kg"),
                    row.get("source"),
                ]
                for row in rows
            ],
        )

        self._apply_report_payload(self.day_report, payload.get("DAY") or {})
        self._apply_report_payload(self.night_report, payload.get("NIGHT") or {})
        authority = str(payload.get("authority") or "UNKNOWN")
        source_label = (
            "saved production plan"
            if authority == "SAVED_R6_CAVITY_PLAN"
            else "imported OVEN fallback"
        )
        self.status_label.setText(
            f"{payload.get('plan_date') or '—'} • {len(rows):,} allocation row(s) • {source_label}"
        )

    @staticmethod
    def _apply_report_payload(editor: _ShiftReportEditor, payload: dict[str, Any]) -> None:
        editor.report_date = str(payload.get("plan_date") or payload.get("report", {}).get("report_date") or editor.report_date or "")
        if not editor.report_date:
            return
        editor.date_label.setText(f"Date: {editor.report_date}")
        editor._loading = True
        try:
            editor.target_summary = dict(payload.get("targets") or {})
            editor._load_payload(dict(payload.get("report") or {}))
            editor._load_targets()
            editor._load_loss_reason_labels()
            editor._update_reconciliation()
            editor._refresh_calculated_fields()
        finally:
            editor._loading = False

    def _async_error(self, message: str) -> None:
        self.status_label.setText(
            "Shift plan load failed: " + (message.splitlines()[-1] if message else "unknown error")
        )


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
                    GREATEST(s.fg_stock, 0) + GREATEST(s.qc_stock, 0) AS net_available,
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

# MPPS V32 OPERATIONS LOAD ONCE
from PySide6.QtCore import QTimer as _V32OpsTimer


def _v32_operations_show_event(self, event):
    QWidget.showEvent(self, event)

    if getattr(
        self,
        "_mpps_v32_loaded_once",
        False,
    ):
        return

    self._mpps_v32_loaded_once = True

    # Let the page shell paint before the first refresh.
    _V32OpsTimer.singleShot(
        30,
        self.refresh,
    )


_OperationsPage.showEvent = _v32_operations_show_event
