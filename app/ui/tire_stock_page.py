from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from app.database import get_session


class TireStockPage(QWidget):
    """Read-only MPPS stock source-of-truth view."""

    def __init__(self, current_user_id=None):
        super().__init__()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search material code, description, or stock status..."
        )
        self.search_input.textChanged.connect(self.filter_table)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.count_label = QLabel("0 items")
        self.count_label.setObjectName("CountBadge")

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Material Code",
                "Description",
                "FG",
                "QC",
                "Scrap",
                "Blocked",
                "Available Stock",
                "Status",
            ]
        )
        self._setup_table()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("MPPS Stock Overview")
        title.setObjectName("SectionTitle")
        hint = QLabel(
            "MPPS Stock Planning is the current stock source of truth. Available "
            "stock is FG + QC - scrap - blocked."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        heading.addLayout(title_box, 1)
        heading.addWidget(self.count_label)
        heading.addWidget(self.refresh_btn)
        layout.addLayout(heading)
        layout.addWidget(self.search_input)
        layout.addWidget(self.table, 1)
        root.addWidget(card, 1)

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        widths = [130, 280, 75, 75, 75, 80, 110, 135]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card { background:white; border:1px solid #e2e8f0; border-radius:14px; }
            QLabel#SectionTitle { color:#0f172a; font-size:16pt; font-weight:900; }
            QLabel#SectionHint { color:#64748b; font-size:9pt; }
            QLabel#CountBadge { background:#dbeafe; color:#1e40af; border-radius:9px; padding:8px 12px; font-weight:900; }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QLineEdit { background:white; border:1px solid #cbd5e1; border-radius:8px; padding:8px 11px; }
            QTableWidget { background:white; border:1px solid #e2e8f0; border-radius:10px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:0; border-right:1px solid #e2e8f0; padding:9px; font-weight:900; }
            """
        )

    def refresh(self, *args) -> None:
        try:
            with get_session() as session:
                rows = list(
                    session.execute(
                        text(
                            """
                            SELECT
                                material_code,
                                item_description,
                                fg_stock,
                                qc_stock,
                                scrap_stock,
                                blocked_stock,
                                (
                                    fg_stock + qc_stock - scrap_stock - blocked_stock
                                )::INTEGER AS available_stock
                            FROM mpps_stock_items
                            WHERE is_active = TRUE
                            ORDER BY material_code;
                            """
                        )
                    ).mappings()
                )
        except Exception as exc:
            QMessageBox.critical(self, "MPPS Stock", str(exc))
            return

        self.table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)
            available = int(row["available_stock"] or 0)
            status = self._status(available)
            values = [
                row["material_code"],
                row["item_description"],
                f"{int(row['fg_stock'] or 0):,}",
                f"{int(row['qc_stock'] or 0):,}",
                f"{int(row['scrap_stock'] or 0):,}",
                f"{int(row['blocked_stock'] or 0):,}",
                f"{available:,}",
                status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column in {6, 7}:
                    self._style_status(item, available)
                self.table.setItem(row_index, column, item)
        self.filter_table()

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        visible = 0
        for row in range(self.table.rowCount()):
            text_value = " ".join(
                self.table.item(row, column).text()
                for column in range(self.table.columnCount())
                if self.table.item(row, column) is not None
            ).lower()
            hidden = bool(search and search not in text_value)
            self.table.setRowHidden(row, hidden)
            if not hidden:
                visible += 1
        self.count_label.setText(f"{visible:,} items")

    def _status(self, available: int) -> str:
        if available < 0:
            return "NEGATIVE STOCK"
        if available == 0:
            return "OUT OF STOCK"
        return "AVAILABLE"

    def _style_status(self, item: QTableWidgetItem, available: int) -> None:
        if available <= 0:
            colors = ("#991b1b", "#fee2e2")
        else:
            colors = ("#166534", "#dcfce7")
        item.setForeground(QColor(colors[0]))
        item.setBackground(QColor(colors[1]))
