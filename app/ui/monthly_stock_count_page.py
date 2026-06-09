from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.models import MonthlyStockCount, Role
from app.services.monthly_stock_count_service import MonthlyStockCountService


class SummaryCard(QFrame):
    def __init__(self, title: str, value: str = "0") -> None:
        super().__init__()

        self.setObjectName("SummaryCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("SummaryCardTitle")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("SummaryCardValue")
        self.value_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)


class MonthlyStockCountPage(QWidget):
    COL_MATERIAL = 0
    COL_DESCRIPTION = 1
    COL_FG = 2
    COL_QC = 3
    COL_BALANCE_TO_OVER_PRD = 4
    COL_OVER_PRD = 5
    COL_FINAL_STOCK = 6

    EDITABLE_COLUMN_FIELDS = {
        COL_FG: "fg_qty",
        COL_QC: "qc_qty",
        COL_BALANCE_TO_OVER_PRD: "balance_to_prd_qty",
        COL_OVER_PRD: "over_prd_qty",
    }

    VIEWER_ROLE_NAME = "Monthly Stock Viewer"

    MONTHS = [
        ("January", 1),
        ("February", 2),
        ("March", 3),
        ("April", 4),
        ("May", 5),
        ("June", 6),
        ("July", 7),
        ("August", 8),
        ("September", 9),
        ("October", 10),
        ("November", 11),
        ("December", 12),
    ]

    def __init__(self, current_user: Any | None = None) -> None:
        super().__init__()

        self.current_user = current_user
        self.is_viewer_mode = self._is_viewer_user()
        self.current_stock_count_id: int | None = None
        self.is_current_stock_editable = False
        self._loading_table = False
        self._loading_month_controls = False
        self._highlighted_row = -1
        self._highlight_brush = QBrush(QColor("#dbeafe"))
        self._default_brush = QBrush()

        self.setObjectName("MonthlyStockCountPage")
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#MonthlyStockCountPage {
                background: #f8fafc;
            }

            QFrame#HeaderCard,
            QFrame#UploadCard,
            QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 23pt;
                font-weight: 950;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 13pt;
                font-weight: 900;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9.5pt;
                font-weight: 850;
            }

            QLabel#SmallFieldLabel {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 800;
            }

            QLabel#InfoBadge {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 12px;
                padding: 7px 12px;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#EditBadge {
                background: #ecfdf5;
                color: #047857;
                border: 1px solid #a7f3d0;
                border-radius: 12px;
                padding: 7px 12px;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#ReadonlyBadge {
                background: #f8fafc;
                color: #64748b;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 7px 12px;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#SavingBadge {
                background: #fffbeb;
                color: #92400e;
                border: 1px solid #fde68a;
                border-radius: 12px;
                padding: 7px 12px;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#ErrorBadge {
                background: #fef2f2;
                color: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 12px;
                padding: 7px 12px;
                font-size: 9pt;
                font-weight: 850;
            }

            QFrame#SummaryCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#SummaryCardTitle {
                color: #64748b;
                font-size: 9pt;
                font-weight: 800;
            }

            QLabel#SummaryCardValue {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }

            QComboBox,
            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 10pt;
                font-weight: 650;
                min-height: 25px;
            }

            QComboBox:focus,
            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QComboBox:disabled,
            QLineEdit:disabled {
                background: #f8fafc;
                color: #64748b;
                border: 1px solid #e2e8f0;
            }

            QComboBox::drop-down {
                border: none;
                width: 24px;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 10pt;
                font-weight: 900;
                min-height: 25px;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 10pt;
                font-weight: 850;
                min-height: 25px;
            }

            QPushButton#SecondaryButton:hover {
                background: #eef2ff;
                border: 1px solid #93c5fd;
            }

            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9.5pt;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #334155;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 9px 8px;
                font-size: 9pt;
                font-weight: 900;
            }

            QTableWidget::item {
                padding: 6px;
            }

            QTableWidget::item:selected {
                background: #dbeafe;
                color: #0f172a;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_header_card())
        root.addWidget(self._build_upload_card())
        root.addLayout(self._build_summary_cards())
        root.addWidget(self._build_table_card(), 1)

    def _build_header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(0)

        title = QLabel("Monthly Stock Count")
        title.setObjectName("PageTitle")

        self.file_badge = QLabel("")
        self.file_badge.hide()

        self.mode_badge = QLabel("")
        self.mode_badge.hide()

        self.save_badge = QLabel("")
        self.save_badge.hide()

        layout.addWidget(title)

        return card

    def _build_upload_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("UploadCard")

        layout = QGridLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)

        section_title = "Month Selection" if self.is_viewer_mode else "Upload & Month Selection"

        title = QLabel(section_title)
        title.setObjectName("SectionTitle")

        self.stock_month_combo = QComboBox()
        self.stock_month_combo.setMinimumWidth(150)

        for month_name, month_number in self.MONTHS:
            self.stock_month_combo.addItem(month_name, month_number)

        self.stock_year_combo = QComboBox()
        self.stock_year_combo.setMinimumWidth(105)

        current_date = QDate.currentDate()
        current_year = current_date.year()

        for year in range(current_year - 5, current_year + 6):
            self.stock_year_combo.addItem(str(year), year)

        self.stock_month_combo.setCurrentIndex(current_date.month() - 1)

        year_index = self.stock_year_combo.findData(current_year)
        if year_index >= 0:
            self.stock_year_combo.setCurrentIndex(year_index)

        self.stock_month_combo.currentIndexChanged.connect(self._on_stock_month_changed)
        self.stock_year_combo.currentIndexChanged.connect(self._on_stock_month_changed)

        self.month_selector = QComboBox()
        self.month_selector.setMinimumWidth(420)
        self.month_selector.currentIndexChanged.connect(self._on_month_selection_changed)

        self.search_input = QLineEdit()
        self.search_input.setMinimumWidth(260)
        self.search_input.setPlaceholderText("Search by Material or Description")
        self.search_input.textChanged.connect(self._on_search_changed)

        self.upload_button = QPushButton("Upload Excel")
        self.upload_button.setObjectName("PrimaryButton")
        self.upload_button.clicked.connect(self._upload_excel)

        if self.is_viewer_mode:
            self.upload_button.hide()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("SecondaryButton")
        self.refresh_button.clicked.connect(self.refresh)

        stock_month_label = QLabel("Stock Month")
        stock_month_label.setObjectName("FieldLabel")

        month_label = QLabel("Month")
        month_label.setObjectName("SmallFieldLabel")

        year_label = QLabel("Year")
        year_label.setObjectName("SmallFieldLabel")

        previous_month_label = QLabel("View Uploaded Stock Month")
        previous_month_label.setObjectName("FieldLabel")

        search_label = QLabel("Search")
        search_label.setObjectName("FieldLabel")

        layout.addWidget(title, 0, 0, 1, 6)

        layout.addWidget(stock_month_label, 1, 0, 1, 2)
        layout.addWidget(previous_month_label, 1, 2, 1, 2)
        layout.addWidget(search_label, 1, 4, 1, 1)

        layout.addWidget(month_label, 2, 0)
        layout.addWidget(year_label, 2, 1)

        layout.addWidget(self.stock_month_combo, 3, 0)
        layout.addWidget(self.stock_year_combo, 3, 1)
        layout.addWidget(self.month_selector, 3, 2, 1, 2)
        layout.addWidget(self.search_input, 3, 4)

        if not self.is_viewer_mode:
            layout.addWidget(self.upload_button, 3, 5)
            layout.addWidget(self.refresh_button, 3, 6)
        else:
            layout.addWidget(self.refresh_button, 3, 5)

        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 1)
        layout.setColumnStretch(4, 2)
        layout.setColumnStretch(5, 0)
        layout.setColumnStretch(6, 0)

        return card

    def _build_summary_cards(self) -> QGridLayout:
        layout = QGridLayout()
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        self.total_materials_card = SummaryCard("Total Materials", "0")
        self.total_fg_card = SummaryCard("Total FG", "0")
        self.total_qc_card = SummaryCard("Total QC", "0")
        self.total_balance_card = SummaryCard("Total Balance to Over PRD", "0")
        self.total_over_prd_card = SummaryCard("Total Over PRD", "0")
        self.total_final_stock_card = SummaryCard("Total Final Stock", "0")

        cards = [
            self.total_materials_card,
            self.total_fg_card,
            self.total_qc_card,
            self.total_balance_card,
            self.total_over_prd_card,
            self.total_final_stock_card,
        ]

        for index, card_item in enumerate(cards):
            layout.addWidget(card_item, 0, index)

        if self.is_viewer_mode:
            self.total_balance_card.hide()
            self.total_over_prd_card.hide()

        return layout

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = QLabel("Stock Count Lines")
        title.setObjectName("SectionTitle")

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            [
                "Material",
                "Description",
                "FG",
                "QC",
                "Balance to Over PRD",
                "Over PRD",
                "Final Stock",
            ]
        )

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        if self.is_viewer_mode:
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        else:
            self.table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
            )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_MATERIAL, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_FG, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_QC, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_BALANCE_TO_OVER_PRD, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_OVER_PRD, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_FINAL_STOCK, QHeaderView.ResizeMode.ResizeToContents)

        self.table.verticalHeader().setVisible(False)

        if self.is_viewer_mode:
            self.table.setColumnHidden(self.COL_BALANCE_TO_OVER_PRD, True)
            self.table.setColumnHidden(self.COL_OVER_PRD, True)

        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.cellChanged.connect(self._on_cell_changed)

        title_row.addWidget(title)
        title_row.addStretch()

        layout.addLayout(title_row)
        layout.addWidget(self.table, 1)

        return card

    def refresh(self) -> None:
        selected_id = self.current_stock_count_id

        self._load_month_selector(selected_id)

        if self.current_stock_count_id is None:
            self._show_need_to_upload_state()
            return

        self._load_selected_stock_count()

    def _selected_month_info(self) -> tuple[str, str]:
        month_number = int(self.stock_month_combo.currentData())
        month_name = self.stock_month_combo.currentText()
        year_value = int(self.stock_year_combo.currentData())

        month_key = f"{year_value:04d}-{month_number:02d}"
        stock_month_label = f"{month_name} {year_value}"

        return month_key, stock_month_label

    def _on_stock_month_changed(self) -> None:
        if self._loading_month_controls:
            return

        self.current_stock_count_id = None
        self._load_month_selector(None)

        if self.current_stock_count_id is None:
            self._show_need_to_upload_state()
            return

        self._load_selected_stock_count()

    def _show_need_to_upload_state(self) -> None:
        _, stock_month_label = self._selected_month_info()

        self._clear_table()
        self._reset_summary_cards()

        self.file_badge.setText(f"{stock_month_label} | Need to upload stock count")
        self._set_badge(self.mode_badge, "Need to upload", "ReadonlyBadge")
        self._set_badge(self.save_badge, "Ready", "ReadonlyBadge")

    def _load_month_selector(self, preferred_stock_count_id: int | None = None) -> None:
        selected_month_key, selected_month_label = self._selected_month_info()

        self.month_selector.blockSignals(True)
        self.month_selector.clear()

        records: list[dict[str, Any]] = []

        try:
            with get_session() as session:
                service = MonthlyStockCountService(session)
                stock_counts = service.list_stock_counts()

                for stock_count in stock_counts:
                    if stock_count.month_key != selected_month_key:
                        continue

                    records.append(
                        {
                            "id": stock_count.id,
                            "label": stock_count.stock_month_label,
                            "month_key": stock_count.month_key,
                            "file_name": stock_count.file_name,
                            "uploaded_at": stock_count.uploaded_at,
                            "is_active": stock_count.is_active,
                            "status": stock_count.status,
                        }
                    )
        except Exception as exc:
            self.month_selector.blockSignals(False)
            QMessageBox.warning(self, "Stock Count Load Error", str(exc))
            return

        if not records:
            self.current_stock_count_id = None
            self.month_selector.addItem(
                f"{selected_month_label}  |  Need to upload stock count",
                None,
            )
            self.month_selector.setEnabled(False)
            self.month_selector.blockSignals(False)
            return

        self.month_selector.setEnabled(True)

        selected_index = 0

        for index, record in enumerate(records):
            active_label = "Active" if record["is_active"] else "Archived"
            uploaded_at = self._format_datetime(record["uploaded_at"])
            label = f"{record['label']}  |  {active_label}  |  {record['file_name']}  |  {uploaded_at}"

            self.month_selector.addItem(label, record["id"])

            if preferred_stock_count_id is not None and record["id"] == preferred_stock_count_id:
                selected_index = index

        self.month_selector.setCurrentIndex(selected_index)
        self.current_stock_count_id = self.month_selector.itemData(selected_index)
        self.month_selector.blockSignals(False)

    def _on_month_selection_changed(self, index: int) -> None:
        if index < 0:
            return

        stock_count_id = self.month_selector.itemData(index)
        self.current_stock_count_id = stock_count_id

        if stock_count_id is None:
            self._show_need_to_upload_state()
            return

        self._load_selected_stock_count()

    def _on_search_changed(self) -> None:
        if self.current_stock_count_id is None:
            return

        self._load_selected_stock_count()

    def _load_selected_stock_count(self) -> None:
        stock_count_id = self.current_stock_count_id

        if stock_count_id is None:
            self._show_need_to_upload_state()
            return

        search_text = self.search_input.text().strip()

        try:
            with get_session() as session:
                service = MonthlyStockCountService(session)
                stock_count = session.get(MonthlyStockCount, stock_count_id)

                if stock_count is None:
                    raise ValueError("Selected stock count was not found.")

                self.is_current_stock_editable = (
                    not self.is_viewer_mode
                    and stock_count.is_active
                )

                summary = service.get_summary(stock_count.id)
                lines = service.get_lines(stock_count.id, search_text)

                stock_info = {
                    "label": stock_count.stock_month_label,
                    "file_name": stock_count.file_name,
                    "uploaded_at": stock_count.uploaded_at,
                    "total_rows": stock_count.total_rows,
                    "is_active": stock_count.is_active,
                    "status": stock_count.status,
                }

                line_data = [
                    {
                        "id": line.id,
                        "material_code": line.material_code,
                        "material_description": line.material_description or "",
                        "fg_qty": line.fg_qty,
                        "qc_qty": line.qc_qty,
                        "balance_to_prd_qty": line.balance_to_prd_qty,
                        "over_prd_qty": line.over_prd_qty,
                        "final_stock_qty": line.final_stock_qty,
                    }
                    for line in lines
                ]

        except Exception as exc:
            QMessageBox.warning(self, "Stock Count Error", str(exc))
            return

        self._update_header_badges(stock_info)
        self._update_summary_cards(summary)
        self._populate_table(line_data)

    def _upload_excel(self) -> None:
        if self.is_viewer_mode:
            QMessageBox.warning(
                self,
                "View Only Access",
                "This user has view-only access and cannot upload stock files.",
            )
            return

        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Monthly Stock Count Excel File",
            "",
            "Excel Files (*.xlsx *.xlsm *.xltx *.xltm);;All Files (*.*)",
        )

        if not selected_file:
            return

        month_key, stock_month_label = self._selected_month_info()
        uploaded_by = self._current_username()

        self.upload_button.setEnabled(False)
        self.upload_button.setText("Importing...")

        try:
            with get_session() as session:
                service = MonthlyStockCountService(session)
                stock_count = service.import_excel(
                    file_path=Path(selected_file),
                    month_key=month_key,
                    stock_month_label=stock_month_label,
                    uploaded_by=uploaded_by,
                )

                imported_id = stock_count.id
                imported_rows = stock_count.total_rows

            QMessageBox.information(
                self,
                "Stock Import Complete",
                f"{stock_month_label} stock count imported successfully.\n\n"
                f"Imported rows: {imported_rows}",
            )

            self.current_stock_count_id = imported_id
            self._load_month_selector(imported_id)
            self._load_selected_stock_count()

        except Exception as exc:
            QMessageBox.critical(self, "Stock Import Failed", str(exc))
        finally:
            self.upload_button.setEnabled(True)
            self.upload_button.setText("Upload Excel")

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        self._loading_table = True
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))

        if self._highlighted_row >= len(rows):
            self._highlighted_row = -1

        for row_index, row in enumerate(rows):
            self._set_readonly_item(row_index, self.COL_MATERIAL, row["material_code"])
            self._set_readonly_item(row_index, self.COL_DESCRIPTION, row["material_description"])

            self._set_stock_value_item(
                row=row_index,
                column=self.COL_FG,
                line_id=row["id"],
                field_name="fg_qty",
                value=row["fg_qty"],
            )
            self._set_stock_value_item(
                row=row_index,
                column=self.COL_QC,
                line_id=row["id"],
                field_name="qc_qty",
                value=row["qc_qty"],
            )
            self._set_stock_value_item(
                row=row_index,
                column=self.COL_BALANCE_TO_OVER_PRD,
                line_id=row["id"],
                field_name="balance_to_prd_qty",
                value=row["balance_to_prd_qty"],
            )
            self._set_stock_value_item(
                row=row_index,
                column=self.COL_OVER_PRD,
                line_id=row["id"],
                field_name="over_prd_qty",
                value=row["over_prd_qty"],
            )

            self._set_readonly_item(
                row_index,
                self.COL_FINAL_STOCK,
                self._format_decimal(row["final_stock_qty"]),
                align_right=True,
            )

        self._loading_table = False

        if self._highlighted_row >= 0:
            self._apply_row_highlight(self._highlighted_row)

    def _set_readonly_item(
        self,
        row: int,
        column: int,
        value: str,
        align_right: bool = False,
    ) -> None:
        item = QTableWidgetItem(value)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.table.setItem(row, column, item)

    def _set_stock_value_item(
        self,
        row: int,
        column: int,
        line_id: int,
        field_name: str,
        value: Decimal | int | float | str | None,
    ) -> None:
        text = self._format_decimal(value)

        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setData(Qt.ItemDataRole.UserRole, line_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, field_name)
        item.setData(Qt.ItemDataRole.UserRole + 2, text)

        if self.is_current_stock_editable and not self.is_viewer_mode:
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
        else:
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        self.table.setItem(row, column, item)

    def _on_table_cell_clicked(self, row: int, column: int) -> None:
        self._apply_row_highlight(row)

    def _on_current_cell_changed(
        self,
        current_row: int,
        current_column: int,
        previous_row: int,
        previous_column: int,
    ) -> None:
        if current_row >= 0:
            self._apply_row_highlight(current_row)

    def _apply_row_highlight(self, selected_row: int) -> None:
        if self._loading_table:
            return

        self._highlighted_row = selected_row

        for row in range(self.table.rowCount()):
            brush = self._highlight_brush if row == selected_row else self._default_brush

            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)

                if item is not None:
                    item.setBackground(brush)

    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._loading_table:
            return

        if self.is_viewer_mode:
            return

        if column not in self.EDITABLE_COLUMN_FIELDS:
            return

        if not self.is_current_stock_editable:
            return

        item = self.table.item(row, column)
        if item is None:
            return

        line_id = item.data(Qt.ItemDataRole.UserRole)
        field_name = item.data(Qt.ItemDataRole.UserRole + 1)
        old_text = item.data(Qt.ItemDataRole.UserRole + 2) or "0"

        if line_id is None or field_name is None:
            return

        new_value_text = item.text().strip()

        try:
            new_value = self._parse_decimal(new_value_text)
        except ValueError as exc:
            self._restore_cell_value(row, column, old_text)
            self._set_badge(self.save_badge, "Not saved", "ErrorBadge")
            QMessageBox.warning(self, "Invalid Stock Value", str(exc))
            return

        old_value = self._parse_decimal(str(old_text))
        if new_value == old_value:
            self._restore_cell_value(row, column, old_text)
            return

        self._set_badge(self.save_badge, "Saving...", "SavingBadge")

        try:
            with get_session() as session:
                service = MonthlyStockCountService(session)
                updated_line = service.update_stock_value(
                    line_id=line_id,
                    field_name=str(field_name),
                    new_value=new_value,
                    username=self._current_username(),
                )

                updated_values = {
                    "fg_qty": updated_line.fg_qty,
                    "qc_qty": updated_line.qc_qty,
                    "balance_to_prd_qty": updated_line.balance_to_prd_qty,
                    "over_prd_qty": updated_line.over_prd_qty,
                    "final_stock_qty": updated_line.final_stock_qty,
                }

            self._loading_table = True
            self._update_row_after_save(row, updated_values)
            self._loading_table = False

            self._set_badge(self.save_badge, "Saved", "EditBadge")
            self._reload_summary_only()

            if self._highlighted_row >= 0:
                self._apply_row_highlight(self._highlighted_row)

        except Exception as exc:
            self._loading_table = False
            self._restore_cell_value(row, column, old_text)
            self._set_badge(self.save_badge, "Not saved", "ErrorBadge")
            QMessageBox.warning(self, "Auto Save Failed", str(exc))

    def _update_row_after_save(self, row: int, values: dict[str, Any]) -> None:
        column_field_map = {
            self.COL_FG: "fg_qty",
            self.COL_QC: "qc_qty",
            self.COL_BALANCE_TO_OVER_PRD: "balance_to_prd_qty",
            self.COL_OVER_PRD: "over_prd_qty",
        }

        for column, field_name in column_field_map.items():
            item = self.table.item(row, column)
            if item is None:
                continue

            text = self._format_decimal(values[field_name])
            item.setText(text)
            item.setData(Qt.ItemDataRole.UserRole + 2, text)

        final_item = self.table.item(row, self.COL_FINAL_STOCK)
        final_text = self._format_decimal(values["final_stock_qty"])

        if final_item is None:
            self._set_readonly_item(row, self.COL_FINAL_STOCK, final_text, align_right=True)
        else:
            final_item.setText(final_text)

    def _restore_cell_value(self, row: int, column: int, old_text: str) -> None:
        self._loading_table = True

        item = self.table.item(row, column)
        if item is not None:
            item.setText(str(old_text))

        self._loading_table = False

    def _reload_summary_only(self) -> None:
        if self.current_stock_count_id is None:
            return

        try:
            with get_session() as session:
                service = MonthlyStockCountService(session)
                summary = service.get_summary(self.current_stock_count_id)

            self._update_summary_cards(summary)
        except Exception:
            pass

    def _update_header_badges(self, stock_info: dict[str, Any]) -> None:
        uploaded_at = self._format_datetime(stock_info["uploaded_at"])
        self.file_badge.setText(
            f"{stock_info['label']} | {stock_info['file_name']} | Uploaded {uploaded_at}"
        )

        if self.is_viewer_mode:
            self._set_badge(self.mode_badge, "View only", "ReadonlyBadge")
        elif self.is_current_stock_editable:
            self._set_badge(self.mode_badge, "Latest active month - editable", "EditBadge")
        else:
            self._set_badge(self.mode_badge, "Previous / archived month - view only", "ReadonlyBadge")

    def _update_summary_cards(self, summary: Any) -> None:
        self.total_materials_card.value_label.setText(str(summary.total_materials))
        self.total_fg_card.value_label.setText(self._format_decimal(summary.total_fg))
        self.total_qc_card.value_label.setText(self._format_decimal(summary.total_qc))
        self.total_balance_card.value_label.setText(self._format_decimal(summary.total_balance_to_prd))
        self.total_over_prd_card.value_label.setText(self._format_decimal(summary.total_over_prd))
        self.total_final_stock_card.value_label.setText(self._format_decimal(summary.total_final_stock))

    def _reset_summary_cards(self) -> None:
        self.total_materials_card.value_label.setText("0")
        self.total_fg_card.value_label.setText("0")
        self.total_qc_card.value_label.setText("0")
        self.total_balance_card.value_label.setText("0")
        self.total_over_prd_card.value_label.setText("0")
        self.total_final_stock_card.value_label.setText("0")

    def _clear_table(self) -> None:
        self._loading_table = True
        self.table.setRowCount(0)
        self._loading_table = False
        self._highlighted_row = -1

    def _set_badge(self, label: QLabel, text: str, object_name: str) -> None:
        label.setText(text)
        label.setObjectName(object_name)
        label.style().unpolish(label)
        label.style().polish(label)

    def _current_username(self) -> str:
        if self.current_user is None:
            return "system"

        username = getattr(self.current_user, "username", None)
        if username:
            return str(username)

        full_name = getattr(self.current_user, "full_name", None)
        if full_name:
            return str(full_name)

        return "system"

    def _current_role_name(self) -> str:
        if self.current_user is None:
            return ""

        try:
            role = getattr(self.current_user, "role", None)

            if role is not None:
                role_name = str(getattr(role, "role_name", "") or "").strip()
                if role_name:
                    return role_name
        except Exception:
            pass

        role_id = getattr(self.current_user, "role_id", None)
        if role_id is None:
            return ""

        try:
            with get_session() as session:
                role = session.get(Role, role_id)
                if role is None:
                    return ""
                return str(role.role_name or "").strip()
        except Exception:
            return ""

    def _is_viewer_user(self) -> bool:
        return self._current_role_name().lower() == self.VIEWER_ROLE_NAME.lower()

    @staticmethod
    def _format_decimal(value: Decimal | int | float | str | None) -> str:
        if value is None:
            return "0"

        try:
            decimal_value = Decimal(str(value)).quantize(Decimal("0.001"))
        except (InvalidOperation, ValueError):
            return "0"

        text = format(decimal_value, "f")

        if "." in text:
            text = text.rstrip("0").rstrip(".")

        return text or "0"

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        text = value.strip().replace(",", "")

        if not text:
            return Decimal("0.000")

        try:
            number = Decimal(text).quantize(Decimal("0.001"))
        except InvalidOperation as exc:
            raise ValueError("Please enter a valid number.") from exc

        if number < 0:
            raise ValueError("Stock value cannot be negative.")

        return number

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "-"

        return value.strftime("%Y-%m-%d %H:%M")
