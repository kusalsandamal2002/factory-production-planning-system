from pathlib import Path

path = Path("app/ui/tyre_item_master_page.py")

code = r'''
from __future__ import annotations

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
                ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'Active'
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS remarks TEXT NOT NULL DEFAULT ''
            """))

    def list_items(self, search_text: str = "") -> list[dict]:
        self.ensure_table()

        query = """
            SELECT id, sap_code, description, status
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
                    INSERT INTO tyre_item_master (sap_code, description, status)
                    VALUES (:sap_code, :description, 'Active')
                """),
                {"sap_code": sap_code, "description": description},
            )

    def update_item(self, item_id: int, sap_code: str, description: str) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tyre_item_master
                    SET sap_code = :sap_code,
                        description = :description,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": item_id, "sap_code": sap_code, "description": description},
            )

    def delete_item(self, item_id: int) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM tyre_item_master WHERE id = :id"),
                {"id": item_id},
            )


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

        breadcrumb = QLabel("Master Data  /  Tyre Item Master")
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
                "ITEM DATA",
                "Tyre Item Data",
                "Maintain SAP code and tyre description table.",
                self._open_item_data,
                True,
            ),
            (
                "CURING TIME",
                "Production / Curing Time",
                "Maintain curing cycle, handling time, day rate and night rate.",
                None,
                False,
            ),
            (
                "LINE RULES",
                "Line & Process Mapping",
                "Map tyre items to production line, process type and category.",
                None,
                False,
            ),
            (
                "MOLD / CASING",
                "Mold & Casing Rules",
                "Maintain mold count, casing type and item compatibility.",
                None,
                False,
            ),
            (
                "PRODUCT GROUP",
                "Weight & Product Group",
                "Maintain item weight, color, layer and product family.",
                None,
                False,
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

        breadcrumb = QLabel("Master Data  /  Tyre Item Master  /  Item Data")
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

    def _open_item_data(self) -> None:
        self.stack.setCurrentIndex(1)
        self.refresh()

    def _back_to_overview(self) -> None:
        self.stack.setCurrentIndex(0)
        self.refresh()

    def refresh(self) -> None:
        try:
            search_text = self.search_input.text().strip() if hasattr(self, "search_input") else ""
            self.items = self.repo.list_items(search_text=search_text)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load tyre items.\n\n{exc}")
            self.items = []

        if hasattr(self, "table"):
            self._refresh_table()

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


TireItemMasterPage = TyreItemMasterPage
'''

path.write_text(code, encoding="utf-8")
print("Tyre Item Master converted to module-card hub layout.")
