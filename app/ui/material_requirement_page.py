from __future__ import annotations

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


class MaterialRequirementPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.loaded_data: list[dict] = []

        # Widgets
        self.total_shortage_items = QLabel("0")
        self.total_bom_weight = QLabel("0 KG")
        self.total_beads_needed = QLabel("0 PCS")
        self.total_bands_needed = QLabel("0 PCS")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search finished code, component code, or description...")
        self.search_input.textChanged.connect(self.filter_table)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["All Component Types", "BOM Raw Materials", "Compounds", "Beads", "Bands"])
        self.category_combo.currentTextChanged.connect(self.filter_table)

        self.refresh_btn = QPushButton("Calculate Requirements")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_report)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Finished Item", "Shortage Qty", "Component Type", "Material Code", "Material Name", "Req Qty", "Unit"]
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
        metrics_layout.addWidget(self._metric_card("Total BOM weight", self.total_bom_weight), 1)
        metrics_layout.addWidget(self._metric_card("Beads Required", self.total_beads_needed), 1)
        metrics_layout.addWidget(self._metric_card("Bands Required", self.total_bands_needed), 1)
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
        title = QLabel("Material Requirement Planning (MRP)")
        title.setObjectName("SectionTitle")
        hint = QLabel("Calculates exact component quantities required to fulfill current production shortage demands.")
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
        form.addWidget(QLabel("Type"))
        form.addWidget(self.category_combo, 1)
        ctrl_layout.addLayout(form)

        root.addWidget(ctrl_card)

        # Table card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Calculated Components Requirements")
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 140)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 70)

    def refresh(self) -> None:
        try:
            self.calculate_mrp()
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "MRP Calculation Error", f"MRP engine failed: {exc}")

    def calculate_mrp(self) -> None:
        self.loaded_data.clear()

        # Load active shortages
        sql_shortages = """
            SELECT material_code, item_description, production_required_qty
            FROM mpps_stock_planning_view
            WHERE production_required_qty > 0;
        """

        with engine.begin() as connection:
            shortages = connection.execute(text(sql_shortages)).mappings().all()
            
            # Load master lists for mapping
            boms = connection.execute(
                text("SELECT finished_item_code, raw_material_code, raw_material_name, usage_per_unit, unit, wastage_percentage FROM mpps_bom_items WHERE is_active=TRUE;")
            ).mappings().all()

            compounds = connection.execute(
                text("SELECT item_code, compound_code, compound_name, compound_weight_per_unit, stage FROM mpps_compound_master WHERE is_active=TRUE;")
            ).mappings().all()

            beads = connection.execute(
                text("SELECT item_code, bead_type, bead_per_tyre FROM mpps_bead_master WHERE is_active=TRUE;")
            ).mappings().all()

            bands = connection.execute(
                text("SELECT item_code, band_code, band_type, band_usage_per_tyre FROM mpps_band_master WHERE is_active=TRUE;")
            ).mappings().all()

        # Group components by finished item
        bom_map = {}
        for b in boms:
            bom_map.setdefault(b["finished_item_code"], []).append(b)

        compound_map = {}
        for c in compounds:
            compound_map.setdefault(c["item_code"], []).append(c)

        bead_map = {}
        for bd in beads:
            bead_map.setdefault(bd["item_code"], []).append(bd)

        band_map = {}
        for bn in bands:
            band_map.setdefault(bn["item_code"], []).append(bn)

        total_bom_weight_kg = 0.0
        total_beads = 0.0
        total_bands = 0.0
        shortage_items_count = len(shortages)

        for s in shortages:
            code = s["material_code"]
            qty = s["production_required_qty"]

            # 1. BOM Materials
            if code in bom_map:
                for b in bom_map[code]:
                    # usage * qty * (1 + wastage%)
                    req = float(qty) * float(b["usage_per_unit"]) * (1.0 + float(b["wastage_percentage"]) / 100.0)
                    total_bom_weight_kg += req
                    self.loaded_data.append({
                        "finished_item": code,
                        "shortage_qty": qty,
                        "comp_type": "BOM Raw Material",
                        "mat_code": b["raw_material_code"],
                        "mat_name": b["raw_material_name"],
                        "req_qty": req,
                        "unit": b["unit"]
                    })

            # 2. Compounds
            if code in compound_map:
                for c in compound_map[code]:
                    req = float(qty) * float(c["compound_weight_per_unit"])
                    total_bom_weight_kg += req
                    self.loaded_data.append({
                        "finished_item": code,
                        "shortage_qty": qty,
                        "comp_type": "Compound",
                        "mat_code": c["compound_code"],
                        "mat_name": f"{c['compound_name']} ({c['stage']})",
                        "req_qty": req,
                        "unit": "KG"
                    })

            # 3. Beads
            if code in bead_map:
                for bd in bead_map[code]:
                    req = float(qty) * float(bd["bead_per_tyre"])
                    total_beads += req
                    self.loaded_data.append({
                        "finished_item": code,
                        "shortage_qty": qty,
                        "comp_type": "Bead",
                        "mat_code": bd["bead_type"],
                        "mat_name": f"Bead type: {bd['bead_type']}",
                        "req_qty": req,
                        "unit": "PCS"
                    })

            # 4. Bands
            if code in band_map:
                for bn in band_map[code]:
                    req = float(qty) * float(bn["band_usage_per_tyre"])
                    total_bands += req
                    self.loaded_data.append({
                        "finished_item": code,
                        "shortage_qty": qty,
                        "comp_type": "Band",
                        "mat_code": bn["band_code"] or "-",
                        "mat_name": f"Band type: {bn['band_type']}",
                        "req_qty": req,
                        "unit": "PCS"
                    })

        self.total_shortage_items.setText(str(shortage_items_count))
        self.total_bom_weight.setText(f"{total_bom_weight_kg:,.2f} KG")
        self.total_beads_needed.setText(f"{int(total_beads):,} PCS")
        self.total_bands_needed.setText(f"{int(total_bands):,} PCS")

    def filter_table(self) -> None:
        search_text = self.search_input.text().strip().lower()
        cat_filter = self.category_combo.currentText()

        # Map UI Category to loaded comp_type values
        cat_map = {
            "BOM Raw Materials": "BOM Raw Material",
            "Compounds": "Compound",
            "Beads": "Bead",
            "Bands": "Band"
        }
        target_type = cat_map.get(cat_filter)

        self.table.setRowCount(0)
        row_idx = 0

        for r in self.loaded_data:
            # Type filter
            if target_type and r["comp_type"] != target_type:
                continue

            # Search filter
            if search_text:
                match = (
                    search_text in r["finished_item"].lower() or
                    search_text in r["mat_code"].lower() or
                    search_text in r["mat_name"].lower() or
                    search_text in r["comp_type"].lower()
                )
                if not match:
                    continue

            self.table.insertRow(row_idx)

            items = [
                r["finished_item"],
                str(r["shortage_qty"]),
                r["comp_type"],
                r["mat_code"],
                r["mat_name"],
                f"{r['req_qty']:,.4f}",
                r["unit"]
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 1, 2, 3, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

            row_idx += 1

        self.table.resizeRowsToContents()

    def export_report(self) -> None:
        try:
            # We want to export whatever is currently loaded in the table
            headers = ["Finished Item", "Shortage Qty", "Component Type", "Material Code", "Material Name", "Req Qty", "Unit"]
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

            filepath = export_to_csv(headers, data, "material_requirement_report")
            QMessageBox.information(self, "Export Success", f"Material requirement report successfully exported to:\n\n{filepath}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export report: {exc}")
