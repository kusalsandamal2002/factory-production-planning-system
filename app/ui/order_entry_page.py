from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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

from app.database import get_session
from app.services.shipment_demand_service import (
    ShipmentDemandRow,
    load_shipment_demands,
)


class ShipmentDemandPage(QWidget):
    def __init__(
        self,
        current_user=None,
        *,
        title: str = "Customer / Shipment Demand",
        subtitle: str = (
            "MPPS shipment demand by customer, material, due date, status, and note."
        ),
    ):
        super().__init__()
        self.current_user = current_user
        self.title_text = title
        self.subtitle_text = subtitle
        self.rows: list[ShipmentDemandRow] = []
        self.visible_rows: list[ShipmentDemandRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search customer, material code, description, status, or note..."
        )
        self.search_input.textChanged.connect(self.filter_table)
        self.status_combo = QComboBox()
        self.status_combo.addItems(
            [
                "ALL",
                "PENDING",
                "CONFIRMED",
                "PLANNED",
                "PARTIALLY_PLANNED",
                "COMPLETED",
                "CANCELLED",
            ]
        )
        self.status_combo.currentTextChanged.connect(self.filter_table)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.count_label = QLabel("0 demands")
        self.count_label.setObjectName("CountBadge")

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Customer",
                "Material Code",
                "Item Description",
                "Demand Qty",
                "Due Date",
                "Priority",
                "Status",
                "Manager Note",
                "Demand ID",
            ]
        )
        self.table.setColumnHidden(8, True)
        self._setup_table()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        header_card = QFrame()
        header_card.setObjectName("Card")
        layout = QVBoxLayout(header_card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(self.title_text)
        title.setObjectName("SectionTitle")
        subtitle = QLabel(self.subtitle_text)
        subtitle.setObjectName("SectionHint")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box, 1)
        heading.addWidget(self.count_label)
        heading.addWidget(self.refresh_btn)
        layout.addLayout(heading)

        notice = QLabel(
            "Receive-date estimation will be based on quantity capacity planning "
            "after demand is saved. The retired tire-type minute scheduler is not used."
        )
        notice.setObjectName("Notice")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 1)
        filters.addWidget(QLabel("Status"))
        filters.addWidget(self.status_combo)
        layout.addLayout(filters)
        root.addWidget(header_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.addWidget(self.table)
        root.addWidget(table_card, 1)

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        widths = [170, 125, 250, 95, 100, 105, 135, 260, 80]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card { background:white; border:1px solid #e2e8f0; border-radius:14px; }
            QLabel#SectionTitle { color:#0f172a; font-size:16pt; font-weight:900; }
            QLabel#SectionHint { color:#64748b; font-size:9pt; }
            QLabel#CountBadge { background:#dbeafe; color:#1e40af; border-radius:9px; padding:8px 12px; font-weight:900; }
            QLabel#Notice { background:#eff6ff; color:#1e3a8a; border:1px solid #bfdbfe; border-radius:9px; padding:10px 12px; }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:0; border-radius:9px; padding:9px 15px; font-weight:900; }
            QLineEdit, QComboBox { background:white; border:1px solid #cbd5e1; border-radius:8px; padding:7px 10px; }
            QTableWidget { background:white; border:1px solid #e2e8f0; border-radius:10px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:0; border-right:1px solid #e2e8f0; padding:9px; font-weight:900; }
            """
        )

    def refresh(self, *args) -> None:
        try:
            with get_session() as session:
                self.rows = load_shipment_demands(session)
            self.filter_table()
        except Exception as exc:
            QMessageBox.critical(self, "Shipment Demand", str(exc))

    def filter_table(self, *args) -> None:
        search = self.search_input.text().strip().lower()
        status = self.status_combo.currentText()
        self.visible_rows = []
        for row in self.rows:
            if status != "ALL" and row.status != status:
                continue
            searchable = (
                f"{row.customer_name} {row.material_code} {row.item_description} "
                f"{row.status} {row.manager_note}"
            ).lower()
            if search and search not in searchable:
                continue
            self.visible_rows.append(row)
        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for row_index, row in enumerate(self.visible_rows):
            self.table.insertRow(row_index)
            values = [
                row.customer_name,
                row.material_code,
                row.item_description,
                f"{row.demand_qty:,}",
                row.due_date.isoformat() if row.due_date else "MISSING",
                row.priority,
                row.status,
                row.manager_note,
                str(row.demand_id),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column not in {0, 2, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 6:
                    self._style_status(item, row.status)
                self.table.setItem(row_index, column, item)
        self.count_label.setText(f"{len(self.visible_rows):,} demands")

    def _style_status(self, item: QTableWidgetItem, status: str) -> None:
        if status in {"CONFIRMED", "PLANNED", "COMPLETED"}:
            colors = ("#166534", "#dcfce7")
        elif status in {"PENDING", "PARTIALLY_PLANNED"}:
            colors = ("#92400e", "#fef3c7")
        else:
            colors = ("#475569", "#f1f5f9")
        item.setForeground(QColor(colors[0]))
        item.setBackground(QColor(colors[1]))


class OrderEntryPage(ShipmentDemandPage):
    pass
