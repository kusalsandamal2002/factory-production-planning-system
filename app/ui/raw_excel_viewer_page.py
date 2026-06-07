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
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text
from app.database import engine


class RawExcelViewerPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.workbooks_map: dict[str, int] = {}
        self.sheets_map: dict[str, int] = {}

        # Controls
        self.workbook_combo = QComboBox()
        self.workbook_combo.currentTextChanged.connect(self.on_workbook_changed)

        self.sheet_combo = QComboBox()
        self.sheet_combo.currentTextChanged.connect(self.on_sheet_changed)

        # Tab 1: Grid View controls
        self.start_row_spin = QSpinBox()
        self.start_row_spin.setRange(1, 999999)
        self.start_row_spin.setValue(1)
        self.start_row_spin.setPrefix("Start Row: ")
        self.start_row_spin.valueChanged.connect(self.refresh_grid)

        self.row_count_spin = QSpinBox()
        self.row_count_spin.setRange(10, 500)
        self.row_count_spin.setValue(100)
        self.row_count_spin.setPrefix("Rows limit: ")
        self.row_count_spin.valueChanged.connect(self.refresh_grid)

        self.refresh_btn = QPushButton("Refresh Grid")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_grid)

        self.grid_table = QTableWidget(0, 0)

        # Tab 2: Search controls
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search cell content or address (e.g. A1, BEAD)...")
        self.search_input.returnPressed.connect(self.search_cells)

        self.search_btn = QPushButton("Search Cells")
        self.search_btn.setObjectName("PrimaryButton")
        self.search_btn.clicked.connect(self.search_cells)

        self.search_results_table = QTableWidget(0, 7)
        self.search_results_table.setHorizontalHeaderLabels([
            "Row #", "Col #", "Address", "Display Value", "Raw Value", "Formula", "Type"
        ])

        self._apply_styles()
        self._build_ui()
        self.load_workbooks()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard,
            QFrame#ViewCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
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
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #475569;
                padding: 8px 16px;
                border: 1px solid #e2e8f0;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0f172a;
                border-bottom-color: #ffffff;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Control Card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("ControlCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(18, 16, 18, 18)
        ctrl_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Raw Excel Workbook Preserver & Viewer")
        title.setObjectName("SectionTitle")
        hint = QLabel("Trace clean MPPS metrics back to their original cell locations in Excel uploads.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        ctrl_layout.addLayout(header)

        selectors_layout = QHBoxLayout()
        selectors_layout.setSpacing(12)
        selectors_layout.addWidget(QLabel("Workbook:"))
        selectors_layout.addWidget(self.workbook_combo, 2)
        selectors_layout.addWidget(QLabel("Sheet:"))
        selectors_layout.addWidget(self.sheet_combo, 2)
        ctrl_layout.addLayout(selectors_layout)

        root.addWidget(ctrl_card)

        # Tabs Card
        view_card = QFrame()
        view_card.setObjectName("ViewCard")
        view_layout = QVBoxLayout(view_card)
        view_layout.setContentsMargins(18, 16, 18, 18)
        view_layout.setSpacing(12)

        self.tabs = QTabWidget()
        
        # Grid View Tab
        grid_tab = QWidget()
        grid_tab_layout = QVBoxLayout(grid_tab)
        grid_tab_layout.setContentsMargins(10, 10, 10, 10)
        grid_tab_layout.setSpacing(10)

        grid_controls = QHBoxLayout()
        grid_controls.addWidget(self.start_row_spin)
        grid_controls.addWidget(self.row_count_spin)
        grid_controls.addStretch()
        grid_controls.addWidget(self.refresh_btn)
        grid_tab_layout.addLayout(grid_controls)

        self.grid_table.setAlternatingRowColors(True)
        grid_tab_layout.addWidget(self.grid_table, 1)

        # Search Cells Tab
        search_tab = QWidget()
        search_tab_layout = QVBoxLayout(search_tab)
        search_tab_layout.setContentsMargins(10, 10, 10, 10)
        search_tab_layout.setSpacing(10)

        search_controls = QHBoxLayout()
        search_controls.addWidget(self.search_input, 1)
        search_controls.addWidget(self.search_btn)
        search_tab_layout.addLayout(search_controls)

        self.search_results_table.setAlternatingRowColors(True)
        self.search_results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        search_header = self.search_results_table.horizontalHeader()
        search_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        search_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        search_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        search_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.search_results_table.setColumnWidth(0, 80)
        self.search_results_table.setColumnWidth(1, 80)
        self.search_results_table.setColumnWidth(2, 90)
        search_tab_layout.addWidget(self.search_results_table, 1)

        self.tabs.addTab(grid_tab, "🔍 Grid Spreadsheet View")
        self.tabs.addTab(search_tab, "🔎 Search Cells")

        view_layout.addWidget(self.tabs, 1)
        root.addWidget(view_card, 1)

    def load_workbooks(self) -> None:
        self.workbook_combo.blockSignals(True)
        self.workbook_combo.clear()
        self.workbooks_map.clear()

        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text("SELECT id, workbook_key, original_file_name FROM excel_workbooks ORDER BY imported_at DESC;")
                ).mappings().all()

                for row in rows:
                    display_name = f"{row['original_file_name']} ({row['workbook_key']})"
                    self.workbooks_map[display_name] = row["id"]
                    self.workbook_combo.addItem(display_name)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to load workbooks: {exc}")

        self.workbook_combo.blockSignals(False)
        self.on_workbook_changed(self.workbook_combo.currentText())

    def on_workbook_changed(self, workbook_name: str) -> None:
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self.sheets_map.clear()

        workbook_id = self.workbooks_map.get(workbook_name)
        if workbook_id is not None:
            try:
                with engine.begin() as connection:
                    rows = connection.execute(
                        text("SELECT id, sheet_name FROM excel_sheets WHERE workbook_id = :wb_id ORDER BY sheet_index ASC;"),
                        {"wb_id": workbook_id}
                    ).mappings().all()

                    for row in rows:
                        self.sheets_map[row["sheet_name"]] = row["id"]
                        self.sheet_combo.addItem(row["sheet_name"])
            except Exception as exc:
                QMessageBox.critical(self, "Database Error", f"Failed to load sheets: {exc}")

        self.sheet_combo.blockSignals(False)
        self.on_sheet_changed(self.sheet_combo.currentText())

    def on_sheet_changed(self, sheet_name: str) -> None:
        self.start_row_spin.setValue(1)
        self.refresh_grid()
        self.search_results_table.setRowCount(0)

    def refresh(self) -> None:
        self.load_workbooks()

    def refresh_grid(self) -> None:
        sheet_name = self.sheet_combo.currentText()
        sheet_id = self.sheets_map.get(sheet_name)
        if sheet_id is None:
            self.grid_table.setRowCount(0)
            self.grid_table.setColumnCount(0)
            return

        start_row = self.start_row_spin.value()
        limit = self.row_count_spin.value()
        end_row = start_row + limit - 1

        try:
            with engine.begin() as connection:
                # Query cells in range
                cells = connection.execute(
                    text(
                        """
                        SELECT row_number, column_number, column_letter, display_value, raw_value, is_formula, formula_value
                        FROM excel_raw_cells
                        WHERE sheet_id = :sheet_id
                          AND row_number BETWEEN :start_row AND :end_row
                        ORDER BY row_number ASC, column_number ASC;
                        """
                    ),
                    {"sheet_id": sheet_id, "start_row": start_row, "end_row": end_row}
                ).mappings().all()

                # Get column information for layout
                col_info = connection.execute(
                    text(
                        """
                        SELECT DISTINCT column_number, column_letter
                        FROM excel_raw_cells
                        WHERE sheet_id = :sheet_id
                        ORDER BY column_number ASC;
                        """
                    ),
                    {"sheet_id": sheet_id}
                ).mappings().all()

            if not col_info:
                self.grid_table.setRowCount(0)
                self.grid_table.setColumnCount(0)
                return

            max_col_num = max(c["column_number"] for c in col_info)

            # Rebuild grid headers
            self.grid_table.clear()
            self.grid_table.setRowCount(limit)
            self.grid_table.setColumnCount(max_col_num)

            # Columns headers are letters (A, B, C...)
            headers = [""] * max_col_num
            for c in col_info:
                headers[c["column_number"] - 1] = c["column_letter"]
            self.grid_table.setHorizontalHeaderLabels(headers)

            # Rows headers are row numbers
            row_headers = [str(r) for r in range(start_row, end_row + 1)]
            self.grid_table.setVerticalHeaderLabels(row_headers)

            # Populate cells
            self.grid_table.blockSignals(True)
            for cell in cells:
                r_idx = cell["row_number"] - start_row
                c_idx = cell["column_number"] - 1

                if r_idx < 0 or r_idx >= limit or c_idx < 0 or c_idx >= max_col_num:
                    continue

                display = cell["display_value"]
                if display is None:
                    display = cell["raw_value"] or ""

                item = QTableWidgetItem(display)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Style formulas subtly
                if cell["is_formula"]:
                    item.setForeground(Qt.GlobalColor.darkBlue)
                    item.setToolTip(f"Formula: {cell['formula_value']}")
                else:
                    item.setToolTip(f"Raw Value: {cell['raw_value']}")

                self.grid_table.setItem(r_idx, c_idx, item)

            self.grid_table.blockSignals(False)
            self.grid_table.resizeColumnsToContents()

        except Exception as exc:
            QMessageBox.critical(self, "Grid Load Error", f"Failed to load grid data: {exc}")

    def search_cells(self) -> None:
        sheet_name = self.sheet_combo.currentText()
        sheet_id = self.sheets_map.get(sheet_name)
        if sheet_id is None:
            return

        query = self.search_input.text().strip()
        if not query:
            return

        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT row_number, column_number, cell_address, display_value, raw_value, formula_value, is_formula, data_type
                        FROM excel_raw_cells
                        WHERE sheet_id = :sheet_id
                          AND (display_value ILIKE :q OR raw_value ILIKE :q OR cell_address ILIKE :q)
                        ORDER BY row_number ASC, column_number ASC
                        LIMIT 500;
                        """
                    ),
                    {"sheet_id": sheet_id, "q": f"%{query}%"}
                ).mappings().all()

            self.search_results_table.setRowCount(0)
            for idx, r in enumerate(rows):
                self.search_results_table.insertRow(idx)

                items = [
                    str(r["row_number"]),
                    str(r["column_number"]),
                    r["cell_address"],
                    r["display_value"] or "",
                    r["raw_value"] or "",
                    r["formula_value"] or "",
                    "FORMULA" if r["is_formula"] else (r["data_type"] or "TEXT")
                ]

                for col_idx, val in enumerate(items):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col_idx in (0, 1, 2, 6):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.search_results_table.setItem(idx, col_idx, item)

            self.search_results_table.resizeRowsToContents()

        except Exception as exc:
            QMessageBox.critical(self, "Search Error", f"Search query failed: {exc}")
