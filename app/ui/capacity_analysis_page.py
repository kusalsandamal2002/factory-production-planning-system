from __future__ import annotations

import math
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


class CapacityAnalysisPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.loaded_data: list[dict] = []

        # Widgets
        self.total_shortage_items = QLabel("0")
        self.total_moulds_active = QLabel("0")
        self.cannot_complete_count = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search item code, description or group...")
        self.search_input.textChanged.connect(self.filter_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All Status", "CAN COMPLETE Only", "CANNOT COMPLETE Only"])
        self.status_combo.currentTextChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Calculate Capacity Analysis")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_report)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Description",
                "Bead Type (Size Group)",
                "Prod Req Qty",
                "Daily Capacity",
                "Days Required",
                "Capacity Gap",
                "Status",
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
                font-size: 19pt;
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
        metrics_layout.setSpacing(14)
        metrics_layout.addWidget(self._metric_card("Shortage Products", self.total_shortage_items), 1)
        metrics_layout.addWidget(self._metric_card("Active Moulds Needed", self.total_moulds_active), 1)
        metrics_layout.addWidget(self._metric_card("Cannot Complete Items", self.cannot_complete_count), 1)
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
        title = QLabel("Mould Capacity Analysis")
        title.setObjectName("SectionTitle")
        hint = QLabel("Compares current production shortages against daily mould curing limits to estimate schedules and gaps.")
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
        form.addWidget(QLabel("Status Filter"))
        form.addWidget(self.status_combo, 1)
        ctrl_layout.addLayout(form)

        root.addWidget(ctrl_card)

        # Table card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Shortage Capacity Allocation")
        table_title.setObjectName("SectionTitle")
        table_layout.addWidget(table_title)
        table_layout.addWidget(self.table, 1)

        root.addWidget(table_card, 1)

    def _metric_card(self, title_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 110)
        self.table.setColumnWidth(7, 140)

    def refresh(self) -> None:
        try:
            self.calculate_capacity()
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Capacity Analysis Error", f"Capacity engine failed: {exc}")

    def calculate_capacity(self) -> None:
        self.loaded_data.clear()

        # Query shortages and join capacity master on bead_type = item_code
        sql = """
            SELECT
                spv.material_code,
                spv.item_description,
                spv.bead_type,
                spv.production_required_qty,
                COALESCE(cm.available_capacity_per_day, 0) AS daily_capacity,
                COALESCE(cm.running_moulds, 0) AS moulds
            FROM mpps_stock_planning_view spv
            LEFT JOIN mpps_capacity_master cm
              ON spv.bead_type = cm.item_code
            WHERE spv.production_required_qty > 0;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql)).mappings().all()

        cannot_complete = 0
        total_moulds = 0.0

        for r in rows:
            qty = r["production_required_qty"]
            cap = float(r["daily_capacity"] or 0)
            moulds = float(r["moulds"] or 0)

            if cap > 0:
                days = float(qty) / cap
                gap = cap - float(qty)
                status = "CAN COMPLETE"
                total_moulds += moulds
            else:
                days = 999.0  # infinite days representation
                gap = -float(qty)
                status = "CANNOT COMPLETE"
                cannot_complete += 1

            self.loaded_data.append({
                "item_code": r["material_code"],
                "description": r["item_description"],
                "bead_type": r["bead_type"] or "-",
                "qty": qty,
                "daily_capacity": cap,
                "days_required": days,
                "capacity_gap": gap,
                "status": status
            })

        self.total_shortage_items.setText(str(len(rows)))
        self.total_moulds_active.setText(f"{total_moulds:.2f}")
        self.cannot_complete_count.setText(str(cannot_complete))

    def filter_table(self) -> None:
        search_text = self.search_input.text().strip().lower()
        status_filter = self.status_combo.currentText()

        self.table.setRowCount(0)
        row_idx = 0

        for r in self.loaded_data:
            # Status filter
            if status_filter == "CAN COMPLETE Only" and r["status"] != "CAN COMPLETE":
                continue
            if status_filter == "CANNOT COMPLETE Only" and r["status"] != "CANNOT COMPLETE":
                continue

            # Search filter
            if search_text:
                match = (
                    search_text in r["item_code"].lower() or
                    search_text in r["description"].lower() or
                    search_text in r["bead_type"].lower() or
                    search_text in r["status"].lower()
                )
                if not match:
                    continue

            self.table.insertRow(row_idx)

            days_val = f"{r['days_required']:.2f}" if r["days_required"] < 999.0 else "∞"
            gap_val = f"{r['capacity_gap']:,.2f}"

            items = [
                r["item_code"],
                r["description"],
                r["bead_type"],
                str(r["qty"]),
                f"{r['daily_capacity']:.2f}",
                days_val,
                gap_val,
                r["status"]
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 2, 3, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Apply color styling to Status
                if col_idx == 7:
                    if r["status"] == "CAN COMPLETE":
                        item.setForeground(Qt.GlobalColor.darkGreen)
                    else:
                        item.setForeground(Qt.GlobalColor.red)
                        item.setToolTip("Missing capacity specification! Production cannot be scheduled.")

                self.table.setItem(row_idx, col_idx, item)

            row_idx += 1

        self.table.resizeRowsToContents()

    def export_report(self) -> None:
        try:
            headers = [
                "Item Code", "Description", "Bead Type (Size Group)", 
                "Prod Req Qty", "Daily Capacity", "Days Required", "Capacity Gap", "Status"
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

            filepath = export_to_csv(headers, data, "capacity_analysis_report")
            QMessageBox.information(self, "Export Success", f"Capacity analysis report successfully exported to:\n\n{filepath}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export report: {exc}")
