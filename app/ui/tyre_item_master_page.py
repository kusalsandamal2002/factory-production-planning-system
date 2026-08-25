
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine
from app.ui.smds_mold_casing_page import SmdsMoldCasingPage
from app.ui.smds_master_page import SMDSMasterPage



def guess_tyre_size(description: str) -> str:
    desc = re.sub(r"\s+", " ", str(description or "").strip())

    if not desc:
        return ""

    parts = desc.split()

    if not parts:
        return ""

    if len(parts) >= 2 and re.match(r"^\d+(\.\d+)?X\d+(\.\d+)?$", parts[0], re.I) and re.match(r"^\d+/\d+-\d+", parts[1]):
        return f"{parts[0]} {parts[1]}"

    if len(parts) >= 2 and re.match(r".*-\d+$", parts[0]) and re.fullmatch(r"\d+/\d+", parts[1]):
        return f"{parts[0]} {parts[1]}"

    return parts[0]




class TyreItemRepository:
    def ensure_table(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tyre_item_master (
                    id BIGSERIAL PRIMARY KEY,
                    sap_code VARCHAR(128) NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS tyre_size VARCHAR(128) NOT NULL DEFAULT ''
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS normal_curing_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS short_cycle_curing_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS handling_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'Active'
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS remarks TEXT NOT NULL DEFAULT ''
            """))

    def list_items(self, search_text: str = "") -> list[dict]:
        self.ensure_table()

        query = """
            SELECT id, sap_code, description, tyre_size, normal_curing_minutes, short_cycle_curing_minutes, handling_minutes, status
            FROM tyre_item_master
            WHERE 1 = 1
        """
        params: dict[str, object] = {}

        if search_text:
            query += """
                AND (
                    LOWER(sap_code) LIKE LOWER(:search)
                    OR LOWER(description) LIKE LOWER(:search)
                )
            """
            params["search"] = f"%{search_text}%"

        query += " ORDER BY sap_code"

        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()

        return [dict(row) for row in rows]

    def create_item(self, sap_code: str, description: str) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO tyre_item_master (sap_code, description, tyre_size, status)
                    VALUES (:sap_code, :description, :tyre_size, 'Active')
                """),
                {
                    "sap_code": sap_code,
                    "description": description,
                    "tyre_size": guess_tyre_size(description),
                },
            )

    def update_item(self, item_id: int, sap_code: str, description: str) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tyre_item_master
                    SET sap_code = :sap_code,
                        description = :description,
                        tyre_size = :tyre_size,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": item_id,
                    "sap_code": sap_code,
                    "description": description,
                    "tyre_size": guess_tyre_size(description),
                },
            )

    def delete_item(self, item_id: int) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM tyre_item_master WHERE id = :id"),
                {"id": item_id},
            )


# Central SMDS table is now the Tyre Item Master source.
from app.services.smds_tyre_repository import TyreItemRepository, guess_tyre_size

class TyreItemDialog(QDialog):
    def __init__(self, parent=None, row: dict | None = None):
        super().__init__(parent)
        self.row = row or {}
        self.is_edit = row is not None

        self.setWindowTitle("Edit Tyre Item" if self.is_edit else "Add Tyre Item")
        self.setMinimumWidth(620)

        self.setStyleSheet("""
            QDialog {
                background: #f8fafc;
            }

            QLabel {
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 850;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 10px 12px;
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(16)

        title = QLabel("Edit Tyre Item" if self.is_edit else "Add Tyre Item")
        title.setStyleSheet("color: #0f172a; font-size: 17pt; font-weight: 950;")
        root.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(14)

        self.sap_code_input = QLineEdit()
        self.sap_code_input.setPlaceholderText("SAP code")
        self.sap_code_input.setText(str(self.row.get("sap_code", "")))

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Tyre description")
        self.description_input.setText(str(self.row.get("description", "")))

        form.addWidget(QLabel("SAP Code"), 0, 0)
        form.addWidget(self.sap_code_input, 0, 1)
        form.addWidget(QLabel("Description"), 1, 0)
        form.addWidget(self.description_input, 1, 1)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.sap_code_input.text().strip():
            QMessageBox.warning(self, "Missing SAP Code", "Please enter SAP Code.")
            return

        if not self.description_input.text().strip():
            QMessageBox.warning(self, "Missing Description", "Please enter description.")
            return

        self.accept()

    def data(self) -> dict:
        return {
            "sap_code": self.sap_code_input.text().strip(),
            "description": self.description_input.text().strip(),
        }


class TyreItemMasterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.repo = TyreItemRepository()
        self.items: list[dict] = []

        self.setStyleSheet("""
            QFrame#PageCard, QFrame#DataSection, QFrame#ModuleCard {
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

            QLabel#PageSubtitle {
                color: #64748b;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 16pt;
                font-weight: 950;
            }

            QLabel#SectionSubtitle {
                color: #64748b;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#ModuleTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#ModuleText {
                color: #64748b;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#ModuleBadge {
                background: #eef2ff;
                color: #4338ca;
                border: 1px solid #c7d2fe;
                border-radius: 9px;
                padding: 5px 11px;
                font-size: 8pt;
                font-weight: 950;
            }

            QLabel#ComingBadge {
                background: #fff7ed;
                color: #c2410c;
                border: 1px solid #fed7aa;
                border-radius: 9px;
                padding: 5px 11px;
                font-size: 8pt;
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

            QPushButton#DisabledButton {
                background: #f1f5f9;
                color: #94a3b8;
                border: 1px solid #e2e8f0;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#ManageButton {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 8.2pt;
                font-weight: 950;
                min-width: 86px;
            }

            QPushButton#ManageButton:hover {
                background: #dbeafe;
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
                font-size: 9pt;
                font-weight: 700;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 9px;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 12px;
                font-size: 8.5pt;
                font-weight: 950;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview_page())
        self.stack.addWidget(self._build_item_data_page())
        self.stack.addWidget(self._build_tyre_size_page())
        self.stack.addWidget(self._build_curing_time_page())
        self.stack.addWidget(self._build_tyre_group_key_page())
        self.mold_casing_rules_page = self._build_mold_casing_rules_page()
        self.stack.addWidget(self.mold_casing_rules_page)
        self.stack.addWidget(self._build_line_process_mapping_page())
        # V19 performance: heavy SMDS child workspaces are lazy.
        # Do not construct/query them while the overview is opening.
        self.smds_master_page = None
        self._smds_master_placeholder = QWidget()
        self._smds_master_placeholder.setProperty(
            "page_key",
            "lazy_smds_master",
        )
        self.stack.addWidget(self._smds_master_placeholder)

        self.smds_mold_casing_page = None
        self._smds_mold_casing_placeholder = QWidget()
        self._smds_mold_casing_placeholder.setProperty(
            "page_key",
            "lazy_smds_mold_casing",
        )
        self.stack.addWidget(self._smds_mold_casing_placeholder)

        root.addWidget(self.stack, 1)

        self.refresh()

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(22)

        layout.addLayout(self._overview_header())
        layout.addWidget(self._module_grid(), 1)

        root.addWidget(card, 1)
        return page

    def _overview_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Tyre Item Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Maintain tyre item master data used for shipment item validation and production planning rules."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        add_button = QPushButton("+ Add Tyre Item")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_item)

        layout.addLayout(text_area, 1)
        layout.addWidget(add_button)

        return layout

    def _module_grid(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        root = QVBoxLayout(section)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(16)

        title = QLabel("Tyre Item Master Modules")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Open each card to maintain item-level planning data step by step.")
        subtitle.setObjectName("SectionSubtitle")

        title_area = QVBoxLayout()
        title_area.setSpacing(5)
        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        cards = [
            (
                "SMDS",
                "SMDS Master",
                "Central SAP, key code, casing, curing and day/night planning table from SMDS6.xlsx.",
                self._open_smds_master,
                True,
            ),
            (
                "ITEM DATA",
                "Tyre Item Data",
                "Maintain SAP code and tyre description table.",
                self._open_item_data,
                True,
            ),
            (
                "TYRE SIZE",
                "Tyre Size Data",
                "Maintain SAP code, description and extracted tyre size.",
                self._open_tyre_size,
                True,
            ),
            (
                "CURING TIME",
                "Production / Curing Time",
                "Maintain normal curing time, short cycle placeholder and handling time.",
                self._open_curing_time,
                True,
            ),
            (
                "GROUP KEY",
                "Tyre Group Key Mapping",
                "Group same tyres under one process key and attach multiple SAP codes.",
                self._open_tyre_group_key,
                True,
            ),
            (
                "LINE RULES",
                "Line Mapping",
                "Maintain SAP-code wise production line mapping from SMDS.",
                self._open_line_process_mapping,
                True,
            ),
            (
                "MOLD / CASING",
                "Mold & Casing Rules",
                "Maintain mold key code and casing type from SMDS.",
                self._open_mold_casing_rules,
                True,
            ),
            (
                "PRODUCT GROUP",
                "Weight & Product Group",
                "Maintain item weight, color, layer and product family.",
                self._open_mold_casing_rules, True,
            ),
            (
                "IMPORT",
                "Excel Import",
                "Import SAP code and description from approved master files.",
                None,
                False,
            ),
        ]

        for index, item in enumerate(cards):
            row = index // 3
            col = index % 3
            grid.addWidget(self._module_card(*item), row, col)
            grid.setColumnStretch(col, 1)

        root.addLayout(title_area)
        root.addLayout(grid)
        root.addStretch()

        return section

    def _module_card(
        self,
        badge_text: str,
        title_text: str,
        description: str,
        action,
        enabled: bool,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("ModuleCard")
        card.setMinimumHeight(210)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        badge = QLabel(badge_text)
        badge.setObjectName("ModuleBadge" if enabled else "ComingBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(30)

        badge_row = QHBoxLayout()
        badge_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        badge_row.addStretch()

        title = QLabel(title_text)
        title.setObjectName("ModuleTitle")
        title.setWordWrap(True)

        desc = QLabel(description)
        desc.setObjectName("ModuleText")
        desc.setWordWrap(True)

        button = QPushButton("Open Module" if enabled else "Coming Soon")
        button.setObjectName("PrimaryButton" if enabled else "DisabledButton")
        button.setEnabled(enabled)

        if enabled and action is not None:
            button.clicked.connect(action)

        layout.addLayout(badge_row)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addWidget(button)

        return card

    def _build_item_data_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._item_data_header())
        layout.addWidget(self._item_data_section(), 1)

        root.addWidget(card, 1)
        return page

    def _item_data_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master  /  Item Data")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Tyre Item Data")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Maintain basic tyre item SAP code and description records.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        add_button = QPushButton("+ Add Tyre Item")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_item)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(add_button)
        layout.addWidget(back_button)

        return layout

    def _item_data_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SAP Code / Description")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Basic item master table for shipment item validation.")
        subtitle.setObjectName("SectionSubtitle")

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.count_badge = QLabel("0 Items")
        self.count_badge.setObjectName("CountBadge")
        self.count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP code or description...")
        self.search_input.textChanged.connect(self.refresh)
        self.search_input.setMinimumWidth(360)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        top.addLayout(title_area, 1)
        top.addWidget(self.count_badge)
        top.addWidget(self.search_input)
        top.addWidget(refresh_button)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["SAP Code", "Description", "Action"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(2, 140)

        layout.addLayout(top)
        layout.addWidget(self.table, 1)

        return section

    def _build_tyre_size_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._tyre_size_header())
        layout.addWidget(self._tyre_size_section(), 1)

        root.addWidget(card, 1)
        return page

    def _tyre_size_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master  /  Tyre Size")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Tyre Size Data")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Maintain SAP code, tyre description and tyre size extracted from item descriptions.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        add_button = QPushButton("+ Add Tyre Item")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_item)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(add_button)
        layout.addWidget(back_button)

        return layout

    def _tyre_size_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SAP Code / Description / Tyre Size")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Tyre size is derived from the tyre description and stored in the database.")
        subtitle.setObjectName("SectionSubtitle")

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.tyre_size_count_badge = QLabel("0 Items")
        self.tyre_size_count_badge.setObjectName("CountBadge")
        self.tyre_size_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.tyre_size_search_input = QLineEdit()
        self.tyre_size_search_input.setPlaceholderText("Search SAP code, description or tyre size...")
        self.tyre_size_search_input.textChanged.connect(self.refresh)
        self.tyre_size_search_input.setMinimumWidth(360)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        top.addLayout(title_area, 1)
        top.addWidget(self.tyre_size_count_badge)
        top.addWidget(self.tyre_size_search_input)
        top.addWidget(refresh_button)

        self.tyre_size_table = QTableWidget(0, 4)
        self.tyre_size_table.setHorizontalHeaderLabels(["SAP Code", "Description", "Tyre Size", "Action"])
        self.tyre_size_table.verticalHeader().setVisible(False)
        self.tyre_size_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tyre_size_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.tyre_size_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        self.tyre_size_table.setColumnWidth(0, 170)
        self.tyre_size_table.setColumnWidth(2, 180)
        self.tyre_size_table.setColumnWidth(3, 140)

        layout.addLayout(top)
        layout.addWidget(self.tyre_size_table, 1)

        return section

    def _open_tyre_size(self) -> None:
        self.stack.setCurrentIndex(2)
        self.refresh()

    def _refresh_tyre_size_table(self) -> None:
        self.tyre_size_count_badge.setText(f"{len(self.items)} Items")
        self.tyre_size_table.setRowCount(len(self.items))

        for row_index, row in enumerate(self.items):
            self.tyre_size_table.setRowHeight(row_index, 56)

            sap_item = QTableWidgetItem(str(row.get("sap_code", "")))
            sap_item.setFlags(sap_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tyre_size_table.setItem(row_index, 0, sap_item)

            desc_item = QTableWidgetItem(str(row.get("description", "")))
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tyre_size_table.setItem(row_index, 1, desc_item)

            size_item = QTableWidgetItem(str(row.get("tyre_size", "")))
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tyre_size_table.setItem(row_index, 2, size_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._manage_item(item_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()

            self.tyre_size_table.setCellWidget(row_index, 3, action_widget)

    def _build_curing_time_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._curing_time_header())
        layout.addWidget(self._curing_time_section(), 1)

        root.addWidget(card, 1)
        return page

    def _curing_time_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master  /  Production Curing Time")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Production / Curing Time")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Maintain normal curing time and handling time imported from Tire production time with curing cycle.xlsx.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(back_button)

        return layout

    def _curing_time_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SAP Code / Description / Curing Time")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Values are loaded from source files. Missing values are shown as '-'. Short Cycle data will be imported later.")
        subtitle.setObjectName("SectionSubtitle")

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.curing_count_badge = QLabel("0 Items")
        self.curing_count_badge.setObjectName("CountBadge")
        self.curing_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.curing_search_input = QLineEdit()
        self.curing_search_input.setPlaceholderText("Search SAP code or description...")
        self.curing_search_input.textChanged.connect(self.refresh)
        self.curing_search_input.setMinimumWidth(360)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        top.addLayout(title_area, 1)
        top.addWidget(self.curing_count_badge)
        top.addWidget(self.curing_search_input)
        top.addWidget(refresh_button)

        self.curing_table = QTableWidget(0, 6)
        self.curing_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Normal Curing Min",
            "Short Cycle Curing Min",
            "Handling Min",
            "Action",
        ])
        self.curing_table.verticalHeader().setVisible(False)
        self.curing_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.curing_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.curing_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.curing_table.setColumnWidth(0, 160)
        self.curing_table.setColumnWidth(2, 155)
        self.curing_table.setColumnWidth(3, 175)
        self.curing_table.setColumnWidth(4, 125)
        self.curing_table.setColumnWidth(5, 130)

        layout.addLayout(top)
        layout.addWidget(self.curing_table, 1)

        return section

    def _open_curing_time(self) -> None:
        self.stack.setCurrentIndex(3)
        self.refresh()

    def _refresh_curing_table(self) -> None:
        self.curing_count_badge.setText(f"{len(self.items)} Items")
        self.curing_table.setRowCount(len(self.items))

        for row_index, row in enumerate(self.items):
            self.curing_table.setRowHeight(row_index, 56)

            values = [
                row.get("sap_code", ""),
                row.get("description", ""),
                self._number_text(row.get("normal_curing_minutes", 0)),
                self._number_text(row.get("short_cycle_curing_minutes", 0)),
                self._number_text(row.get("handling_minutes", 0)),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.curing_table.setItem(row_index, col, item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._manage_item(item_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()

            self.curing_table.setCellWidget(row_index, 5, action_widget)

    def _number_text(self, value) -> str:
        try:
            number = float(value or 0)

            if number <= 0:
                return "-"

            if number.is_integer():
                return str(int(number))

            return str(number).rstrip("0").rstrip(".")
        except Exception:
            return "-"


    def _build_tyre_group_key_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._tyre_group_key_header())
        layout.addWidget(self._tyre_group_key_section(), 1)

        root.addWidget(card, 1)
        return page

    def _tyre_group_key_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master  /  Tyre Group Key Mapping")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Tyre Group Key Mapping")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Same-size and same-process tyres are grouped under one process key. Multiple SAP codes can use one production rule set.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(back_button)

        return layout

    def _tyre_group_key_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("Tyre Process Groups")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Group Key = Tyre Size | Rim/Width | Aperture | Tread | Layer | Color.")
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.group_key_count_badge = QLabel("0 Groups")
        self.group_key_count_badge.setObjectName("CountBadge")
        self.group_key_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.group_key_search_input = QLineEdit()
        self.group_key_search_input.setPlaceholderText("Search group key, size, rim, aperture, tread, layer, color...")
        self.group_key_search_input.setMinimumWidth(390)
        self.group_key_search_input.textChanged.connect(self._refresh_tyre_group_key_table)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self._refresh_tyre_group_key_table)

        top.addLayout(title_area, 1)
        top.addWidget(self.group_key_count_badge)
        top.addWidget(self.group_key_search_input)
        top.addWidget(refresh_button)

        self.group_key_table = QTableWidget(0, 9)
        self.group_key_table.setHorizontalHeaderLabels([
            "Group Key",
            "Tyre Size",
            "Rim/Width",
            "Aperture",
            "Tread",
            "Layer",
            "Color",
            "SAP Count",
            "Action",
        ])
        self.group_key_table.verticalHeader().setVisible(False)
        self.group_key_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_key_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.group_key_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for col in range(1, 9):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        self.group_key_table.setColumnWidth(1, 120)
        self.group_key_table.setColumnWidth(2, 95)
        self.group_key_table.setColumnWidth(3, 105)
        self.group_key_table.setColumnWidth(4, 90)
        self.group_key_table.setColumnWidth(5, 90)
        self.group_key_table.setColumnWidth(6, 95)
        self.group_key_table.setColumnWidth(7, 95)
        self.group_key_table.setColumnWidth(8, 125)

        layout.addLayout(top)
        layout.addWidget(self.group_key_table, 1)

        return section

    def _open_tyre_group_key(self) -> None:
        self.stack.setCurrentIndex(4)
        self._refresh_tyre_group_key_table()

    def _list_tyre_group_keys(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                g.id,
                g.group_key,
                g.tyre_size,
                COALESCE(g.rim_width, '') AS rim_width,
                COALESCE(g.aperture_type, '') AS aperture_type,
                g.pattern AS tread_pattern,
                g.layer,
                g.color,
                COUNT(i.sap_code) AS sap_count
            FROM tyre_process_groups g
            LEFT JOIN tyre_process_group_items i ON i.group_id = g.id
        """

        params = {}

        if search:
            sql += """
                WHERE LOWER(g.group_key) LIKE :search
                   OR LOWER(g.tyre_size) LIKE :search
                   OR LOWER(COALESCE(g.rim_width, '')) LIKE :search
                   OR LOWER(COALESCE(g.aperture_type, '')) LIKE :search
                   OR LOWER(g.pattern) LIKE :search
                   OR LOWER(g.layer) LIKE :search
                   OR LOWER(g.color) LIKE :search
            """
            params["search"] = f"%{search}%"

        sql += """
            GROUP BY
                g.id,
                g.group_key,
                g.tyre_size,
                g.rim_width,
                g.aperture_type,
                g.pattern,
                g.layer,
                g.color
            ORDER BY COUNT(i.sap_code) DESC, g.group_key
        """

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def _refresh_tyre_group_key_table(self) -> None:
        try:
            search_text = ""
            if hasattr(self, "group_key_search_input"):
                search_text = self.group_key_search_input.text().strip()

            rows = self._list_tyre_group_keys(search_text)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load tyre group keys. " + str(exc))
            rows = []

        self.group_key_count_badge.setText(f"{len(rows)} Groups")
        self.group_key_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.group_key_table.setRowHeight(row_index, 56)

            values = [
                row.get("group_key", ""),
                self._group_key_display_value(row.get("tyre_size", "")),
                self._group_key_display_value(row.get("rim_width", "")),
                self._group_key_display_value(row.get("aperture_type", "")),
                self._group_key_display_value(row.get("tread_pattern", "")),
                self._group_key_display_value(row.get("layer", "")),
                self._group_key_display_value(row.get("color", "")),
                row.get("sap_count", 0),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.group_key_table.setItem(row_index, col, item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            view_button = QPushButton("View SAP")
            view_button.setObjectName("ManageButton")
            view_button.clicked.connect(lambda checked=False, group_id=row["id"]: self._show_group_sap_codes(group_id))

            action_layout.addStretch()
            action_layout.addWidget(view_button)
            action_layout.addStretch()

            self.group_key_table.setCellWidget(row_index, 8, action_widget)

    def _group_key_display_value(self, value) -> str:
        text_value = str(value or "").strip()

        if text_value in {
            "",
            "UNKNOWN",
            "NO_RIM",
            "NO_TREAD",
            "NO_LAYER",
            "NO_COLOR",
            "NO_SIZE",
        }:
            return "-"

        return text_value

    def _show_group_sap_codes(self, group_id: int) -> None:
        try:
            with engine.connect() as conn:
                group = conn.execute(
                    text("""
                        SELECT group_key
                        FROM tyre_process_groups
                        WHERE id = :group_id
                    """),
                    {"group_id": group_id},
                ).mappings().first()

                rows = conn.execute(
                    text("""
                        SELECT sap_code, description
                        FROM tyre_process_group_items
                        WHERE group_id = :group_id
                        ORDER BY sap_code
                        LIMIT 120
                    """),
                    {"group_id": group_id},
                ).mappings().all()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load SAP codes.\n\n{exc}")
            return

        group_key = group["group_key"] if group else ""

        lines = []
        for row in rows:
            lines.append(f'{row["sap_code"]}  -  {row["description"]}')

        if not lines:
            lines.append("No SAP codes linked.")

        message = "\n".join(lines)

        if len(rows) >= 120:
            message += "\n\nShowing first 120 SAP codes only."

        QMessageBox.information(
            self,
            "SAP Codes in Group",
            f"Group Key:\n{group_key}\n\nSAP Codes:\n{message}",
        )

    def _group_number_text(self, value) -> str:
        try:
            number = float(value or 0)
            if number.is_integer():
                return str(int(number))
            return str(number).rstrip("0").rstrip(".")
        except Exception:
            return ""

    def _open_smds_master(self) -> None:
        self.stack.setCurrentIndex(5)
        if hasattr(self, "smds_master_page"):
            self.smds_master_page.refresh()


    def _build_line_process_mapping_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page_key", "line_process_mapping")

        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._line_process_mapping_header())
        layout.addWidget(self._line_process_mapping_section(), 1)

        root.addWidget(card, 1)
        return page

    def _line_process_mapping_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master  /  Line & Process Mapping")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Line Mapping")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Production line and process rules are read directly from the central SMDS table.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(back_button)

        return layout

    def _line_process_mapping_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SAP Code / Production Line / Process Rule")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Line, key code, casing, curing and daily capacity are mapped from SMDS. Search by SAP, description, line, key code or casing type.")
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.line_process_count_badge = QLabel("0 Items")
        self.line_process_count_badge.setObjectName("CountBadge")
        self.line_process_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.line_process_search_input = QLineEdit()
        self.line_process_search_input.setPlaceholderText("Search SAP, description, line, key code or casing...")
        self.line_process_search_input.setMinimumWidth(420)
        self.line_process_search_input.textChanged.connect(self._refresh_line_process_mapping_table)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self._refresh_line_process_mapping_table)

        top.addLayout(title_area, 1)
        top.addWidget(self.line_process_count_badge)
        top.addWidget(self.line_process_search_input)
        top.addWidget(refresh_button)

        self.line_process_table = QTableWidget(0, 10)
        self.line_process_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Mapped Line",
            "Line Options",
            "Process Type",
            "Key Code",
            "Casing Type",
            "Curing Time",
            "Daily Plan",
            "Action",
        ])
        self.line_process_table.verticalHeader().setVisible(False)
        self.line_process_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.line_process_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.line_process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)

        self.line_process_table.setColumnWidth(0, 135)
        self.line_process_table.setColumnWidth(2, 135)
        self.line_process_table.setColumnWidth(3, 185)
        self.line_process_table.setColumnWidth(4, 130)
        self.line_process_table.setColumnWidth(5, 120)
        self.line_process_table.setColumnWidth(6, 130)
        self.line_process_table.setColumnWidth(7, 120)
        self.line_process_table.setColumnWidth(8, 105)
        self.line_process_table.setColumnWidth(9, 110)

        layout.addLayout(top)
        layout.addWidget(self.line_process_table, 1)

        return section

    def _open_line_process_mapping(self) -> None:
        for index in range(self.stack.count()):
            widget = self.stack.widget(index)
            if widget is not None and widget.property("page_key") == "line_process_mapping":
                self.stack.setCurrentIndex(index)
                self._refresh_line_process_mapping_table()
                return

        QMessageBox.warning(self, "Module Error", "Line & Process Mapping page is not connected.")

    def _smds_existing_columns(self) -> list[str]:
        with engine.connect() as conn:
            return [
                row[0]
                for row in conn.execute(
                    text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'smds'
                        ORDER BY ordinal_position
                    """)
                ).all()
            ]

    def _line_process_pick_column(self, columns: list[str], *names: str) -> str | None:
        column_set = set(columns)
        for name in names:
            if name in column_set:
                return name
        return None

    def _line_process_display_value(self, value) -> str:
        text_value = str(value or "").strip()
        if not text_value or text_value.upper() in {"-", "NONE", "NULL", "N/A", "NA", "0"}:
            return "-"
        return text_value

    def _line_process_number_display(self, value) -> str:
        try:
            number = float(value or 0)
            if number <= 0:
                return "-"
            if number.is_integer():
                return str(int(number))
            return str(number).rstrip("0").rstrip(".")
        except Exception:
            return self._line_process_display_value(value)

    def _line_process_process_type(self, mapped_line: str, line_options: str, key_code: str) -> str:
        combined = f"{mapped_line} {line_options} {key_code}".lower()
        if "press" in combined:
            return "Press"
        if "line" in combined:
            return "Line Production"
        if key_code and key_code != "-":
            return "Grouped Process"
        return "-"

    def _line_process_format_curing(self, row: dict) -> str:
        text_value = self._line_process_display_value(row.get("normal_curing_time_text"))
        if text_value != "-":
            return text_value

        minutes = row.get("normal_curing_minutes")
        try:
            number = int(float(minutes or 0))
        except Exception:
            number = 0

        if number <= 0:
            return self._line_process_display_value(row.get("curing_cycle"))

        hours = number // 60
        mins = number % 60
        if hours and mins:
            return f"{hours}h {mins}m ({number} min)"
        if hours:
            return f"{hours}h ({number} min)"
        return f"{number} min"

    def _line_process_line_options(self, row: dict, line_flag_columns: list[str]) -> str:
        options: list[str] = []

        mapped_line = self._line_process_display_value(row.get("production_line"))
        if mapped_line != "-":
            options.append(mapped_line)

        for column_name in line_flag_columns:
            value = self._line_process_display_value(row.get(column_name))
            if value == "-":
                continue

            label = column_name
            if label.startswith("line_"):
                label = "Line-" + label.replace("line_", "", 1).replace("_", "-")
            elif label == "press_line":
                label = "Press-LINE"
            else:
                label = label.replace("_", " ").title()

            if value.lower() in {"ok", "yes", "y", "true", "1"}:
                options.append(label)
            else:
                options.append(f"{label}: {value}")

        clean_options = []
        seen = set()
        for option in options:
            key = option.lower()
            if key not in seen:
                clean_options.append(option)
                seen.add(key)

        return ", ".join(clean_options) if clean_options else "-"

    def _list_line_process_rows(self, search_text: str = "") -> tuple[list[dict], list[str]]:
        columns = self._smds_existing_columns()
        if not columns:
            return [], []

        sap_col = self._line_process_pick_column(columns, "sap_code", "sap", "sap_no")
        desc_col = self._line_process_pick_column(columns, "material_description", "description")
        line_col = self._line_process_pick_column(columns, "line", "production_line")
        key_col = self._line_process_pick_column(columns, "key_code")
        casing_col = self._line_process_pick_column(columns, "casing_type")
        curing_col = self._line_process_pick_column(columns, "curing_cycle")
        curing_min_col = self._line_process_pick_column(columns, "normal_curing_minutes")
        curing_text_col = self._line_process_pick_column(columns, "normal_curing_time_text")
        handling_col = self._line_process_pick_column(columns, "handling_minutes", "handling_time")
        day_col = self._line_process_pick_column(columns, "day_plan")
        night_col = self._line_process_pick_column(columns, "night_plan")
        total_col = self._line_process_pick_column(columns, "total_plan")

        line_flag_columns = [
            column for column in columns
            if column.startswith("line_") or column == "press_line"
        ]

        def select_expr(column_name: str | None, alias: str, default: str = "''") -> str:
            if column_name is None:
                return f"{default} AS {alias}"
            return f"{column_name} AS {alias}"

        selected = [
            select_expr(self._line_process_pick_column(columns, "id"), "id", "ROW_NUMBER() OVER ()"),
            select_expr(sap_col, "sap_code"),
            select_expr(desc_col, "description"),
            select_expr(line_col, "production_line"),
            select_expr(key_col, "key_code"),
            select_expr(casing_col, "casing_type"),
            select_expr(curing_col, "curing_cycle"),
            select_expr(curing_min_col, "normal_curing_minutes", "0"),
            select_expr(curing_text_col, "normal_curing_time_text"),
            select_expr(handling_col, "handling_minutes", "0"),
            select_expr(day_col, "day_plan", "0"),
            select_expr(night_col, "night_plan", "0"),
            select_expr(total_col, "total_plan", "0"),
        ]

        for column_name in line_flag_columns:
            selected.append(f"{column_name} AS {column_name}")

        where_parts = []
        params = {}
        search = (search_text or "").strip()
        if search:
            searchable_columns = [sap_col, desc_col, line_col, key_col, casing_col, curing_col]
            searchable_columns.extend(line_flag_columns)
            for column_name in searchable_columns:
                if column_name:
                    where_parts.append(f"CAST({column_name} AS TEXT) ILIKE :search")
            params["search"] = f"%{search}%"

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " OR ".join(where_parts)

        order_sql = "sap_code"
        query = f"""
            SELECT {', '.join(selected)}
            FROM smds
            {where_sql}
            ORDER BY {order_sql}
            LIMIT 1200
        """

        with engine.connect() as conn:
            rows = [dict(row) for row in conn.execute(text(query), params).mappings().all()]

        return rows, line_flag_columns

    def _refresh_line_process_mapping_table(self) -> None:
        try:
            search_text = ""
            if hasattr(self, "line_process_search_input"):
                search_text = self.line_process_search_input.text().strip()
            rows, line_flag_columns = self._list_line_process_rows(search_text)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load SMDS line mapping. " + str(exc))
            rows = []
            line_flag_columns = []

        if hasattr(self, "line_process_count_badge"):
            suffix = " / showing first 1200" if len(rows) >= 1200 else ""
            self.line_process_count_badge.setText(f"{len(rows)} Items{suffix}")

        self.line_process_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.line_process_table.setRowHeight(row_index, 56)

            mapped_line = self._line_process_display_value(row.get("production_line"))
            key_code = self._line_process_display_value(row.get("key_code"))
            line_options = self._line_process_line_options(row, line_flag_columns)
            process_type = self._line_process_process_type(mapped_line, line_options, key_code)
            day_plan = self._line_process_number_display(row.get("day_plan"))
            night_plan = self._line_process_number_display(row.get("night_plan"))
            total_plan = self._line_process_number_display(row.get("total_plan"))

            daily_plan_parts = []
            if day_plan != "-":
                daily_plan_parts.append(f"D {day_plan}")
            if night_plan != "-":
                daily_plan_parts.append(f"N {night_plan}")
            if total_plan != "-":
                daily_plan_parts.append(f"T {total_plan}")
            daily_plan = " / ".join(daily_plan_parts) if daily_plan_parts else "-"

            values = [
                self._line_process_display_value(row.get("sap_code")),
                self._line_process_display_value(row.get("description")),
                mapped_line,
                line_options,
                process_type,
                key_code,
                self._line_process_display_value(row.get("casing_type")),
                self._line_process_format_curing(row),
                daily_plan,
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.line_process_table.setItem(row_index, col, item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            view_button = QPushButton("View")
            view_button.setObjectName("ManageButton")
            view_button.clicked.connect(lambda checked=False, data=dict(row): self._show_line_process_detail(data))

            action_layout.addStretch()
            action_layout.addWidget(view_button)
            action_layout.addStretch()

            self.line_process_table.setCellWidget(row_index, 9, action_widget)

    def _show_line_process_detail(self, row: dict) -> None:
        details = [
            f"SAP Code: {self._line_process_display_value(row.get('sap_code'))}",
            f"Description: {self._line_process_display_value(row.get('description'))}",
            f"Mapped Line: {self._line_process_display_value(row.get('production_line'))}",
            f"Key Code: {self._line_process_display_value(row.get('key_code'))}",
            f"Casing Type: {self._line_process_display_value(row.get('casing_type'))}",
            f"Curing Time: {self._line_process_format_curing(row)}",
            f"Handling Min: {self._line_process_number_display(row.get('handling_minutes'))}",
            f"Day Plan: {self._line_process_number_display(row.get('day_plan'))}",
            f"Night Plan: {self._line_process_number_display(row.get('night_plan'))}",
            f"Total Plan: {self._line_process_number_display(row.get('total_plan'))}",
        ]

        QMessageBox.information(
            self,
            "SMDS Line Mapping",
            "\n".join(details),
        )


    def _open_mold_casing_rules(self) -> None:
        page = getattr(self, "smds_mold_casing_page", None)

        if page is None:
            QMessageBox.warning(self, "Module Error", "Mold & Casing Rules page is not available.")
            return

        self.stack.setCurrentWidget(page)

        refresh = getattr(page, "refresh", None)

        if callable(refresh):
            refresh()


    def _build_mold_casing_rules_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._mold_casing_rules_header())
        layout.addWidget(self._mold_casing_rules_section(), 1)

        root.addWidget(card, 1)
        return page

    def _mold_casing_rules_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Data / Tyre Item Master  /  Mold & Casing Rules")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Mold & Casing Rules")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Maintain mold key code and casing type directly from the central SMDS table."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(back_button)

        return layout

    def _mold_casing_rules_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SAP Code / Mold Key Code / Casing Type")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Mold key code = SMDS Key Code. Casing Type is saved back to SMDS. "
            "Missing values show as '-'. Use 'No Casing' when the item does not need casing."
        )
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.mold_casing_count_badge = QLabel("0 Items")
        self.mold_casing_count_badge.setObjectName("CountBadge")
        self.mold_casing_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.mold_casing_search_input = QLineEdit()
        self.mold_casing_search_input.setPlaceholderText(
            "Search SAP, description, mold key code or casing type..."
        )
        self.mold_casing_search_input.setMinimumWidth(390)
        self.mold_casing_search_input.textChanged.connect(self._refresh_mold_casing_rules_table)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self._refresh_mold_casing_rules_table)

        top.addLayout(title_area, 1)
        top.addWidget(self.mold_casing_count_badge)
        top.addWidget(self.mold_casing_search_input)
        top.addWidget(refresh_button)

        self.mold_casing_table = QTableWidget(0, 5)
        self.mold_casing_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Mold Key Code",
            "Casing Type",
            "Action",
        ])
        self.mold_casing_table.verticalHeader().setVisible(False)
        self.mold_casing_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mold_casing_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mold_casing_table.cellDoubleClicked.connect(self._edit_mold_casing_row_from_cell)

        header = self.mold_casing_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.mold_casing_table.setColumnWidth(0, 150)
        self.mold_casing_table.setColumnWidth(2, 210)
        self.mold_casing_table.setColumnWidth(3, 150)
        self.mold_casing_table.setColumnWidth(4, 120)

        layout.addLayout(top)
        layout.addWidget(self.mold_casing_table, 1)

        return section

    def _open_mold_casing_rules(self) -> None:
        page = getattr(self, "mold_casing_rules_page", None)

        if page is not None:
            page_index = self.stack.indexOf(page)
            if page_index >= 0:
                self.stack.setCurrentIndex(page_index)
                self._refresh_mold_casing_rules_table()
                return

        self.stack.setCurrentIndex(0)

    def _list_mold_casing_rules(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                id,
                sap_code,
                COALESCE(NULLIF(material_description, ''), '-') AS description,
                COALESCE(NULLIF(key_code, ''), '-') AS mold_key_code,
                CASE
                    WHEN casing_type IS NULL OR BTRIM(casing_type) = '' THEN '-'
                    ELSE casing_type
                END AS casing_type
            FROM smds
        """

        params = {}

        if search:
            sql += """
                WHERE LOWER(COALESCE(sap_code, '')) LIKE :search
                   OR LOWER(COALESCE(material_description, '')) LIKE :search
                   OR LOWER(COALESCE(key_code, '')) LIKE :search
                   OR LOWER(COALESCE(casing_type, '')) LIKE :search
            """
            params["search"] = f"%{search}%"

        sql += """
            ORDER BY
                CASE WHEN COALESCE(NULLIF(key_code, ''), '-') = '-' THEN 1 ELSE 0 END,
                key_code,
                sap_code
            LIMIT 1200
        """

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def _refresh_mold_casing_rules_table(self) -> None:
        if not hasattr(self, "mold_casing_table"):
            return

        try:
            search_text = ""
            if hasattr(self, "mold_casing_search_input"):
                search_text = self.mold_casing_search_input.text().strip()

            rows = self._list_mold_casing_rules(search_text)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Database Error",
                "Could not load SMDS mold and casing rules. " + str(exc),
            )
            rows = []

        self.mold_casing_rows = rows
        self.mold_casing_count_badge.setText(f"{len(rows)} Items")
        self.mold_casing_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.mold_casing_table.setRowHeight(row_index, 56)

            values = [
                row.get("sap_code", ""),
                row.get("description", ""),
                row.get("mold_key_code", "-"),
                row.get("casing_type", "-"),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or "-"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col in (0, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.mold_casing_table.setItem(row_index, col, item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("ManageButton")
            edit_button.clicked.connect(
                lambda checked=False, smds_id=row["id"]: self._edit_mold_casing_row(smds_id)
            )

            action_layout.addStretch()
            action_layout.addWidget(edit_button)
            action_layout.addStretch()

            self.mold_casing_table.setCellWidget(row_index, 4, action_widget)

    def _edit_mold_casing_row_from_cell(self, row: int, column: int) -> None:
        if not hasattr(self, "mold_casing_rows"):
            return

        if row < 0 or row >= len(self.mold_casing_rows):
            return

        self._edit_mold_casing_row(self.mold_casing_rows[row]["id"])

    def _edit_mold_casing_row(self, smds_id: int) -> None:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT
                            id,
                            sap_code,
                            COALESCE(NULLIF(material_description, ''), '-') AS description,
                            COALESCE(NULLIF(key_code, ''), '-') AS mold_key_code,
                            CASE
                                WHEN casing_type IS NULL OR BTRIM(casing_type) = '' THEN '-'
                                ELSE casing_type
                            END AS casing_type
                        FROM smds
                        WHERE id = :id
                    """),
                    {"id": smds_id},
                ).mappings().first()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load SMDS row.\n\n{exc}")
            return

        if row is None:
            QMessageBox.warning(self, "Not Found", "Selected SMDS row was not found.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Mold & Casing Rule")
        dialog.setMinimumWidth(620)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title = QLabel("Edit Mold & Casing Rule")
        title.setStyleSheet("color: #0f172a; font-size: 17pt; font-weight: 950;")
        layout.addWidget(title)

        info = QLabel(
            f"SAP Code: {row['sap_code']}\n"
            f"Description: {row['description']}\n\n"
            "Use '-' for unknown values. Use 'No Casing' when this item does not need casing."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        mold_input = QLineEdit(str(row.get("mold_key_code") or "-"))
        mold_input.setPlaceholderText("Mold Key Code / Key Code")

        casing_input = QLineEdit(str(row.get("casing_type") or "-"))
        casing_input.setPlaceholderText("Casing Type, No Casing, or -")

        form.addWidget(QLabel("Mold Key Code"), 0, 0)
        form.addWidget(mold_input, 0, 1)
        form.addWidget(QLabel("Casing Type"), 1, 0)
        form.addWidget(casing_input, 1, 1)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        mold_key_code = mold_input.text().strip() or "-"
        casing_type = casing_input.text().strip() or "-"

        try:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE smds
                        SET key_code = :key_code,
                            casing_type = :casing_type,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {
                        "id": smds_id,
                        "key_code": mold_key_code,
                        "casing_type": casing_type,
                    },
                )
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not update SMDS row.\n\n{exc}")
            return

        self._refresh_mold_casing_rules_table()

    def _open_item_data(self) -> None:
        self.stack.setCurrentIndex(1)
        self.refresh()

    def _back_to_overview(self) -> None:
        self.stack.setCurrentIndex(0)
        self.refresh()

    def refresh(self) -> None:
        current_index = self.stack.currentIndex() if hasattr(self, "stack") else 0

        # Performance fix:
        # Do not load 3314 tyre item rows while the Tyre Item Master overview card page is open.
        # Rows are loaded only when a detail module is opened.
        if current_index == 0:
            self.items = []
            return

        if current_index == 5 and hasattr(self, "smds_master_page"):
            self.smds_master_page.refresh()
            return

        try:
            search_text = ""

            if current_index == 3 and hasattr(self, "curing_search_input"):
                search_text = self.curing_search_input.text().strip()
            elif current_index == 2 and hasattr(self, "tyre_size_search_input"):
                search_text = self.tyre_size_search_input.text().strip()
            elif current_index == 1 and hasattr(self, "search_input"):
                search_text = self.search_input.text().strip()

            self.items = self.repo.list_items(search_text=search_text)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load tyre items.\n\n{exc}")
            self.items = []

        if current_index == 1 and hasattr(self, "table"):
            self._refresh_table()
        elif current_index == 2 and hasattr(self, "tyre_size_table"):
            self._refresh_tyre_size_table()
        elif current_index == 3 and hasattr(self, "curing_table"):
            self._refresh_curing_table()
        elif current_index == 4 and hasattr(self, "group_key_table"):
            self._refresh_tyre_group_key_table()
        elif (
            hasattr(self, "mold_casing_rules_page")
            and current_index == self.stack.indexOf(self.mold_casing_rules_page)
            and hasattr(self, "mold_casing_table")
        ):
            self._refresh_mold_casing_rules_table()
        else:
            try:
                widget = self.stack.currentWidget()
                if widget is not None and widget.property("page_key") == "line_process_mapping" and hasattr(self, "line_process_table"):
                    self._refresh_line_process_mapping_table()
            except Exception:
                pass

    refresh_page = refresh
    load_data = refresh

    def _refresh_table(self) -> None:
        self.count_badge.setText(f"{len(self.items)} Items")
        self.table.setRowCount(len(self.items))

        for row_index, row in enumerate(self.items):
            self.table.setRowHeight(row_index, 56)

            sap_item = QTableWidgetItem(str(row.get("sap_code", "")))
            sap_item.setFlags(sap_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 0, sap_item)

            desc_item = QTableWidgetItem(str(row.get("description", "")))
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 1, desc_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._manage_item(item_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()

            self.table.setCellWidget(row_index, 2, action_widget)

    def _find_item(self, item_id: int) -> dict | None:
        for item in self.items:
            if item["id"] == item_id:
                return item
        return None

    def _add_item(self) -> None:
        dialog = TyreItemDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        try:
            self.repo.create_item(data["sap_code"], data["description"])
        except Exception as exc:
            QMessageBox.critical(self, "Add Failed", f"Could not add tyre item.\n\n{exc}")
            return

        self.refresh()

    def _manage_item(self, item_id: int) -> None:
        row = self._find_item(item_id)
        if row is None:
            return

        sap_code = row.get("sap_code", "")

        box = QMessageBox(self)
        box.setWindowTitle("Manage Tyre Item")
        box.setText(str(sap_code))
        box.setInformativeText("Choose what you want to do with this tyre item.")
        box.setIcon(QMessageBox.Icon.Question)

        edit_button = box.addButton("Edit", QMessageBox.ButtonRole.AcceptRole)
        delete_button = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        box.exec()
        clicked = box.clickedButton()

        if clicked == edit_button:
            self._edit_item(item_id)
        elif clicked == delete_button:
            self._delete_item(item_id)
        elif clicked == cancel_button:
            return

    def _edit_item(self, item_id: int) -> None:
        row = self._find_item(item_id)
        if row is None:
            return

        dialog = TyreItemDialog(self, row=row)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        try:
            self.repo.update_item(item_id, data["sap_code"], data["description"])
        except Exception as exc:
            QMessageBox.critical(self, "Update Failed", f"Could not update tyre item.\n\n{exc}")
            return

        self.refresh()

    def _delete_item(self, item_id: int) -> None:
        row = self._find_item(item_id)
        if row is None:
            return

        sap_code = row.get("sap_code", "")

        confirm = QMessageBox.question(
            self,
            "Delete Tyre Item",
            f"Delete tyre item {sap_code}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete_item(item_id)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Failed", f"Could not delete tyre item.\n\n{exc}")
            return

        self.refresh()



# --- SMDS central table overrides -------------------------------------------------
# These overrides keep the existing Tyre Item Master UI, but make the data source
# the central SMDS table instead of old tyre_item_master / tyre_process_* tables.

def _smds_list_tyre_group_keys(self, search_text: str = "") -> list[dict]:
    search = (search_text or "").strip().lower()

    try:
        with engine.connect() as conn:
            records = [
                dict(row)
                for row in conn.execute(
                    text("""
                        SELECT
                            sap_code,
                            material_description,
                            line,
                            heel,
                            soft,
                            tred,
                            key_code,
                            casing_type
                        FROM smds
                        ORDER BY key_code NULLS LAST, sap_code
                    """)
                ).mappings().all()
            ]
    except Exception:
        return []

    grouped: dict[str, dict] = {}

    for record in records:
        group_key = str(record.get("key_code") or "").strip() or "NO_KEY"
        description = str(record.get("material_description") or "").strip()
        line = str(record.get("line") or "").strip()
        casing_type = str(record.get("casing_type") or "").strip()
        tread = str(record.get("tred") or "").strip()
        heel = str(record.get("heel") or "").strip()
        soft = str(record.get("soft") or "").strip()
        tyre_size = guess_tyre_size(description)

        search_blob = " ".join([group_key, description, line, casing_type, tread, heel, soft, tyre_size]).lower()
        if search and search not in search_blob:
            continue

        if group_key not in grouped:
            grouped[group_key] = {
                "id": group_key,
                "group_key": group_key,
                "tyre_size": tyre_size,
                "rim_width": line,
                "aperture_type": casing_type,
                "tread_pattern": tread,
                "layer": heel,
                "color": soft,
                "sap_count": 0,
            }

        grouped[group_key]["sap_count"] += 1

    return sorted(grouped.values(), key=lambda item: (-int(item.get("sap_count") or 0), str(item.get("group_key") or "")))


def _smds_refresh_tyre_group_key_table(self) -> None:
    try:
        search_text = ""
        if hasattr(self, "group_key_search_input"):
            search_text = self.group_key_search_input.text().strip()

        rows = self._list_tyre_group_keys(search_text)
    except Exception as exc:
        QMessageBox.critical(self, "Database Error", "Could not load SMDS tyre group keys. " + str(exc))
        rows = []

    self.group_key_count_badge.setText(f"{len(rows)} Groups")
    self.group_key_table.setRowCount(len(rows))

    for row_index, row in enumerate(rows):
        self.group_key_table.setRowHeight(row_index, 56)

        values = [
            row.get("group_key", ""),
            self._group_key_display_value(row.get("tyre_size", "")),
            self._group_key_display_value(row.get("rim_width", "")),
            self._group_key_display_value(row.get("aperture_type", "")),
            self._group_key_display_value(row.get("tread_pattern", "")),
            self._group_key_display_value(row.get("layer", "")),
            self._group_key_display_value(row.get("color", "")),
            row.get("sap_count", 0),
        ]

        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.group_key_table.setItem(row_index, col, item)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(6, 5, 6, 5)

        view_button = QPushButton("View SAP")
        view_button.setObjectName("ManageButton")
        view_button.clicked.connect(lambda checked=False, group_key=row["group_key"]: self._show_group_sap_codes(group_key))

        action_layout.addStretch()
        action_layout.addWidget(view_button)
        action_layout.addStretch()

        self.group_key_table.setCellWidget(row_index, 8, action_widget)


def _smds_show_group_sap_codes(self, group_key: str) -> None:
    try:
        with engine.connect() as conn:
            if str(group_key or "") == "NO_KEY":
                rows = conn.execute(
                    text("""
                        SELECT sap_code, material_description, line, casing_type, curing_cycle
                        FROM smds
                        WHERE NULLIF(TRIM(COALESCE(key_code, '')), '') IS NULL
                        ORDER BY sap_code
                        LIMIT 120
                    """)
                ).mappings().all()
            else:
                rows = conn.execute(
                    text("""
                        SELECT sap_code, material_description, line, casing_type, curing_cycle
                        FROM smds
                        WHERE TRIM(COALESCE(key_code, '')) = :group_key
                        ORDER BY sap_code
                        LIMIT 120
                    """),
                    {"group_key": group_key},
                ).mappings().all()
    except Exception as exc:
        QMessageBox.critical(self, "Database Error", f"Could not load SMDS SAP codes.\n\n{exc}")
        return

    lines = []
    for row in rows:
        details = []
        if row.get("line"):
            details.append(f"Line: {row['line']}")
        if row.get("casing_type"):
            details.append(f"Casing: {row['casing_type']}")
        if row.get("curing_cycle"):
            details.append(f"Curing: {row['curing_cycle']}")
        suffix = f"  ({', '.join(details)})" if details else ""
        lines.append(f'{row["sap_code"]}  -  {row["material_description"]}{suffix}')

    if not lines:
        lines.append("No SAP codes linked in SMDS.")

    message = "\n".join(lines)
    if len(rows) >= 120:
        message += "\n\nShowing first 120 SAP codes only."

    QMessageBox.information(
        self,
        "SMDS SAP Codes in Group",
        f"Group Key:\n{group_key}\n\nSAP Codes:\n{message}",
    )


TyreItemMasterPage._list_tyre_group_keys = _smds_list_tyre_group_keys
TyreItemMasterPage._refresh_tyre_group_key_table = _smds_refresh_tyre_group_key_table
TyreItemMasterPage._show_group_sap_codes = _smds_show_group_sap_codes
# -------------------------------------------------------------------------------

# --- SMDS V4 central table overrides -----------------------------------------
# Normal curing time now comes from SMDS.curing_cycle and is converted from
# values like '8h' / '7h 30m' to minutes for the Curing Time screen.

try:
    _original_number_text = TyreItemMasterPage._number_text

    def _smds_v4_number_text(self, value) -> str:
        try:
            number = float(value or 0)
            if number <= 0:
                return "-"
            if number.is_integer():
                return str(int(number))
            return str(number).rstrip("0").rstrip(".")
        except Exception:
            text_value = str(value or "").strip()
            return text_value if text_value and text_value != "0" else "-"

    TyreItemMasterPage._number_text = _smds_v4_number_text
except Exception:
    pass
# -------------------------------------------------------------------------------

# --- SMDS V5 curing-time display override ------------------------------------
# Keep numeric normal_curing_minutes for planning/analysis, but show operators a
# readable duration such as '8h (480 min)' or '7h 30m (450 min)'.

try:
    def _smds_v5_curing_display(row: dict) -> str:
        text_value = str(row.get("normal_curing_display") or "").strip()
        if text_value and text_value != "-":
            return text_value

        text_value = str(row.get("normal_curing_time_text") or "").strip()
        minutes_value = row.get("normal_curing_minutes", 0)
        try:
            minutes_number = float(minutes_value or 0)
        except Exception:
            minutes_number = 0

        if minutes_number <= 0:
            return "-"

        if text_value and text_value != "-":
            if minutes_number.is_integer():
                return f"{text_value} ({int(minutes_number)} min)"
            return f"{text_value} ({str(minutes_number).rstrip('0').rstrip('.')} min)"

        whole_minutes = int(minutes_number)
        hours = whole_minutes // 60
        minutes = whole_minutes % 60

        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")

        duration = " ".join(parts) if parts else f"{whole_minutes}m"
        if minutes_number.is_integer():
            return f"{duration} ({int(minutes_number)} min)"
        return f"{duration} ({str(minutes_number).rstrip('0').rstrip('.')} min)"

    def _smds_v5_refresh_curing_table(self) -> None:
        self.curing_count_badge.setText(f"{len(self.items)} Items")
        self.curing_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Normal Curing Time",
            "Short Cycle Curing Min",
            "Handling Min",
            "Action",
        ])
        self.curing_table.setRowCount(len(self.items))

        for row_index, row in enumerate(self.items):
            self.curing_table.setRowHeight(row_index, 56)

            values = [
                row.get("sap_code", ""),
                row.get("description", ""),
                _smds_v5_curing_display(row),
                self._number_text(row.get("short_cycle_curing_minutes", 0)),
                self._number_text(row.get("handling_minutes", 0)),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.curing_table.setItem(row_index, col, item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._manage_item(item_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()

            self.curing_table.setCellWidget(row_index, 5, action_widget)

    TyreItemMasterPage._refresh_curing_table = _smds_v5_refresh_curing_table
except Exception:
    pass
# -------------------------------------------------------------------------------

TireItemMasterPage = TyreItemMasterPage

# --- SMDS V7 line-only mapping page patch ---
def _smds_v7_normalise_line_key(value) -> str:
    text_value = str(value or "").strip().lower()
    text_value = text_value.replace("press -line", "press-line")
    return "".join(ch for ch in text_value if ch.isalnum())


def _smds_v7_known_line_definitions() -> list[tuple[str, str]]:
    return [
        ("Line-400", "line_400"),
        ("Line-800", "line_800"),
        ("Press-LINE", "press_line"),
        ("NANCY PRESS", "nancy_press"),
        ("400 T PRESS", "press_400_t"),
        ("T 600 -01 PRESS", "t_600_01_press"),
        ("T 600 -02 PRESS", "t_600_02_press"),
        ("L-PRESS-1250", "l_press_1250"),
        ("L-PRESS-1500", "l_press_1500"),
        ("L-PRESS-1800", "l_press_1800"),
        ("ORING-PRESS", "oring_press"),
        ("NEW PRESS", "new_press"),
    ]


def _v7_build_line_process_mapping_page(self) -> QWidget:
    page = QWidget()
    page.setProperty("page_key", "line_process_mapping")

    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    card = QFrame()
    card.setObjectName("PageCard")

    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 18, 22, 22)
    layout.setSpacing(18)

    layout.addLayout(self._line_process_mapping_header())
    layout.addWidget(self._line_process_mapping_section(), 1)

    root.addWidget(card, 1)
    return page


def _v7_line_process_mapping_header(self) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(14)

    text_area = QVBoxLayout()
    text_area.setSpacing(8)

    breadcrumb = QLabel("Data / Tyre Item Master  /  Line Mapping")
    breadcrumb.setObjectName("Breadcrumb")

    title = QLabel("Line Mapping")
    title.setObjectName("PageTitle")

    subtitle = QLabel("Maintain SAP-code wise production line mapping directly in the central SMDS table.")
    subtitle.setObjectName("PageSubtitle")
    subtitle.setWordWrap(True)

    text_area.addWidget(breadcrumb)
    text_area.addWidget(title)
    text_area.addWidget(subtitle)

    back_button = QPushButton("Back to Tyre Master")
    back_button.setObjectName("SecondaryButton")
    back_button.clicked.connect(self._back_to_overview)

    layout.addLayout(text_area, 1)
    layout.addWidget(back_button)

    return layout


def _v7_line_process_mapping_section(self) -> QFrame:
    section = QFrame()
    section.setObjectName("DataSection")

    layout = QVBoxLayout(section)
    layout.setContentsMargins(20, 18, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
    top.setSpacing(12)

    title_area = QVBoxLayout()
    title_area.setSpacing(5)

    title = QLabel("SAP Code / Description / Line")
    title.setObjectName("SectionTitle")

    subtitle = QLabel("Only line mapping is shown here. Double-click any SAP row to open a dropdown line selector. Selected line columns save as 'ok'; unselected line columns save as '-' in SMDS.")
    subtitle.setObjectName("SectionSubtitle")
    subtitle.setWordWrap(True)

    title_area.addWidget(title)
    title_area.addWidget(subtitle)

    self.line_process_count_badge = QLabel("0 Items")
    self.line_process_count_badge.setObjectName("CountBadge")
    self.line_process_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

    self.line_process_search_input = QLineEdit()
    self.line_process_search_input.setPlaceholderText("Search SAP, description or line...")
    self.line_process_search_input.setMinimumWidth(420)
    self.line_process_search_input.textChanged.connect(self._refresh_line_process_mapping_table)

    refresh_button = QPushButton("Refresh")
    refresh_button.setObjectName("SecondaryButton")
    refresh_button.clicked.connect(self._refresh_line_process_mapping_table)

    top.addLayout(title_area, 1)
    top.addWidget(self.line_process_count_badge)
    top.addWidget(self.line_process_search_input)
    top.addWidget(refresh_button)

    self.line_process_table = QTableWidget(0, 3)
    self.line_process_table.setHorizontalHeaderLabels(["SAP Code", "Description", "Line"])
    self.line_process_table.verticalHeader().setVisible(False)
    self.line_process_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.line_process_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.line_process_table.cellDoubleClicked.connect(self._edit_line_mapping_from_cell)

    header = self.line_process_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)

    self.line_process_table.setColumnWidth(0, 160)
    self.line_process_table.setColumnWidth(2, 460)

    layout.addLayout(top)
    layout.addWidget(self.line_process_table, 1)

    return section


def _v7_open_line_process_mapping(self) -> None:
    for index in range(self.stack.count()):
        widget = self.stack.widget(index)
        if widget is not None and widget.property("page_key") == "line_process_mapping":
            self.stack.setCurrentIndex(index)
            self._refresh_line_process_mapping_table()
            return

    QMessageBox.warning(self, "Module Error", "Line Mapping page is not connected.")


def _v7_smds_existing_columns(self) -> list[str]:
    with engine.connect() as conn:
        return [
            row[0]
            for row in conn.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'smds'
                    ORDER BY ordinal_position
                """)
            ).all()
        ]


def _v7_line_mapping_display_value(self, value) -> str:
    text_value = str(value or "").strip()
    if not text_value or text_value.upper() in {"-", "NONE", "NULL", "N/A", "NA", "0"}:
        return "-"
    return text_value


def _v7_line_mapping_split_lines(self, value) -> list[str]:
    text_value = str(value or "").strip()
    if not text_value or text_value == "-":
        return []

    # Users often paste comma, semicolon, slash or newline separated line lists.
    parts = []
    for part in text_value.replace("\r", "\n").replace(";", ",").replace("/", ",").replace("\n", ",").split(","):
        clean = " ".join(part.strip().split())
        if clean:
            parts.append(clean)

    unique = []
    seen = set()
    for part in parts:
        key = _smds_v7_normalise_line_key(part)
        if key and key not in seen:
            unique.append(part)
            seen.add(key)
    return unique


def _v7_line_mapping_known_columns(self, columns: list[str]) -> list[tuple[str, str]]:
    column_set = set(columns)
    known = [(label, column) for label, column in _smds_v7_known_line_definitions() if column in column_set]

    existing_columns = {column for _label, column in known}
    existing_keys = {_smds_v7_normalise_line_key(label) for label, _column in known}

    for column in columns:
        if column in existing_columns:
            continue
        if not (column.startswith("line_") or column.endswith("_press") or "press" in column):
            continue
        label = column
        if column.startswith("line_"):
            label = "Line-" + column.replace("line_", "", 1).replace("_", "-")
        else:
            label = column.replace("_", " ").upper()
        key = _smds_v7_normalise_line_key(label)
        if key and key not in existing_keys:
            known.append((label, column))
            existing_keys.add(key)

    return known


def _v7_line_mapping_lines_from_row(self, row: dict, known_columns: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    seen = set()

    def add_line(line_text: str) -> None:
        clean = " ".join(str(line_text or "").strip().split())
        if not clean or clean == "-":
            return
        key = _smds_v7_normalise_line_key(clean)
        if key and key not in seen:
            lines.append(clean)
            seen.add(key)

    for line_text in self._line_mapping_split_lines(row.get("line")):
        add_line(line_text)

    for label, column in known_columns:
        value = self._line_mapping_display_value(row.get(column))
        if value == "-":
            continue
        if value.lower() in {"ok", "yes", "y", "true", "1"}:
            add_line(label)
        else:
            # Some SMDS cells contain the real line name instead of just OK.
            add_line(label if _smds_v7_normalise_line_key(value) in {"ok", "yes", "y", "true", "1"} else value)

    return ", ".join(lines) if lines else "-"


def _v7_line_mapping_where_sql(self, search_text: str, columns: list[str], known_columns: list[tuple[str, str]]) -> tuple[str, dict]:
    search = (search_text or "").strip()
    if not search:
        return "", {}

    searchable = []
    for column in ("sap_code", "material_description", "description", "line"):
        if column in columns:
            searchable.append(column)
    searchable.extend(column for _label, column in known_columns)

    if not searchable:
        return "", {}

    where_sql = "WHERE " + " OR ".join(f"CAST({column} AS TEXT) ILIKE :search" for column in searchable)
    return where_sql, {"search": f"%{search}%"}


def _v7_list_line_process_rows(self, search_text: str = "") -> tuple[list[dict], int, list[tuple[str, str]]]:
    columns = self._smds_existing_columns()
    if not columns:
        return [], 0, []

    known_columns = self._line_mapping_known_columns(columns)
    desc_column = "material_description" if "material_description" in columns else "description"

    selected = ["id", "sap_code"]
    if desc_column in columns:
        selected.append(f"{desc_column} AS description")
    else:
        selected.append("'' AS description")

    if "line" in columns:
        selected.append("line")
    else:
        selected.append("'' AS line")

    for _label, column in known_columns:
        selected.append(column)

    where_sql, params = self._line_mapping_where_sql(search_text, columns, known_columns)

    count_sql = f"SELECT COUNT(*) FROM smds {where_sql}"
    query = f"""
        SELECT {', '.join(selected)}
        FROM smds
        {where_sql}
        ORDER BY sap_code
        LIMIT 1200
    """

    with engine.connect() as conn:
        total_count = int(conn.execute(text(count_sql), params).scalar() or 0)
        rows = [dict(row) for row in conn.execute(text(query), params).mappings().all()]

    return rows, total_count, known_columns


def _v7_refresh_line_process_mapping_table(self) -> None:
    try:
        search_text = ""
        if hasattr(self, "line_process_search_input"):
            search_text = self.line_process_search_input.text().strip()
        rows, total_count, known_columns = self._list_line_process_rows(search_text)
    except Exception as exc:
        QMessageBox.critical(self, "Database Error", "Could not load SMDS line mapping. " + str(exc))
        rows = []
        total_count = 0
        known_columns = []

    self._line_process_rows = rows
    self._line_process_known_columns = known_columns

    if hasattr(self, "line_process_count_badge"):
        suffix = f" / showing {len(rows)}" if total_count > len(rows) else ""
        self.line_process_count_badge.setText(f"{total_count} Items{suffix}")

    self.line_process_table.setRowCount(len(rows))

    for row_index, row in enumerate(rows):
        self.line_process_table.setRowHeight(row_index, 58)
        values = [
            self._line_mapping_display_value(row.get("sap_code")),
            self._line_mapping_display_value(row.get("description")),
            self._line_mapping_lines_from_row(row, known_columns),
        ]

        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 0:
                item.setToolTip("Double-click this row to edit line mapping")
            self.line_process_table.setItem(row_index, col, item)


def _v7_edit_line_mapping_from_cell(self, row_index: int, column_index: int) -> None:
    rows = getattr(self, "_line_process_rows", [])
    if row_index < 0 or row_index >= len(rows):
        return
    self._edit_line_mapping_row(dict(rows[row_index]))


def _v7_edit_line_mapping_row(self, row: dict) -> None:
    known_columns = getattr(self, "_line_process_known_columns", [])
    current_lines = self._line_mapping_lines_from_row(row, known_columns)
    if current_lines == "-":
        current_lines = ""

    dialog = QDialog(self)
    dialog.setWindowTitle("Edit SMDS Line Mapping")
    dialog.setMinimumWidth(720)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(22, 22, 22, 22)
    root.setSpacing(14)

    title = QLabel("Edit Line Mapping")
    title.setStyleSheet("color: #0f172a; font-size: 17pt; font-weight: 950;")

    sap_label = QLabel(f"SAP Code: {self._line_mapping_display_value(row.get('sap_code'))}")
    sap_label.setWordWrap(True)

    desc_label = QLabel(f"Description: {self._line_mapping_display_value(row.get('description'))}")
    desc_label.setWordWrap(True)

    hint = QLabel("Type line names separated by commas. Example: Line-400, Line-800, Press-LINE. Clear this field to remove all mapped lines for this SAP code.")
    hint.setObjectName("SectionSubtitle")
    hint.setWordWrap(True)

    known_text = ", ".join(label for label, _column in known_columns) or "No known line columns found. You can still save a custom line name in SMDS.line."
    known_label = QLabel("Available SMDS line columns: " + known_text)
    known_label.setObjectName("SectionSubtitle")
    known_label.setWordWrap(True)

    line_input = QLineEdit()
    line_input.setPlaceholderText("Line-400, Line-800, Press-LINE")
    line_input.setText(current_lines)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    root.addWidget(title)
    root.addWidget(sap_label)
    root.addWidget(desc_label)
    root.addWidget(hint)
    root.addWidget(known_label)
    root.addWidget(QLabel("Lines"))
    root.addWidget(line_input)
    root.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    try:
        self._save_smds_lines(str(row.get("sap_code", "")), line_input.text())
    except Exception as exc:
        QMessageBox.critical(self, "Save Failed", f"Could not update SMDS line mapping.\n\n{exc}")
        return

    self._refresh_line_process_mapping_table()


def _v7_save_smds_lines(self, sap_code: str, line_text: str) -> None:
    sap_code = str(sap_code or "").strip()
    if not sap_code:
        raise ValueError("SAP code is missing.")

    columns = self._smds_existing_columns()
    if "smds" == "":
        return

    known_columns = self._line_mapping_known_columns(columns)
    known_by_key = {
        _smds_v7_normalise_line_key(label): (label, column)
        for label, column in known_columns
    }

    parsed_lines = self._line_mapping_split_lines(line_text)
    canonical_lines: list[str] = []
    seen = set()
    flag_values = {column: None for _label, column in known_columns}

    for line in parsed_lines:
        key = _smds_v7_normalise_line_key(line)
        if not key or key in seen:
            continue
        seen.add(key)

        known = known_by_key.get(key)
        if known is not None:
            label, column = known
            canonical_lines.append(label)
            flag_values[column] = "ok"
        else:
            canonical_lines.append(line)

    line_value = ", ".join(canonical_lines) if canonical_lines else None

    set_parts = []
    params = {"sap_code": sap_code, "line_value": line_value}

    if "line" in columns:
        set_parts.append("line = :line_value")

    for column, value in flag_values.items():
        set_parts.append(f"{column} = :{column}")
        params[column] = value

    if "updated_at" in columns:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")

    if not set_parts:
        raise RuntimeError("No editable line columns were found in the SMDS table.")

    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE smds SET {', '.join(set_parts)} WHERE sap_code = :sap_code"),
            params,
        )

    if result.rowcount == 0:
        raise ValueError(f"SAP code not found in SMDS: {sap_code}")


TyreItemMasterPage._build_line_process_mapping_page = _v7_build_line_process_mapping_page
TyreItemMasterPage._line_process_mapping_header = _v7_line_process_mapping_header
TyreItemMasterPage._line_process_mapping_section = _v7_line_process_mapping_section
TyreItemMasterPage._open_line_process_mapping = _v7_open_line_process_mapping
TyreItemMasterPage._smds_existing_columns = _v7_smds_existing_columns
TyreItemMasterPage._line_mapping_display_value = _v7_line_mapping_display_value
TyreItemMasterPage._line_mapping_split_lines = _v7_line_mapping_split_lines
TyreItemMasterPage._line_mapping_known_columns = _v7_line_mapping_known_columns
TyreItemMasterPage._line_mapping_lines_from_row = _v7_line_mapping_lines_from_row
TyreItemMasterPage._line_mapping_where_sql = _v7_line_mapping_where_sql
TyreItemMasterPage._list_line_process_rows = _v7_list_line_process_rows
TyreItemMasterPage._refresh_line_process_mapping_table = _v7_refresh_line_process_mapping_table
TyreItemMasterPage._edit_line_mapping_from_cell = _v7_edit_line_mapping_from_cell
TyreItemMasterPage._edit_line_mapping_row = _v7_edit_line_mapping_row
TyreItemMasterPage._save_smds_lines = _v7_save_smds_lines
# --- end SMDS V7 line-only mapping page patch ---

# --- SMDS V8 line flag ok/dash save patch ---
def _v8_save_smds_lines(self, sap_code: str, line_text: str) -> None:
    sap_code = str(sap_code or "").strip()
    if not sap_code:
        raise ValueError("SAP code is missing.")

    columns = self._smds_existing_columns()
    known_columns = self._line_mapping_known_columns(columns)
    known_by_key = {
        _smds_v7_normalise_line_key(label): (label, column)
        for label, column in known_columns
    }

    parsed_lines = self._line_mapping_split_lines(line_text)
    canonical_lines: list[str] = []
    seen = set()

    # Important SMDS rule:
    # selected line columns are saved as 'ok'; unselected line columns are saved as '-'.
    flag_values = {column: "-" for _label, column in known_columns}

    for line in parsed_lines:
        key = _smds_v7_normalise_line_key(line)
        if not key or key in seen:
            continue
        seen.add(key)

        known = known_by_key.get(key)
        if known is not None:
            label, column = known
            canonical_lines.append(label)
            flag_values[column] = "ok"
        else:
            # Custom line name: keep it in smds.line even when there is no dedicated flag column.
            canonical_lines.append(line)

    line_value = ", ".join(canonical_lines) if canonical_lines else "-"

    set_parts = []
    params = {"sap_code": sap_code, "line_value": line_value}

    if "line" in columns:
        set_parts.append("line = :line_value")

    for column, value in flag_values.items():
        set_parts.append(f"{column} = :{column}")
        params[column] = value

    if "updated_at" in columns:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")

    if not set_parts:
        raise RuntimeError("No editable line columns were found in the SMDS table.")

    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE smds SET {', '.join(set_parts)} WHERE sap_code = :sap_code"),
            params,
        )

    if result.rowcount == 0:
        raise ValueError(f"SAP code not found in SMDS: {sap_code}")


TyreItemMasterPage._save_smds_lines = _v8_save_smds_lines
# --- end SMDS V8 line flag ok/dash save patch ---

# --- SMDS V9 dropdown multi-line mapping patch ---
def _smds_v9_normalise_line_key(value) -> str:
    text_value = str(value or "").strip().lower()
    text_value = text_value.replace("press -line", "press-line")
    return "".join(ch for ch in text_value if ch.isalnum())


def _v9_save_smds_lines(self, sap_code: str, line_text: str) -> None:
    sap_code = str(sap_code or "").strip()
    if not sap_code:
        raise ValueError("SAP code is missing.")

    columns = self._smds_existing_columns()
    known_columns = self._line_mapping_known_columns(columns)
    known_by_key = {
        _smds_v9_normalise_line_key(label): (label, column)
        for label, column in known_columns
    }

    parsed_lines = self._line_mapping_split_lines(line_text)
    canonical_lines: list[str] = []
    seen = set()

    # SMDS database rule:
    # selected line columns save as 'ok'; unselected line columns save as '-'.
    flag_values = {column: "-" for _label, column in known_columns}

    for line in parsed_lines:
        key = _smds_v9_normalise_line_key(line)
        if not key or key in seen:
            continue
        seen.add(key)

        known = known_by_key.get(key)
        if known is not None:
            label, column = known
            canonical_lines.append(label)
            flag_values[column] = "ok"
        else:
            # Custom line names are kept only in smds.line if no dedicated flag column exists.
            canonical_lines.append(line)

    line_value = ", ".join(canonical_lines) if canonical_lines else "-"

    set_parts = []
    params = {"sap_code": sap_code, "line_value": line_value}

    if "line" in columns:
        set_parts.append("line = :line_value")

    for column, value in flag_values.items():
        set_parts.append(f"{column} = :{column}")
        params[column] = value

    if "updated_at" in columns:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")

    if not set_parts:
        raise RuntimeError("No editable line columns were found in the SMDS table.")

    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE smds SET {', '.join(set_parts)} WHERE sap_code = :sap_code"),
            params,
        )

    if result.rowcount == 0:
        raise ValueError(f"SAP code not found in SMDS: {sap_code}")


def _v9_edit_line_mapping_row(self, row: dict) -> None:
    from PySide6.QtWidgets import QComboBox, QListWidget, QAbstractItemView

    known_columns = getattr(self, "_line_process_known_columns", [])
    current_lines_text = self._line_mapping_lines_from_row(row, known_columns)
    current_lines = [] if current_lines_text == "-" else self._line_mapping_split_lines(current_lines_text)

    available_lines = []
    seen_available = set()
    for label, _column in known_columns:
        key = _smds_v9_normalise_line_key(label)
        if key and key not in seen_available:
            available_lines.append(label)
            seen_available.add(key)

    # Keep any currently saved custom line visible even when it has no dedicated SMDS flag column.
    for line in current_lines:
        key = _smds_v9_normalise_line_key(line)
        if key and key not in seen_available:
            available_lines.append(line)
            seen_available.add(key)

    dialog = QDialog(self)
    dialog.setWindowTitle("Edit SMDS Line Mapping")
    dialog.setMinimumWidth(760)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(22, 22, 22, 22)
    root.setSpacing(14)

    title = QLabel("Edit Line Mapping")
    title.setStyleSheet("color: #0f172a; font-size: 17pt; font-weight: 950;")

    sap_label = QLabel(f"SAP Code: {self._line_mapping_display_value(row.get('sap_code'))}")
    sap_label.setWordWrap(True)

    desc_label = QLabel(f"Description: {self._line_mapping_display_value(row.get('description'))}")
    desc_label.setWordWrap(True)

    hint = QLabel(
        "Select a line from the dropdown and click Add Line. "
        "Use Remove Selected or Clear All to delete mapped lines. "
        "When saved, selected line columns become 'ok' and all other line columns become '-' in SMDS."
    )
    hint.setObjectName("SectionSubtitle")
    hint.setWordWrap(True)

    add_row = QHBoxLayout()
    add_row.setSpacing(10)

    line_combo = QComboBox()
    line_combo.setEditable(True)
    line_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    line_combo.setMinimumWidth(420)
    line_combo.addItems(available_lines)
    line_combo.setPlaceholderText("Select or type line name...")

    add_button = QPushButton("Add Line")
    add_button.setObjectName("PrimaryButton")

    add_row.addWidget(line_combo, 1)
    add_row.addWidget(add_button)

    selected_label = QLabel("Selected Lines")
    selected_label.setObjectName("SectionSubtitle")

    selected_list = QListWidget()
    selected_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    selected_list.setMinimumHeight(145)

    remove_row = QHBoxLayout()
    remove_row.setSpacing(10)

    remove_button = QPushButton("Remove Selected")
    remove_button.setObjectName("SecondaryButton")

    clear_button = QPushButton("Clear All")
    clear_button.setObjectName("SecondaryButton")

    remove_row.addStretch()
    remove_row.addWidget(remove_button)
    remove_row.addWidget(clear_button)

    def selected_line_values() -> list[str]:
        return [selected_list.item(i).text() for i in range(selected_list.count())]

    def add_line(line_text: str) -> None:
        clean = " ".join(str(line_text or "").strip().split())
        if not clean or clean == "-":
            return

        new_key = _smds_v9_normalise_line_key(clean)
        for existing in selected_line_values():
            if _smds_v9_normalise_line_key(existing) == new_key:
                return

        # If typed text matches a known line, save the official SMDS label.
        for label in available_lines:
            if _smds_v9_normalise_line_key(label) == new_key:
                clean = label
                break

        selected_list.addItem(clean)

    for line in current_lines:
        add_line(line)

    def add_from_combo() -> None:
        add_line(line_combo.currentText())

    def remove_selected() -> None:
        for item in selected_list.selectedItems():
            selected_list.takeItem(selected_list.row(item))

    def clear_all() -> None:
        selected_list.clear()

    add_button.clicked.connect(add_from_combo)
    line_combo.lineEdit().returnPressed.connect(add_from_combo)
    remove_button.clicked.connect(remove_selected)
    clear_button.clicked.connect(clear_all)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    root.addWidget(title)
    root.addWidget(sap_label)
    root.addWidget(desc_label)
    root.addWidget(hint)
    root.addLayout(add_row)
    root.addWidget(selected_label)
    root.addWidget(selected_list)
    root.addLayout(remove_row)
    root.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    line_text = ", ".join(selected_line_values())

    try:
        self._save_smds_lines(str(row.get("sap_code", "")), line_text)
    except Exception as exc:
        QMessageBox.critical(self, "Save Failed", f"Could not update SMDS line mapping.\n\n{exc}")
        return

    QMessageBox.information(self, "Saved", "SMDS line mapping saved successfully.")
    self._refresh_line_process_mapping_table()


TyreItemMasterPage._save_smds_lines = _v9_save_smds_lines
TyreItemMasterPage._edit_line_mapping_row = _v9_edit_line_mapping_row
# --- end SMDS V9 dropdown multi-line mapping patch ---

# --- SMDS V11 CARD ROUTING FIX START ---
# Fixes the Tyre Item Master overview card routing so SMDS Master opens the
# SMDS detail page, and Line Mapping opens the line-mapping page. This patch is
# intentionally isolated and can be removed/replaced safely in a later cleanup.

def _smds_v11_find_stack_page_index(self, required_texts, forbidden_texts=()):
    try:
        from PySide6.QtWidgets import QLabel
    except Exception:
        return None

    stack = getattr(self, "stack", None)
    if stack is None:
        return None

    required = [str(text).lower() for text in required_texts]
    forbidden = [str(text).lower() for text in forbidden_texts]

    for index in range(stack.count()):
        widget = stack.widget(index)
        if widget is None:
            continue

        label_texts = []
        try:
            for label in widget.findChildren(QLabel):
                label_texts.append(str(label.text() or ""))
        except Exception:
            continue

        haystack = "\n".join(label_texts).lower()

        if all(text in haystack for text in required) and not any(text in haystack for text in forbidden):
            return index

    return None


def _smds_v11_open_smds_master(self):
    index = _smds_v11_find_stack_page_index(
        self,
        required_texts=("smds central data table",),
        forbidden_texts=("sap code / description / line",),
    )

    if index is None:
        index = _smds_v11_find_stack_page_index(
            self,
            required_texts=("smds master", "central sap"),
            forbidden_texts=("line mapping",),
        )

    if index is None:
        # Common stack position used by earlier SMDS updates.
        index = 5 if getattr(self, "stack", None) is not None and self.stack.count() > 5 else None

    if index is not None:
        self.stack.setCurrentIndex(index)
        if hasattr(self, "refresh"):
            self.refresh()


def _smds_v11_open_line_mapping(self):
    index = _smds_v11_find_stack_page_index(
        self,
        required_texts=("sap code / description / line",),
        forbidden_texts=("smds central data table",),
    )

    if index is None:
        index = _smds_v11_find_stack_page_index(
            self,
            required_texts=("line mapping", "maintain sap-code wise"),
            forbidden_texts=("smds master",),
        )

    if index is None:
        # Common stack position used by earlier SMDS updates.
        index = 6 if getattr(self, "stack", None) is not None and self.stack.count() > 6 else None

    if index is not None:
        self.stack.setCurrentIndex(index)
        if hasattr(self, "refresh"):
            self.refresh()


def _smds_v11_module_card(self, badge_text, title_text, description, action, enabled):
    card = QFrame()
    card.setObjectName("ModuleCard")
    card.setMinimumHeight(210)

    if enabled and action is not None:
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event, action=action: action()

    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(12)

    badge = QLabel(str(badge_text))
    badge.setObjectName("ModuleBadge" if enabled else "ComingBadge")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedHeight(30)

    badge_row = QHBoxLayout()
    badge_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
    badge_row.addStretch()

    title = QLabel(str(title_text))
    title.setObjectName("ModuleTitle")
    title.setWordWrap(True)

    desc = QLabel(str(description))
    desc.setObjectName("ModuleText")
    desc.setWordWrap(True)

    button = QPushButton("Open Module" if enabled else "Coming Soon")
    button.setObjectName("PrimaryButton" if enabled else "DisabledButton")
    button.setEnabled(bool(enabled))

    if enabled and action is not None:
        button.clicked.connect(lambda checked=False, action=action: action())

    layout.addLayout(badge_row)
    layout.addWidget(title)
    layout.addWidget(desc)
    layout.addStretch()
    layout.addWidget(button)

    return card


def _smds_v11_module_grid(self):
    section = QFrame()
    section.setObjectName("DataSection")

    root = QVBoxLayout(section)
    root.setContentsMargins(20, 18, 20, 20)
    root.setSpacing(16)

    title = QLabel("Tyre Item Master Modules")
    title.setObjectName("SectionTitle")

    subtitle = QLabel("Open each card to maintain item-level planning data step by step.")
    subtitle.setObjectName("SectionSubtitle")

    title_area = QVBoxLayout()
    title_area.setSpacing(5)
    title_area.addWidget(title)
    title_area.addWidget(subtitle)

    cards = [
        (
            "SMDS",
            "SMDS Master",
            "Central SAP, key code, casing, curing and day/night planning table from SMDS6.xlsx.",
            self._open_smds_master,
            True,
        ),
        (
            "ITEM DATA",
            "Tyre Item Data",
            "Maintain SAP code and tyre description table.",
            self._open_item_data,
            True,
        ),
        (
            "TYRE SIZE",
            "Tyre Size Data",
            "Maintain SAP code, description and extracted tyre size.",
            self._open_tyre_size,
            True,
        ),
        (
            "CURING TIME",
            "Production / Curing Time",
            "Maintain normal curing time, short cycle placeholder and handling time.",
            self._open_curing_time,
            True,
        ),
        (
            "GROUP KEY",
            "Tyre Group Key Mapping",
            "Group same tyres under one process key and attach multiple SAP codes.",
            self._open_tyre_group_key,
            True,
        ),
        (
            "LINE RULES",
            "Line Mapping",
            "Maintain SAP-code wise production line mapping from SMDS.",
            self._open_line_mapping,
            True,
        ),
        (
            "MOLD / CASING",
            "Mold & Casing Rules",
            "Maintain mold count, casing type and item compatibility.",
            self._open_mold_casing_rules, True,
        ),
        (
            "PRODUCT GROUP",
            "Weight & Product Group",
            "Maintain item weight, color, layer and product family.",
            self._open_mold_casing_rules, True,
        ),
        (
            "IMPORT",
            "Excel Import",
            "Import SAP code and description from approved master files.",
            None,
            False,
        ),
    ]

    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(14)

    for index, item in enumerate(cards):
        row = index // 3
        col = index % 3
        grid.addWidget(self._module_card(*item), row, col)
        grid.setColumnStretch(col, 1)

    root.addLayout(title_area)
    root.addLayout(grid)
    root.addStretch()

    return section


try:
    TyreItemMasterPage._open_smds_master = _smds_v11_open_smds_master
    TyreItemMasterPage._open_line_mapping = _smds_v11_open_line_mapping
    TyreItemMasterPage._module_card = _smds_v11_module_card
    TyreItemMasterPage._module_grid = _smds_v11_module_grid
    TireItemMasterPage = TyreItemMasterPage
except NameError:
    pass
# --- SMDS V11 CARD ROUTING FIX END ---

# --- SMDS V15 WEIGHT PRODUCT GROUP START ---
# Completes the Weight & Product Group module using the central SMDS table.
# Data source: smds.weight_per_tyre_kg, smds.heel, smds.soft, smds.tred, smds.remark.
# Save target: direct UPDATE to the same SMDS row.


def _smds_v15_find_stack_page_index(self, required_texts, forbidden_texts=()):
    try:
        from PySide6.QtWidgets import QLabel
    except Exception:
        return None

    stack = getattr(self, "stack", None)
    if stack is None:
        return None

    required = [str(text).lower() for text in required_texts]
    forbidden = [str(text).lower() for text in forbidden_texts]

    for index in range(stack.count()):
        widget = stack.widget(index)
        if widget is None:
            continue

        label_texts = []
        try:
            for label in widget.findChildren(QLabel):
                label_texts.append(str(label.text() or ""))
        except Exception:
            continue

        haystack = "\n".join(label_texts).lower()
        if all(text in haystack for text in required) and not any(text in haystack for text in forbidden):
            return index

    return None


def _smds_v15_open_smds_master(self):
    index = _smds_v15_find_stack_page_index(
        self,
        required_texts=("smds central data table",),
        forbidden_texts=("sap code / description / line", "weight / product"),
    )

    if index is None:
        index = _smds_v15_find_stack_page_index(
            self,
            required_texts=("smds master", "central sap"),
            forbidden_texts=("line mapping", "weight"),
        )

    if index is not None:
        self.stack.setCurrentIndex(index)
        if hasattr(self, "refresh"):
            self.refresh()


def _smds_v15_open_line_mapping(self):
    index = _smds_v15_find_stack_page_index(
        self,
        required_texts=("sap code / description / line",),
        forbidden_texts=("smds central data table", "weight / product"),
    )

    if index is None:
        index = _smds_v15_find_stack_page_index(
            self,
            required_texts=("line mapping", "maintain sap-code wise"),
            forbidden_texts=("smds master", "weight"),
        )

    if index is not None:
        self.stack.setCurrentIndex(index)
        if hasattr(self, "refresh"):
            self.refresh()


def _smds_v15_clean_text(value, *, blank_as_dash: bool = True) -> str:
    text_value = str(value or "").strip()
    if text_value.upper() in {"NULL", "NONE", "N/A", "NA"}:
        text_value = ""
    if blank_as_dash and not text_value:
        return "-"
    return text_value


def _smds_v15_number_text(value) -> str:
    try:
        if value is None:
            return "-"
        number = float(value)
        if number <= 0:
            return "-"
        if number.is_integer():
            return str(int(number))
        return (f"{number:.3f}").rstrip("0").rstrip(".")
    except Exception:
        return "-"


def _smds_v15_parse_weight(text_value: str):
    value = str(text_value or "").strip()
    if value in {"", "-"}:
        return None
    value = value.replace(",", "")
    try:
        number = float(value)
    except Exception:
        raise ValueError("Weight must be a number, or '-' for unknown.")
    if number < 0:
        raise ValueError("Weight cannot be negative.")
    return number


def _smds_v15_ensure_weight_product_columns(self) -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS weight_per_tyre_kg NUMERIC(14, 3)"))
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS heel TEXT"))
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS soft TEXT"))
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS tred TEXT"))
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS remark TEXT"))
        conn.execute(text("ALTER TABLE smds ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"))
        conn.execute(text("UPDATE smds SET heel = '-' WHERE heel IS NULL OR BTRIM(CAST(heel AS TEXT)) = ''"))
        conn.execute(text("UPDATE smds SET soft = '-' WHERE soft IS NULL OR BTRIM(CAST(soft AS TEXT)) = ''"))
        conn.execute(text("UPDATE smds SET tred = '-' WHERE tred IS NULL OR BTRIM(CAST(tred AS TEXT)) = ''"))
        conn.execute(text("UPDATE smds SET remark = '-' WHERE remark IS NULL OR BTRIM(CAST(remark AS TEXT)) = ''"))


def _smds_v15_build_weight_product_group_page(self) -> QWidget:
    page = QWidget()
    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    card = QFrame()
    card.setObjectName("PageCard")

    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 18, 22, 22)
    layout.setSpacing(18)

    layout.addLayout(self._weight_product_group_header())
    layout.addWidget(self._weight_product_group_section(), 1)

    root.addWidget(card, 1)
    return page


def _smds_v15_weight_product_group_header(self) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(14)

    text_area = QVBoxLayout()
    text_area.setSpacing(8)

    breadcrumb = QLabel("Data / Tyre Item Master  /  Weight & Product Group")
    breadcrumb.setObjectName("Breadcrumb")

    title = QLabel("Weight & Product Group")
    title.setObjectName("PageTitle")

    subtitle = QLabel(
        "Maintain tyre weight and product attributes directly from the central SMDS table."
    )
    subtitle.setObjectName("PageSubtitle")
    subtitle.setWordWrap(True)

    text_area.addWidget(breadcrumb)
    text_area.addWidget(title)
    text_area.addWidget(subtitle)

    back_button = QPushButton("Back to Tyre Master")
    back_button.setObjectName("SecondaryButton")
    back_button.clicked.connect(self._back_to_overview)

    layout.addLayout(text_area, 1)
    layout.addWidget(back_button)
    return layout


def _smds_v15_weight_product_group_section(self) -> QFrame:
    section = QFrame()
    section.setObjectName("DataSection")

    layout = QVBoxLayout(section)
    layout.setContentsMargins(20, 18, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
    top.setSpacing(12)

    title_area = QVBoxLayout()
    title_area.setSpacing(5)

    title = QLabel("SAP Code / Weight / Product Attributes")
    title.setObjectName("SectionTitle")

    subtitle = QLabel(
        "Weight stays numeric in SMDS for planning analysis. HEEL, SOFT, Tread and Remark are editable product attributes. Missing values show as '-'."
    )
    subtitle.setObjectName("SectionSubtitle")
    subtitle.setWordWrap(True)

    title_area.addWidget(title)
    title_area.addWidget(subtitle)

    self.weight_product_count_badge = QLabel("0 Items")
    self.weight_product_count_badge.setObjectName("CountBadge")
    self.weight_product_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

    self.weight_product_search_input = QLineEdit()
    self.weight_product_search_input.setPlaceholderText(
        "Search SAP, description, weight, HEEL, SOFT, tread or remark..."
    )
    self.weight_product_search_input.setMinimumWidth(390)
    self.weight_product_search_input.textChanged.connect(self._refresh_weight_product_group_table)

    refresh_button = QPushButton("Refresh")
    refresh_button.setObjectName("SecondaryButton")
    refresh_button.clicked.connect(self._refresh_weight_product_group_table)

    top.addLayout(title_area, 1)
    top.addWidget(self.weight_product_count_badge)
    top.addWidget(self.weight_product_search_input)
    top.addWidget(refresh_button)

    self.weight_product_table = QTableWidget(0, 8)
    self.weight_product_table.setHorizontalHeaderLabels([
        "SAP Code",
        "Description",
        "Weight/Tyre Kg",
        "HEEL",
        "SOFT",
        "Tread",
        "Remark",
        "Action",
    ])
    self.weight_product_table.verticalHeader().setVisible(False)
    self.weight_product_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.weight_product_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.weight_product_table.itemDoubleClicked.connect(
        lambda item: self._edit_weight_product_group_by_row(item.row())
    )

    header = self.weight_product_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

    self.weight_product_table.setColumnWidth(0, 145)
    self.weight_product_table.setColumnWidth(2, 135)
    self.weight_product_table.setColumnWidth(3, 95)
    self.weight_product_table.setColumnWidth(4, 95)
    self.weight_product_table.setColumnWidth(5, 130)
    self.weight_product_table.setColumnWidth(6, 155)
    self.weight_product_table.setColumnWidth(7, 120)

    layout.addLayout(top)
    layout.addWidget(self.weight_product_table, 1)
    return section


def _smds_v15_open_weight_product_group(self) -> None:
    if not hasattr(self, "weight_product_group_page"):
        self.weight_product_group_page = self._build_weight_product_group_page()
        self.stack.addWidget(self.weight_product_group_page)

    page_index = self.stack.indexOf(self.weight_product_group_page)
    if page_index < 0:
        self.stack.addWidget(self.weight_product_group_page)
        page_index = self.stack.indexOf(self.weight_product_group_page)

    self.stack.setCurrentIndex(page_index)
    self._refresh_weight_product_group_table()


def _smds_v15_list_weight_product_group_rows(self, search_text: str = "") -> list[dict]:
    self._ensure_weight_product_columns()

    search = (search_text or "").strip()
    sql = """
        SELECT
            id,
            sap_code,
            material_description,
            weight_per_tyre_kg,
            heel,
            soft,
            tred,
            remark
        FROM smds
        WHERE 1 = 1
    """
    params: dict[str, object] = {"limit": 1200}

    if search:
        sql += """
            AND (
                CAST(sap_code AS TEXT) ILIKE :search
                OR CAST(material_description AS TEXT) ILIKE :search
                OR CAST(weight_per_tyre_kg AS TEXT) ILIKE :search
                OR COALESCE(heel, '') ILIKE :search
                OR COALESCE(soft, '') ILIKE :search
                OR COALESCE(tred, '') ILIKE :search
                OR COALESCE(remark, '') ILIKE :search
            )
        """
        params["search"] = f"%{search}%"

    sql += """
        ORDER BY sap_code
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    return [dict(row) for row in rows]


def _smds_v15_refresh_weight_product_group_table(self) -> None:
    if not hasattr(self, "weight_product_table"):
        return

    try:
        search_text = ""
        if hasattr(self, "weight_product_search_input"):
            search_text = self.weight_product_search_input.text().strip()
        rows = self._list_weight_product_group_rows(search_text)
    except Exception as exc:
        QMessageBox.critical(self, "Database Error", f"Could not load SMDS weight/product data.\n\n{exc}")
        rows = []

    self.weight_product_rows = rows

    if hasattr(self, "weight_product_count_badge"):
        self.weight_product_count_badge.setText(f"{len(rows)} Items / showing first 1200")

    self.weight_product_table.setRowCount(len(rows))

    for row_index, row in enumerate(rows):
        self.weight_product_table.setRowHeight(row_index, 56)

        values = [
            row.get("sap_code", ""),
            row.get("material_description", ""),
            _smds_v15_number_text(row.get("weight_per_tyre_kg")),
            _smds_v15_clean_text(row.get("heel")),
            _smds_v15_clean_text(row.get("soft")),
            _smds_v15_clean_text(row.get("tred")),
            _smds_v15_clean_text(row.get("remark")),
        ]

        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col in (0, 2, 3, 4):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.weight_product_table.setItem(row_index, col, item)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(6, 5, 6, 5)

        edit_button = QPushButton("Edit")
        edit_button.setObjectName("ManageButton")
        edit_button.clicked.connect(lambda checked=False, idx=row_index: self._edit_weight_product_group_by_row(idx))

        action_layout.addStretch()
        action_layout.addWidget(edit_button)
        action_layout.addStretch()
        self.weight_product_table.setCellWidget(row_index, 7, action_widget)


def _smds_v15_edit_weight_product_group_by_row(self, row_index: int) -> None:
    if not hasattr(self, "weight_product_rows"):
        return
    if row_index < 0 or row_index >= len(self.weight_product_rows):
        return
    self._edit_weight_product_group_row(self.weight_product_rows[row_index])


def _smds_v15_edit_weight_product_group_row(self, row: dict) -> None:
    dialog = QDialog(self)
    dialog.setWindowTitle("Edit Weight & Product Group")
    dialog.setMinimumWidth(680)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(22, 22, 22, 22)
    root.setSpacing(14)

    title = QLabel("Edit Weight & Product Group")
    title.setStyleSheet("color: #0f172a; font-size: 17pt; font-weight: 950;")

    sap_label = QLabel(f"SAP Code: {row.get('sap_code', '')}")
    sap_label.setWordWrap(True)

    desc_label = QLabel(f"Description: {row.get('material_description', '')}")
    desc_label.setWordWrap(True)

    hint = QLabel(
        "Weight is saved as a numeric value for planning analysis. Use '-' when weight is unknown. Other blank product attributes are saved as '-'."
    )
    hint.setObjectName("SectionSubtitle")
    hint.setWordWrap(True)

    form = QGridLayout()
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(12)

    weight_input = QLineEdit(_smds_v15_number_text(row.get("weight_per_tyre_kg")))
    weight_input.setPlaceholderText("Example: 16.806 or -")

    heel_input = QLineEdit(_smds_v15_clean_text(row.get("heel")))
    soft_input = QLineEdit(_smds_v15_clean_text(row.get("soft")))
    tred_input = QLineEdit(_smds_v15_clean_text(row.get("tred")))
    remark_input = QLineEdit(_smds_v15_clean_text(row.get("remark")))

    form.addWidget(QLabel("Weight/Tyre Kg"), 0, 0)
    form.addWidget(weight_input, 0, 1)
    form.addWidget(QLabel("HEEL"), 1, 0)
    form.addWidget(heel_input, 1, 1)
    form.addWidget(QLabel("SOFT"), 2, 0)
    form.addWidget(soft_input, 2, 1)
    form.addWidget(QLabel("Tread"), 3, 0)
    form.addWidget(tred_input, 3, 1)
    form.addWidget(QLabel("Remark / Product Group"), 4, 0)
    form.addWidget(remark_input, 4, 1)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    root.addWidget(title)
    root.addWidget(sap_label)
    root.addWidget(desc_label)
    root.addWidget(hint)
    root.addLayout(form)
    root.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    try:
        weight_value = _smds_v15_parse_weight(weight_input.text())
    except ValueError as exc:
        QMessageBox.warning(self, "Validation", str(exc))
        return

    payload = {
        "id": row["id"],
        "weight_per_tyre_kg": weight_value,
        "heel": _smds_v15_clean_text(heel_input.text()),
        "soft": _smds_v15_clean_text(soft_input.text()),
        "tred": _smds_v15_clean_text(tred_input.text()),
        "remark": _smds_v15_clean_text(remark_input.text()),
    }

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE smds
                    SET weight_per_tyre_kg = :weight_per_tyre_kg,
                        heel = :heel,
                        soft = :soft,
                        tred = :tred,
                        remark = :remark,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                payload,
            )
    except Exception as exc:
        QMessageBox.critical(self, "Save Failed", f"Could not update SMDS weight/product data.\n\n{exc}")
        return

    self._refresh_weight_product_group_table()


def _smds_v15_module_card(self, badge_text, title_text, description, action, enabled):
    card = QFrame()
    card.setObjectName("ModuleCard")
    card.setMinimumHeight(210)

    if enabled and action is not None:
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event, action=action: action()

    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(12)

    badge = QLabel(str(badge_text))
    badge.setObjectName("ModuleBadge" if enabled else "ComingBadge")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedHeight(30)

    badge_row = QHBoxLayout()
    badge_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
    badge_row.addStretch()

    title = QLabel(str(title_text))
    title.setObjectName("ModuleTitle")
    title.setWordWrap(True)

    desc = QLabel(str(description))
    desc.setObjectName("ModuleText")
    desc.setWordWrap(True)

    button = QPushButton("Open Module" if enabled else "Coming Soon")
    button.setObjectName("PrimaryButton" if enabled else "DisabledButton")
    button.setEnabled(bool(enabled))

    if enabled and action is not None:
        button.clicked.connect(lambda checked=False, action=action: action())

    layout.addLayout(badge_row)
    layout.addWidget(title)
    layout.addWidget(desc)
    layout.addStretch()
    layout.addWidget(button)
    return card


def _smds_v15_module_grid(self):
    section = QFrame()
    section.setObjectName("DataSection")

    root = QVBoxLayout(section)
    root.setContentsMargins(20, 18, 20, 20)
    root.setSpacing(16)

    title = QLabel("Tyre Item Master Modules")
    title.setObjectName("SectionTitle")

    subtitle = QLabel("Open each card to maintain item-level planning data step by step.")
    subtitle.setObjectName("SectionSubtitle")

    title_area = QVBoxLayout()
    title_area.setSpacing(5)
    title_area.addWidget(title)
    title_area.addWidget(subtitle)

    mold_action = getattr(self, "_open_mold_casing_rules", None)

    cards = [
        (
            "SMDS",
            "SMDS Master",
            "Central SAP, key code, casing, curing and day/night planning table from SMDS6.xlsx.",
            self._open_smds_master,
            True,
        ),
        (
            "ITEM DATA",
            "Tyre Item Data",
            "Maintain SAP code and tyre description table.",
            self._open_item_data,
            True,
        ),
        (
            "TYRE SIZE",
            "Tyre Size Data",
            "Maintain SAP code, description and extracted tyre size.",
            self._open_tyre_size,
            True,
        ),
        (
            "CURING TIME",
            "Production / Curing Time",
            "Maintain normal curing time, short cycle placeholder and handling time.",
            self._open_curing_time,
            True,
        ),
        (
            "GROUP KEY",
            "Tyre Group Key Mapping",
            "Group same tyres under one process key and attach multiple SAP codes.",
            self._open_tyre_group_key,
            True,
        ),
        (
            "LINE RULES",
            "Line Mapping",
            "Maintain SAP-code wise production line mapping from SMDS.",
            self._open_line_mapping,
            True,
        ),
        (
            "MOLD / CASING",
            "Mold & Casing Rules",
            "Maintain mold key code and casing type from SMDS.",
            mold_action,
            callable(mold_action),
        ),
        (
            "PRODUCT GROUP",
            "Weight & Product Group",
            "Maintain item weight, HEEL, SOFT, tread and product remarks from SMDS.",
            self._open_weight_product_group,
            True,
        ),
        (
            "IMPORT",
            "Excel Import",
            "Import SAP code and description from approved master files.",
            None,
            False,
        ),
    ]

    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(14)

    for index, item in enumerate(cards):
        row = index // 3
        col = index % 3
        grid.addWidget(self._module_card(*item), row, col)
        grid.setColumnStretch(col, 1)

    root.addLayout(title_area)
    root.addLayout(grid)
    root.addStretch()
    return section


try:
    TyreItemMasterPage._open_smds_master = _smds_v15_open_smds_master
    TyreItemMasterPage._open_line_mapping = _smds_v15_open_line_mapping
    TyreItemMasterPage._ensure_weight_product_columns = _smds_v15_ensure_weight_product_columns
    TyreItemMasterPage._build_weight_product_group_page = _smds_v15_build_weight_product_group_page
    TyreItemMasterPage._weight_product_group_header = _smds_v15_weight_product_group_header
    TyreItemMasterPage._weight_product_group_section = _smds_v15_weight_product_group_section
    TyreItemMasterPage._open_weight_product_group = _smds_v15_open_weight_product_group
    TyreItemMasterPage._list_weight_product_group_rows = _smds_v15_list_weight_product_group_rows
    TyreItemMasterPage._refresh_weight_product_group_table = _smds_v15_refresh_weight_product_group_table
    TyreItemMasterPage._edit_weight_product_group_by_row = _smds_v15_edit_weight_product_group_by_row
    TyreItemMasterPage._edit_weight_product_group_row = _smds_v15_edit_weight_product_group_row
    TyreItemMasterPage._module_card = _smds_v15_module_card
    TyreItemMasterPage._module_grid = _smds_v15_module_grid
    TireItemMasterPage = TyreItemMasterPage
except NameError:
    pass
# --- SMDS V15 WEIGHT PRODUCT GROUP END ---



# MPPS V19 LAZY TYRE ITEM MASTER CHILD WORKSPACES
def _mpps_v19_replace_lazy_page(self, placeholder_attr, page_attr, factory):
    page = getattr(self, page_attr, None)
    created_now = False

    if page is None:
        placeholder = getattr(self, placeholder_attr, None)
        target_index = (
            self.stack.indexOf(placeholder)
            if placeholder is not None
            else -1
        )

        page = factory()
        setattr(self, page_attr, page)

        if placeholder is not None and target_index >= 0:
            self.stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self.stack.insertWidget(target_index, page)
        else:
            self.stack.addWidget(page)

        created_now = True

    self.stack.setCurrentWidget(page)
    return page, created_now


def _mpps_v19_open_smds_master(self):
    page, created_now = _mpps_v19_replace_lazy_page(
        self,
        "_smds_master_placeholder",
        "smds_master_page",
        lambda: SMDSMasterPage(
            on_back=self._back_to_overview
        ),
    )

    # Constructor performs its initial load. Only explicitly refresh
    # when revisiting an already-created child page.
    if not created_now:
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()


def _mpps_v19_open_mold_casing_rules(self):
    page, created_now = _mpps_v19_replace_lazy_page(
        self,
        "_smds_mold_casing_placeholder",
        "smds_mold_casing_page",
        lambda: SmdsMoldCasingPage(
            on_back=self._back_to_overview
        ),
    )

    if not created_now:
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()


# Final aliases intentionally come after legacy V11/V15 aliases.
TyreItemMasterPage._open_smds_master = _mpps_v19_open_smds_master
TyreItemMasterPage._open_mold_casing_rules = _mpps_v19_open_mold_casing_rules

try:
    TireItemMasterPage._open_smds_master = _mpps_v19_open_smds_master
    TireItemMasterPage._open_mold_casing_rules = _mpps_v19_open_mold_casing_rules
except NameError:
    pass

# MPPS V30 TYRE ITEM MASTER PRO NONBLOCKING WORKSPACE
from PySide6.QtCore import QThread as _V30QThread, Signal as _V30Signal, QTimer as _V30QTimer
from PySide6.QtWidgets import (
    QAbstractItemView as _V30AbstractItemView,
    QButtonGroup as _V30ButtonGroup,
    QComboBox as _V30ComboBox,
)
from app.database import get_session as _v30_get_session
from app.services.tyre_master_intelligence_service import (
    TyreMasterIntelligenceService as _V30TyreIntelligence,
)


_TyreItemMasterLegacyV30 = TyreItemMasterPage


def _v30_smds_columns():
    with engine.connect() as conn:
        return [
            str(row[0])
            for row in conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'smds'
                    ORDER BY ordinal_position
                    """
                )
            ).all()
        ]


def _v30_pick(columns, *names):
    pool = set(columns)
    return next((name for name in names if name in pool), None)


def _v30_load_line_rows(search_text=""):
    columns = _v30_smds_columns()
    if not columns:
        return []

    sap = _v30_pick(columns, "sap_code", "sap", "sap_no")
    desc = _v30_pick(columns, "material_description", "description")
    line = _v30_pick(columns, "line", "production_line")
    key = _v30_pick(columns, "key_code")
    casing = _v30_pick(columns, "casing_type")
    curing = _v30_pick(columns, "normal_curing_minutes", "curing_cycle")
    day = _v30_pick(columns, "day_plan")
    night = _v30_pick(columns, "night_plan")
    total = _v30_pick(columns, "total_plan")

    def expr(column, alias, default="''"):
        return f"{column} AS {alias}" if column else f"{default} AS {alias}"

    selected = [
        expr(sap, "sap_code"),
        expr(desc, "description"),
        expr(line, "production_line"),
        expr(key, "key_code"),
        expr(casing, "casing_type"),
        expr(curing, "curing"),
        expr(day, "day_plan", "0"),
        expr(night, "night_plan", "0"),
        expr(total, "total_plan", "0"),
    ]

    params = {}
    where = ""
    search = str(search_text or "").strip()
    searchable = [value for value in (sap, desc, line, key, casing) if value]

    if search and searchable:
        where = "WHERE " + " OR ".join(
            f"CAST({column} AS TEXT) ILIKE :search"
            for column in searchable
        )
        params["search"] = f"%{search}%"

    order = sap or desc or columns[0]
    query = f"""
        SELECT {', '.join(selected)}
        FROM smds
        {where}
        ORDER BY {order}
        LIMIT 1500
    """

    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(text(query), params).mappings().all()
        ]


def _v30_load_mold_rows(search_text=""):
    search = str(search_text or "").strip()
    params = {}
    where = ""

    if search:
        where = """
            WHERE CAST(sap_code AS TEXT) ILIKE :search
               OR COALESCE(material_description, '') ILIKE :search
               OR COALESCE(key_code, '') ILIKE :search
               OR COALESCE(casing_type, '') ILIKE :search
        """
        params["search"] = f"%{search}%"

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT id,
                       COALESCE(sap_code, '') AS sap_code,
                       COALESCE(material_description, '') AS description,
                       COALESCE(key_code, '-') AS mold_key_code,
                       COALESCE(casing_type, '-') AS casing_type
                FROM smds
                {where}
                ORDER BY sap_code
                LIMIT 1500
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


def _v30_load_group_rows(search_text=""):
    search = str(search_text or "").strip()
    params = {}
    where = ""

    if search:
        where = """
            WHERE g.group_key ILIKE :search
               OR g.tyre_size ILIKE :search
               OR COALESCE(g.pattern, '') ILIKE :search
               OR COALESCE(g.layer, '') ILIKE :search
               OR COALESCE(g.color, '') ILIKE :search
        """
        params["search"] = f"%{search}%"

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT g.id,
                       g.group_key,
                       g.tyre_size,
                       COALESCE(g.pattern, '-') AS tread,
                       COALESCE(g.layer, '-') AS layer,
                       COALESCE(g.color, '-') AS color,
                       COUNT(i.sap_code) AS sap_count
                FROM tyre_process_groups g
                LEFT JOIN tyre_process_group_items i
                  ON i.group_id = g.id
                {where}
                GROUP BY g.id, g.group_key, g.tyre_size,
                         g.pattern, g.layer, g.color
                ORDER BY COUNT(i.sap_code) DESC, g.group_key
                LIMIT 1200
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


def _v30_load_smds_rows(search_text=""):
    search = str(search_text or "").strip()
    params = {}
    where = ""

    if search:
        where = """
            WHERE CAST(sap_code AS TEXT) ILIKE :search
               OR COALESCE(material_description, '') ILIKE :search
               OR COALESCE(key_code, '') ILIKE :search
               OR COALESCE(casing_type, '') ILIKE :search
        """
        params["search"] = f"%{search}%"

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM smds
                {where}
                ORDER BY sap_code
                LIMIT 1000
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


class _V30DataWorker(_V30QThread):
    completed = _V30Signal(str, object)
    failed = _V30Signal(str, str)

    def __init__(self, action, search_text=""):
        super().__init__()
        self.action = str(action)
        self.search_text = str(search_text or "")

    def run(self):
        try:
            if self.action in {"items", "size", "curing"}:
                rows = TyreItemRepository().list_items(
                    search_text=self.search_text
                )
            elif self.action == "line":
                rows = _v30_load_line_rows(self.search_text)
            elif self.action == "mold":
                rows = _v30_load_mold_rows(self.search_text)
            elif self.action == "groups":
                rows = _v30_load_group_rows(self.search_text)
            elif self.action == "smds":
                rows = _v30_load_smds_rows(self.search_text)
            else:
                rows = []

            self.completed.emit(self.action, rows)
        except Exception as exc:
            self.failed.emit(self.action, str(exc))


class _V30AIWorker(_V30QThread):
    completed = _V30Signal(object)
    failed = _V30Signal(str)

    def run(self):
        try:
            with _v30_get_session() as session:
                result = _V30TyreIntelligence.dashboard(session)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class _V30TrainAllWorker(_V30QThread):
    completed = _V30Signal(object)
    failed = _V30Signal(str)

    def run(self):
        try:
            with _v30_get_session() as session:
                result = _V30TyreIntelligence.request_train_all(session)
                session.commit()
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TyreItemMasterPage(QWidget):
    """Professional non-blocking Tyre Item Master workspace.

    V30 intentionally does not instantiate the old all-in-one page in the
    constructor. Data is fetched in background workers and rendered in chunks.
    The original full SMDS editor is available only when explicitly requested.
    """

    TABS = (
        ("Tyre Items", "items"),
        ("Tyre Size", "size"),
        ("Process & Curing", "curing"),
        ("Line Mapping", "line"),
        ("Mold & Casing", "mold"),
        ("Product Groups", "groups"),
        ("SMDS", "smds"),
        ("AI / ML", "ai"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._active_key = "items"
        self._tab_buttons = {}
        self._pages = {}
        self._tables = {}
        self._searches = {}
        self._status_labels = {}
        self._rows = {}
        self._render_tokens = {}
        self._data_worker = None
        self._ai_worker = None
        self._train_worker = None
        self._ai_dashboard = {}
        self._legacy_smds_dialog = None
        self._search_timer = _V30QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._reload_active)

        self._build_ui()

        # Event-loop handoff: shell paints first, data starts asynchronously.
        _V30QTimer.singleShot(
            0,
            lambda: self._activate_tab("Tyre Items", "items"),
        )
        _V30QTimer.singleShot(
            450,
            self._refresh_ai_background,
        )

    def _build_ui(self):
        self.setStyleSheet(
            """
            QWidget { font-family: "Segoe UI"; }

            QFrame#V30Header,
            QFrame#V30Panel,
            QFrame#V30Metric {
                background:#ffffff;
                border:1px solid #dbe4ef;
                border-radius:16px;
            }

            QLabel#V30Breadcrumb {
                color:#2563eb;
                font-size:9pt;
                font-weight:950;
            }

            QLabel#V30Title {
                color:#0f172a;
                font-size:24pt;
                font-weight:950;
            }

            QLabel#V30Subtitle {
                color:#64748b;
                font-size:9pt;
                font-weight:650;
            }

            QLabel#V30Health {
                background:#ecfdf5;
                color:#047857;
                border:1px solid #a7f3d0;
                border-radius:12px;
                padding:8px 12px;
                font-size:8.5pt;
                font-weight:950;
            }

            QPushButton#V30Tab {
                background:transparent;
                color:#334155;
                border:none;
                border-radius:0px;
                padding:10px 14px;
                font-size:9pt;
                font-weight:900;
            }

            QPushButton#V30Tab:hover {
                background:#eff6ff;
                color:#1d4ed8;
            }

            QPushButton#V30Tab:checked {
                background:#2563eb;
                color:#ffffff;
            }

            QPushButton#V30Primary {
                background:#2563eb;
                color:#ffffff;
                border:none;
                border-radius:9px;
                padding:9px 15px;
                font-weight:950;
            }

            QPushButton#V30Secondary {
                background:#e2e8f0;
                color:#0f172a;
                border:none;
                border-radius:9px;
                padding:9px 15px;
                font-weight:900;
            }

            QLineEdit {
                background:#ffffff;
                border:1px solid #cbd5e1;
                border-radius:9px;
                padding:8px 11px;
                color:#0f172a;
            }

            QLineEdit:focus {
                border:1px solid #2563eb;
            }

            QTableWidget {
                background:#ffffff;
                alternate-background-color:#f8fafc;
                border:1px solid #dbe4ef;
                gridline-color:#e2e8f0;
                selection-background-color:#dbeafe;
                selection-color:#0f172a;
            }

            QTableWidget::item {
                padding:6px 8px;
            }

            QHeaderView::section {
                background:#edf3f9;
                color:#1e293b;
                border:none;
                border-right:1px solid #dbe4ef;
                border-bottom:1px solid #dbe4ef;
                padding:9px 8px;
                font-weight:950;
            }

            QLabel#V30MetricValue {
                color:#0f172a;
                font-size:19pt;
                font-weight:950;
            }

            QLabel#V30MetricLabel {
                color:#64748b;
                font-size:8.3pt;
                font-weight:850;
            }

            QLabel#V30Notice {
                background:#f8fafc;
                color:#475569;
                border:1px solid #e2e8f0;
                border-radius:9px;
                padding:8px 10px;
                font-size:8.5pt;
                font-weight:700;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        header = QFrame()
        header.setObjectName("V30Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 14, 20, 14)
        header_layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        breadcrumb = QLabel("Data / Tyre Item Master")
        breadcrumb.setObjectName("V30Breadcrumb")

        title = QLabel("Tyre Item Master")
        title.setObjectName("V30Title")

        subtitle = QLabel(
            "Central tyre master, process rules, production compatibility "
            "and training-ready AI / ML intelligence."
        )
        subtitle.setObjectName("V30Subtitle")

        title_box.addWidget(breadcrumb)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header_layout.addLayout(title_box, 1)

        self._health_badge = QLabel("MASTER HEALTH  --")
        self._health_badge.setObjectName("V30Health")
        self._health_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._health_badge.setMinimumWidth(155)
        header_layout.addWidget(self._health_badge)

        root.addWidget(header)

        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(0)

        self._tab_group = _V30ButtonGroup(self)
        self._tab_group.setExclusive(True)

        for label, key in self.TABS:
            button = QPushButton(label)
            button.setObjectName("V30Tab")
            button.setCheckable(True)
            button.setMinimumHeight(38)
            button.clicked.connect(
                lambda checked=False, tab_label=label, tab_key=key:
                    self._activate_tab(tab_label, tab_key)
            )
            self._tab_group.addButton(button)
            self._tab_buttons[label] = button
            tab_layout.addWidget(button)

        tab_layout.addStretch()
        root.addLayout(tab_layout)

        self._stack = QStackedWidget()

        self._pages["items"] = self._build_data_page(
            "items",
            "Tyre Items",
            "SAP code and tyre description master.",
            ["SAP Code", "Description", "Tyre Size", "Status"],
            add_actions=True,
        )
        self._pages["size"] = self._build_data_page(
            "size",
            "Tyre Size",
            "Tyre size derived from the central item description.",
            ["SAP Code", "Description", "Tyre Size", "Status"],
            add_actions=True,
        )
        self._pages["curing"] = self._build_data_page(
            "curing",
            "Process & Curing",
            "Curing and handling master values used by production planning.",
            [
                "SAP Code",
                "Description",
                "Normal Curing",
                "Short Cycle",
                "Handling",
                "Status",
            ],
            add_actions=True,
        )
        self._pages["line"] = self._build_data_page(
            "line",
            "Line Mapping",
            "Production line, key code, casing and daily planning compatibility from SMDS.",
            [
                "SAP Code",
                "Description",
                "Line",
                "Key Code",
                "Casing",
                "Curing",
                "Day",
                "Night",
                "Total",
            ],
        )
        self._pages["mold"] = self._build_data_page(
            "mold",
            "Mold & Casing",
            "SMDS mold key code and casing-type control.",
            ["SAP Code", "Description", "Mold Key Code", "Casing Type"],
            mold_actions=True,
        )
        self._pages["groups"] = self._build_data_page(
            "groups",
            "Product Groups",
            "Tyre process-group mapping and linked SAP coverage.",
            ["Group Key", "Tyre Size", "Tread", "Layer", "Color", "SAP Count"],
        )
        self._pages["smds"] = self._build_data_page(
            "smds",
            "SMDS",
            "Central SMDS master preview. Full editor is loaded only on demand.",
            [
                "SAP Code",
                "Description",
                "Key Code",
                "Casing",
                "Curing",
                "Day",
                "Night",
                "Total",
                "Weight",
            ],
            smds_actions=True,
        )
        self._pages["ai"] = self._build_ai_page()

        for _, key in self.TABS:
            self._stack.addWidget(self._pages[key])

        root.addWidget(self._stack, 1)

    def _build_data_page(
        self,
        key,
        title_text,
        subtitle_text,
        headers,
        add_actions=False,
        mold_actions=False,
        smds_actions=False,
    ):
        page = QFrame()
        page.setObjectName("V30Panel")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)

        top = QHBoxLayout()
        text_box = QVBoxLayout()
        text_box.setSpacing(2)

        title = QLabel(title_text)
        title.setStyleSheet(
            "font-size:15pt;font-weight:950;color:#0f172a;"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("V30Subtitle")
        subtitle.setWordWrap(True)

        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        top.addLayout(text_box, 1)

        status = QLabel("Ready")
        status.setObjectName("V30Notice")
        self._status_labels[key] = status
        top.addWidget(status)

        search = QLineEdit()
        search.setPlaceholderText(f"Search {title_text.lower()}...")
        search.setMinimumWidth(330)
        search.textChanged.connect(
            lambda _value, tab_key=key: self._queue_search(tab_key)
        )
        self._searches[key] = search
        top.addWidget(search)

        if add_actions:
            add_btn = QPushButton("+ Add Tyre Item")
            add_btn.setObjectName("V30Primary")
            add_btn.clicked.connect(self._add_item)
            top.addWidget(add_btn)

            manage_btn = QPushButton("Manage Selected")
            manage_btn.setObjectName("V30Secondary")
            manage_btn.clicked.connect(
                lambda checked=False, tab_key=key:
                    self._manage_selected_item(tab_key)
            )
            top.addWidget(manage_btn)

        if mold_actions:
            edit_btn = QPushButton("Edit Selected")
            edit_btn.setObjectName("V30Primary")
            edit_btn.clicked.connect(self._edit_selected_mold)
            top.addWidget(edit_btn)

        if smds_actions:
            full_btn = QPushButton("Open Full SMDS Editor")
            full_btn.setObjectName("V30Primary")
            full_btn.clicked.connect(self._open_full_smds)
            top.addWidget(full_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("V30Secondary")
        refresh_btn.clicked.connect(
            lambda checked=False, tab_key=key: self._load_tab(tab_key)
        )
        top.addWidget(refresh_btn)

        layout.addLayout(top)

        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(
            _V30AbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            _V30AbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            _V30AbstractItemView.SelectionMode.SingleSelection
        )
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        table.horizontalHeader().setMinimumHeight(40)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        if len(headers) > 1:
            table.horizontalHeader().setSectionResizeMode(
                1,
                QHeaderView.ResizeMode.Stretch,
            )

        if add_actions:
            table.doubleClicked.connect(
                lambda _index, tab_key=key:
                    self._manage_selected_item(tab_key)
            )

        self._tables[key] = table
        layout.addWidget(table, 1)

        return page

    def _metric(self, key, label_text):
        card = QFrame()
        card.setObjectName("V30Metric")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)

        value = QLabel("0")
        value.setObjectName("V30MetricValue")
        label = QLabel(label_text)
        label.setObjectName("V30MetricLabel")
        label.setWordWrap(True)

        layout.addWidget(value)
        layout.addWidget(label)
        self._ai_metrics[key] = value
        return card

    def _build_ai_page(self):
        page = QFrame()
        page.setObjectName("V30Panel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        self._ai_metrics = {}

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Tyre Master AI / ML Training Suite")
        title.setStyleSheet(
            "font-size:15pt;font-weight:950;color:#0f172a;"
        )
        self._ai_history = QLabel("Historical evidence: loading...")
        self._ai_history.setObjectName("V30Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(self._ai_history)
        top.addLayout(title_box, 1)

        refresh_btn = QPushButton("Refresh Intelligence")
        refresh_btn.setObjectName("V30Secondary")
        refresh_btn.clicked.connect(self._refresh_ai_background)
        top.addWidget(refresh_btn)

        self._train_all_btn = QPushButton("Train All Models")
        self._train_all_btn.setObjectName("V30Primary")
        self._train_all_btn.setEnabled(False)
        self._train_all_btn.clicked.connect(self._train_all)
        top.addWidget(self._train_all_btn)

        layout.addLayout(top)

        metrics = QHBoxLayout()
        metrics.setSpacing(9)
        metrics.addWidget(self._metric("items", "Master Items"))
        metrics.addWidget(self._metric("health", "Master Health"))
        metrics.addWidget(self._metric("modules", "AI / ML Modules"))
        metrics.addWidget(self._metric("ready", "Ready To Train"))
        metrics.addWidget(self._metric("trained", "Trained Models"))
        layout.addLayout(metrics)

        notice = QLabel(
            "Official SMDS / tyre master data remains authoritative. "
            "AI / ML is advisory and never silently overwrites master values. "
            "All modules share one future Train-All pipeline."
        )
        notice.setObjectName("V30Notice")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self._ai_table = QTableWidget(0, 7)
        self._ai_table.setHorizontalHeaderLabels(
            [
                "Module",
                "Purpose",
                "Training Mode",
                "Min History",
                "Readiness",
                "Model Status",
                "Last Trained",
            ]
        )
        self._ai_table.setAlternatingRowColors(True)
        self._ai_table.setEditTriggers(
            _V30AbstractItemView.EditTrigger.NoEditTriggers
        )
        self._ai_table.verticalHeader().setVisible(False)
        self._ai_table.verticalHeader().setDefaultSectionSize(42)
        self._ai_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._ai_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._ai_table, 1)

        self._ai_notice = QLabel("AI / ML readiness is loading in background.")
        self._ai_notice.setObjectName("V30Notice")
        self._ai_notice.setWordWrap(True)
        layout.addWidget(self._ai_notice)

        return page

    def _activate_tab(self, label, key):
        self._active_key = key
        button = self._tab_buttons.get(label)
        if button is not None:
            button.setChecked(True)

        index = [item_key for _, item_key in self.TABS].index(key)
        self._stack.setCurrentIndex(index)

        if key == "ai":
            self._refresh_ai_background()
        else:
            self._load_tab(key)

    def _queue_search(self, key):
        if key != self._active_key:
            return
        self._search_timer.start()

    def _reload_active(self):
        if self._active_key != "ai":
            self._load_tab(self._active_key)

    def _load_tab(self, key):
        if key == "ai":
            self._refresh_ai_background()
            return

        if self._data_worker is not None and self._data_worker.isRunning():
            self._status_labels.get(key, QLabel()).setText(
                "Previous load finishing..."
            )
            return

        search = ""
        if key in self._searches:
            search = self._searches[key].text().strip()

        status = self._status_labels.get(key)
        if status is not None:
            status.setText("Loading in background...")

        worker = _V30DataWorker(key, search)
        worker.setParent(self)
        worker.completed.connect(self._data_loaded)
        worker.failed.connect(self._data_failed)
        worker.finished.connect(self._data_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._data_worker = worker
        worker.start()

    def _data_worker_finished(self):
        self._data_worker = None

    def _data_loaded(self, key, rows):
        self._rows[key] = list(rows or [])
        status = self._status_labels.get(key)
        if status is not None:
            status.setText(f"{len(self._rows[key]):,} rows")

        self._render_table_chunked(key)

    def _data_failed(self, key, message):
        status = self._status_labels.get(key)
        if status is not None:
            status.setText("Load failed")
            status.setToolTip(str(message))

        table = self._tables.get(key)
        if table is not None:
            table.setRowCount(0)

    def _display(self, value, default="-"):
        text_value = str(value or "").strip()
        return text_value if text_value else default

    def _item_values(self, key, row):
        if key in {"items", "size"}:
            return [
                row.get("sap_code"),
                row.get("description"),
                row.get("tyre_size"),
                row.get("status"),
            ]

        if key == "curing":
            return [
                row.get("sap_code"),
                row.get("description"),
                self._number(row.get("normal_curing_minutes")),
                self._number(row.get("short_cycle_curing_minutes")),
                self._number(row.get("handling_minutes")),
                row.get("status"),
            ]

        if key == "line":
            return [
                row.get("sap_code"),
                row.get("description"),
                row.get("production_line"),
                row.get("key_code"),
                row.get("casing_type"),
                row.get("curing"),
                self._number(row.get("day_plan")),
                self._number(row.get("night_plan")),
                self._number(row.get("total_plan")),
            ]

        if key == "mold":
            return [
                row.get("sap_code"),
                row.get("description"),
                row.get("mold_key_code"),
                row.get("casing_type"),
            ]

        if key == "groups":
            return [
                row.get("group_key"),
                row.get("tyre_size"),
                row.get("tread"),
                row.get("layer"),
                row.get("color"),
                row.get("sap_count"),
            ]

        if key == "smds":
            return [
                row.get("sap_code"),
                row.get("material_description") or row.get("description"),
                row.get("key_code"),
                row.get("casing_type"),
                row.get("normal_curing_minutes") or row.get("curing_cycle"),
                row.get("day_plan"),
                row.get("night_plan"),
                row.get("total_plan"),
                row.get("weight_per_tyre_kg") or row.get("weight_kg"),
            ]

        return []

    def _number(self, value):
        try:
            number = float(value or 0)
            if number == 0:
                return "-"
            if number.is_integer():
                return str(int(number))
            return f"{number:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return self._display(value)

    def _render_table_chunked(self, key):
        table = self._tables.get(key)
        rows = self._rows.get(key, [])

        if table is None:
            return

        token = int(self._render_tokens.get(key, 0)) + 1
        self._render_tokens[key] = token

        table.setUpdatesEnabled(False)
        table.clearContents()
        table.setRowCount(len(rows))
        table.setUpdatesEnabled(True)

        def render_from(start):
            if self._render_tokens.get(key) != token:
                return

            end = min(start + 120, len(rows))
            table.setUpdatesEnabled(False)

            for row_index in range(start, end):
                values = self._item_values(key, rows[row_index])

                for column, value in enumerate(values):
                    item = QTableWidgetItem(self._display(value))
                    if column != 1:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignCenter
                        )
                    table.setItem(row_index, column, item)

            table.setUpdatesEnabled(True)
            table.viewport().update()

            if end < len(rows):
                _V30QTimer.singleShot(
                    0,
                    lambda: render_from(end),
                )

        render_from(0)

    def _selected_row(self, key):
        table = self._tables.get(key)
        rows = self._rows.get(key, [])

        if table is None:
            return None

        current = table.currentRow()
        if current < 0 or current >= len(rows):
            return None

        return rows[current]

    def _add_item(self):
        dialog = TyreItemDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()
        try:
            TyreItemRepository().create_item(
                data["sap_code"],
                data["description"],
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Add Failed",
                f"Could not add tyre item.\n\n{exc}",
            )
            return

        self._load_tab(self._active_key)

    def _manage_selected_item(self, key):
        row = self._selected_row(key)
        if row is None:
            QMessageBox.information(
                self,
                "Tyre Item",
                "Select a tyre item first.",
            )
            return

        dialog = TyreItemDialog(self, row=row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()
        try:
            TyreItemRepository().update_item(
                int(row["id"]),
                data["sap_code"],
                data["description"],
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Update Failed",
                f"Could not update tyre item.\n\n{exc}",
            )
            return

        self._load_tab(key)

    def _edit_selected_mold(self):
        row = self._selected_row("mold")
        if row is None:
            QMessageBox.information(
                self,
                "Mold & Casing",
                "Select a row first.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Mold & Casing")
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(
            f"{row.get('sap_code', '')}  -  {row.get('description', '')}"
        )
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size:13pt;font-weight:950;color:#0f172a;"
        )
        layout.addWidget(title)

        form = QGridLayout()
        mold_input = QLineEdit(
            self._display(row.get("mold_key_code"))
        )
        casing_input = QLineEdit(
            self._display(row.get("casing_type"))
        )
        form.addWidget(QLabel("Mold Key Code"), 0, 0)
        form.addWidget(mold_input, 0, 1)
        form.addWidget(QLabel("Casing Type"), 1, 0)
        form.addWidget(casing_input, 1, 1)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE smds
                        SET key_code = :key_code,
                            casing_type = :casing_type,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": row.get("id"),
                        "key_code": mold_input.text().strip() or "-",
                        "casing_type": casing_input.text().strip() or "-",
                    },
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not update SMDS.\n\n{exc}",
            )
            return

        self._load_tab("mold")

    def _open_full_smds(self):
        if self._legacy_smds_dialog is not None:
            self._legacy_smds_dialog.raise_()
            self._legacy_smds_dialog.activateWindow()
            return

        self._status_labels["smds"].setText(
            "Opening full editor..."
        )

        # Explicit user action only. This heavy editor is never created during
        # Tyre Item Master page startup.
        dialog = QDialog(self)
        dialog.setWindowTitle("SMDS Master")
        dialog.resize(1450, 820)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(6, 6, 6, 6)

        try:
            editor = SMDSMasterPage(
                on_back=dialog.close
            )
            layout.addWidget(editor)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "SMDS Editor",
                f"Could not open full SMDS editor.\n\n{exc}",
            )
            dialog.deleteLater()
            self._status_labels["smds"].setText(
                "Full editor failed"
            )
            return

        dialog.finished.connect(
            lambda _result: self._smds_dialog_closed()
        )
        self._legacy_smds_dialog = dialog
        dialog.show()

    def _smds_dialog_closed(self):
        self._legacy_smds_dialog = None
        self._load_tab("smds")

    def _refresh_ai_background(self):
        if self._ai_worker is not None and self._ai_worker.isRunning():
            return

        self._ai_notice.setText(
            "Refreshing AI / ML readiness in background..."
        )
        worker = _V30AIWorker()
        worker.setParent(self)
        worker.completed.connect(self._ai_loaded)
        worker.failed.connect(self._ai_failed)
        worker.finished.connect(self._ai_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._ai_worker = worker
        worker.start()

    def _ai_worker_finished(self):
        self._ai_worker = None

    def _ai_failed(self, message):
        self._ai_notice.setText(
            f"AI / ML readiness unavailable: {message}"
        )

    def _ai_loaded(self, dashboard):
        self._ai_dashboard = dict(dashboard or {})
        master = self._ai_dashboard.get("master", {})
        history = self._ai_dashboard.get("history", {})

        health = float(master.get("health_score") or 0)
        self._health_badge.setText(
            f"MASTER HEALTH  {health:.1f}%"
        )

        self._ai_metrics["items"].setText(
            f"{int(master.get('items') or 0):,}"
        )
        self._ai_metrics["health"].setText(
            f"{health:.1f}%"
        )
        self._ai_metrics["modules"].setText(
            str(int(self._ai_dashboard.get("module_count") or 0))
        )
        self._ai_metrics["ready"].setText(
            str(int(self._ai_dashboard.get("ready_count") or 0))
        )
        self._ai_metrics["trained"].setText(
            str(int(self._ai_dashboard.get("trained_count") or 0))
        )

        self._ai_history.setText(
            "Historical evidence: "
            f"{int(history.get('historical_days') or 0):,} production days  •  "
            f"{int(history.get('historical_workbooks') or 0):,} workbooks"
        )

        modules = self._ai_dashboard.get("modules", [])
        self._ai_table.setRowCount(len(modules))

        for row_index, row in enumerate(modules):
            min_history = int(row.get("minimum_history_days") or 0)
            values = [
                row.get("name"),
                row.get("purpose"),
                row.get("training_mode"),
                "Master only" if min_history <= 0 else f"{min_history} days",
                row.get("readiness"),
                row.get("status"),
                row.get("last_trained_at") or "-",
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(self._display(value))
                if column in {0, 2, 3, 4, 5, 6}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                self._ai_table.setItem(
                    row_index,
                    column,
                    item,
                )

            readiness_item = self._ai_table.item(row_index, 4)
            if readiness_item is not None:
                readiness_item.setToolTip(
                    str(row.get("explanation") or "")
                )

        all_ready = bool(self._ai_dashboard.get("all_ready"))
        self._train_all_btn.setEnabled(all_ready)

        if all_ready:
            self._ai_notice.setText(
                "All AI / ML modules passed readiness gates. "
                "Train All is enabled for the shared training pipeline."
            )
        else:
            self._ai_notice.setText(
                f"{int(self._ai_dashboard.get('ready_count') or 0)} of "
                f"{int(self._ai_dashboard.get('module_count') or 0)} modules "
                "are training-ready. No fake training is performed."
            )

    def _train_all(self):
        if self._train_worker is not None and self._train_worker.isRunning():
            return

        self._train_all_btn.setEnabled(False)
        self._ai_notice.setText(
            "Validating the shared Train-All pipeline..."
        )

        worker = _V30TrainAllWorker()
        worker.setParent(self)
        worker.completed.connect(self._train_all_complete)
        worker.failed.connect(self._train_all_failed)
        worker.finished.connect(self._train_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._train_worker = worker
        worker.start()

    def _train_worker_finished(self):
        self._train_worker = None

    def _train_all_complete(self, result):
        self._ai_notice.setText(
            str(result.get("message") or result.get("status") or "")
        )
        self._refresh_ai_background()

    def _train_all_failed(self, message):
        self._ai_notice.setText(
            f"Train-All validation failed: {message}"
        )
        self._refresh_ai_background()

    # MainWindow compatibility hooks.
    def refresh(self):
        if self._active_key == "ai":
            self._refresh_ai_background()
        else:
            self._load_tab(self._active_key)

    refresh_page = refresh
    load_data = refresh

# MPPS V29 TYRE ITEM MASTER PRO + AI/ML WORKSPACE
from PySide6.QtCore import QThread as _TyreQThread, Signal as _TyreSignal
from PySide6.QtWidgets import (
    QAbstractItemView as _TyreAbstractItemView,
    QButtonGroup as _TyreButtonGroup,
)
from app.database import get_session as _tyre_get_session
from app.services.tyre_master_intelligence_service import (
    TyreMasterIntelligenceService as _TyreMasterIntelligenceService,
)


_LegacyTyreItemMasterPageV29 = TyreItemMasterPage


class _TyreMLWorkerV29(_TyreQThread):
    completed = _TyreSignal(object)
    failed = _TyreSignal(str)

    def run(self) -> None:
        try:
            with _tyre_get_session() as session:
                service = _TyreMasterIntelligenceService()
                result = service.request_train_all(session)
                session.commit()
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TyreItemMasterPage(QWidget):
    """Unified professional tyre master workspace.

    Existing master-data modules remain the operational editors. V29 replaces
    only the card-grid navigation with Factory-Capacity-style tabs and adds a
    training-ready AI/ML intelligence control tab.
    """

    TAB_MAP = (
        ("Tyre Items", 1),
        ("Tyre Size", 2),
        ("Process & Curing", 3),
        ("Line Mapping", 6),
        ("Mold & Casing", 5),
        ("Product Groups", 4),
        ("SMDS", 7),
        ("AI / ML", None),
    )

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._legacy = _LegacyTyreItemMasterPageV29()
        self._ai_service = _TyreMasterIntelligenceService()
        self._worker = None
        self._tab_buttons = {}
        self._metrics = {}

        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI";
            }

            QFrame#TyreProHeader,
            QFrame#TyreAISection,
            QFrame#TyreMetricCard {
                background: #ffffff;
                border: 1px solid #dbe4ef;
                border-radius: 16px;
            }

            QLabel#TyreBreadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 950;
            }

            QLabel#TyreTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#TyreSubtitle {
                color: #64748b;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#TyreStatusBadge {
                background: #ecfdf5;
                color: #047857;
                border: 1px solid #a7f3d0;
                border-radius: 12px;
                padding: 8px 13px;
                font-size: 8.5pt;
                font-weight: 950;
            }

            QPushButton#TyreTab {
                background: transparent;
                color: #334155;
                border: none;
                border-radius: 0px;
                padding: 10px 15px;
                font-size: 9pt;
                font-weight: 900;
            }

            QPushButton#TyreTab:hover {
                background: #eff6ff;
                color: #1d4ed8;
            }

            QPushButton#TyreTab:checked {
                background: #2563eb;
                color: #ffffff;
            }

            QLabel#TyreMetricValue {
                color: #0f172a;
                font-size: 20pt;
                font-weight: 950;
            }

            QLabel#TyreMetricLabel {
                color: #64748b;
                font-size: 8.4pt;
                font-weight: 850;
            }

            QLabel#TyreSectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#TyreNotice {
                background: #f8fafc;
                color: #475569;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 8.7pt;
                font-weight: 700;
            }

            QPushButton#TyrePrimary {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 9px 16px;
                font-weight: 950;
                min-height: 22px;
            }

            QPushButton#TyrePrimary:hover {
                background: #1d4ed8;
            }

            QPushButton#TyreSecondary {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 9px;
                padding: 9px 16px;
                font-weight: 900;
                min-height: 22px;
            }

            QTableWidget#TyreMLTable {
                background: #ffffff;
                border: 1px solid #dbe4ef;
                gridline-color: #e2e8f0;
                alternate-background-color: #f8fafc;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget#TyreMLTable::item {
                padding: 7px 9px;
            }

            QTableWidget#TyreMLTable QHeaderView::section {
                background: #edf3f9;
                color: #1e293b;
                border: none;
                border-right: 1px solid #dbe4ef;
                border-bottom: 1px solid #dbe4ef;
                padding: 9px 8px;
                font-weight: 950;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self._build_header())
        root.addLayout(self._build_tabs())

        self._content = QStackedWidget()
        self._content.addWidget(self._legacy)
        self._ai_page = self._build_ai_page()
        self._content.addWidget(self._ai_page)
        root.addWidget(self._content, 1)

        self._suppress_legacy_overview_chrome()
        self._select_tab("Tyre Items")
        self._refresh_ai()

    def _build_header(self):
        card = QFrame()
        card.setObjectName("TyreProHeader")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 15, 20, 15)
        layout.setSpacing(14)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)

        breadcrumb = QLabel("Data / Tyre Item Master")
        breadcrumb.setObjectName("TyreBreadcrumb")

        title = QLabel("Tyre Item Master")
        title.setObjectName("TyreTitle")

        subtitle = QLabel(
            "Central tyre master, process rules, production compatibility "
            "and training-ready AI / ML intelligence."
        )
        subtitle.setObjectName("TyreSubtitle")
        subtitle.setWordWrap(True)

        text_box.addWidget(breadcrumb)
        text_box.addWidget(title)
        text_box.addWidget(subtitle)

        layout.addLayout(text_box, 1)

        self._health_badge = QLabel("MASTER HEALTH  --")
        self._health_badge.setObjectName("TyreStatusBadge")
        self._health_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._health_badge.setMinimumWidth(150)
        layout.addWidget(self._health_badge)

        return card

    def _build_tabs(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        self._tab_group = _TyreButtonGroup(self)
        self._tab_group.setExclusive(True)

        for name, _legacy_index in self.TAB_MAP:
            button = QPushButton(name)
            button.setObjectName("TyreTab")
            button.setCheckable(True)
            button.setMinimumHeight(38)
            button.clicked.connect(
                lambda checked=False, tab_name=name: self._select_tab(tab_name)
            )
            self._tab_group.addButton(button)
            self._tab_buttons[name] = button
            layout.addWidget(button)

        layout.addStretch()
        return layout

    def _suppress_legacy_overview_chrome(self):
        for label in self._legacy.findChildren(QLabel):
            if label.objectName() in {
                "Breadcrumb",
                "PageTitle",
                "PageSubtitle",
            }:
                label.hide()

        for button in self._legacy.findChildren(QPushButton):
            caption = button.text().strip().lower()
            if caption in {
                "back",
                "← back",
                "back to tyre item master",
                "back to master",
            }:
                button.hide()

    def _select_tab(self, name: str):
        button = self._tab_buttons.get(name)
        if button is not None:
            button.setChecked(True)

        mapping = dict(self.TAB_MAP)
        legacy_index = mapping.get(name)

        if name == "AI / ML":
            self._content.setCurrentIndex(1)
            self._refresh_ai()
            return

        self._content.setCurrentIndex(0)

        if legacy_index is not None:
            try:
                self._legacy.stack.setCurrentIndex(int(legacy_index))
            except Exception:
                pass

        try:
            self._legacy.refresh()
        except Exception:
            pass

        self._suppress_legacy_overview_chrome()

    def _metric_card(self, key: str, caption: str):
        card = QFrame()
        card.setObjectName("TyreMetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(2)

        value = QLabel("0")
        value.setObjectName("TyreMetricValue")

        label = QLabel(caption)
        label.setObjectName("TyreMetricLabel")
        label.setWordWrap(True)

        layout.addWidget(value)
        layout.addWidget(label)

        self._metrics[key] = value
        return card

    def _build_ai_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        metrics.addWidget(self._metric_card("items", "Master Items"))
        metrics.addWidget(self._metric_card("health", "Master Health"))
        metrics.addWidget(self._metric_card("modules", "AI / ML Modules"))
        metrics.addWidget(self._metric_card("ready", "Ready To Train"))
        metrics.addWidget(self._metric_card("trained", "Trained Models"))
        root.addLayout(metrics)

        section = QFrame()
        section.setObjectName("TyreAISection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel("Tyre Master AI / ML Training Suite")
        title.setObjectName("TyreSectionTitle")

        self._history_label = QLabel("Historical data: --")
        self._history_label.setObjectName("TyreSubtitle")

        title_box.addWidget(title)
        title_box.addWidget(self._history_label)
        top.addLayout(title_box, 1)

        refresh_btn = QPushButton("Refresh Intelligence")
        refresh_btn.setObjectName("TyreSecondary")
        refresh_btn.clicked.connect(self._refresh_ai)
        top.addWidget(refresh_btn)

        self._train_all_btn = QPushButton("Train All Models")
        self._train_all_btn.setObjectName("TyrePrimary")
        self._train_all_btn.clicked.connect(self._request_train_all)
        top.addWidget(self._train_all_btn)

        layout.addLayout(top)

        notice = QLabel(
            "AI / ML is advisory. Official SMDS / tyre master values are never "
            "silently overwritten. V29 provides one shared Train-All pipeline "
            "and strict data-readiness gates; no fake model accuracy is created."
        )
        notice.setObjectName("TyreNotice")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self._module_table = QTableWidget(0, 8)
        self._module_table.setObjectName("TyreMLTable")
        self._module_table.setHorizontalHeaderLabels(
            [
                "Module",
                "Purpose",
                "Training Mode",
                "Data Source",
                "Min History",
                "Readiness",
                "Model Status",
                "Last Trained",
            ]
        )
        self._module_table.setAlternatingRowColors(True)
        self._module_table.setEditTriggers(
            _TyreAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._module_table.setSelectionBehavior(
            _TyreAbstractItemView.SelectionBehavior.SelectRows
        )
        self._module_table.verticalHeader().setVisible(False)
        self._module_table.verticalHeader().setDefaultSectionSize(44)

        header = self._module_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

        layout.addWidget(self._module_table, 1)

        self._training_notice = QLabel("")
        self._training_notice.setObjectName("TyreNotice")
        self._training_notice.setWordWrap(True)
        layout.addWidget(self._training_notice)

        root.addWidget(section, 1)
        return page

    def _refresh_ai(self):
        try:
            with _tyre_get_session() as session:
                dashboard = self._ai_service.dashboard(session)
                session.commit()
        except Exception as exc:
            self._training_notice.setText(
                f"AI / ML dashboard unavailable: {exc}"
            )
            return

        master = dashboard.get("master", {})
        history = dashboard.get("history", {})

        self._metrics["items"].setText(
            f"{int(master.get('items') or 0):,}"
        )
        self._metrics["health"].setText(
            f"{float(master.get('health_score') or 0):.1f}%"
        )
        self._metrics["modules"].setText(
            str(int(dashboard.get("module_count") or 0))
        )
        self._metrics["ready"].setText(
            str(int(dashboard.get("ready_count") or 0))
        )
        self._metrics["trained"].setText(
            str(int(dashboard.get("trained_count") or 0))
        )

        health = float(master.get("health_score") or 0)
        self._health_badge.setText(
            f"MASTER HEALTH  {health:.1f}%"
        )

        self._history_label.setText(
            "Historical evidence: "
            f"{int(history.get('historical_days') or 0):,} production days  •  "
            f"{int(history.get('historical_workbooks') or 0):,} workbooks"
        )

        modules = dashboard.get("modules", [])
        self._module_table.setRowCount(len(modules))

        for row_index, row in enumerate(modules):
            values = [
                row.get("name"),
                row.get("purpose"),
                row.get("training_mode"),
                row.get("data_source"),
                (
                    "Master only"
                    if int(row.get("minimum_history_days") or 0) <= 0
                    else f"{int(row.get('minimum_history_days') or 0)} days"
                ),
                row.get("readiness"),
                row.get("status"),
                row.get("last_trained_at") or "-",
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if column in {0, 4, 5, 6, 7}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                self._module_table.setItem(
                    row_index,
                    column,
                    item,
                )

            ready_item = self._module_table.item(row_index, 5)
            if ready_item is not None:
                ready_item.setToolTip(
                    str(row.get("explanation") or "")
                )

        all_ready = bool(dashboard.get("all_ready"))
        self._train_all_btn.setEnabled(all_ready)

        if all_ready:
            self._training_notice.setText(
                "All AI / ML modules passed data-readiness gates. "
                "The single Train-All orchestration pipeline is ready."
            )
        else:
            self._training_notice.setText(
                f"{int(dashboard.get('ready_count') or 0)} of "
                f"{int(dashboard.get('module_count') or 0)} modules are "
                "currently training-ready. Train All remains locked until "
                "every module has the required master/history evidence."
            )

    def _request_train_all(self):
        if self._worker and self._worker.isRunning():
            return

        self._train_all_btn.setEnabled(False)
        self._training_notice.setText(
            "Validating all Tyre Master AI / ML modules..."
        )

        self._worker = _TyreMLWorkerV29()
        self._worker.setParent(self)
        self._worker.completed.connect(
            self._train_all_complete
        )
        self._worker.failed.connect(
            self._train_all_failed
        )
        self._worker.finished.connect(
            self._worker.deleteLater
        )
        self._worker.start()

    def _train_all_complete(self, result):
        self._training_notice.setText(
            str(result.get("message") or result.get("status") or "")
        )
        self._worker = None
        self._refresh_ai()

    def _train_all_failed(self, message: str):
        self._training_notice.setText(
            f"Train-All validation failed: {message}"
        )
        self._worker = None
        self._refresh_ai()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_ai()
