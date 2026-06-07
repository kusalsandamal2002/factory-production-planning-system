from __future__ import annotations

import math
from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text
from app.database import engine
from app.utils.reports_export import export_to_csv


class ShipmentRiskPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.loaded_data: list[dict] = []

        # Widgets
        self.total_demands = QLabel("0")
        self.low_risk_count = QLabel("0")
        self.med_risk_count = QLabel("0")
        self.high_risk_count = QLabel("0")
        self.cannot_complete_count = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search customer, material code, or risk status...")
        self.search_input.textChanged.connect(self.filter_table)

        self.risk_combo = QComboBox()
        self.risk_combo.addItems(["All Risk Levels", "LOW RISK", "MEDIUM RISK", "HIGH RISK", "CANNOT COMPLETE"])
        self.risk_combo.currentTextChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Run Risk Analysis")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_report)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Customer Demand",
                "Material Code",
                "Ship Date",
                "Demand Qty",
                "Avail Stock",
                "Shortage Qty",
                "Daily Cap",
                "Est Days",
                "Risk Status",
            ]
        )

        self._setup_table()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard,
            QFrame#TableCard,
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
            QLabel#MetricTitle {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 850;
            }
            QLabel#MetricValue {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }
            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }
            QLabel#SectionHint {
                color: #64748b;
                font-size: 9.5pt;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Metrics layout
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(10)
        metrics_layout.addWidget(self._metric_card("Total Demands", self.total_demands), 1)
        metrics_layout.addWidget(self._metric_card("Low Risk", self.low_risk_count), 1)
        metrics_layout.addWidget(self._metric_card("Medium Risk", self.med_risk_count), 1)
        metrics_layout.addWidget(self._metric_card("High Risk", self.high_risk_count), 1)
        metrics_layout.addWidget(self._metric_card("Cannot Complete", self.cannot_complete_count), 1)
        root.addLayout(metrics_layout)

        # Controls card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("ControlCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(18, 16, 18, 18)
        ctrl_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Shipment Risk Assessment")
        title.setObjectName("SectionTitle")
        hint = QLabel("Calculates schedule buffer days against curing capacity constraints to classify customer demand delivery risks.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        header.addWidget(self.refresh_btn)
        header.addWidget(self.export_btn)
        ctrl_layout.addLayout(header)

        form = QHBoxLayout()
        form.setSpacing(12)
        form.addWidget(QLabel("Search"))
        form.addWidget(self.search_input, 2)
        form.addWidget(QLabel("Risk Level"))
        form.addWidget(self.risk_combo, 1)
        ctrl_layout.addLayout(form)

        root.addWidget(ctrl_card)

        # Table card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Demands Risk Assessment Table")
        table_title.setObjectName("SectionTitle")
        table_layout.addWidget(table_title)
        table_layout.addWidget(self.table, 1)

        root.addWidget(table_card, 1)

    def _metric_card(self, title_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("MetricTitle")
        value_label.setObjectName("MetricValue")

        layout.addWidget(title)
        layout.addWidget(value_label)
        return card

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 90)
        self.table.setColumnWidth(7, 90)
        self.table.setColumnWidth(8, 140)

    def refresh(self) -> None:
        try:
            self.calculate_risks()
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Risk Assessment Error", f"Risk engine failed: {exc}")

    def calculate_risks(self) -> None:
        self.loaded_data.clear()

        # Load customer demands, stocks, and daily capacity mapping
        sql = """
            SELECT
                sd.id,
                COALESCE(sd.customer_name, 'EXCEL_DEMAND') AS customer_name,
                sd.material_code,
                sd.demand_qty,
                sd.shipment_date,
                COALESCE(si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock, 0) AS available_stock,
                COALESCE(cm.available_capacity_per_day, 0) AS daily_capacity
            FROM mpps_shipment_demand sd
            LEFT JOIN mpps_stock_items si
              ON sd.material_code = si.material_code
            LEFT JOIN mpps_capacity_master cm
              ON si.bead_type = cm.item_code
            WHERE sd.status IN ('PENDING', 'CONFIRMED', 'PLANNED', 'PARTIALLY_PLANNED')
              AND sd.demand_qty > 0;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql)).mappings().all()

        low_risk = 0
        med_risk = 0
        high_risk = 0
        cannot_comp = 0
        today_date = date.today()

        for r in rows:
            qty = r["demand_qty"]
            stock = r["available_stock"]
            cap = float(r["daily_capacity"] or 0.0)
            ship_date = r["shipment_date"]

            shortage = max(qty - stock, 0)

            # Est. remaining calendar days to ship date
            if ship_date:
                remaining_days = max((ship_date - today_date).days, 0)
            else:
                remaining_days = 999  # Treat missing date as long buffer or warn

            if shortage == 0:
                status = "LOW RISK"
                days_required = 0.0
                low_risk += 1
            else:
                if cap > 0.0:
                    days_required = float(shortage) / cap
                    est_days = math.ceil(days_required)
                    if est_days <= remaining_days:
                        status = "MEDIUM RISK"
                        med_risk += 1
                    else:
                        status = "HIGH RISK"
                        high_risk += 1
                else:
                    days_required = 999.0
                    status = "CANNOT COMPLETE"
                    cannot_comp += 1

            self.loaded_data.append({
                "id": r["id"],
                "customer": r["customer_name"],
                "material_code": r["material_code"],
                "ship_date": ship_date,
                "qty": qty,
                "stock": stock,
                "shortage": shortage,
                "capacity": cap,
                "est_days": days_required,
                "status": status
            })

        self.total_demands.setText(str(len(rows)))
        self.low_risk_count.setText(str(low_risk))
        self.med_risk_count.setText(str(med_risk))
        self.high_risk_count.setText(str(high_risk))
        self.cannot_complete_count.setText(str(cannot_comp))

    def filter_table(self) -> None:
        search_text = self.search_input.text().strip().lower()
        risk_filter = self.risk_combo.currentText()

        self.table.setRowCount(0)
        row_idx = 0

        for r in self.loaded_data:
            # Risk level filter
            if risk_filter != "All Risk Levels" and r["status"] != risk_filter:
                continue

            # Search filter
            if search_text:
                match = (
                    search_text in r["customer"].lower() or
                    search_text in r["material_code"].lower() or
                    search_text in r["status"].lower()
                )
                if not match:
                    continue

            self.table.insertRow(row_idx)

            date_str = r["ship_date"].strftime("%Y-%m-%d") if r["ship_date"] else "No Date"
            days_str = f"{math.ceil(r['est_days'])}" if r["est_days"] < 999.0 else "∞"
            cap_str = f"{r['capacity']:.2f}"

            items = [
                r["customer"],
                r["material_code"],
                date_str,
                str(r["qty"]),
                str(r["stock"]),
                str(r["shortage"]),
                cap_str,
                days_str,
                r["status"]
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (1, 2, 3, 4, 5, 6, 7, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Style status badge
                if col_idx == 8:
                    if r["status"] == "LOW RISK":
                        item.setForeground(Qt.GlobalColor.darkGreen)
                    elif r["status"] == "MEDIUM RISK":
                        item.setForeground(Qt.GlobalColor.darkBlue)
                    elif r["status"] == "HIGH RISK":
                        item.setForeground(Qt.GlobalColor.darkYellow)
                    else:
                        item.setForeground(Qt.GlobalColor.red)
                        item.setToolTip("Cannot cure! No capacity allocated for this tire group.")

                self.table.setItem(row_idx, col_idx, item)

            row_idx += 1

        self.table.resizeRowsToContents()

    def export_report(self) -> None:
        try:
            headers = [
                "Customer Demand", "Material Code", "Ship Date", "Demand Qty", 
                "Avail Stock", "Shortage Qty", "Daily Cap", "Est Days", "Risk Status"
            ]
            data = []
            
            for row in range(self.table.rowCount()):
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item else "")
                data.append(row_data)

            if not data:
                QMessageBox.warning(self, "Export Report", "No records found in the table to export.")
                return

            filepath = export_to_csv(headers, data, "shipment_risk_report")
            QMessageBox.information(self, "Export Success", f"Shipment risk report successfully exported to:\n\n{filepath}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export report: {exc}")
