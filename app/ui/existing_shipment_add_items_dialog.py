from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCompleter,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine
from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)


def _to_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if not value:
                return default
        return int(float(value))
    except Exception:
        return default


def _format_int(value: Any) -> str:
    return f"{_to_int(value):,}"


def _fmt_date(value: Any) -> str:
    if value is None:
        return "Pending"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


# DELIVERY DATE INTEGRITY V6.3: review shipments cannot receive planned dates
class ExistingShipmentAddItemsDialog(QDialog):
    """Dedicated modal workspace for adding items to a saved shipment."""

    def __init__(
        self,
        shipment_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.shipment_id = int(shipment_id)
        self.shipment: dict[str, Any] = {}
        self.saved_items: list[dict[str, Any]] = []
        self.new_items: list[dict[str, Any]] = []
        self.master_items: list[dict[str, Any]] = []

        self.planner = FactoryPlanningEngine(
            start_date=date.today()
        )

        self.setWindowTitle(
            "Add Items to Existing Shipment"
        )
        self.setModal(True)
        self.setMinimumSize(1080, 700)
        self.resize(1360, 800)
        self.setWindowFlag(
            Qt.WindowType.WindowMaximizeButtonHint,
            True,
        )
        self.setObjectName(
            "ExistingShipmentAddItemsDialog"
        )

        self._build_ui()
        self._apply_style()
        self._setup_tables()
        self._load_workspace()

    def showEvent(self, event) -> None:
        super().showEvent(event)

        if getattr(
            self,
            "_screen_fitted",
            False,
        ):
            return

        self._screen_fitted = True

        screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()
        target_width = min(
            1460,
            max(
                1080,
                int(available.width() * 0.92),
            ),
        )
        target_height = min(
            840,
            max(
                700,
                int(available.height() * 0.88),
            ),
        )

        self.resize(
            target_width,
            target_height,
        )
        frame = self.frameGeometry()
        frame.moveCenter(
            available.center()
        )
        self.move(frame.topLeft())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            16,
            14,
            16,
            14,
        )
        root.setSpacing(10)

        header = self._card("HeaderCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            18,
            13,
            18,
            13,
        )
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel(
            "Add Items to Existing Shipment"
        )
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Add approved items to the selected saved shipment "
            "without changing its existing item records."
        )
        subtitle.setObjectName("PageHint")
        subtitle.setWordWrap(True)

        self.shipment_context = QLabel(
            "Loading shipment..."
        )
        self.shipment_context.setObjectName(
            "ContextBanner"
        )
        self.shipment_context.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_box.addWidget(
            self.shipment_context
        )

        mode_badge = QLabel(
            "ADD-ONLY WORKSPACE"
        )
        mode_badge.setObjectName("ModeBadge")
        mode_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        header_layout.addLayout(title_box, 1)
        header_layout.addWidget(mode_badge)
        root.addWidget(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)

        self.saved_count_value = QLabel("0")
        self.saved_qty_value = QLabel("0")
        self.new_count_value = QLabel("0")
        self.new_qty_value = QLabel("0")
        self.factory_receive_value = QLabel(
            "Pending"
        )

        metrics.addWidget(
            self._metric_card(
                self.saved_count_value,
                "Saved Items",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.saved_qty_value,
                "Saved Quantity",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.new_count_value,
                "New Items",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.new_qty_value,
                "New Quantity",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.factory_receive_value,
                "Preview Receive Date",
            )
        )

        root.addLayout(metrics)

        entry_and_readiness = QHBoxLayout()
        entry_and_readiness.setSpacing(12)

        entry_card = self._card()
        entry_layout = QVBoxLayout(entry_card)
        entry_layout.setContentsMargins(
            17,
            13,
            17,
            13,
        )
        entry_layout.setSpacing(8)

        entry_title = QLabel(
            "Add New Shipment Item"
        )
        entry_title.setObjectName(
            "SectionTitle"
        )

        entry_hint = QLabel(
            "Search an approved SMDS item. "
            "Item Receive Date is calculated automatically."
        )
        entry_hint.setObjectName("Hint")
        entry_hint.setWordWrap(True)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)

        item_label = QLabel(
            "SAP Code / Description"
        )
        item_label.setObjectName(
            "FieldLabel"
        )

        quantity_label = QLabel(
            "Quantity"
        )
        quantity_label.setObjectName(
            "FieldLabel"
        )

        self.item_search = QLineEdit()
        self.item_search.setPlaceholderText(
            "Search approved SAP code or tyre description..."
        )
        self.item_search.textChanged.connect(
            self._update_item_preview
        )
        self.item_search.returnPressed.connect(
            self._add_selected_item
        )

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(
            1,
            999999999,
        )
        self.quantity_input.setValue(1)
        self.quantity_input.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        self.add_button = QPushButton(
            "+ Add Item"
        )
        self.add_button.setObjectName(
            "PrimaryButton"
        )
        self.add_button.clicked.connect(
            self._add_selected_item
        )

        form.addWidget(item_label, 0, 0)
        form.addWidget(quantity_label, 0, 1)
        form.addWidget(self.item_search, 1, 0)
        form.addWidget(
            self.quantity_input,
            1,
            1,
        )
        form.addWidget(self.add_button, 1, 2)

        preview = QFrame()
        preview.setObjectName(
            "PreviewCard"
        )
        preview.setMinimumHeight(76)
        preview.setMaximumHeight(86)
        preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(
            14,
            9,
            14,
            9,
        )
        preview_layout.setSpacing(3)

        preview_caption = QLabel(
            "SELECTED ITEM PREVIEW"
        )
        preview_caption.setObjectName(
            "PreviewCaption"
        )

        self.preview_sap = QLabel(
            "No approved item selected"
        )
        self.preview_sap.setObjectName(
            "PreviewSap"
        )
        self.preview_sap.setMinimumHeight(20)

        self.preview_description = QLabel(
            "Search by SAP code or description."
        )
        self.preview_description.setObjectName(
            "PreviewDescription"
        )
        self.preview_description.setWordWrap(
            True
        )
        self.preview_description.setMinimumHeight(24)
        self.preview_description.setAlignment(
            Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignLeft
        )

        preview_layout.addWidget(
            preview_caption
        )
        preview_layout.addWidget(
            self.preview_sap
        )
        preview_layout.addWidget(
            self.preview_description
        )

        entry_layout.addWidget(entry_title)
        entry_layout.addWidget(entry_hint)
        entry_layout.addLayout(form)
        entry_layout.addWidget(preview)

        readiness_card = self._card()
        readiness_layout = QVBoxLayout(
            readiness_card
        )
        readiness_layout.setContentsMargins(
            17,
            13,
            17,
            13,
        )
        readiness_layout.setSpacing(7)

        readiness_title = QLabel(
            "New Item Readiness"
        )
        readiness_title.setObjectName(
            "SectionTitle"
        )

        self.readiness_status = QLabel(
            "ADD NEW ITEMS TO CALCULATE"
        )
        self.readiness_status.setObjectName(
            "ReadinessPending"
        )
        self.readiness_status.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.readiness_status.setWordWrap(True)

        self.readiness_detail = QLabel(
            "Preview checks stock, shipment priority, "
            "mold, casing, cavity capacity and line load."
        )
        self.readiness_detail.setObjectName(
            "Hint"
        )
        self.readiness_detail.setWordWrap(True)

        readiness_layout.addWidget(
            readiness_title
        )
        readiness_layout.addWidget(
            self.readiness_status
        )
        readiness_layout.addWidget(
            self.readiness_detail
        )
        readiness_layout.addStretch(1)

        entry_and_readiness.addWidget(
            entry_card,
            3,
        )
        entry_and_readiness.addWidget(
            readiness_card,
            2,
        )
        root.addLayout(entry_and_readiness)

        new_card = self._card()
        new_layout = QVBoxLayout(new_card)
        new_layout.setContentsMargins(
            16,
            14,
            16,
            16,
        )
        new_layout.setSpacing(8)

        new_header = QHBoxLayout()
        new_title_box = QVBoxLayout()
        new_title_box.setSpacing(3)

        new_title = QLabel(
            "New Items to Add"
        )
        new_title.setObjectName(
            "SectionTitle"
        )

        new_hint = QLabel(
            "Only rows in this table will be inserted "
            "when Save New Items and Replan is clicked."
        )
        new_hint.setObjectName("Hint")
        new_hint.setWordWrap(True)

        self.new_items_badge = QLabel(
            "0 new items"
        )
        self.new_items_badge.setObjectName(
            "NewBadge"
        )
        self.new_items_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        new_title_box.addWidget(new_title)
        new_title_box.addWidget(new_hint)
        new_header.addLayout(
            new_title_box,
            1,
        )
        new_header.addWidget(
            self.new_items_badge
        )

        self.new_items_table = QTableWidget(
            0,
            9,
        )
        self.new_items_table.setMinimumHeight(145)
        self.new_items_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Qty",
            "Stock",
            "Prod Qty",
            "Cavities",
            "Receive Date",
            "Planning Reason",
            "Action",
        ])

        new_layout.addLayout(new_header)
        new_layout.addWidget(
            self.new_items_table
        )

        saved_card = self._card()
        saved_layout = QVBoxLayout(
            saved_card
        )
        saved_layout.setContentsMargins(
            16,
            14,
            16,
            16,
        )
        saved_layout.setSpacing(8)

        saved_header = QHBoxLayout()
        saved_title_box = QVBoxLayout()
        saved_title_box.setSpacing(3)

        saved_title = QLabel(
            "Already Saved Shipment Items"
        )
        saved_title.setObjectName(
            "SectionTitle"
        )

        saved_hint = QLabel(
            "Read-only reference. These rows are already saved "
            "and will not be duplicated, edited or rewritten."
        )
        saved_hint.setObjectName("Hint")
        saved_hint.setWordWrap(True)

        self.saved_items_badge = QLabel(
            "0 saved items"
        )
        self.saved_items_badge.setObjectName(
            "SavedBadge"
        )
        self.saved_items_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        saved_title_box.addWidget(
            saved_title
        )
        saved_title_box.addWidget(
            saved_hint
        )
        saved_header.addLayout(
            saved_title_box,
            1,
        )
        saved_header.addWidget(
            self.saved_items_badge
        )

        self.saved_items_table = QTableWidget(
            0,
            12,
        )
        self.saved_items_table.setMinimumHeight(145)
        self.saved_items_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Order Qty",
            "Stock",
            "Production Required",
            "Produced",
            "Completed",
            "Remaining",
            "Cavities",
            "Daily Capacity",
            "Receive Date",
            "Status",
        ])

        saved_layout.addLayout(
            saved_header
        )
        saved_layout.addWidget(
            self.saved_items_table
        )

        self.items_splitter = QSplitter(
            Qt.Orientation.Vertical
        )
        self.items_splitter.setObjectName(
            "ItemsSplitter"
        )
        self.items_splitter.setChildrenCollapsible(
            False
        )
        self.items_splitter.setHandleWidth(7)
        self.items_splitter.addWidget(
            new_card
        )
        self.items_splitter.addWidget(
            saved_card
        )
        self.items_splitter.setStretchFactor(
            0,
            1,
        )
        self.items_splitter.setStretchFactor(
            1,
            1,
        )
        self.items_splitter.setSizes([
            240,
            220,
        ])

        root.addWidget(
            self.items_splitter,
            1,
        )

        footer_frame = QFrame()
        footer_frame.setObjectName(
            "FooterBar"
        )
        footer = QHBoxLayout(
            footer_frame
        )
        footer.setContentsMargins(
            14,
            9,
            14,
            9,
        )
        footer.setSpacing(10)

        footer_note = QLabel(
            "Saving adds only the new rows, then replans "
            "all active shipments using the existing shipment priority."
        )
        footer_note.setObjectName("Hint")
        footer_note.setWordWrap(True)

        self.cancel_button = QPushButton(
            "Cancel"
        )
        self.cancel_button.setObjectName(
            "SecondaryButton"
        )
        self.cancel_button.setMinimumWidth(105)
        self.cancel_button.clicked.connect(
            self.reject
        )

        self.save_button = QPushButton(
            "Save New Items and Replan"
        )
        self.save_button.setObjectName(
            "PrimaryButton"
        )
        self.save_button.setMinimumWidth(205)
        self.save_button.clicked.connect(
            self._save_new_items
        )
        self.save_button.setEnabled(False)

        footer.addWidget(footer_note, 1)
        footer.addWidget(
            self.cancel_button
        )
        footer.addWidget(
            self.save_button
        )
        root.addWidget(footer_frame)

    def _card(
        self,
        object_name: str = "Card",
    ) -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        return card

    def _metric_card(
        self,
        value_label: QLabel,
        title: str,
    ) -> QFrame:
        card = self._card("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            14,
            9,
            14,
            9,
        )
        layout.setSpacing(2)
        card.setMinimumHeight(66)
        card.setMaximumHeight(74)

        value_label.setObjectName(
            "MetricValue"
        )
        caption = QLabel(title)
        caption.setObjectName(
            "MetricCaption"
        )

        layout.addWidget(value_label)
        layout.addWidget(caption)
        return card

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ExistingShipmentAddItemsDialog {
                background:#f1f5f9;
            }

            QFrame#Card,
            QFrame#HeaderCard,
            QFrame#MetricCard {
                background:#ffffff;
                border:1px solid #d8e2ee;
                border-radius:12px;
            }

            QFrame#FooterBar {
                background:#ffffff;
                border:1px solid #d8e2ee;
                border-radius:11px;
            }

            QSplitter#ItemsSplitter::handle {
                background:#e2e8f0;
                border-radius:3px;
                margin:2px 160px;
            }

            QSplitter#ItemsSplitter::handle:hover {
                background:#bfdbfe;
            }

            QFrame#PreviewCard {
                background:#f8fafc;
                border:1px solid #dbe4f0;
                border-radius:10px;
            }

            QLabel#PageTitle {
                color:#0f172a;
                font-size:18pt;
                font-weight:950;
            }

            QLabel#PageHint,
            QLabel#Hint {
                color:#64748b;
                font-weight:650;
            }

            QLabel#SectionTitle {
                color:#0f172a;
                font-size:12pt;
                font-weight:900;
            }

            QLabel#FieldLabel {
                color:#334155;
                font-weight:850;
            }

            QLabel#ContextBanner {
                background:#f8fafc;
                color:#334155;
                border:1px solid #dbe4f0;
                border-radius:8px;
                padding:7px 9px;
                font-weight:800;
            }

            QLabel#ModeBadge {
                background:#dbeafe;
                color:#1d4ed8;
                border:1px solid #bfdbfe;
                border-radius:9px;
                padding:8px 12px;
                font-weight:950;
            }

            QLabel#MetricValue {
                color:#0f172a;
                font-size:16pt;
                font-weight:950;
            }

            QLabel#MetricCaption {
                color:#64748b;
                font-weight:750;
            }

            QLabel#PreviewCaption {
                color:#64748b;
                font-size:8pt;
                font-weight:900;
            }

            QLabel#PreviewSap {
                color:#0f172a;
                font-size:12pt;
                font-weight:950;
            }

            QLabel#PreviewDescription {
                color:#334155;
                font-weight:700;
            }

            QLabel#ReadinessPending {
                background:#fffbeb;
                color:#92400e;
                border:1px solid #fde68a;
                border-radius:9px;
                padding:9px 11px;
                font-weight:950;
            }

            QLabel#ReadinessReady {
                background:#ecfdf5;
                color:#047857;
                border:1px solid #a7f3d0;
                border-radius:9px;
                padding:9px 11px;
                font-weight:950;
            }

            QLabel#ReadinessBlocked {
                background:#fef2f2;
                color:#b91c1c;
                border:1px solid #fecaca;
                border-radius:9px;
                padding:9px 11px;
                font-weight:950;
            }

            QLabel#NewBadge {
                background:#dbeafe;
                color:#1d4ed8;
                border:1px solid #bfdbfe;
                border-radius:9px;
                padding:7px 11px;
                font-weight:900;
            }

            QLabel#SavedBadge {
                background:#dcfce7;
                color:#047857;
                border:1px solid #bbf7d0;
                border-radius:9px;
                padding:7px 11px;
                font-weight:900;
            }

            QLineEdit,
            QSpinBox {
                background:#ffffff;
                color:#0f172a;
                border:1px solid #cbd5e1;
                border-radius:9px;
                padding:9px 11px;
                font-weight:700;
                min-height:25px;
            }

            QLineEdit:focus,
            QSpinBox:focus {
                border:2px solid #2563eb;
            }

            QTableWidget {
                background:#ffffff;
                alternate-background-color:#f8fafc;
                border:1px solid #d8e2ee;
                border-radius:8px;
                gridline-color:#e8eef5;
                selection-background-color:#dbeafe;
                selection-color:#0f172a;
            }

            QHeaderView::section {
                background:#eef2f7;
                color:#0f172a;
                border:none;
                border-right:1px solid #dbe4f0;
                border-bottom:1px solid #dbe4f0;
                padding:8px 7px;
                font-weight:900;
                min-height:23px;
            }

            QPushButton#PrimaryButton {
                background:#2563eb;
                color:#ffffff;
                border:1px solid #2563eb;
                border-radius:9px;
                padding:10px 16px;
                font-weight:900;
            }

            QPushButton#PrimaryButton:hover {
                background:#1d4ed8;
            }

            QPushButton#PrimaryButton:disabled {
                background:#94a3b8;
                border-color:#94a3b8;
            }

            QPushButton#SecondaryButton {
                background:#e2e8f0;
                color:#0f172a;
                border:1px solid #cbd5e1;
                border-radius:9px;
                padding:10px 16px;
                font-weight:850;
            }

            QPushButton#SmallButton {
                background:#dbeafe;
                color:#1d4ed8;
                border:1px solid #bfdbfe;
                border-radius:7px;
                padding:5px 8px;
                font-weight:850;
            }

            QPushButton#DangerButton {
                background:#fee2e2;
                color:#b91c1c;
                border:1px solid #fecaca;
                border-radius:7px;
                padding:5px 8px;
                font-weight:850;
            }
            """
        )

    def _setup_tables(self) -> None:
        for table in (
            self.new_items_table,
            self.saved_items_table,
        ):
            table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers
            )
            table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows
            )
            table.setSelectionMode(
                QAbstractItemView.SelectionMode.SingleSelection
            )
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(
                36
            )

        self.new_items_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.saved_items_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )

        new_header = (
            self.new_items_table.horizontalHeader()
        )
        new_header.setStretchLastSection(False)

        for column in range(
            self.new_items_table.columnCount()
        ):
            new_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        new_header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        new_header.setSectionResizeMode(
            7,
            QHeaderView.ResizeMode.Stretch,
        )

        self.new_items_table.setColumnWidth(0, 105)
        self.new_items_table.setColumnWidth(2, 72)
        self.new_items_table.setColumnWidth(3, 76)
        self.new_items_table.setColumnWidth(4, 98)
        self.new_items_table.setColumnWidth(5, 84)
        self.new_items_table.setColumnWidth(6, 118)
        self.new_items_table.setColumnWidth(8, 132)

        saved_header = (
            self.saved_items_table.horizontalHeader()
        )
        saved_header.setStretchLastSection(False)

        for column in range(
            self.saved_items_table.columnCount()
        ):
            saved_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        saved_header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )

        self.saved_items_table.setColumnWidth(0, 105)
        self.saved_items_table.setColumnWidth(2, 88)
        self.saved_items_table.setColumnWidth(3, 76)
        self.saved_items_table.setColumnWidth(4, 150)
        self.saved_items_table.setColumnWidth(5, 86)
        self.saved_items_table.setColumnWidth(6, 92)
        self.saved_items_table.setColumnWidth(7, 92)
        self.saved_items_table.setColumnWidth(8, 82)
        self.saved_items_table.setColumnWidth(9, 112)
        self.saved_items_table.setColumnWidth(10, 120)
        self.saved_items_table.setColumnWidth(11, 108)

    def _load_workspace(self) -> None:
        self._load_shipment()
        self._load_saved_items()
        self._load_master_items()
        self._refresh_saved_items_table()
        self._refresh_new_items_table()
        self._update_metrics()

    def _load_shipment(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT *
                    FROM mpps_shipments
                    WHERE id = :shipment_id
                    LIMIT 1
                    """
                ),
                {
                    "shipment_id": self.shipment_id
                },
            ).mappings().first()

        if not row:
            raise RuntimeError(
                "The selected shipment does not exist."
            )

        self.shipment = dict(row)
        shipment_status = str(
            self.shipment.get("status") or ""
        ).strip().lower()
        planning_status = str(
            self.shipment.get("planning_status") or ""
        ).strip().lower()
        target_source = str(
            self.shipment.get("target_date_source") or ""
        ).strip().lower()
        self.review_required = (
            shipment_status
            in {
                "imported review",
                "review required",
                "draft import",
                "excel review hold",
            }
            or planning_status == "review required"
            or target_source == "excel import - date missing"
        )

        shipment_no = str(
            self.shipment.get("shipment_no")
            or self.shipment_id
        )
        shipment_name = str(
            self.shipment.get("shipment_name")
            or shipment_no
        )
        customer = str(
            self.shipment.get("customer_name")
            or "-"
        )
        target = self.shipment.get("target_date")
        target_display = (
            "Approval Required"
            if self.review_required
            else _fmt_date(target)
        )

        self.shipment_context.setText(
            f"{shipment_name}  •  "
            f"Shipment ID: {shipment_no}  •  "
            f"Customer: {customer}  •  "
            f"Target Date: {target_display}"
        )
        self.setWindowTitle(
            f"Add Items — {shipment_name}"
        )

    def _load_saved_items(self) -> None:
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        sap_code,
                        item_description,
                        quantity,
                        COALESCE(
                            stock_allocated_qty,
                            0
                        ) AS stock_allocated_qty,
                        COALESCE(
                            production_required_qty,
                            0
                        ) AS production_required_qty,
                        COALESCE(
                            produced_qty,
                            0
                        ) AS produced_qty,
                        COALESCE(
                            completed_qty,
                            0
                        ) AS completed_qty,
                        COALESCE(
                            remaining_qty,
                            0
                        ) AS remaining_qty,
                        COALESCE(
                            allocated_cavity_count,
                            allocated_cavities,
                            0
                        ) AS cavity_count,
                        COALESCE(
                            daily_capacity,
                            0
                        ) AS daily_capacity,
                        COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date,
                            start_date
                        ) AS item_receive_date,
                        COALESCE(
                            NULLIF(item_status, ''),
                            'Pending'
                        ) AS item_status
                    FROM mpps_shipment_items
                    WHERE shipment_id = :shipment_id
                    ORDER BY
                        item_receive_date ASC NULLS LAST,
                        sap_code ASC,
                        id ASC
                    """
                ),
                {
                    "shipment_id": self.shipment_id
                },
            ).mappings().all()

        self.saved_items = [
            dict(row)
            for row in rows
        ]

    def _load_master_items(self) -> None:
        rows: list[dict[str, Any]] = []

        try:
            with engine.begin() as connection:
                result = connection.execute(
                    text(
                        """
                        SELECT
                            sap_code,
                            COALESCE(
                                material_description,
                                tyre_description,
                                ''
                            ) AS tyre_description
                        FROM smds
                        WHERE sap_code IS NOT NULL
                          AND TRIM(sap_code) <> ''
                        ORDER BY sap_code ASC
                        """
                    )
                ).mappings().all()
            rows = [
                dict(row)
                for row in result
            ]
        except Exception:
            rows = []

        if not rows:
            try:
                with engine.begin() as connection:
                    result = connection.execute(
                        text(
                            """
                            SELECT
                                sap_code,
                                tyre_description
                            FROM mpps_sap_stock_items
                            WHERE is_active = TRUE
                            ORDER BY sap_code ASC
                            """
                        )
                    ).mappings().all()
                rows = [
                    dict(row)
                    for row in result
                ]
            except Exception:
                rows = []

        self.master_items = rows

        values = [
            (
                f"{item.get('sap_code') or ''} - "
                f"{item.get('tyre_description') or ''}"
            )
            for item in rows
        ]

        completer = QCompleter(
            values,
            self.item_search,
        )
        completer.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        completer.setFilterMode(
            Qt.MatchFlag.MatchContains
        )
        self.item_search.setCompleter(
            completer
        )

    def _find_master_item(
        self,
        search_text: str,
    ) -> dict[str, Any] | None:
        value = search_text.strip()
        if not value:
            return None

        lowered = value.lower()

        for item in self.master_items:
            sap = str(
                item.get("sap_code")
                or ""
            ).strip()
            description = str(
                item.get("tyre_description")
                or ""
            ).strip()
            display = f"{sap} - {description}"

            if (
                lowered == display.lower()
                or lowered == sap.lower()
            ):
                return item

        for item in self.master_items:
            sap = str(
                item.get("sap_code")
                or ""
            ).strip()
            description = str(
                item.get("tyre_description")
                or ""
            ).strip()

            if (
                sap.lower() in lowered
                or lowered in description.lower()
            ):
                return item

        return None

    def _update_item_preview(
        self,
        search_text: str,
    ) -> None:
        item = self._find_master_item(
            search_text
        )

        if not item:
            self.preview_sap.setText(
                "No approved item selected"
            )
            self.preview_description.setText(
                "Search by SAP code or description."
            )
            return

        self.preview_sap.setText(
            str(item.get("sap_code") or "-")
        )
        self.preview_description.setText(
            str(
                item.get("tyre_description")
                or "-"
            )
        )

    def _add_selected_item(self) -> None:
        master_item = self._find_master_item(
            self.item_search.text()
        )

        if not master_item:
            QMessageBox.warning(
                self,
                "Approved Item Required",
                "Select a valid approved SMDS item.",
            )
            self.item_search.setFocus()
            return

        sap_code = str(
            master_item.get("sap_code")
            or ""
        ).strip()
        description = str(
            master_item.get("tyre_description")
            or ""
        ).strip()
        quantity = int(
            self.quantity_input.value()
        )

        for item in self.new_items:
            if item["sap_code"] == sap_code:
                item["quantity"] += quantity
                self._recalculate_new_items()
                self._refresh_new_items_table()
                self._reset_entry()
                return

        self.new_items.append({
            "sap_code": sap_code,
            "item_description": description,
            "quantity": quantity,
            "produced_qty": 0,
        })

        self._recalculate_new_items()
        self._refresh_new_items_table()
        self._reset_entry()

    def _reset_entry(self) -> None:
        self.item_search.clear()
        self.quantity_input.setValue(1)
        self.item_search.setFocus()

    def _recalculate_new_items(self) -> None:
        if not self.new_items:
            self._update_metrics()
            return

        # Workbook plan dates and manager/order dates are not approved
        # customer target dates.
        target_date = self.shipment.get("target_date")

        target_is_manual = bool(
            self.shipment.get(
                "target_date_is_manual"
            )
        )
        created_at = self.shipment.get(
            "created_at"
        )

        preview_items = [
            {
                "sap_code": item["sap_code"],
                "item_description": (
                    item["item_description"]
                ),
                "quantity": item["quantity"],
                "produced_qty": 0,
            }
            for item in self.new_items
        ]

        try:
            results = (
                self.planner.calculate_cart_items(
                    preview_items,
                    target_date=target_date,
                    exclude_shipment_id=None,
                    target_date_is_manual=(
                        target_is_manual
                    ),
                    draft_created_at=created_at,
                )
            )
        except Exception as exc:
            for item in self.new_items:
                item.update({
                    "stock_allocated_qty": 0,
                    "production_required_qty": (
                        item["quantity"]
                    ),
                    "allocated_cavity_count": 0,
                    "daily_capacity": 0,
                    "production_days": 0,
                    "item_receive_date": None,
                    "item_status": "Blocked",
                    "schedule_reason": (
                        "Planning preview failed: "
                        f"{exc}"
                    ),
                })
            self._update_readiness()
            self._update_metrics()
            return

        for item, result in zip(
            self.new_items,
            results,
        ):
            item["stock_allocated_qty"] = _to_int(
                result.get(
                    "stock_allocated_qty"
                )
            )
            item["production_required_qty"] = _to_int(
                result.get(
                    "production_required_qty"
                )
            )
            item["allocated_cavity_count"] = _to_int(
                result.get(
                    "allocated_cavity_count"
                )
            )
            item["daily_capacity"] = _to_int(
                result.get("daily_capacity")
            )
            item["production_days"] = _to_int(
                result.get("production_days")
            )
            item["item_receive_date"] = (
                result.get("receive_date")
                or result.get(
                    "item_receive_date"
                )
            )
            item["item_status"] = str(
                result.get("status")
                or result.get("item_status")
                or "Pending"
            )
            item["schedule_reason"] = str(
                result.get("reason")
                or result.get(
                    "schedule_reason"
                )
                or ""
            )

            if self.review_required:
                # Keep non-reserving stock/production preview, but do not
                # manufacture production dates or capacity before target
                # approval.
                item["allocated_cavity_count"] = 0
                item["daily_capacity"] = 0
                item["production_days"] = 0
                item["item_receive_date"] = None
                item["item_status"] = "Imported Review"
                item["schedule_reason"] = (
                    "Target date approval required before live planning."
                )

        self._update_readiness()
        self._update_metrics()

    def _blocked_items(self) -> list[dict[str, Any]]:
        blocked_statuses = {
            "",
            "blocked",
            "pending",
            "unplanned",
            "failed",
            "error",
        }

        blocked: list[dict[str, Any]] = []

        for item in self.new_items:
            production_required = _to_int(
                item.get(
                    "production_required_qty"
                )
            )
            status = str(
                item.get("item_status")
                or ""
            ).strip().lower()
            receive_date = item.get(
                "item_receive_date"
            )

            if (
                production_required > 0
                and (
                    receive_date is None
                    or status in blocked_statuses
                )
            ):
                blocked.append(item)

        return blocked

    def _update_readiness(self) -> None:
        if not self.new_items:
            self.readiness_status.setObjectName(
                "ReadinessPending"
            )
            self.readiness_status.setText(
                "ADD NEW ITEMS TO CALCULATE"
            )
            self.readiness_detail.setText(
                "Preview checks stock, shipment priority, "
                "mold, casing, cavity capacity and line load."
            )
            self.save_button.setEnabled(False)
        else:
            blocked = self._blocked_items()

            if blocked:
                self.readiness_status.setObjectName(
                    "ReadinessBlocked"
                )
                self.readiness_status.setText(
                    f"BLOCKED — {len(blocked)} "
                    f"{'ITEM' if len(blocked) == 1 else 'ITEMS'} "
                    "CANNOT BE PLANNED"
                )
                self.readiness_detail.setText(
                    "Save New Items and Replan remains disabled "
                    "until every new item has a valid receive date."
                )
                self.save_button.setEnabled(False)
            else:
                self.readiness_status.setObjectName(
                    "ReadinessReady"
                )
                self.readiness_status.setText(
                    "NEW ITEMS READY TO ADD"
                )
                self.readiness_detail.setText(
                    "All new items have valid stock or production "
                    "plans and calculated receive dates."
                )
                self.save_button.setEnabled(True)

        self.readiness_status.style().unpolish(
            self.readiness_status
        )
        self.readiness_status.style().polish(
            self.readiness_status
        )

    def _refresh_new_items_table(self) -> None:
        table = self.new_items_table
        table.setRowCount(0)

        for row_index, item in enumerate(
            self.new_items
        ):
            table.insertRow(row_index)

            values = [
                item.get("sap_code") or "-",
                item.get(
                    "item_description"
                ) or "-",
                _format_int(
                    item.get("quantity")
                ),
                _format_int(
                    item.get(
                        "stock_allocated_qty"
                    )
                ),
                _format_int(
                    item.get(
                        "production_required_qty"
                    )
                ),
                _format_int(
                    item.get(
                        "allocated_cavity_count"
                    )
                ),
                _fmt_date(
                    item.get(
                        "item_receive_date"
                    )
                ),
                item.get(
                    "schedule_reason"
                ) or "-",
            ]

            for column, value in enumerate(
                values
            ):
                cell = QTableWidgetItem(
                    str(value)
                )
                cell.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )

                if column in {
                    0,
                    2,
                    3,
                    4,
                    5,
                    6,
                }:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column in {1, 7}:
                    cell.setToolTip(
                        str(value)
                    )

                table.setItem(
                    row_index,
                    column,
                    cell,
                )

            actions = QWidget()
            action_layout = QHBoxLayout(
                actions
            )
            action_layout.setContentsMargins(
                2,
                2,
                2,
                2,
            )
            action_layout.setSpacing(4)

            qty_button = QPushButton("Qty")
            qty_button.setObjectName(
                "SmallButton"
            )
            qty_button.clicked.connect(
                lambda checked=False, row=row_index:
                self._change_quantity(row)
            )

            remove_button = QPushButton(
                "Remove"
            )
            remove_button.setObjectName(
                "DangerButton"
            )
            remove_button.clicked.connect(
                lambda checked=False, row=row_index:
                self._remove_new_item(row)
            )

            action_layout.addWidget(
                qty_button
            )
            action_layout.addWidget(
                remove_button
            )

            table.setCellWidget(
                row_index,
                8,
                actions,
            )

        self.new_items_badge.setText(
            f"{len(self.new_items)} new "
            f"{'item' if len(self.new_items) == 1 else 'items'}"
        )
        table.resizeRowsToContents()
        self._update_metrics()
        self._update_readiness()

    def _refresh_saved_items_table(self) -> None:
        table = self.saved_items_table
        table.setRowCount(0)

        for row_index, item in enumerate(
            self.saved_items
        ):
            table.insertRow(row_index)

            values = [
                item.get("sap_code") or "-",
                item.get(
                    "item_description"
                ) or "-",
                _format_int(
                    item.get("quantity")
                ),
                _format_int(
                    item.get(
                        "stock_allocated_qty"
                    )
                ),
                _format_int(
                    item.get(
                        "production_required_qty"
                    )
                ),
                _format_int(
                    item.get("produced_qty")
                ),
                _format_int(
                    item.get("completed_qty")
                ),
                _format_int(
                    item.get("remaining_qty")
                ),
                _format_int(
                    item.get("cavity_count")
                ),
                _format_int(
                    item.get("daily_capacity")
                ),
                _fmt_date(
                    item.get(
                        "item_receive_date"
                    )
                ),
                item.get("item_status")
                or "Pending",
            ]

            for column, value in enumerate(
                values
            ):
                cell = QTableWidgetItem(
                    str(value)
                )
                cell.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )

                if column in {
                    0,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                }:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column == 1:
                    cell.setToolTip(
                        str(value)
                    )

                table.setItem(
                    row_index,
                    column,
                    cell,
                )

        self.saved_items_badge.setText(
            f"{len(self.saved_items)} saved "
            f"{'item' if len(self.saved_items) == 1 else 'items'}"
        )
        table.resizeRowsToContents()

    def _change_quantity(
        self,
        row: int,
    ) -> None:
        if row < 0 or row >= len(
            self.new_items
        ):
            return

        item = self.new_items[row]

        quantity, accepted = (
            QInputDialog.getInt(
                self,
                "Change New Item Quantity",
                (
                    f"{item['sap_code']} — "
                    "Required Quantity"
                ),
                int(item.get("quantity") or 1),
                1,
                999999999,
            )
        )

        if not accepted:
            return

        item["quantity"] = quantity
        self._recalculate_new_items()
        self._refresh_new_items_table()

    def _remove_new_item(
        self,
        row: int,
    ) -> None:
        if row < 0 or row >= len(
            self.new_items
        ):
            return

        self.new_items.pop(row)

        if self.new_items:
            self._recalculate_new_items()

        self._refresh_new_items_table()

    def _update_metrics(self) -> None:
        saved_qty = sum(
            _to_int(item.get("quantity"))
            for item in self.saved_items
        )
        new_qty = sum(
            _to_int(item.get("quantity"))
            for item in self.new_items
        )

        valid_dates = [
            item.get("item_receive_date")
            for item in self.new_items
            if item.get("item_receive_date")
            is not None
        ]
        preview_receive = (
            max(valid_dates)
            if valid_dates
            and len(valid_dates)
            == len(self.new_items)
            else None
        )

        self.saved_count_value.setText(
            _format_int(
                len(self.saved_items)
            )
        )
        self.saved_qty_value.setText(
            _format_int(saved_qty)
        )
        self.new_count_value.setText(
            _format_int(
                len(self.new_items)
            )
        )
        self.new_qty_value.setText(
            _format_int(new_qty)
        )
        self.factory_receive_value.setText(
            _fmt_date(preview_receive)
        )

    def _blocked_warning(
        self,
        blocked: list[dict[str, Any]],
    ) -> str:
        lines = [
            (
                "The new items cannot be added because "
                f"{len(blocked)} "
                f"{'item is' if len(blocked) == 1 else 'items are'} "
                "not fully plannable."
            ),
            "",
            "Exact reasons:",
        ]

        for index, item in enumerate(
            blocked,
            start=1,
        ):
            lines.extend([
                "",
                (
                    f"{index}. SAP "
                    f"{item.get('sap_code') or '-'}"
                ),
                (
                    "   Description: "
                    f"{item.get('item_description') or '-'}"
                ),
                (
                    "   Quantity: "
                    f"{_format_int(item.get('quantity'))}"
                ),
                (
                    "   Reason: "
                    f"{item.get('schedule_reason') or 'No planning reason available.'}"
                ),
            ])

        return "\n".join(lines)

    def _save_new_items(self) -> None:
        if not self.new_items:
            QMessageBox.warning(
                self,
                "New Items Required",
                "Add at least one new item first.",
            )
            return

        self._recalculate_new_items()
        self._refresh_new_items_table()

        blocked = self._blocked_items()
        if blocked:
            QMessageBox.warning(
                self,
                "New Items Cannot Be Added",
                self._blocked_warning(blocked),
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Save New Items and Replan",
            (
                f"Add {len(self.new_items)} new "
                f"{'item' if len(self.new_items) == 1 else 'items'} "
                "to this shipment?\n\n"
                "Only the new rows will be inserted. "
                "Existing saved items remain unchanged."
            ),
        )

        if (
            confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        inserted_ids: list[int] = []

        try:
            if self.review_required:
                for item in self.new_items:
                    item["allocated_cavity_count"] = 0
                    item["daily_capacity"] = 0
                    item["production_days"] = 0
                    item["item_receive_date"] = None
                    item["item_status"] = "Imported Review"
                    item["schedule_reason"] = (
                        "Target date approval required before live planning."
                    )

            with engine.begin() as connection:
                for item in self.new_items:
                    item_id = int(
                        connection.execute(
                            text(
                                """
                                INSERT INTO
                                    mpps_shipment_items
                                (
                                    shipment_id,
                                    sap_code,
                                    item_description,
                                    quantity,
                                    start_date,
                                    end_date,
                                    receive_date,
                                    item_receive_date,
                                    item_status,
                                    note,
                                    stock_allocated_qty,
                                    production_required_qty,
                                    allocated_cavity_count,
                                    allocated_cavities,
                                    daily_capacity,
                                    production_days,
                                    produced_qty,
                                    completed_qty,
                                    remaining_qty,
                                    progress_pct,
                                    schedule_reason,
                                    updated_at
                                )
                                VALUES
                                (
                                    :shipment_id,
                                    :sap_code,
                                    :item_description,
                                    :quantity,
                                    :receive_date,
                                    :receive_date,
                                    :receive_date,
                                    :receive_date,
                                    :item_status,
                                    :note,
                                    :stock_allocated_qty,
                                    :production_required_qty,
                                    :allocated_cavity_count,
                                    :allocated_cavity_count,
                                    :daily_capacity,
                                    :production_days,
                                    0,
                                    :stock_allocated_qty,
                                    :remaining_qty,
                                    :progress_pct,
                                    :schedule_reason,
                                    CURRENT_TIMESTAMP
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "shipment_id": (
                                    self.shipment_id
                                ),
                                "sap_code": (
                                    item["sap_code"]
                                ),
                                "item_description": (
                                    item[
                                        "item_description"
                                    ]
                                ),
                                "quantity": (
                                    item["quantity"]
                                ),
                                "receive_date": (
                                    item.get(
                                        "item_receive_date"
                                    )
                                ),
                                "item_status": (
                                    item.get(
                                        "item_status"
                                    )
                                    or "Planned"
                                ),
                                "note": (
                                    "Added through dedicated "
                                    "existing-shipment popup."
                                ),
                                "stock_allocated_qty": (
                                    _to_int(
                                        item.get(
                                            "stock_allocated_qty"
                                        )
                                    )
                                ),
                                "production_required_qty": (
                                    _to_int(
                                        item.get(
                                            "production_required_qty"
                                        )
                                    )
                                ),
                                "allocated_cavity_count": (
                                    _to_int(
                                        item.get(
                                            "allocated_cavity_count"
                                        )
                                    )
                                ),
                                "daily_capacity": (
                                    _to_int(
                                        item.get(
                                            "daily_capacity"
                                        )
                                    )
                                ),
                                "production_days": (
                                    _to_int(
                                        item.get(
                                            "production_days"
                                        )
                                    )
                                ),
                                "remaining_qty": (
                                    _to_int(
                                        item.get(
                                            "production_required_qty"
                                        )
                                    )
                                ),
                                "progress_pct": (
                                    round(
                                        (
                                            _to_int(
                                                item.get(
                                                    "stock_allocated_qty"
                                                )
                                            )
                                            /
                                            max(
                                                1,
                                                _to_int(
                                                    item.get(
                                                        "quantity"
                                                    )
                                                ),
                                            )
                                            * 100
                                        ),
                                        2,
                                    )
                                ),
                                "schedule_reason": (
                                    item.get(
                                        "schedule_reason"
                                    )
                                    or ""
                                ),
                            },
                        ).scalar_one()
                    )
                    inserted_ids.append(item_id)

            if not self.review_required:
                self.planner.replan_all_open_shipments(
                    trigger_reason=(
                        "existing_shipment_popup_items_added_"
                        f"{self.shipment_id}"
                    ),
                    created_by=(
                        "existing_shipment_add_items_popup"
                    ),
                )

        except Exception as exc:
            if inserted_ids:
                try:
                    with engine.begin() as connection:
                        for item_id in inserted_ids:
                            connection.execute(
                                text(
                                    """
                                    DELETE FROM
                                        planning_resource_reservations
                                    WHERE shipment_item_id =
                                        :item_id
                                    """
                                ),
                                {"item_id": item_id},
                            )
                            connection.execute(
                                text(
                                    """
                                    DELETE FROM
                                        shipment_stock_allocations
                                    WHERE shipment_item_id =
                                        :item_id
                                    """
                                ),
                                {"item_id": item_id},
                            )
                            connection.execute(
                                text(
                                    """
                                    DELETE FROM
                                        mpps_shipment_items
                                    WHERE id = :item_id
                                    """
                                ),
                                {"item_id": item_id},
                            )

                    self.planner.replan_all_open_shipments(
                        trigger_reason=(
                            "rollback_existing_shipment_"
                            "popup_item_addition_"
                            f"{self.shipment_id}"
                        ),
                        created_by=(
                            "existing_shipment_add_items_popup"
                        ),
                    )
                except Exception:
                    pass

            QMessageBox.critical(
                self,
                "Add Items Failed",
                (
                    "The new items could not be added. "
                    "Existing saved items were not changed."
                    f"\n\nReason: {exc}"
                ),
            )
            return

        QMessageBox.information(
            self,
            "Shipment Updated",
            (
                f"{len(inserted_ids)} new "
                f"{'item was' if len(inserted_ids) == 1 else 'items were'} "
                "added successfully.\n\n"
                + (
                    "Target approval is still required before planning."
                    if self.review_required
                    else "All active shipments were replanned."
                )
            ),
        )
        self.accept()
