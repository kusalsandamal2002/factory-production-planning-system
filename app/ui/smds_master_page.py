from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
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
from app.services.smds_excel_importer import import_smds_workbook
from app.services.smds_schema import ensure_smds_table


class SMDSRepository:
    DISPLAY_COLUMNS: list[tuple[str, str, int]] = [
        ("sap_code", "SAP CODE", 120),
        ("material_description", "Material Description", 340),
        ("line", "Line", 90),
        ("heel", "HEEL", 80),
        ("soft", "SOFT", 80),
        ("tred", "Tred", 90),
        ("remark", "Remark", 120),
        ("weight_per_tyre_kg", "Weight/Tyre Kg", 130),
        ("line_400", "Line-400", 90),
        ("line_800", "Line-800", 90),
        ("press_line", "Press -LINE", 105),
        ("nancy_press", "NANCY PRESS", 115),
        ("press_400_t", "400 T PRESS", 115),
        ("t_600_01_press", "T 600 -01 PRESS", 130),
        ("t_600_02_press", "T 600 -02 PRESS", 130),
        ("l_press_1250", "L-PRESS-1250", 125),
        ("l_press_1500", "L-PRESS-1500", 125),
        ("l_press_1800", "L-PRESS-1800", 125),
        ("oring_press", "ORING-PRESS", 115),
        ("new_press", "NEW PRESS", 105),
        ("key_code", "Key Code", 150),
        ("casing_type", "Casing Type", 115),
        ("curing_cycle", "Curing Cycle", 110),
        ("handling_time", "Handling time", 115),
        ("day_plan", "Day plan", 95),
        ("night_plan", "Night plan", 95),
        ("total_plan", "Total Plan", 95),
    ]

    def ensure_table(self) -> None:
        ensure_smds_table()

    def count_rows(self, search_text: str = "") -> int:
        self.ensure_table()
        query = "SELECT COUNT(*) FROM smds WHERE 1 = 1"
        params: dict[str, object] = {}

        if search_text:
            query += self._search_clause()
            params["search"] = f"%{search_text}%"

        with engine.connect() as conn:
            return int(conn.execute(text(query), params).scalar() or 0)

    def list_rows(self, search_text: str = "", limit: int = 800) -> list[dict]:
        self.ensure_table()
        column_sql = ", ".join(column for column, _title, _width in self.DISPLAY_COLUMNS)
        query = f"""
            SELECT {column_sql}
            FROM smds
            WHERE 1 = 1
        """
        params: dict[str, object] = {"limit": limit}

        if search_text:
            query += self._search_clause()
            params["search"] = f"%{search_text}%"

        query += " ORDER BY sap_code LIMIT :limit"

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(query), params).mappings().all()]

    def _search_clause(self) -> str:
        return """
            AND (
                LOWER(sap_code) LIKE LOWER(:search)
                OR LOWER(material_description) LIKE LOWER(:search)
                OR LOWER(COALESCE(key_code, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(casing_type, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(curing_cycle, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(line, '')) LIKE LOWER(:search)
            )
        """


class SMDSMasterPage(QWidget):
    def __init__(self, on_back=None):
        super().__init__()
        self.repo = SMDSRepository()
        self.on_back = on_back
        self.rows: list[dict] = []
        self.limit = 800

        self.setStyleSheet("""
            QFrame#PageCard, QFrame#DataSection {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
            }

            QLabel#Breadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 950;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle, QLabel#SectionSubtitle {
                color: #64748b;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 16pt;
                font-weight: 950;
            }

            QLabel#CountBadge {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 11px;
                padding: 6px 12px;
                font-size: 8.5pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                color: #0f172a;
                font-size: 9pt;
                font-weight: 650;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 8.6pt;
                font-weight: 700;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 7px;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px;
                font-size: 8.2pt;
                font-weight: 950;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 22)
        card_layout.setSpacing(18)

        card_layout.addLayout(self._build_header())
        card_layout.addWidget(self._build_table_section(), 1)

        root.addWidget(card, 1)
        self.refresh()

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Master Data  /  Tyre Item Master  /  SMDS Master")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("SMDS Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Central SAP, key code, casing, curing cycle and day/night planning table imported from SMDS6.xlsx."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        import_button = QPushButton("Import SMDS Excel")
        import_button.setObjectName("PrimaryButton")
        import_button.clicked.connect(self._import_excel)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._go_back)

        layout.addLayout(text_area, 1)
        layout.addWidget(import_button)
        layout.addWidget(back_button)
        return layout

    def _build_table_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SMDS Central Data Table")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Search by SAP code, description, key code, casing type, curing cycle or line. Table shows first 800 matching rows.")
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.count_badge = QLabel("0 Rows")
        self.count_badge.setObjectName("CountBadge")
        self.count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP, description, key code, casing, curing, line...")
        self.search_input.setMinimumWidth(420)
        self.search_input.textChanged.connect(self.refresh)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        top.addLayout(title_area, 1)
        top.addWidget(self.count_badge)
        top.addWidget(self.search_input)
        top.addWidget(refresh_button)

        self.table = QTableWidget(0, len(self.repo.DISPLAY_COLUMNS))
        self.table.setHorizontalHeaderLabels([title for _column, title, _width in self.repo.DISPLAY_COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for index, (_column, _title, width) in enumerate(self.repo.DISPLAY_COLUMNS):
            self.table.setColumnWidth(index, width)

        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        return section

    def _go_back(self) -> None:
        if callable(self.on_back):
            self.on_back()

    def refresh(self) -> None:
        try:
            search_text = self.search_input.text().strip() if hasattr(self, "search_input") else ""
            total_rows = self.repo.count_rows(search_text)
            self.rows = self.repo.list_rows(search_text, limit=self.limit)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load SMDS data.\n\n{exc}")
            self.rows = []
            total_rows = 0

        suffix = "" if total_rows <= self.limit else f" / showing {self.limit}"
        self.count_badge.setText(f"{total_rows} Rows{suffix}")
        self._fill_table()

    refresh_page = refresh
    load_data = refresh

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.rows))

        for row_index, row in enumerate(self.rows):
            self.table.setRowHeight(row_index, 48)

            for col_index, (column_name, _title, _width) in enumerate(self.repo.DISPLAY_COLUMNS):
                item = QTableWidgetItem(self._display_value(row.get(column_name)))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, col_index, item)

    def _display_value(self, value) -> str:
        if value is None:
            return "-"

        if isinstance(value, Decimal):
            if value == 0:
                return "-"

            if value == value.to_integral_value():
                return str(int(value))

            return format(value.normalize(), "f")

        text_value = str(value).strip()
        return text_value if text_value else "-"

    def _import_excel(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select SMDS Excel File",
            "",
            "Excel Files (*.xlsx *.xlsm);;All Files (*)",
        )

        if not file_path:
            return

        confirm = QMessageBox.question(
            self,
            "Import SMDS Excel",
            "This will replace existing SMDS rows with the selected workbook data. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            result = import_smds_workbook(file_path=file_path, sheet_name="ALL", replace=True)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not import SMDS Excel.\n\n{exc}")
            return

        QMessageBox.information(
            self,
            "Import Completed",
            f"SMDS import completed.\n\nImported rows: {result.imported_rows}\nSkipped rows: {result.skipped_rows}",
        )
        self.refresh()
