from __future__ import annotations

# STOCK ALLOCATION INTEGRITY V6.2

import csv
from datetime import date, datetime, timedelta
from time import perf_counter

from PySide6.QtCore import QDate, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine
from app.services.factory_planning_engine import FactoryPlanningEngine
from app.services.factory_out_forecast_service import load_shipment_forecasts
from app.services.operational_source_service import OperationalSourceService
from app.services.shipment_details_async_service import load_shipment_portfolio
from app.services.shipment_command_service import (
    day_count,
    portfolio_metrics,
    shipment_risk_profile,
    shipment_execution_state,
    item_execution_timeline,
)
from app.ui.existing_shipment_add_items_dialog import ExistingShipmentAddItemsDialog


def _to_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value == "":
                return default
        return int(float(value))
    except Exception:
        return default


class _ShipmentPortfolioWorker(QThread):
    """Read and score the Shipment Details portfolio off the GUI thread."""

    progress = Signal(int, str, int)
    loaded = Signal(object, int)
    failed = Signal(str, int)

    def __init__(
        self,
        filters: dict,
        generation: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.filters = dict(filters)
        self.generation = int(generation)

    def run(self) -> None:
        try:
            self.progress.emit(
                4,
                "Starting background shipment load...",
                self.generation,
            )

            payload = load_shipment_portfolio(
                self.filters,
                progress=lambda percent, message: self.progress.emit(
                    int(percent),
                    str(message),
                    self.generation,
                ),
            )

            self.loaded.emit(payload, self.generation)
        except Exception as exc:
            self.failed.emit(str(exc), self.generation)


from app.ui.item_resource_control_center_page import ItemResourceControlCenterPage

class ShipmentDialog(QDialog):
    def __init__(self, parent=None, shipment: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Shipment Header")
        self.setMinimumWidth(620)

        self.shipment_no_input = QLineEdit()
        self.shipment_no_input.setPlaceholderText("Shipment ID / shipment name")

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer / destination")

        self.order_date_input = QDateEdit()
        self.order_date_input.setCalendarPopup(True)
        self.order_date_input.setDate(QDate.currentDate())

        self.status_input = QComboBox()
        self.status_input.addItems(["Planned", "In Progress", "Completed", "On Hold", "Cancelled"])

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Shipment note / remarks")
        self.note_input.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Shipment Header")
        title.setStyleSheet("font-size:18pt; font-weight:950; color:#0f172a;")
        layout.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Shipment ID / Name"), 0, 0)
        form.addWidget(self.shipment_no_input, 1, 0)
        form.addWidget(QLabel("Customer / Destination"), 0, 1)
        form.addWidget(self.customer_input, 1, 1)
        form.addWidget(QLabel("Order / Priority Date"), 2, 0)
        form.addWidget(self.order_date_input, 3, 0)
        form.addWidget(QLabel("Status"), 2, 1)
        form.addWidget(self.status_input, 3, 1)
        form.addWidget(QLabel("Note"), 4, 0, 1, 2)
        form.addWidget(self.note_input, 5, 0, 1, 2)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if shipment:
            self.shipment_no_input.setText(str(shipment.get("shipment_no") or ""))
            self.customer_input.setText(str(shipment.get("customer_name") or ""))
            order_date = shipment.get("manager_order_date") or shipment.get("shipment_date") or shipment.get("created_at")
            if hasattr(order_date, "year"):
                self.order_date_input.setDate(QDate(order_date.year, order_date.month, order_date.day))
            status = str(shipment.get("status") or "Planned")
            index = self.status_input.findText(status)
            if index >= 0:
                self.status_input.setCurrentIndex(index)
            self.note_input.setPlainText(str(shipment.get("note") or ""))

    def get_data(self) -> dict:
        order_date = self.order_date_input.date().toPython()
        return {
            "shipment_no": self.shipment_no_input.text().strip(),
            "shipment_name": self.shipment_no_input.text().strip(),
            "customer_name": self.customer_input.text().strip(),
            "manager_order_date": order_date,
            "shipment_date": order_date,
            "status": self.status_input.currentText(),
            "note": self.note_input.toPlainText().strip(),
        }


class ShipmentItemDialog(QDialog):
    def __init__(
        self,
        parent=None,
        base_date=None,
        item: dict | None = None,
    ):
        super().__init__(parent)

        self.is_edit_mode = item is not None
        self.current_status = str(
            (item or {}).get("item_status")
            or "Pending"
        )

        self.setWindowTitle(
            "Edit Shipment Item"
            if self.is_edit_mode
            else "Add Shipment Item"
        )
        self.setModal(True)
        self.setMinimumSize(820, 650)
        self.resize(880, 690)
        self.setObjectName(
            "ShipmentItemDialog"
        )

        self.master_items = (
            self.load_master_items()
        )

        self._build_ui()
        self._apply_dialog_style()

        if item:
            self.populate_item(item)
        else:
            self._refresh_selected_preview()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            22,
            20,
            22,
            18,
        )
        root.setSpacing(14)

        header = QFrame()
        header.setObjectName(
            "DialogHeaderCard"
        )
        header_layout = QHBoxLayout(
            header
        )
        header_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )
        header_layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        title = QLabel(
            "Edit Shipment Item"
            if self.is_edit_mode
            else "Add Shipment Item"
        )
        title.setObjectName(
            "DialogTitle"
        )

        subtitle = QLabel(
            "Select an approved SMDS tyre item and "
            "enter only the required quantity. "
            "Planning dates and execution status are "
            "controlled by the production planner."
        )
        subtitle.setObjectName(
            "DialogSubtitle"
        )
        subtitle.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        control_badge = QLabel(
            "PLANNER CONTROLLED"
        )
        control_badge.setObjectName(
            "ControlBadge"
        )
        control_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        control_badge.setMinimumWidth(
            175
        )

        header_layout.addLayout(
            title_box,
            1,
        )
        header_layout.addWidget(
            control_badge
        )

        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        item_card = self._dialog_card()
        item_layout = QVBoxLayout(
            item_card
        )
        item_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )
        item_layout.setSpacing(10)

        item_title = QLabel(
            "Approved Tyre Item"
        )
        item_title.setObjectName(
            "DialogSectionTitle"
        )

        item_hint = QLabel(
            "Search by SAP code or tyre description. "
            "Only Planning Manager approved SMDS "
            "records are available."
        )
        item_hint.setObjectName(
            "DialogHint"
        )
        item_hint.setWordWrap(True)

        item_label = QLabel(
            "SAP Code / Description"
        )
        item_label.setObjectName(
            "DialogFieldLabel"
        )

        self.sap_input = QComboBox()
        self.sap_input.setEditable(True)
        self.sap_input.setInsertPolicy(
            QComboBox.InsertPolicy.NoInsert
        )
        self.sap_input.setMaxVisibleItems(16)
        self.sap_input.addItem(
            "Search approved SAP code or description...",
            None,
        )

        for master_item in self.master_items:
            self.sap_input.addItem(
                (
                    f"{master_item['sap_code']}  •  "
                    f"{master_item['tyre_description']}"
                ),
                master_item,
            )

        combo_line_edit = (
            self.sap_input.lineEdit()
        )
        if combo_line_edit is not None:
            combo_line_edit.setPlaceholderText(
                "Search approved SAP code or description..."
            )

        self.sap_input.currentIndexChanged.connect(
            self.update_description_from_master
        )

        preview = QFrame()
        preview.setObjectName(
            "ItemPreviewCard"
        )
        preview_layout = QGridLayout(
            preview
        )
        preview_layout.setContentsMargins(
            14,
            12,
            14,
            12,
        )
        preview_layout.setHorizontalSpacing(
            12
        )
        preview_layout.setVerticalSpacing(
            7
        )

        preview_sap_label = QLabel(
            "SAP CODE"
        )
        preview_sap_label.setObjectName(
            "PreviewCaption"
        )
        preview_desc_label = QLabel(
            "APPROVED DESCRIPTION"
        )
        preview_desc_label.setObjectName(
            "PreviewCaption"
        )

        self.preview_sap_value = QLabel(
            "Not selected"
        )
        self.preview_sap_value.setObjectName(
            "PreviewValue"
        )

        self.preview_description_value = QLabel(
            "Select an approved item to preview details."
        )
        self.preview_description_value.setObjectName(
            "PreviewDescription"
        )
        self.preview_description_value.setWordWrap(
            True
        )

        preview_layout.addWidget(
            preview_sap_label,
            0,
            0,
        )
        preview_layout.addWidget(
            self.preview_sap_value,
            1,
            0,
        )
        preview_layout.addWidget(
            preview_desc_label,
            2,
            0,
        )
        preview_layout.addWidget(
            self.preview_description_value,
            3,
            0,
        )

        self.description_input = QLineEdit()
        self.description_input.setReadOnly(True)
        self.description_input.setVisible(False)

        item_layout.addWidget(item_title)
        item_layout.addWidget(item_hint)
        item_layout.addSpacing(2)
        item_layout.addWidget(item_label)
        item_layout.addWidget(self.sap_input)
        item_layout.addWidget(preview)
        item_layout.addStretch(1)

        requirement_card = self._dialog_card()
        requirement_layout = QVBoxLayout(
            requirement_card
        )
        requirement_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )
        requirement_layout.setSpacing(10)

        requirement_title = QLabel(
            "Order Requirement"
        )
        requirement_title.setObjectName(
            "DialogSectionTitle"
        )

        requirement_hint = QLabel(
            "Enter the customer-required quantity. "
            "Stock allocation and production quantity "
            "will be recalculated automatically."
        )
        requirement_hint.setObjectName(
            "DialogHint"
        )
        requirement_hint.setWordWrap(True)

        quantity_label = QLabel(
            "Required Quantity"
        )
        quantity_label.setObjectName(
            "DialogFieldLabel"
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

        planning_box = QFrame()
        planning_box.setObjectName(
            "PlanningControlCard"
        )
        planning_layout = QVBoxLayout(
            planning_box
        )
        planning_layout.setContentsMargins(
            14,
            12,
            14,
            12,
        )
        planning_layout.setSpacing(8)

        planning_title = QLabel(
            "Automatic Planning Controls"
        )
        planning_title.setObjectName(
            "PlanningTitle"
        )

        receive_row = QHBoxLayout()
        receive_caption = QLabel(
            "Item Receive Date"
        )
        receive_caption.setObjectName(
            "PlanningCaption"
        )
        receive_value = QLabel(
            "CALCULATED AUTOMATICALLY"
        )
        receive_value.setObjectName(
            "AutoBadge"
        )
        receive_value.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        receive_row.addWidget(
            receive_caption,
            1,
        )
        receive_row.addWidget(
            receive_value
        )

        status_row = QHBoxLayout()
        status_caption = QLabel(
            "Execution Status"
        )
        status_caption.setObjectName(
            "PlanningCaption"
        )
        self.status_badge = QLabel(
            self.current_status.upper()
        )
        self.status_badge.setObjectName(
            "StatusBadge"
        )
        self.status_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        status_row.addWidget(
            status_caption,
            1,
        )
        status_row.addWidget(
            self.status_badge
        )

        planning_note = QLabel(
            "Priority, stock, mold, casing, cavity "
            "capacity and existing shipment load are "
            "validated when this item is saved."
        )
        planning_note.setObjectName(
            "PlanningNote"
        )
        planning_note.setWordWrap(True)

        planning_layout.addWidget(
            planning_title
        )
        planning_layout.addLayout(
            receive_row
        )
        planning_layout.addLayout(
            status_row
        )
        planning_layout.addWidget(
            planning_note
        )

        requirement_layout.addWidget(
            requirement_title
        )
        requirement_layout.addWidget(
            requirement_hint
        )
        requirement_layout.addSpacing(2)
        requirement_layout.addWidget(
            quantity_label
        )
        requirement_layout.addWidget(
            self.quantity_input
        )
        requirement_layout.addWidget(
            planning_box
        )
        requirement_layout.addStretch(1)

        body.addWidget(
            item_card,
            3,
        )
        body.addWidget(
            requirement_card,
            2,
        )
        root.addLayout(body, 1)

        note_card = self._dialog_card()
        note_layout = QVBoxLayout(
            note_card
        )
        note_layout.setContentsMargins(
            18,
            14,
            18,
            14,
        )
        note_layout.setSpacing(7)

        note_header = QHBoxLayout()

        note_title = QLabel(
            "Planning Note / Special Instruction"
        )
        note_title.setObjectName(
            "DialogSectionTitle"
        )

        optional_badge = QLabel(
            "OPTIONAL"
        )
        optional_badge.setObjectName(
            "OptionalBadge"
        )
        optional_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        note_header.addWidget(
            note_title,
            1,
        )
        note_header.addWidget(
            optional_badge
        )

        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText(
            "Add an item-specific instruction for "
            "planning, production or delivery..."
        )
        self.note_input.setMinimumHeight(96)
        self.note_input.setMaximumHeight(120)

        note_layout.addLayout(
            note_header
        )
        note_layout.addWidget(
            self.note_input
        )

        root.addWidget(note_card)

        footer = QHBoxLayout()
        footer.setSpacing(10)

        footer_note = QLabel(
            "Saving runs cumulative replanning for all active shipments."
        )
        footer_note.setObjectName(
            "FooterHint"
        )
        footer_note.setWordWrap(True)

        self.cancel_button = QPushButton(
            "Cancel"
        )
        self.cancel_button.setObjectName(
            "DialogCancelButton"
        )
        self.cancel_button.clicked.connect(
            self.reject
        )

        self.save_button = QPushButton(
            (
                "Save Changes & Replan"
                if self.is_edit_mode
                else "Add Item & Replan"
            )
        )
        self.save_button.setObjectName(
            "DialogSaveButton"
        )
        self.save_button.clicked.connect(
            self._validate_and_accept
        )
        self.save_button.setDefault(True)

        footer.addWidget(
            footer_note,
            1,
        )
        footer.addWidget(
            self.cancel_button
        )
        footer.addWidget(
            self.save_button
        )

        root.addLayout(footer)

    def _dialog_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName(
            "DialogCard"
        )
        return card

    def _apply_dialog_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ShipmentItemDialog {
                background: #f1f5f9;
            }

            QFrame#DialogHeaderCard,
            QFrame#DialogCard {
                background: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 14px;
            }

            QFrame#ItemPreviewCard {
                background: #f8fafc;
                border: 1px solid #dbe4f0;
                border-radius: 11px;
            }

            QFrame#PlanningControlCard {
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 11px;
            }

            QLabel#DialogTitle {
                color: #0f172a;
                font-size: 20pt;
                font-weight: 950;
            }

            QLabel#DialogSubtitle,
            QLabel#DialogHint,
            QLabel#FooterHint {
                color: #64748b;
                font-weight: 650;
            }

            QLabel#DialogSectionTitle {
                color: #0f172a;
                font-size: 13pt;
                font-weight: 900;
            }

            QLabel#DialogFieldLabel,
            QLabel#PlanningCaption {
                color: #334155;
                font-weight: 800;
            }

            QLabel#ControlBadge {
                background: #dbeafe;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 10px;
                padding: 9px 13px;
                font-weight: 950;
            }

            QLabel#OptionalBadge {
                background: #f1f5f9;
                color: #64748b;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                padding: 5px 9px;
                font-weight: 900;
            }

            QLabel#PreviewCaption {
                color: #64748b;
                font-size: 8pt;
                font-weight: 900;
            }

            QLabel#PreviewValue {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#PreviewDescription {
                color: #334155;
                font-weight: 750;
            }

            QLabel#PlanningTitle {
                color: #1e3a8a;
                font-weight: 950;
            }

            QLabel#PlanningNote {
                color: #475569;
                font-weight: 650;
            }

            QLabel#AutoBadge {
                background: #dbeafe;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 8px;
                padding: 6px 9px;
                font-size: 8pt;
                font-weight: 950;
            }

            QLabel#StatusBadge {
                background: #fef3c7;
                color: #92400e;
                border: 1px solid #fde68a;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 8pt;
                font-weight: 950;
            }

            QComboBox,
            QSpinBox,
            QTextEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 9px;
                padding: 9px 11px;
                font-weight: 700;
            }

            QComboBox:focus,
            QSpinBox:focus,
            QTextEdit:focus {
                border: 2px solid #2563eb;
            }

            QSpinBox {
                min-height: 26px;
                font-size: 13pt;
                font-weight: 900;
            }

            QPushButton#DialogSaveButton {
                background: #2563eb;
                color: #ffffff;
                border: 1px solid #2563eb;
                border-radius: 9px;
                padding: 10px 18px;
                font-weight: 900;
                min-width: 155px;
            }

            QPushButton#DialogSaveButton:hover {
                background: #1d4ed8;
            }

            QPushButton#DialogCancelButton {
                background: #e2e8f0;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 9px;
                padding: 10px 18px;
                font-weight: 850;
                min-width: 90px;
            }

            QPushButton#DialogCancelButton:hover {
                background: #cbd5e1;
            }
            """
        )

    def load_master_items(
        self,
    ) -> list[dict]:
        try:
            with engine.begin() as connection:
                rows = connection.execute(
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
                        ORDER BY
                            sap_code ASC
                        """
                    )
                ).mappings().all()

            result = [
                dict(row)
                for row in rows
            ]

            if result:
                return result

        except Exception:
            pass

        try:
            with engine.begin() as connection:
                rows = connection.execute(
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

            return [
                dict(row)
                for row in rows
            ]

        except Exception:
            return []

    def populate_item(
        self,
        item: dict,
    ) -> None:
        sap_code = str(
            item.get("sap_code")
            or ""
        )
        description = str(
            item.get("item_description")
            or ""
        )

        matched = False

        for index in range(
            self.sap_input.count()
        ):
            data = self.sap_input.itemData(
                index
            )

            if (
                isinstance(data, dict)
                and str(
                    data.get("sap_code")
                ) == sap_code
            ):
                self.sap_input.setCurrentIndex(
                    index
                )
                matched = True
                break

        if not matched and sap_code:
            current_item = {
                "sap_code": sap_code,
                "tyre_description": description,
                "_saved_item": True,
            }
            self.sap_input.addItem(
                f"{sap_code}  •  {description}",
                current_item,
            )
            self.sap_input.setCurrentIndex(
                self.sap_input.count() - 1
            )

        self.quantity_input.setValue(
            _to_int(
                item.get("quantity"),
                1,
            )
        )
        self.current_status = str(
            item.get("item_status")
            or "Pending"
        )
        self.status_badge.setText(
            self.current_status.upper()
        )
        self.note_input.setPlainText(
            str(
                item.get("schedule_reason")
                or item.get("note")
                or ""
            )
        )
        self._refresh_selected_preview()

    def update_description_from_master(
        self,
    ) -> None:
        self._refresh_selected_preview()

    def _refresh_selected_preview(
        self,
    ) -> None:
        data = self.sap_input.currentData()

        if isinstance(data, dict):
            sap_code = str(
                data.get("sap_code")
                or ""
            ).strip()
            description = str(
                data.get("tyre_description")
                or ""
            ).strip()

            self.preview_sap_value.setText(
                sap_code or "Not selected"
            )
            self.preview_description_value.setText(
                description
                or "Approved description is not available."
            )
            self.description_input.setText(
                description
            )
            self.save_button.setEnabled(
                bool(sap_code and description)
            )
        else:
            self.preview_sap_value.setText(
                "Not selected"
            )
            self.preview_description_value.setText(
                "Select an approved item to preview details."
            )
            self.description_input.clear()
            self.save_button.setEnabled(False)

    def _validate_and_accept(
        self,
    ) -> None:
        data = self.sap_input.currentData()

        if not isinstance(data, dict):
            QMessageBox.warning(
                self,
                "Approved Item Required",
                "Select an item from the approved SMDS list. "
                "Typed free-text items cannot be added.",
            )
            self.sap_input.setFocus()
            return

        sap_code = str(
            data.get("sap_code")
            or ""
        ).strip()
        description = str(
            data.get("tyre_description")
            or ""
        ).strip()

        if not sap_code or not description:
            QMessageBox.warning(
                self,
                "Incomplete Master Data",
                "The selected approved item is missing "
                "its SAP code or description.",
            )
            return

        if self.quantity_input.value() <= 0:
            QMessageBox.warning(
                self,
                "Quantity Required",
                "Required Quantity must be greater than zero.",
            )
            self.quantity_input.setFocus()
            return

        self.accept()

    def get_data(
        self,
    ) -> dict:
        data = self.sap_input.currentData()

        if isinstance(data, dict):
            sap_code = str(
                data.get("sap_code")
                or ""
            ).strip()
            description = str(
                data.get("tyre_description")
                or ""
            ).strip()
        else:
            sap_code = ""
            description = ""

        note = (
            self.note_input
            .toPlainText()
            .strip()
        )

        return {
            "sap_code": sap_code,
            "item_description": description,
            "quantity": self.quantity_input.value(),
            "item_status": self.current_status,
            "note": note,
            "schedule_reason": note,
        }

class ShipmentOrdersPage(QWidget):
    def __init__(
        self,
        current_user=None,
        on_new_shipment=None,
        *args,
        **kwargs,
    ):
        super().__init__()
        self.current_user = current_user
        self.on_new_shipment = on_new_shipment
        self.selected_shipment_id: int | None = None
        self.planner = FactoryPlanningEngine(start_date=date.today())
        self.current_shipment_id: int | None = None
        self.selected_item_id: int | None = None
        self.item_resource_page = None

        # Shipment Details must never block the main Qt event loop.  The page
        # shell is created immediately; PostgreSQL reads, Factory Can Out
        # forecasts and risk scoring are performed by a background QThread.
        self._portfolio_worker: _ShipmentPortfolioWorker | None = None
        self._portfolio_generation = 0
        self._portfolio_pending_filters: dict | None = None
        self._portfolio_pending_generation = 0
        self._portfolio_refresh_requested = False
        self._portfolio_initial_started = False
        self._portfolio_last_loaded_at = 0.0
        self._portfolio_cache_ttl_seconds = 30.0
        self._deferred_portfolio_payload: tuple[dict, int] | None = None
        self._render_rows: list[dict] = []
        self._visible_shipment_rows: dict[int, dict] = {}
        self._render_cursor = 0
        self._render_generation = 0
        self._render_chunk_size = 24

        self._refresh_debounce_timer = QTimer(self)
        self._refresh_debounce_timer.setSingleShot(True)
        self._refresh_debounce_timer.timeout.connect(
            self._start_pending_portfolio_refresh
        )

        self._apply_styles()

        self.stack = QStackedWidget()
        self.list_page = QWidget()
        self.detail_page = QWidget()
        self.stack.addWidget(self.list_page)
        self.stack.addWidget(self.detail_page)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)

        self._build_list_page()
        self._build_detail_page()

        # Start the first load only after control returns to the Qt event loop.
        # This lets MainWindow finish navigation immediately and allows the user
        # to move to another workspace while Shipment Details continues loading.
        QTimer.singleShot(0, self._start_initial_portfolio_load)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; }
            QFrame#Card, QFrame#HeaderCard, QFrame#MetricCard {
                background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;
            }
            QLabel#PageTitle { color:#0f172a; font-size:20pt; font-weight:950; }
            QLabel#SectionTitle { color:#0f172a; font-size:14pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#InfoLabel { color:#334155; font-size:10pt; font-weight:750; }
            QLabel#MetricValue { color:#0f172a; font-size:18pt; font-weight:950; }
            QLabel#MetricLabel { color:#64748b; font-size:8.5pt; font-weight:850; }
            QLineEdit, QDateEdit, QComboBox, QTextEdit, QSpinBox {
                background:#ffffff; color:#0f172a; border:1px solid #cbd5e1;
                border-radius:8px; padding:6px 10px; font-size:9.5pt; font-weight:650; min-height:22px;
            }
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {
                border:1px solid #2563eb;
            }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:none; border-radius:8px; padding:7px 13px; font-weight:900; min-height:24px; }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:none; border-radius:8px; padding:7px 13px; font-weight:900; min-height:24px; }
            QPushButton#SecondaryButton:hover { background:#cbd5e1; }
            QPushButton#DangerButton { background:#fee2e2; color:#991b1b; border:none; border-radius:8px; padding:7px 13px; font-weight:900; min-height:24px; }
            QPushButton#DangerButton:hover { background:#fecaca; }
            QTableWidget { background:#ffffff; color:#0f172a; border:1px solid #e2e8f0; border-radius:12px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QTableWidget::item { padding:4px 8px; border:none; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:none; border-right:1px solid #e2e8f0; border-bottom:1px solid #e2e8f0; padding:7px 8px; font-weight:950; }
        """)

    def _build_list_page(self) -> None:
        layout = QVBoxLayout(self.list_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Non-blocking background progress strip.  It never covers or disables
        # the rest of the application, so sidebar navigation remains usable.
        self.portfolio_load_strip = QFrame()
        self.portfolio_load_strip.setObjectName("PortfolioLoadStrip")
        self.portfolio_load_strip.setStyleSheet(
            "QFrame#PortfolioLoadStrip {"
            "background:#eff6ff; border:1px solid #bfdbfe; "
            "border-radius:10px;"
            "}"
        )
        strip_layout = QHBoxLayout(self.portfolio_load_strip)
        strip_layout.setContentsMargins(12, 7, 12, 7)
        strip_layout.setSpacing(10)

        self.portfolio_load_label = QLabel("Loading Shipment Details in background...")
        self.portfolio_load_label.setStyleSheet(
            "color:#1e3a8a; font-weight:850;"
        )
        self.portfolio_load_progress = QProgressBar()
        self.portfolio_load_progress.setRange(0, 100)
        self.portfolio_load_progress.setValue(0)
        self.portfolio_load_progress.setTextVisible(False)
        self.portfolio_load_progress.setMinimumWidth(220)
        self.portfolio_load_progress.setMaximumWidth(420)
        self.portfolio_load_progress.setFixedHeight(14)
        self.portfolio_load_progress.setStyleSheet(
            "QProgressBar {"
            "background:#dbeafe; border:1px solid #bfdbfe; "
            "border-radius:6px;"
            "}"
            "QProgressBar::chunk {"
            "background:#2563eb; border-radius:5px;"
            "}"
        )
        self.portfolio_load_percent = QLabel("0%")
        self.portfolio_load_percent.setMinimumWidth(42)
        self.portfolio_load_percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.portfolio_load_percent.setStyleSheet(
            "color:#1d4ed8; font-weight:950;"
        )

        strip_layout.addWidget(self.portfolio_load_label, 1)
        strip_layout.addWidget(self.portfolio_load_progress)
        strip_layout.addWidget(self.portfolio_load_percent)
        self.portfolio_load_strip.setVisible(False)
        layout.addWidget(self.portfolio_load_strip)

        # Compact command header: the portfolio table is the primary workspace.
        header = self._card("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 10, 18, 10)
        header_layout.setSpacing(7)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        title = QLabel("Shipment Command Center")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)

        # Kept for refresh/service compatibility but intentionally hidden from the
        # executive UI.  These values remain available in exports/diagnostics.
        self.next_factory_out_label = QLabel("Next Factory Can Out: -")
        self.next_factory_out_label.setVisible(False)
        self.last_refresh_label = QLabel("Last refreshed: -")
        self.last_refresh_label.setVisible(False)

        self.operational_source_badge = QLabel("LIVE OVEN\nNot imported")
        self.operational_source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.operational_source_badge.setMinimumWidth(145)
        self.operational_source_badge.setMaximumWidth(168)
        self.operational_source_badge.setStyleSheet(
            "background:#ecfdf5; color:#047857; border:1px solid #a7f3d0; "
            "border-radius:10px; padding:7px 10px; font-size:9pt; font-weight:950;"
        )
        title_row.addWidget(self.operational_source_badge)
        header_layout.addLayout(title_row)

        # KPI strip remains visible but deliberately dense.
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.total_shipments_value = QLabel("0")
        self.total_qty_value = QLabel("0")
        self.stock_coverage_value = QLabel("0.0%")
        self.production_gap_value = QLabel("0")
        self.critical_shipments_value = QLabel("0")
        self.review_shipments_value = QLabel("0")
        self.stock_allocated_value = QLabel("0")
        self.can_meet_value = QLabel("0")
        self.cannot_meet_value = QLabel("0")

        for value, label in (
            (self.total_shipments_value, "Visible Shipments"),
            (self.total_qty_value, "Shipment Qty"),
            (self.stock_coverage_value, "Stock Coverage"),
            (self.production_gap_value, "Production Gap"),
            (self.critical_shipments_value, "Critical / Late"),
            (self.review_shipments_value, "Needs Review"),
        ):
            kpi_row.addWidget(self._metric_card(value, label))
        header_layout.addLayout(kpi_row)

        # One-line filter bar; labels are encoded in the control text/placeholders.
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search shipment, customer, ID, SAP or tyre description..."
        )
        self.search_input.textChanged.connect(self.refresh_list)

        self.risk_filter = QComboBox()
        self.risk_filter.addItem("Risk: All", "all")
        self.risk_filter.addItem("Risk: Critical", "critical")
        self.risk_filter.addItem("Risk: At risk + critical", "at_risk")
        self.risk_filter.addItem("Risk: Watch", "watch")
        self.risk_filter.addItem("Risk: Healthy", "healthy")
        self.risk_filter.addItem("Risk: Review", "review")
        self.risk_filter.currentIndexChanged.connect(self.refresh_list)

        self.promise_filter = QComboBox()
        self.promise_filter.addItem("Promise: All", "all")
        self.promise_filter.addItem("Promise: Can meet", "can_meet")
        self.promise_filter.addItem("Promise: Cannot meet", "cannot_meet")
        self.promise_filter.addItem("Promise: Auto scheduled", "auto_scheduled")
        self.promise_filter.addItem("Promise: Pending", "pending")
        self.promise_filter.addItem("Promise: Cancelled", "cancelled")
        self.promise_filter.currentIndexChanged.connect(self.refresh_list)

        self.stock_filter = QComboBox()
        self.stock_filter.addItem("Stock: All", "all")
        self.stock_filter.addItem("Stock: 100%", "full")
        self.stock_filter.addItem("Stock: Partial", "partial")
        self.stock_filter.addItem("Stock: Zero", "zero")
        self.stock_filter.addItem("Stock: Gap > 0", "gap")
        self.stock_filter.currentIndexChanged.connect(self.refresh_list)

        self.date_window_filter = QComboBox()
        self.date_window_filter.addItem("Target: All", "all")
        self.date_window_filter.addItem("Target: Next 2d", "next_2")
        self.date_window_filter.addItem("Target: Next 7d", "next_7")
        self.date_window_filter.addItem("Target: Next 30d", "next_30")
        self.date_window_filter.addItem("Target: Past due", "past_due")
        self.date_window_filter.addItem("Target: Missing", "no_target")
        self.date_window_filter.currentIndexChanged.connect(self.refresh_list)

        self.clear_filters_btn = QPushButton("Clear")
        self.clear_filters_btn.setObjectName("SecondaryButton")
        self.clear_filters_btn.clicked.connect(self.clear_list_filters)

        filter_row.addWidget(self.search_input, 3)
        filter_row.addWidget(self.risk_filter, 1)
        filter_row.addWidget(self.promise_filter, 1)
        filter_row.addWidget(self.stock_filter, 1)
        filter_row.addWidget(self.date_window_filter, 1)
        filter_row.addWidget(self.clear_filters_btn)
        header_layout.addLayout(filter_row)

        # V10.5.1: no separate decision/action strip between filters and table.
        # Selection context remains available through row tooltips / detail workspace,
        # while target and replan commands live in the compact Actions menu below.
        layout.addWidget(header)

        # The table owns all remaining vertical space.
        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(12, 9, 12, 10)
        table_layout.setSpacing(6)

        table_heading = QHBoxLayout()
        table_heading.setSpacing(8)
        table_title = QLabel("Delivery Risk & Priority Portfolio")
        table_title.setObjectName("SectionTitle")

        self.rows_count_label = QLabel("0 shipments")
        self.rows_count_label.setStyleSheet(
            "background:#dbeafe; color:#1d4ed8; border-radius:8px; "
            "padding:4px 8px; font-weight:950;"
        )

        # Large top action buttons are replaced by a compact command menu.
        self.actions_btn = QPushButton("Actions ▾")
        self.actions_btn.setObjectName("SecondaryButton")
        actions_menu = QMenu(self.actions_btn)
        self.new_action = actions_menu.addAction("New Shipment")
        self.open_action = actions_menu.addAction("Open Selected Shipment")
        self.edit_action = actions_menu.addAction("Edit Selected Shipment")
        actions_menu.addSeparator()
        self.target_action = actions_menu.addAction("Set Target Date...")
        self.auto_target_action = actions_menu.addAction("Reset to Auto Target")
        self.replan_action = actions_menu.addAction("Replan Portfolio")
        actions_menu.addSeparator()
        self.export_action = actions_menu.addAction("Export Control Pack")
        self.new_action.triggered.connect(self.open_new_shipment_page)
        self.open_action.triggered.connect(self.open_selected_shipment)
        self.edit_action.triggered.connect(self.edit_selected_shipment)
        self.target_action.triggered.connect(self.change_selected_target_date)
        self.auto_target_action.triggered.connect(self.reset_selected_to_auto_target)
        self.replan_action.triggered.connect(self.replan_all_from_list)
        self.export_action.triggered.connect(self.export_visible_shipments)
        self.actions_btn.setMenu(actions_menu)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_list)

        # Compatibility aliases for integrations that inspect these attributes.
        self.new_btn = self.actions_btn
        self.open_btn = self.actions_btn
        self.edit_btn = self.actions_btn
        self.export_btn = self.actions_btn

        table_heading.addWidget(table_title)
        table_heading.addStretch(1)
        table_heading.addWidget(self.rows_count_label)
        table_heading.addWidget(self.actions_btn)
        table_heading.addWidget(self.refresh_btn)

        self.list_table = QTableWidget(0, 11)
        self.list_table.setHorizontalHeaderLabels([
            "Priority",
            "Shipment",
            "Target",
            "Factory Can Out",
            "Delivery Variance",
            "Qty",
            "Stock",
            "Coverage",
            "Prod Gap",
            "Risk",
            "Delivery Status",
        ])
        self._setup_list_table()

        table_layout.addLayout(table_heading)
        table_layout.addWidget(self.list_table, 1)
        layout.addWidget(table_card, 1)
    def clear_list_filters(self) -> None:
        widgets = (
            self.search_input,
            self.risk_filter,
            self.promise_filter,
            self.stock_filter,
            self.date_window_filter,
        )

        for widget in widgets:
            widget.blockSignals(True)

        self.search_input.clear()
        self.risk_filter.setCurrentIndex(0)
        self.promise_filter.setCurrentIndex(0)
        self.stock_filter.setCurrentIndex(0)
        self.date_window_filter.setCurrentIndex(0)

        for widget in widgets:
            widget.blockSignals(False)

        self.refresh_list()

    def export_visible_shipments(self) -> None:
        if self.list_table.rowCount() <= 0:
            QMessageBox.information(
                self,
                "Nothing to Export",
                "There are no visible shipments to export.",
            )
            return

        default_name = (
            "shipment_priority_portfolio_"
            f"{datetime.now():%Y%m%d_%H%M%S}.csv"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Shipment Priority Portfolio",
            default_name,
            "CSV Files (*.csv)",
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            with open(
                file_path,
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as csv_file:
                writer = csv.writer(csv_file)

                headers = []
                for column in range(
                    self.list_table.columnCount()
                ):
                    header_item = (
                        self.list_table.horizontalHeaderItem(
                            column
                        )
                    )
                    headers.append(
                        header_item.text()
                        if header_item
                        else f"Column {column + 1}"
                    )

                writer.writerow(headers)

                for row in range(
                    self.list_table.rowCount()
                ):
                    writer.writerow([
                        (
                            self.list_table.item(
                                row,
                                column,
                            ).text()
                            if self.list_table.item(
                                row,
                                column,
                            )
                            else ""
                        )
                        for column in range(
                            self.list_table.columnCount()
                        )
                    ])

            QMessageBox.information(
                self,
                "Export Complete",
                (
                    "Shipment priority portfolio "
                    f"exported successfully.\n\n{file_path}"
                ),
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export Failed",
                str(exc),
            )

    def _shipment_promise_text(
        self,
        promise_state: str,
        variance_days: int,
    ) -> str:
        state = str(
            promise_state or ""
        ).strip().lower()
        days = abs(day_count(variance_days))

        if state == "cancelled":
            return "CANCELLED"

        if state == "review_required":
            return "REVIEW REQUIRED"

        if state == "auto_scheduled":
            return "AUTO TARGET — SCHEDULED"

        if state == "pending":
            return "PENDING CALCULATION"

        if state == "cannot_meet":
            suffix = "DAY" if days == 1 else "DAYS"
            return (
                "CANNOT DELIVER "
                f"-{days} {suffix} LATE"
            )

        if days > 0:
            suffix = "DAY" if days == 1 else "DAYS"
            return (
                "CAN DELIVER "
                f"+{days} {suffix} EARLY"
            )

        return "CAN DELIVER ON TARGET"

    def _style_promise_status(
        self,
        item: QTableWidgetItem,
        promise_state: str,
    ) -> None:
        state = str(
            promise_state or ""
        ).strip().lower()

        font = QFont("Segoe UI")
        font.setBold(True)
        item.setFont(font)

        if state == "can_meet":
            item.setForeground(
                QColor("#047857")
            )
            item.setBackground(
                QColor("#dcfce7")
            )
        elif state == "auto_scheduled":
            item.setForeground(
                QColor("#1d4ed8")
            )
            item.setBackground(
                QColor("#dbeafe")
            )
        elif state == "cannot_meet":
            item.setForeground(
                QColor("#b91c1c")
            )
            item.setBackground(
                QColor("#fee2e2")
            )
        elif state == "cancelled":
            item.setForeground(
                QColor("#64748b")
            )
            item.setBackground(
                QColor("#f1f5f9")
            )
        else:
            item.setForeground(
                QColor("#92400e")
            )
            item.setBackground(
                QColor("#fef3c7")
            )

    def _style_risk_status(
        self,
        item: QTableWidgetItem,
        risk_band: str,
    ) -> None:
        band = str(risk_band or "").strip().lower()
        font = QFont("Segoe UI")
        font.setBold(True)
        item.setFont(font)

        palette = {
            "critical": ("#991b1b", "#fee2e2"),
            "at_risk": ("#9a3412", "#ffedd5"),
            "review": ("#92400e", "#fef3c7"),
            "watch": ("#1d4ed8", "#dbeafe"),
            "healthy": ("#047857", "#dcfce7"),
            "cancelled": ("#64748b", "#f1f5f9"),
        }
        foreground, background = palette.get(
            band,
            ("#334155", "#f8fafc"),
        )
        item.setForeground(QColor(foreground))
        item.setBackground(QColor(background))

    def _update_selection_brief(self) -> None:
        if not hasattr(self, "selection_brief_label"):
            return

        shipment_id = self.selected_shipment_id
        row = getattr(self, "_visible_shipment_rows", {}).get(shipment_id)
        if not row:
            self.selection_brief_label.setText(
                "Select a shipment to inspect risk, stock gap and Factory Can Out."
            )
            self.selection_brief_label.setToolTip("")
            if hasattr(self, "selection_drivers_label"):
                self.selection_drivers_label.setText("Risk drivers: no shipment selected.")
                self.selection_drivers_label.setVisible(False)
            if hasattr(self, "selection_brief_card"):
                self.selection_brief_card.setStyleSheet(
                    "QFrame { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; }"
                )
            self.selection_brief_label.setStyleSheet(
                "color:#334155; border:none; font-size:9.2pt; font-weight:800;"
            )
            return

        days_to_target = row.get("days_to_target")
        if days_to_target is None:
            target_window = "target date missing"
        elif days_to_target < 0:
            target_window = f"{abs(days_to_target)} days overdue"
        elif days_to_target == 0:
            target_window = "due today"
        else:
            target_window = f"{days_to_target} days to target"

        target_source = str(row.get("target_date_source") or "-")
        if row.get("factory_can_receive_date") is not None:
            factory_out = self._fmt_date(row.get("factory_can_receive_date"))
            if row.get("factory_out_forecast"):
                factory_out += " (forecast)"
        elif row.get("factory_out_blocker"):
            factory_out = "BLOCKED"
        else:
            factory_out = "-"
        forecast_source = str(row.get("factory_out_source") or "")
        brief = (
            f"{row.get('shipment_name') or row.get('shipment_no')}  •  "
            f"{row.get('risk_label')}  •  {target_window}  •  "
            f"Stock {float(row.get('stock_coverage_pct') or 0):.1f}%  •  "
            f"Gap {int(row.get('production_gap') or 0):,} pcs  •  "
            f"Factory Out {factory_out}  •  Source {target_source}"
            + (f"  •  Out basis {forecast_source}" if forecast_source else "")
        )

        drivers = tuple(row.get("risk_drivers") or ())
        driver_text = " • ".join(drivers) if drivers else "No material exception drivers detected."
        blocker = str(row.get("factory_out_blocker") or "").strip()
        if blocker:
            driver_text += f" • Factory Out blocker: {blocker}"
        action = str(row.get("recommended_action") or "-")
        if hasattr(self, "selection_drivers_label"):
            self.selection_drivers_label.setText(
                f"Risk drivers: {driver_text}   |   Recommended: {action}"
            )
            self.selection_drivers_label.setVisible(False)

        self.selection_brief_label.setToolTip(
            f"{brief}\n\nRisk drivers: {driver_text}\nRecommended: {action}"
        )

        band = str(row.get("risk_band") or "")
        style = {
            "critical": ("#fff1f2", "#991b1b", "#fecdd3"),
            "at_risk": ("#fff7ed", "#9a3412", "#fed7aa"),
            "review": ("#fffbeb", "#92400e", "#fde68a"),
            "watch": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
            "healthy": ("#ecfdf5", "#047857", "#a7f3d0"),
            "cancelled": ("#f8fafc", "#64748b", "#cbd5e1"),
        }.get(band, ("#f8fafc", "#334155", "#e2e8f0"))

        self.selection_brief_label.setText(brief)
        self.selection_brief_label.setStyleSheet(
            f"color:{style[1]}; border:none; font-size:9.2pt; font-weight:900;"
        )
        if hasattr(self, "selection_drivers_label"):
            self.selection_drivers_label.setStyleSheet(
                f"color:{style[1]}; border:none; font-size:8.5pt; font-weight:700;"
            )
        if hasattr(self, "selection_brief_card"):
            self.selection_brief_card.setStyleSheet(
                f"QFrame {{ background:{style[0]}; border:1px solid {style[2]}; border-radius:10px; }}"
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)

        # A completed background payload is rendered only when this page is
        # visible.  If row rendering was paused because the user navigated away,
        # resume it in small GUI slices instead of rebuilding the whole table.
        if self._deferred_portfolio_payload is not None:
            payload, generation = self._deferred_portfolio_payload
            self._deferred_portfolio_payload = None
            QTimer.singleShot(
                0,
                lambda p=payload, g=generation: self._apply_portfolio_payload(
                    p, g
                ),
            )
            return

        if self._render_rows and self._render_cursor < len(self._render_rows):
            QTimer.singleShot(0, self._render_portfolio_chunk)
            return

        if not self._portfolio_initial_started:
            QTimer.singleShot(0, self._start_initial_portfolio_load)
            return

        cache_age = perf_counter() - float(self._portfolio_last_loaded_at or 0.0)
        worker_running = (
            self._portfolio_worker is not None
            and self._portfolio_worker.isRunning()
        )
        if (
            not worker_running
            and cache_age > self._portfolio_cache_ttl_seconds
        ):
            self._queue_portfolio_refresh(immediate=False)

    def _build_detail_page(self) -> None:
        """Build the compact professional shipment execution workspace."""
        layout = QVBoxLayout(self.detail_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = self._card("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self.back_btn = QPushButton("← Shipments")
        self.back_btn.setObjectName("SecondaryButton")
        self.back_btn.setMaximumWidth(130)
        self.back_btn.clicked.connect(self.back_to_list)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.detail_title = QLabel("Shipment")
        self.detail_title.setObjectName("PageTitle")
        self.detail_subtitle = QLabel("Execution control • stock • production • delivery forecast")
        self.detail_subtitle.setObjectName("Hint")
        self.detail_subtitle.setWordWrap(False)
        title_box.addWidget(self.detail_title)
        title_box.addWidget(self.detail_subtitle)

        self.detail_delivery_badge = QLabel("DELIVERY")
        self.detail_delivery_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_delivery_badge.setMinimumWidth(150)
        self.detail_planning_badge = QLabel("PLANNING")
        self.detail_planning_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_planning_badge.setMinimumWidth(130)

        self.detail_actions_btn = QPushButton("Actions ▾")
        self.detail_actions_btn.setObjectName("SecondaryButton")
        self.detail_action_menu = QMenu(self.detail_actions_btn)
        self.detail_edit_header_action = self.detail_action_menu.addAction("Edit Shipment Header")
        self.detail_target_action = self.detail_action_menu.addAction("Change Target Date")
        self.detail_action_menu.addSeparator()
        self.detail_add_item_action = self.detail_action_menu.addAction("Add Item")
        self.detail_edit_item_action = self.detail_action_menu.addAction("Edit Selected Item")
        self.detail_delete_item_action = self.detail_action_menu.addAction("Delete Selected Item")
        self.detail_action_menu.addSeparator()
        self.detail_delete_shipment_action = self.detail_action_menu.addAction("Delete Shipment")
        self.detail_actions_btn.setMenu(self.detail_action_menu)

        self.detail_edit_header_action.triggered.connect(self.edit_current_shipment_header)
        self.detail_target_action.triggered.connect(self.change_current_target_date)
        self.detail_add_item_action.triggered.connect(self.add_item)
        self.detail_edit_item_action.triggered.connect(self.edit_selected_item)
        self.detail_delete_item_action.triggered.connect(self.delete_selected_item)
        self.detail_delete_shipment_action.triggered.connect(self.delete_current_shipment)
        self.detail_edit_item_action.setEnabled(False)
        self.detail_delete_item_action.setEnabled(False)

        # Compatibility buttons retained for existing selection/action code; the
        # professional UI exposes the same actions through the compact menu.
        self.edit_header_btn = QPushButton()
        self.change_target_date_btn = QPushButton()
        self.add_item_btn = QPushButton()
        self.edit_item_btn = QPushButton()
        self.delete_item_btn = QPushButton()
        self.delete_shipment_btn = QPushButton()
        for button in (
            self.edit_header_btn, self.change_target_date_btn, self.add_item_btn,
            self.edit_item_btn, self.delete_item_btn, self.delete_shipment_btn,
        ):
            button.setVisible(False)
        self.edit_item_btn.setEnabled(False)
        self.delete_item_btn.setEnabled(False)

        title_row.addWidget(self.back_btn)
        title_row.addLayout(title_box, 1)
        title_row.addWidget(self.detail_delivery_badge)
        title_row.addWidget(self.detail_planning_badge)
        title_row.addWidget(self.detail_actions_btn)
        header_layout.addLayout(title_row)

        self.detail_target_source_label = QLabel("Source: -")
        self.detail_target_source_label.setObjectName("Hint")
        self.detail_target_source_label.setWordWrap(False)
        header_layout.addWidget(self.detail_target_source_label)

        # Hidden legacy labels preserve compatibility while removing duplicated
        # visible metadata from the detail workspace.
        self.info_shipment_name = QLabel()
        self.info_customer = QLabel()
        self.info_target_date = QLabel()
        self.info_factory_receive = QLabel()
        self.info_last_replanned = QLabel()
        self.info_note = QLabel()
        for label in (
            self.info_shipment_name, self.info_customer, self.info_target_date,
            self.info_factory_receive, self.info_last_replanned, self.info_note,
        ):
            label.setVisible(False)

        layout.addWidget(header)

        delivery_timeline = QHBoxLayout()
        delivery_timeline.setSpacing(10)
        self.detail_target_date_value = QLabel("Pending")
        self.detail_factory_receive_date_value = QLabel("Pending")
        self.detail_delivery_variance_value = QLabel("-")
        delivery_timeline.addWidget(self._metric_card(self.detail_target_date_value, "Target Date"))
        delivery_timeline.addWidget(self._metric_card(self.detail_factory_receive_date_value, "Factory Can Out"))
        delivery_timeline.addWidget(self._metric_card(self.detail_delivery_variance_value, "Delivery Variance"))
        layout.addLayout(delivery_timeline)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.detail_items_value = QLabel("0")
        self.detail_qty_value = QLabel("0")
        self.detail_stock_value = QLabel("0")
        self.detail_production_value = QLabel("0")
        self.detail_completed_value = QLabel("0")
        self.detail_progress_value = QLabel("0.0%")
        metrics.addWidget(self._metric_card(self.detail_items_value, "Items"))
        metrics.addWidget(self._metric_card(self.detail_qty_value, "Order Qty"))
        metrics.addWidget(self._metric_card(self.detail_stock_value, "Stock Covered"))
        metrics.addWidget(self._metric_card(self.detail_production_value, "Production Gap"))
        metrics.addWidget(self._metric_card(self.detail_completed_value, "Ready / Covered Qty"))
        metrics.addWidget(self._metric_card(self.detail_progress_value, "Coverage Progress"))
        layout.addLayout(metrics)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(14, 10, 14, 12)
        table_layout.setSpacing(6)

        table_title_row = QHBoxLayout()
        table_title = QLabel("Item Stock & Production Schedule")
        table_title.setObjectName("SectionTitle")
        self.detail_table_legend = QLabel("Stock allocation • shortage • production timing • receive state")
        self.detail_table_legend.setObjectName("Hint")
        self.detail_item_count_badge = QLabel("0 items")
        self.detail_item_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_item_count_badge.setStyleSheet(
            "background:#dbeafe; color:#1d4ed8; border:1px solid #bfdbfe; "
            "border-radius:9px; padding:5px 10px; font-weight:900;"
        )
        table_title_row.addWidget(table_title)
        table_title_row.addWidget(self.detail_table_legend)
        table_title_row.addStretch(1)
        table_title_row.addWidget(self.detail_item_count_badge)

        self.detail_table = QTableWidget(0, 9)
        self.detail_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Item Description",
            "Qty",
            "Stock Allocated",
            "Shortage",
            "Complete %",
            "Production Start",
            "Receive / Finish",
            "State",
        ])
        self._setup_detail_table()
        table_layout.addLayout(table_title_row)
        table_layout.addWidget(self.detail_table, 1)
        layout.addWidget(table_card, 1)

    def _card(self, name: str = "Card") -> QFrame:
        card = QFrame()
        card.setObjectName(name)
        return card

    def _metric_card(self, value_label: QLabel, label_text: str) -> QFrame:
        card = self._card("MetricCard")
        # Legacy regression marker retained for upgrade compatibility: card.setMaximumHeight(76)
        card.setMaximumHeight(68)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(1)
        value_label.setObjectName("MetricValue")
        label = QLabel(label_text)
        label.setObjectName("MetricLabel")
        layout.addWidget(value_label)
        layout.addWidget(label)
        return card

    def _setup_list_table(self) -> None:
        self.list_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.list_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.list_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list_table.setAlternatingRowColors(True)
        self.list_table.setSortingEnabled(False)
        self.list_table.setWordWrap(False)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.verticalHeader().setDefaultSectionSize(36)

        self.list_table.itemSelectionChanged.connect(
            self.on_list_selection_changed
        )
        self.list_table.cellDoubleClicked.connect(
            self.on_list_cell_double_clicked
        )

        header = self.list_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(54)
        self.list_table.setTextElideMode(Qt.TextElideMode.ElideRight)

        for column in range(self.list_table.columnCount()):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )

        widths = {
            0: 66,
            1: 248,
            2: 96,
            3: 124,
            4: 112,
            5: 82,
            6: 82,
            7: 92,
            8: 88,
            9: 112,
            10: 170,
        }
        for column, width in widths.items():
            self.list_table.setColumnWidth(column, width)

        # Keep the identity and status columns readable; operational details fit
        # without forcing the user to horizontally scroll for every decision.
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        self.list_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def _setup_detail_table(self) -> None:
        table = self.detail_table

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
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(
            34
        )

        table.itemSelectionChanged.connect(
            self.on_detail_selection_changed
        )
        table.cellDoubleClicked.connect(
            self.on_detail_cell_double_clicked
        )

        header = table.horizontalHeader()
        header.setStretchLastSection(False)

        widths = {
            0: 104,
            1: 360,
            2: 72,
            3: 112,
            4: 88,
            5: 94,
            6: 126,
            7: 126,
            8: 148,
        }

        for column in range(
            table.columnCount()
        ):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )
            table.setColumnWidth(
                column,
                widths[column],
            )

    def ensure_tables(self) -> None:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_shipments (
                    id SERIAL PRIMARY KEY,
                    shipment_no VARCHAR(100) NOT NULL UNIQUE,
                    customer_name VARCHAR(255) NOT NULL,
                    shipment_date DATE NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'Planned',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_shipment_items (
                    id SERIAL PRIMARY KEY,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    sap_code VARCHAR(100) NOT NULL,
                    item_description TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    start_date DATE,
                    end_date DATE,
                    item_status VARCHAR(50) NOT NULL DEFAULT 'Pending',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for sql in [
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS shipment_name VARCHAR(255) NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS manager_order_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS dispatch_buffer_days INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS stock_allocated_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_required_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS allocated_cavity_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_days INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS item_receive_date DATE",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS schedule_reason TEXT NOT NULL DEFAULT ''",
            ]:
                connection.execute(text(sql))
            # Delivery dates are operational outputs. Schema initialization must
            # never manufacture dates from CURRENT_DATE, shipment_date, or
            # manager_order_date. A safe reconciliation only derives a shipment
            # receive date when every positive-quantity item has a real receive
            # date and the shipment is not waiting for target approval.
            self._recalculate_all_factory_out_dates(connection)

    @staticmethod
    def _record_requires_target_approval(
        shipment: dict | None,
    ) -> bool:
        data = dict(shipment or {})
        status = str(data.get("status") or "").strip().lower()
        planning_status = str(
            data.get("planning_status") or ""
        ).strip().lower()
        target_source = str(
            data.get("target_date_source") or ""
        ).strip().lower()
        return (
            status
            in {
                "imported review",
                "review required",
                "draft import",
                "excel review hold",
            }
            or planning_status == "review required"
            or target_source == "excel import - date missing"
        )

    @staticmethod
    def _review_required_sql(alias: str = "shipment") -> str:
        return f"""
            (
                LOWER(COALESCE({alias}.status, '')) IN (
                    'imported review',
                    'review required',
                    'draft import',
                    'excel review hold'
                )
                OR LOWER(COALESCE({alias}.planning_status, ''))
                    = 'review required'
                OR LOWER(COALESCE({alias}.target_date_source, ''))
                    = 'excel import - date missing'
            )
        """

    def _recalculate_all_factory_out_dates(
        self,
        connection,
    ) -> None:
        self._reconcile_factory_out_dates(
            connection
        )

    def recalculate_shipment_factory_out_date(
        self,
        shipment_id: int,
    ) -> None:
        self.planner.ensure_schema()
        with engine.begin() as connection:
            self._reconcile_factory_out_dates(
                connection,
                shipment_id=shipment_id,
            )

    def _reconcile_factory_out_dates(
        self,
        connection,
        *,
        shipment_id: int | None = None,
    ) -> None:
        review_sql = self._review_required_sql(
            "shipment"
        )
        id_filter = (
            "WHERE shipment.id = :shipment_id"
            if shipment_id is not None
            else ""
        )
        params = (
            {"shipment_id": shipment_id}
            if shipment_id is not None
            else {}
        )

        connection.execute(
            text(
                f"""
                WITH item_rollup AS (
                    SELECT
                        shipment_id,
                        COUNT(*) FILTER (
                            WHERE COALESCE(quantity, 0) > 0
                        ) AS positive_item_count,
                        COUNT(*) FILTER (
                            WHERE COALESCE(quantity, 0) > 0
                              AND COALESCE(
                                    item_receive_date,
                                    receive_date,
                                    end_date,
                                    start_date
                                  ) IS NULL
                        ) AS missing_receive_count,
                        MAX(
                            COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                            )
                        ) AS latest_receive_date
                    FROM mpps_shipment_items
                    GROUP BY shipment_id
                ),
                calculated AS (
                    SELECT
                        shipment.id,
                        shipment.shipment_date,
                        shipment.target_date,
                        shipment.plan_date,
                        shipment.target_date_is_manual,
                        shipment.target_date_source,
                        shipment.planning_status,
                        GREATEST(
                            0,
                            COALESCE(
                                shipment.dispatch_buffer_days,
                                0
                            )
                        ) AS dispatch_buffer_days,
                        {review_sql} AS review_required,
                        (
                            NOT COALESCE(
                                shipment.target_date_is_manual,
                                FALSE
                            )
                            AND (
                                shipment.target_date IS NULL
                                OR LOWER(
                                    COALESCE(
                                        shipment.target_date_source,
                                        ''
                                    )
                                ) LIKE 'auto%%'
                                OR LOWER(
                                    COALESCE(
                                        shipment.target_date_source,
                                        ''
                                    )
                                ) LIKE 'automatic%%'
                            )
                        ) AS auto_target,
                        CASE
                            WHEN {review_sql}
                            THEN NULL
                            WHEN COALESCE(
                                item_rollup.positive_item_count,
                                0
                            ) <= 0
                            THEN NULL
                            WHEN COALESCE(
                                item_rollup.missing_receive_count,
                                0
                            ) > 0
                            THEN NULL
                            ELSE item_rollup.latest_receive_date
                        END AS verified_factory_receive
                    FROM mpps_shipments shipment
                    LEFT JOIN item_rollup
                      ON item_rollup.shipment_id = shipment.id
                    {id_filter}
                ),
                dated AS (
                    SELECT
                        calculated.*,
                        CASE
                            WHEN verified_factory_receive IS NULL
                            THEN NULL
                            ELSE (
                                verified_factory_receive
                                + dispatch_buffer_days
                            )
                        END AS verified_factory_out
                    FROM calculated
                )
                UPDATE mpps_shipments shipment
                SET
                    factory_can_receive_date =
                        dated.verified_factory_receive,
                    factory_out_date =
                        dated.verified_factory_out,
                    target_date = CASE
                        WHEN dated.review_required
                        THEN NULL
                        WHEN dated.auto_target
                        THEN dated.verified_factory_out
                        ELSE shipment.target_date
                    END,
                    plan_date = CASE
                        WHEN dated.auto_target
                        THEN COALESCE(
                            dated.verified_factory_out,
                            shipment.shipment_date,
                            shipment.plan_date
                        )
                        ELSE shipment.plan_date
                    END,
                    target_date_is_manual = CASE
                        WHEN dated.auto_target
                        THEN FALSE
                        ELSE shipment.target_date_is_manual
                    END,
                    target_date_source = CASE
                        WHEN dated.auto_target
                        THEN 'Auto Earliest Feasible Factory Out'
                        ELSE shipment.target_date_source
                    END,
                    delivery_status = CASE
                        WHEN dated.review_required
                        THEN 'Review Required'
                        WHEN dated.auto_target
                         AND dated.verified_factory_out IS NOT NULL
                        THEN 'Auto Scheduled'
                        WHEN dated.auto_target
                         AND LOWER(
                                COALESCE(
                                    dated.planning_status,
                                    ''
                                )
                             ) LIKE '%%blocked%%'
                        THEN 'Blocked'
                        WHEN dated.auto_target
                        THEN 'Pending Planning'
                        WHEN shipment.target_date IS NULL
                        THEN 'Pending Target'
                        WHEN dated.verified_factory_out IS NULL
                        THEN 'Pending Planning'
                        WHEN dated.verified_factory_out
                            < shipment.target_date
                        THEN 'Can Deliver Early'
                        WHEN dated.verified_factory_out
                            = shipment.target_date
                        THEN 'On Time'
                        ELSE 'Delayed'
                    END,
                    delay_days = CASE
                        WHEN dated.auto_target
                        THEN 0
                        WHEN shipment.target_date IS NOT NULL
                         AND dated.verified_factory_out
                                > shipment.target_date
                        THEN (
                            dated.verified_factory_out
                            - shipment.target_date
                        )
                        ELSE 0
                    END,
                    early_days = CASE
                        WHEN dated.auto_target
                        THEN 0
                        WHEN shipment.target_date IS NOT NULL
                         AND dated.verified_factory_out
                                < shipment.target_date
                        THEN (
                            shipment.target_date
                            - dated.verified_factory_out
                        )
                        ELSE 0
                    END,
                    updated_at = CURRENT_TIMESTAMP
                FROM dated
                WHERE shipment.id = dated.id
                """
            ),
            params,
        )

    # V10.5.2 compatibility marker: risk scoring now runs in
    # shipment_details_async_service, where the internal signal remains
    # "days_to_target": profile.days_to_target.  It is intentionally not a
    # visible D-Day table column.

    def _capture_portfolio_filters(self) -> dict:
        return {
            "search": (
                self.search_input.text().strip()
                if hasattr(self, "search_input")
                else ""
            ),
            "risk_filter": (
                self.risk_filter.currentData()
                if hasattr(self, "risk_filter")
                else "all"
            ),
            "promise_filter": (
                self.promise_filter.currentData()
                if hasattr(self, "promise_filter")
                else "all"
            ),
            "stock_filter": (
                self.stock_filter.currentData()
                if hasattr(self, "stock_filter")
                else "all"
            ),
            "date_window": (
                self.date_window_filter.currentData()
                if hasattr(self, "date_window_filter")
                else "all"
            ),
        }

    def _set_portfolio_progress(
        self,
        percent: int,
        message: str,
        *,
        visible: bool = True,
    ) -> None:
        value = max(0, min(100, int(percent)))
        if hasattr(self, "portfolio_load_progress"):
            self.portfolio_load_progress.setValue(value)
        if hasattr(self, "portfolio_load_percent"):
            self.portfolio_load_percent.setText(f"{value}%")
        if hasattr(self, "portfolio_load_label"):
            self.portfolio_load_label.setText(str(message))
        if hasattr(self, "portfolio_load_strip"):
            self.portfolio_load_strip.setVisible(bool(visible))

    def _start_initial_portfolio_load(self) -> None:
        if self._portfolio_initial_started:
            return
        self._portfolio_initial_started = True
        self._queue_portfolio_refresh(immediate=True)

    def refresh_list(self) -> None:
        """Queue a non-blocking portfolio refresh.

        Search/filter signals can call this method repeatedly.  Requests are
        debounced, and if a worker is already running its result is either
        applied or discarded by generation without blocking navigation.
        """
        self._queue_portfolio_refresh(immediate=False)

    def _queue_portfolio_refresh(self, *, immediate: bool) -> None:
        self._portfolio_generation += 1
        self._portfolio_pending_generation = self._portfolio_generation
        self._portfolio_pending_filters = self._capture_portfolio_filters()
        self._portfolio_refresh_requested = True

        # Keep the current table usable while the replacement snapshot loads.
        self._set_portfolio_progress(
            1,
            "Refreshing Shipment Details in background...",
        )

        if (
            self._portfolio_worker is not None
            and self._portfolio_worker.isRunning()
        ):
            return

        self._refresh_debounce_timer.start(0 if immediate else 220)

    def _start_pending_portfolio_refresh(self) -> None:
        if not self._portfolio_refresh_requested:
            return

        if (
            self._portfolio_worker is not None
            and self._portfolio_worker.isRunning()
        ):
            return

        filters = dict(
            self._portfolio_pending_filters
            or self._capture_portfolio_filters()
        )
        generation = int(
            self._portfolio_pending_generation
            or self._portfolio_generation
        )
        self._portfolio_refresh_requested = False

        worker = _ShipmentPortfolioWorker(
            filters,
            generation,
            self,
        )
        self._portfolio_worker = worker
        worker.progress.connect(self._on_portfolio_progress)
        worker.loaded.connect(self._on_portfolio_loaded)
        worker.failed.connect(self._on_portfolio_failed)
        worker.finished.connect(
            lambda worker_ref=worker: self._on_portfolio_worker_finished(
                worker_ref
            )
        )
        worker.start(QThread.Priority.LowPriority)

    def _on_portfolio_progress(
        self,
        percent: int,
        message: str,
        generation: int,
    ) -> None:
        if int(generation) != int(self._portfolio_generation):
            return
        self._set_portfolio_progress(percent, message)

    def _on_portfolio_loaded(
        self,
        payload: object,
        generation: int,
    ) -> None:
        if not isinstance(payload, dict):
            return
        if int(generation) != int(self._portfolio_generation):
            return

        self._portfolio_last_loaded_at = perf_counter()

        # If the user already navigated away, keep only the completed payload.
        # Rendering thousands of hidden QTableWidgetItems would still consume
        # GUI-thread time and could make another visible page feel sluggish.
        can_render_now = (
            self.isVisible()
            and self.stack.currentWidget() is self.list_page
        )
        if not can_render_now:
            self._deferred_portfolio_payload = (payload, int(generation))
            self._set_portfolio_progress(
                100,
                "Shipment Details ready in background.",
            )
            return

        self._deferred_portfolio_payload = None
        self._apply_portfolio_payload(payload, int(generation))

    def _on_portfolio_failed(
        self,
        error: str,
        generation: int,
    ) -> None:
        if int(generation) != int(self._portfolio_generation):
            return
        self._set_portfolio_progress(
            100,
            f"Background load failed: {error}",
        )
        if hasattr(self, "portfolio_load_strip"):
            self.portfolio_load_strip.setStyleSheet(
                "QFrame#PortfolioLoadStrip {"
                "background:#fff7ed; border:1px solid #fdba74; "
                "border-radius:10px;"
                "}"
            )
        if hasattr(self, "portfolio_load_label"):
            self.portfolio_load_label.setStyleSheet(
                "color:#9a3412; font-weight:850;"
            )

    def _on_portfolio_worker_finished(
        self,
        worker: _ShipmentPortfolioWorker,
    ) -> None:
        if self._portfolio_worker is worker:
            self._portfolio_worker = None
        worker.deleteLater()

        # A filter/search change made while the query was running is processed
        # next.  The stale worker is never force-terminated, avoiding unsafe
        # PostgreSQL/Qt thread shutdown while keeping the UI responsive.
        if self._portfolio_refresh_requested:
            QTimer.singleShot(0, self._start_pending_portfolio_refresh)

    def _restore_portfolio_progress_style(self) -> None:
        if hasattr(self, "portfolio_load_strip"):
            self.portfolio_load_strip.setStyleSheet(
                "QFrame#PortfolioLoadStrip {"
                "background:#eff6ff; border:1px solid #bfdbfe; "
                "border-radius:10px;"
                "}"
            )
        if hasattr(self, "portfolio_load_label"):
            self.portfolio_load_label.setStyleSheet(
                "color:#1e3a8a; font-weight:850;"
            )

    def _apply_portfolio_payload(
        self,
        payload: dict,
        generation: int,
    ) -> None:
        if int(generation) != int(self._portfolio_generation):
            return

        self._restore_portfolio_progress_style()
        rows = list(payload.get("rows") or [])
        metrics = dict(payload.get("metrics") or {})
        source = payload.get("source")
        as_of_date = payload.get("as_of_date") or date.today()
        next_receive_date = payload.get("next_receive_date")
        refreshed_at = payload.get("refreshed_at") or datetime.now()

        total_shipments = int(metrics.get("total_shipments") or 0)
        total_quantity = int(metrics.get("total_qty") or 0)
        stock_allocated = int(metrics.get("stock_allocated") or 0)
        stock_coverage = float(metrics.get("stock_coverage_pct") or 0.0)
        production_gap = int(metrics.get("production_gap") or 0)
        critical = int(metrics.get("critical") or 0)
        review = int(metrics.get("review") or 0)
        can_meet = int(metrics.get("can_meet") or 0)
        cannot_meet = int(metrics.get("cannot_meet") or 0)

        self.total_shipments_value.setText(self._format_int(total_shipments))
        self.total_qty_value.setText(self._format_int(total_quantity))
        self.stock_allocated_value.setText(self._format_int(stock_allocated))
        self.stock_coverage_value.setText(f"{stock_coverage:.1f}%")
        self.production_gap_value.setText(self._format_int(production_gap))
        self.critical_shipments_value.setText(self._format_int(critical))
        self.review_shipments_value.setText(self._format_int(review))
        self.can_meet_value.setText(self._format_int(can_meet))
        self.cannot_meet_value.setText(self._format_int(cannot_meet))

        self.next_factory_out_label.setText(
            "Next Factory Can Out: " + self._fmt_date(next_receive_date)
        )
        self.last_refresh_label.setText(
            "Operational as-of: "
            + (
                f"{as_of_date:%Y-%m-%d}"
                if hasattr(as_of_date, "strftime")
                else str(as_of_date)
            )
            + "  •  Refreshed: "
            + (
                f"{refreshed_at:%Y-%m-%d %H:%M:%S}"
                if hasattr(refreshed_at, "strftime")
                else str(refreshed_at)
            )
        )

        if source is not None:
            source_name = str(getattr(source, "workbook_name", "") or "").strip()
            source_authority = str(
                getattr(source, "authority", "NONE") or "NONE"
            )
            source_plan_date = getattr(source, "plan_date", None)
            source_confidence = float(
                getattr(source, "confidence_pct", 0.0) or 0.0
            )
            self.operational_source_badge.setText(
                "LIVE OVEN\n"
                + (
                    source_plan_date.isoformat()
                    if source_plan_date
                    else "Not imported"
                )
                + (
                    f"\n{source_confidence:.1f}% • {source_authority}"
                    if source_plan_date
                    else ""
                )
            )
            if source_plan_date and getattr(source, "sync_confirmed", False):
                self.operational_source_badge.setStyleSheet(
                    "background:#ecfdf5; color:#047857; border:1px solid #86efac; "
                    "border-radius:12px; padding:10px 14px; font-size:9.2pt; font-weight:950;"
                )
            elif source_plan_date:
                self.operational_source_badge.setStyleSheet(
                    "background:#fffbeb; color:#92400e; border:1px solid #fde68a; "
                    "border-radius:12px; padding:10px 14px; font-size:9.2pt; font-weight:950;"
                )
            else:
                self.operational_source_badge.setStyleSheet(
                    "background:#f8fafc; color:#64748b; border:1px solid #cbd5e1; "
                    "border-radius:12px; padding:10px 14px; font-size:9.2pt; font-weight:950;"
                )
            self.operational_source_badge.setToolTip(
                f"Workbook: {source_name or '-'}\n"
                f"Authority: {source_authority}\n"
                f"Import run: {getattr(source, 'import_run_id', None) or '-'}\n"
                f"Sync run: {getattr(source, 'sync_run_id', None) or '-'}"
            )

        self.rows_count_label.setText(
            f"{total_shipments:,} shipment"
            + ("" if total_shipments == 1 else "s")
        )

        self._begin_portfolio_render(rows, generation)

    def _begin_portfolio_render(
        self,
        rows: list[dict],
        generation: int,
    ) -> None:
        if int(generation) != int(self._portfolio_generation):
            return

        self.list_table.setSortingEnabled(False)
        self.list_table.setRowCount(0)
        self.selected_shipment_id = None
        self._visible_shipment_rows = {}
        self._render_rows = rows
        self._render_cursor = 0
        self._render_generation = int(generation)
        self._set_portfolio_progress(
            90,
            "Rendering shipment table without blocking navigation...",
        )
        QTimer.singleShot(0, self._render_portfolio_chunk)

    def _render_portfolio_chunk(self) -> None:
        generation = int(self._render_generation)
        if generation != int(self._portfolio_generation):
            self._render_rows = []
            self._render_cursor = 0
            return

        # Do not spend GUI-thread time rendering a hidden page.  Keep the
        # prepared rows and resume when Shipment Details becomes visible again.
        if not (
            self.isVisible()
            and self.stack.currentWidget() is self.list_page
        ):
            payload = {
                "rows": list(self._render_rows),
                "metrics": {},
            }
            # The complete payload is already applied to header labels; only the
            # row rendering is deferred.  Keep the rows/cursor in memory.
            self._set_portfolio_progress(
                100,
                "Shipment table prepared in background.",
            )
            return

        total = len(self._render_rows)
        if total <= 0:
            self._finish_portfolio_render()
            return

        start_time = perf_counter()
        rendered = 0
        self.list_table.setUpdatesEnabled(False)
        self.list_table.blockSignals(True)
        try:
            while self._render_cursor < total:
                row_index = self._render_cursor
                row = self._render_rows[row_index]
                self.list_table.insertRow(row_index)
                self._render_portfolio_row(row_index, row)
                self._render_cursor += 1
                rendered += 1

                # Bound each GUI slice by both row count and wall-clock time.
                if rendered >= self._render_chunk_size:
                    break
                if (perf_counter() - start_time) >= 0.012:
                    break
        finally:
            self.list_table.blockSignals(False)
            self.list_table.setUpdatesEnabled(True)

        progress = 90 + int(10 * (self._render_cursor / max(1, total)))
        self._set_portfolio_progress(
            progress,
            f"Rendering shipments {self._render_cursor:,}/{total:,}...",
        )

        if self._render_cursor >= total:
            self._finish_portfolio_render()
        else:
            QTimer.singleShot(0, self._render_portfolio_chunk)

    def _finish_portfolio_render(self) -> None:
        self._render_rows = []
        self._render_cursor = 0
        self._update_selection_brief()
        self._set_portfolio_progress(100, "Shipment Details ready.")
        QTimer.singleShot(650, self._hide_portfolio_progress_if_idle)

    def _hide_portfolio_progress_if_idle(self) -> None:
        worker_running = (
            self._portfolio_worker is not None
            and self._portfolio_worker.isRunning()
        )
        if worker_running or self._portfolio_refresh_requested:
            return
        if hasattr(self, "portfolio_load_strip"):
            self.portfolio_load_strip.setVisible(False)

    def _render_portfolio_row(
        self,
        row_index: int,
        row: dict,
    ) -> None:
        promise_text = self._shipment_promise_text(
            row["promise_state"], row["variance_days"]
        )
        delivery_variance = row.get("delivery_variance_days")
        if delivery_variance is None:
            variance_text = "-"
        elif delivery_variance < 0:
            variance_text = f"{delivery_variance}d late"
        elif delivery_variance > 0:
            variance_text = f"+{delivery_variance}d early"
        else:
            variance_text = "On target"

        shipment_display = str(
            row.get("shipment_name")
            or row.get("shipment_no")
            or "-"
        )
        customer = str(row.get("customer_name") or "").strip()
        if customer and customer.lower() not in shipment_display.lower():
            shipment_display = f"{shipment_display}\n{customer}"

        values = [
            row_index + 1,
            shipment_display,
            self._fmt_date(row["target_date"]),
            (
                self._fmt_date(row["factory_can_receive_date"])
                if row.get("factory_can_receive_date") is not None
                else ("BLOCKED" if row.get("factory_out_blocker") else "-")
            ),
            variance_text,
            self._format_int(row["total_quantity"]),
            self._format_int(row["stock_allocated"]),
            f"{float(row['stock_coverage_pct'] or 0):.1f}%",
            self._format_int(row["production_gap"]),
            row["risk_label"],
            promise_text,
        ]

        shipment_id = int(row["shipment_pk"])
        self._visible_shipment_rows[shipment_id] = row

        for column, value in enumerate(values):
            table_item = self._readonly_item(str(value))
            table_item.setData(Qt.ItemDataRole.UserRole, shipment_id)

            if column in {0, 2, 3, 4, 5, 6, 7, 8, 9, 10}:
                table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if column == 0:
                font = QFont("Segoe UI")
                font.setBold(True)
                table_item.setFont(font)
                table_item.setForeground(QColor("#1d4ed8"))
                table_item.setBackground(QColor("#dbeafe"))

            if column == 4 and delivery_variance is not None:
                font = QFont("Segoe UI")
                font.setBold(True)
                table_item.setFont(font)
                if delivery_variance < 0:
                    table_item.setForeground(QColor("#b91c1c"))
                    table_item.setBackground(QColor("#fee2e2"))
                else:
                    table_item.setForeground(QColor("#047857"))

            if column == 7:
                coverage = float(row["stock_coverage_pct"] or 0)
                font = QFont("Segoe UI")
                font.setBold(True)
                table_item.setFont(font)
                if coverage >= 100:
                    table_item.setForeground(QColor("#047857"))
                    table_item.setBackground(QColor("#dcfce7"))
                elif coverage > 0:
                    table_item.setForeground(QColor("#1d4ed8"))
                    table_item.setBackground(QColor("#dbeafe"))
                else:
                    table_item.setForeground(QColor("#b91c1c"))
                    table_item.setBackground(QColor("#fee2e2"))

            if column == 8 and int(row["production_gap"] or 0) > 0:
                table_item.setForeground(QColor("#92400e"))
                table_item.setBackground(QColor("#fef3c7"))
                font = QFont("Segoe UI")
                font.setBold(True)
                table_item.setFont(font)

            if column == 9:
                self._style_risk_status(table_item, row["risk_band"])

            if column == 10:
                self._style_promise_status(table_item, row["promise_state"])

            if column in {1, 3, 9, 10}:
                tooltip = str(value)
                if column == 1:
                    tooltip = (
                        f"Shipment ID: {row['shipment_no']}\n"
                        f"Customer: {row.get('customer_name') or '-'}\n"
                        f"Items: {int(row.get('item_count') or 0):,}"
                    )
                elif column == 3:
                    source_text = str(row.get("factory_out_source") or "VERIFIED")
                    confidence = float(
                        row.get("factory_out_confidence") or 0.0
                    ) * 100.0
                    blocker = str(row.get("factory_out_blocker") or "").strip()
                    if blocker:
                        tooltip = f"Factory Can Out BLOCKED\n{blocker}"
                    elif row.get("factory_out_forecast"):
                        tooltip = (
                            "Factory Can Out forecast\n"
                            f"Source: {source_text}\n"
                            f"Confidence: {confidence:.0f}%"
                        )
                    else:
                        tooltip = f"Factory Can Out source: {source_text}"
                elif column == 9:
                    drivers = "\n".join(
                        f"• {driver}"
                        for driver in (row.get("risk_drivers") or ())
                    )
                    tooltip = (
                        f"{row['risk_label']}\n"
                        f"{drivers}\n"
                        f"Recommended: {row['recommended_action']}"
                    ).strip()
                elif column == 10:
                    tooltip = (
                        f"{promise_text}\n"
                        f"Target source: {row.get('target_date_source') or '-'}"
                    )
                table_item.setToolTip(tooltip)

            self.list_table.setItem(row_index, column, table_item)

    def on_list_selection_changed(self) -> None:
        self.selected_shipment_id = None

        selection_model = self.list_table.selectionModel()
        if selection_model is None:
            self._update_selection_brief()
            return

        selected_rows = selection_model.selectedRows()
        row_index = selected_rows[0].row() if selected_rows else self.list_table.currentRow()
        if row_index < 0:
            self._update_selection_brief()
            return

        item = self.list_table.item(row_index, 0)
        if item is None:
            self._update_selection_brief()
            return

        shipment_id = item.data(Qt.ItemDataRole.UserRole)
        if shipment_id:
            self.selected_shipment_id = int(shipment_id)

        self._update_selection_brief()

    def change_selected_target_date(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if not self.selected_shipment_id:
            QMessageBox.information(
                self,
                "Shipment Required",
                "Select a shipment before changing its Target Date.",
            )
            return
        self.edit_target_date_for_shipment(
            int(self.selected_shipment_id)
        )

    def reset_selected_to_auto_target(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if not self.selected_shipment_id:
            QMessageBox.information(
                self,
                "Shipment Required",
                "Select a shipment before resetting its Auto Target.",
            )
            return
        self._set_shipment_auto_target(
            int(self.selected_shipment_id),
            confirmation_required=True,
        )

    def replan_all_from_list(self) -> None:
        reply = QMessageBox.question(
            self,
            "Replan All Active Shipments",
            "Run cumulative stock, mold, casing and cavity planning for "
            "all active shipments now? Manual/Excel targets keep priority; "
            "Auto Target shipments receive the earliest feasible Factory "
            "Can Out date.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self.planner.replan_all_open_shipments(
                trigger_reason="shipment_portfolio_replan_all",
                created_by="shipment_orders",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Replanning Failed",
                str(exc),
            )
            return

        self.refresh_list()
        QMessageBox.information(
            self,
            "Replanning Complete",
            f"Planning run #{result.planning_run_id or '-'} completed for "
            f"{len(result.shipments):,} active shipments.",
        )

    def open_selected_shipment(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if self.selected_shipment_id:
            self.open_shipment_detail(int(self.selected_shipment_id))

    def open_shipment_detail(
        self,
        shipment_id: int,
    ) -> None:
        # Opening a detail page is read-only. Delivery dates are recalculated by
        # the planner, explicit target-date approval, or integrity maintenance.
        # A screen view must never change target or receive dates.
        shipment = self.get_shipment(
            shipment_id
        )
        if not shipment:
            return

        shipment = dict(shipment)

        self.current_shipment_id = (
            shipment_id
        )
        self.selected_item_id = None
        self.edit_item_btn.setEnabled(False)
        self.delete_item_btn.setEnabled(False)
        if hasattr(self, "detail_edit_item_action"):
            self.detail_edit_item_action.setEnabled(False)
            self.detail_delete_item_action.setEnabled(False)

        shipment_no = str(
            shipment.get("shipment_no")
            or "-"
        )
        shipment_name = str(
            shipment.get("shipment_name")
            or shipment_no
        )
        customer = str(
            shipment.get("customer_name")
            or "-"
        )

        self.detail_title.setText(
            shipment_name
        )
        self.detail_subtitle.setText(
            f"Shipment ID: {shipment_no}  •  "
            f"Customer / Destination: {customer}"
        )

        with engine.begin() as connection:
            stats = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(id) AS items,
                        COALESCE(
                            SUM(GREATEST(0, COALESCE(quantity, 0))),
                            0
                        ) AS qty,
                        COALESCE(
                            SUM(
                                GREATEST(
                                    0,
                                    LEAST(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        ),
                                        COALESCE(
                                            stock_allocated_qty,
                                            0
                                        )
                                    )
                                )
                            ),
                            0
                        ) AS stock_qty,
                        COALESCE(
                            SUM(
                                GREATEST(
                                    0,
                                    GREATEST(
                                        0,
                                        COALESCE(quantity, 0)
                                    )
                                    - GREATEST(
                                        0,
                                        LEAST(
                                            GREATEST(
                                                0,
                                                COALESCE(quantity, 0)
                                            ),
                                            COALESCE(
                                                stock_allocated_qty,
                                                0
                                            )
                                        )
                                    )
                                    - GREATEST(
                                        0,
                                        LEAST(
                                            GREATEST(
                                                0,
                                                COALESCE(quantity, 0)
                                            ),
                                            COALESCE(
                                                produced_qty,
                                                0
                                            )
                                        )
                                    )
                                )
                            ),
                            0
                        ) AS production_qty,
                        COALESCE(
                            SUM(
                                GREATEST(
                                    0,
                                    LEAST(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        ),
                                        COALESCE(produced_qty, 0)
                                    )
                                )
                            ),
                            0
                        ) AS produced_qty,
                        COALESCE(
                            SUM(
                                GREATEST(
                                    0,
                                    LEAST(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        ),
                                        GREATEST(
                                            0,
                                            COALESCE(
                                                stock_allocated_qty,
                                                0
                                            )
                                        )
                                        + GREATEST(
                                            0,
                                            COALESCE(produced_qty, 0)
                                        )
                                    )
                                )
                            ),
                            0
                        ) AS completed_qty,
                        COALESCE(
                            SUM(
                                GREATEST(
                                    0,
                                    GREATEST(
                                        0,
                                        COALESCE(quantity, 0)
                                    )
                                    - GREATEST(
                                        0,
                                        LEAST(
                                            GREATEST(
                                                0,
                                                COALESCE(quantity, 0)
                                            ),
                                            GREATEST(
                                                0,
                                                COALESCE(
                                                    stock_allocated_qty,
                                                    0
                                                )
                                            )
                                            + GREATEST(
                                                0,
                                                COALESCE(
                                                    produced_qty,
                                                    0
                                                )
                                            )
                                        )
                                    )
                                )
                            ),
                            0
                        ) AS remaining_qty,
                        MIN(
                            COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                            )
                        ) AS first_item_date,
                        MAX(
                            COALESCE(
                                item_receive_date,
                                receive_date,
                                end_date,
                                start_date
                            )
                        ) AS factory_receive_date,
                        COUNT(*) FILTER (
                            WHERE COALESCE(quantity, 0) > 0
                              AND COALESCE(
                                    item_receive_date,
                                    receive_date,
                                    end_date,
                                    start_date
                                  ) IS NULL
                        ) AS missing_receive_count,
                        ROUND(
                            CASE
                                WHEN COALESCE(
                                    SUM(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        )
                                    ),
                                    0
                                ) > 0
                                THEN (
                                    COALESCE(
                                        SUM(
                                            GREATEST(
                                                0,
                                                LEAST(
                                                    GREATEST(
                                                        0,
                                                        COALESCE(
                                                            quantity,
                                                            0
                                                        )
                                                    ),
                                                    GREATEST(
                                                        0,
                                                        COALESCE(
                                                            stock_allocated_qty,
                                                            0
                                                        )
                                                    )
                                                    + GREATEST(
                                                        0,
                                                        COALESCE(
                                                            produced_qty,
                                                            0
                                                        )
                                                    )
                                                )
                                            )
                                        ),
                                        0
                                    )::numeric
                                    /
                                    SUM(
                                        GREATEST(
                                            0,
                                            COALESCE(quantity, 0)
                                        )
                                    )
                                    * 100
                                )
                                ELSE 0
                            END,
                            1
                        ) AS progress_pct
                    FROM mpps_shipment_items
                    WHERE shipment_id =
                        :shipment_id
                    """
                ),
                {
                    "shipment_id": shipment_id
                },
            ).mappings().first()

            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        sap_code,
                        item_description,
                        GREATEST(
                            0,
                            COALESCE(quantity, 0)
                        ) AS quantity,
                        GREATEST(
                            0,
                            LEAST(
                                GREATEST(
                                    0,
                                    COALESCE(quantity, 0)
                                ),
                                COALESCE(
                                    stock_allocated_qty,
                                    0
                                )
                            )
                        ) AS stock_allocated_qty,
                        GREATEST(
                            0,
                            GREATEST(
                                0,
                                COALESCE(quantity, 0)
                            )
                            - GREATEST(
                                0,
                                LEAST(
                                    GREATEST(
                                        0,
                                        COALESCE(quantity, 0)
                                    ),
                                    COALESCE(
                                        stock_allocated_qty,
                                        0
                                    )
                                )
                            )
                            - GREATEST(
                                0,
                                LEAST(
                                    GREATEST(
                                        0,
                                        COALESCE(quantity, 0)
                                    ),
                                    COALESCE(
                                        produced_qty,
                                        0
                                    )
                                )
                            )
                        ) AS production_required_qty,
                        GREATEST(
                            0,
                            LEAST(
                                GREATEST(
                                    0,
                                    COALESCE(quantity, 0)
                                ),
                                COALESCE(produced_qty, 0)
                            )
                        ) AS produced_qty,
                        GREATEST(
                            0,
                            LEAST(
                                GREATEST(
                                    0,
                                    COALESCE(quantity, 0)
                                ),
                                GREATEST(
                                    0,
                                    COALESCE(
                                        stock_allocated_qty,
                                        0
                                    )
                                )
                                + GREATEST(
                                    0,
                                    COALESCE(produced_qty, 0)
                                )
                            )
                        ) AS completed_qty,
                        GREATEST(
                            0,
                            GREATEST(
                                0,
                                COALESCE(quantity, 0)
                            )
                            - GREATEST(
                                0,
                                LEAST(
                                    GREATEST(
                                        0,
                                        COALESCE(quantity, 0)
                                    ),
                                    GREATEST(
                                        0,
                                        COALESCE(
                                            stock_allocated_qty,
                                            0
                                        )
                                    )
                                    + GREATEST(
                                        0,
                                        COALESCE(
                                            produced_qty,
                                            0
                                        )
                                    )
                                )
                            )
                        ) AS remaining_qty,
                        COALESCE(
                            allocated_cavity_count,
                            allocated_cavities,
                            0
                        ) AS cavity_count,
                        daily_capacity,
                        start_date AS production_start_date,
                        COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date
                        ) AS item_receive_date,
                        CASE
                            WHEN GREATEST(
                                0,
                                COALESCE(quantity, 0)
                            ) > 0
                            THEN ROUND(
                                (
                                    GREATEST(
                                        0,
                                        LEAST(
                                            GREATEST(
                                                0,
                                                COALESCE(quantity, 0)
                                            ),
                                            GREATEST(
                                                0,
                                                COALESCE(
                                                    stock_allocated_qty,
                                                    0
                                                )
                                            )
                                            + GREATEST(
                                                0,
                                                COALESCE(
                                                    produced_qty,
                                                    0
                                                )
                                            )
                                        )
                                    )::NUMERIC
                                    /
                                    GREATEST(
                                        0,
                                        COALESCE(quantity, 0)
                                    )
                                ) * 100,
                                1
                            )
                            ELSE 0
                        END AS progress_pct,
                        item_status,
                        COALESCE(
                            NULLIF(
                                schedule_reason,
                                ''
                            ),
                            NULLIF(
                                planning_note,
                                ''
                            ),
                            NULLIF(
                                factory_out_reason,
                                ''
                            ),
                            note,
                            ''
                        ) AS schedule_reason
                    FROM mpps_shipment_items
                    WHERE shipment_id =
                        :shipment_id
                    ORDER BY
                        item_receive_date
                            ASC NULLS LAST,
                        sap_code ASC,
                        id ASC
                    """
                ),
                {
                    "shipment_id": shipment_id
                },
            ).mappings().all()

            operational_source = OperationalSourceService.latest(connection)
            detail_as_of_date = operational_source.plan_date or date.today()
            detail_item_forecasts = {}
            detail_forecast = load_shipment_forecasts(
                connection,
                [shipment_id],
                as_of_date=detail_as_of_date,
                item_forecast_sink=detail_item_forecasts,
            ).get(shipment_id)

        # Build a live execution state from verified dates + current ML
        # forecasts.  Persisted planning_status values can be stale after new
        # forecast evidence becomes available and must not drive the badge.
        execution_items = []
        for raw_row in rows:
            live_row = dict(raw_row)
            item_id = int(live_row.get("id") or 0)
            item_forecast = detail_item_forecasts.get(item_id)
            verified_date = live_row.get("item_receive_date")
            forecast_date = None
            blocker = ""
            if verified_date is None and item_forecast is not None:
                forecast_date = item_forecast.ready_date
                blocker = item_forecast.blocker or ""
            execution_items.append({
                "quantity": live_row.get("quantity") or 0,
                "ready_qty": live_row.get("completed_qty") or 0,
                "remaining_qty": live_row.get("remaining_qty") or 0,
                "verified_receive_date": verified_date,
                "forecast_receive_date": forecast_date,
                "blocker": blocker,
            })
        execution_state = shipment_execution_state(execution_items)

        stats = dict(stats or {})

        shipment_status = str(
            shipment.get("status") or ""
        ).strip()
        planning_status = str(
            shipment.get("planning_status")
            or shipment_status
            or "Pending"
        )
        target_source_raw = str(
            shipment.get("target_date_source") or ""
        ).strip()
        review_required = (
            shipment_status.lower()
            in {
                "imported review",
                "review required",
                "draft import",
                "excel review hold",
            }
            or planning_status.lower() == "review required"
            or target_source_raw.lower()
                == "excel import - date missing"
        )
        if not review_required:
            planning_status = execution_state.label

        # Excel snapshots without a target are automatically scheduled. The
        # earliest verified Factory Can Out date becomes an editable Auto Target.
        target_date = (
            None
            if review_required
            else shipment.get("target_date")
        )
        auto_target = (
            not review_required
            and not bool(
                shipment.get(
                    "target_date_is_manual"
                )
            )
            and (
                target_date is None
                or target_source_raw.lower().startswith(
                    "auto"
                )
                or target_source_raw.lower().startswith(
                    "automatic"
                )
            )
        )

        missing_receive_count = int(
            stats.get("missing_receive_count") or 0
        )
        verified_item_receive_date = (
            stats.get("factory_receive_date")
            if missing_receive_count <= 0
            else None
        )
        dispatch_buffer_days = max(
            0,
            int(
                shipment.get(
                    "dispatch_buffer_days"
                )
                or 0
            ),
        )
        factory_receive_date = (
            None
            if review_required
            else (
                verified_item_receive_date
                or (
                    shipment.get(
                        "factory_can_receive_date"
                    )
                    if missing_receive_count <= 0
                    else None
                )
            )
        )
        factory_out_date = (
            None
            if review_required
            else (
                (
                    shipment.get(
                        "factory_out_date"
                    )
                    if missing_receive_count <= 0
                    else None
                )
                or (
                    factory_receive_date
                    + timedelta(
                        days=dispatch_buffer_days
                    )
                    if factory_receive_date
                    is not None
                    else None
                )
                or (
                    detail_forecast.factory_out_date
                    if detail_forecast is not None
                    else None
                )
            )
        )
        factory_out_is_forecast = bool(
            factory_out_date is not None
            and missing_receive_count > 0
            and detail_forecast is not None
            and detail_forecast.factory_out_date == factory_out_date
        )
        factory_out_blocker = (
            detail_forecast.blocker
            if detail_forecast is not None and detail_forecast.factory_out_date is None
            else ""
        )

        if auto_target and factory_out_date is not None:
            target_date = factory_out_date

        if review_required:
            target_source = (
                "Excel Import — Legacy Approval Required"
            )
            delivery_status = "Review Required"
            planning_status = "Review Required"
        elif auto_target:
            target_source = (
                "Auto Earliest Feasible Factory Out"
            )
            if factory_out_date is not None:
                delivery_status = "Auto Scheduled"
            elif "blocked" in planning_status.lower():
                delivery_status = "Blocked"
            else:
                delivery_status = "Pending Planning"
        else:
            target_source = (
                target_source_raw
                or "Manual / Excel Approved"
            )
            if target_date is None:
                delivery_status = "Pending Target"
            elif factory_out_date is None:
                delivery_status = "Pending Planning"
            elif factory_out_date < target_date:
                delivery_status = "Can Deliver Early"
            elif factory_out_date == target_date:
                delivery_status = "On Time"
            else:
                delivery_status = "Delayed"

        def format_datetime(value) -> str:
            if value is None:
                return "-"
            if hasattr(
                value,
                "strftime",
            ):
                return value.strftime(
                    "%Y-%m-%d %H:%M"
                )
            return str(value)

        def style_badge(
            label: QLabel,
            text_value: str,
        ) -> None:
            normalized = (
                text_value.strip().lower()
            )

            if any(
                token in normalized
                for token in (
                    "cannot",
                    "late",
                    "delay",
                    "blocked",
                    "failed",
                    "cancel",
                    "error",
                )
            ):
                background = "#fee2e2"
                foreground = "#b91c1c"
                border = "#fecaca"
            elif any(
                token in normalized
                for token in (
                    "pending",
                    "hold",
                    "unplanned",
                    "warning",
                )
            ):
                background = "#fef3c7"
                foreground = "#92400e"
                border = "#fde68a"
            elif any(
                token in normalized
                for token in (
                    "deliver",
                    "ready",
                    "complete",
                    "on time",
                    "early",
                )
            ):
                background = "#dcfce7"
                foreground = "#047857"
                border = "#bbf7d0"
            else:
                background = "#dbeafe"
                foreground = "#1d4ed8"
                border = "#bfdbfe"

            label.setText(
                text_value.upper()
            )
            label.setStyleSheet(
                f"background:{background}; "
                f"color:{foreground}; "
                f"border:1px solid {border}; "
                "border-radius:10px; "
                "padding:8px 12px; "
                "font-weight:950;"
            )

        style_badge(
            self.detail_delivery_badge,
            delivery_status,
        )
        style_badge(
            self.detail_planning_badge,
            planning_status,
        )

        self.detail_subtitle.setText(
            f"{shipment_no}  •  {customer}  •  {target_source}"
        )
        last_replanned_text = format_datetime(shipment.get("last_replanned_at"))
        note_text = str(shipment.get("note") or shipment.get("planning_note") or "").strip()
        meta_text = f"Last replanned: {last_replanned_text}"
        if note_text:
            compact_note = note_text if len(note_text) <= 120 else note_text[:117] + "..."
            meta_text += f"  •  {compact_note}"
        self.detail_target_source_label.setText(meta_text)

        self.info_shipment_name.setText(
            f"Shipment ID: {shipment_no}"
        )
        self.info_customer.setText(
            f"Customer / Destination: {customer}"
        )
        target_display = (
            "Approval Required"
            if review_required
            else (
                "Auto Planning"
                if auto_target
                and target_date is None
                else self._fmt_date(
                    target_date
                )
            )
        )
        out_display = (
            "Pending Approval"
            if review_required
            else (
                ("BLOCKED — " + factory_out_blocker[:90])
                if factory_out_date is None and factory_out_blocker
                else (
                    "Pending Planning"
                    if factory_out_date is None
                    else (
                        self._fmt_date(factory_out_date)
                        + ("  •  FORECAST" if factory_out_is_forecast else "")
                    )
                )
            )
        )

        self.info_target_date.setText(
            (
                "Auto Target Date: "
                if auto_target
                else "Target / Priority Date: "
            )
            + f"{target_display}"
        )
        self.info_factory_receive.setText(
            "Factory Can Out: "
            f"{out_display}"
        )

        self.detail_target_date_value.setText(
            target_display
        )
        self.detail_factory_receive_date_value.setText(
            out_display
        )

        if auto_target:
            if factory_out_date is not None:
                variance_text = (
                    "Auto target = Factory Can Out"
                )
                variance_color = "#1d4ed8"
            elif "blocked" in planning_status.lower():
                variance_text = "Blocked — review item reasons"
                variance_color = "#b91c1c"
            else:
                variance_text = "Pending auto planning"
                variance_color = "#92400e"
        elif (
            target_date is not None
            and factory_out_date is not None
            and hasattr(target_date, "toordinal")
            and hasattr(
                factory_out_date,
                "toordinal",
            )
        ):
            variance_days = (
                target_date
                - factory_out_date
            ).days

            if variance_days > 0:
                variance_text = (
                    f"{variance_days} days early"
                )
                variance_color = "#047857"
            elif variance_days < 0:
                variance_text = (
                    f"{abs(variance_days)} days late"
                )
                variance_color = "#b91c1c"
            else:
                variance_text = "On target"
                variance_color = "#047857"
        else:
            if review_required:
                variance_text = "Pending approval"
            elif target_date is None:
                variance_text = "Pending target"
            else:
                variance_text = "Pending planning"
            variance_color = "#92400e"

        self.detail_delivery_variance_value.setText(
            variance_text
        )
        self.detail_delivery_variance_value.setStyleSheet(
            f"color:{variance_color}; "
            "font-size:17pt; font-weight:950;"
        )

        self.info_last_replanned.setText(
            "Last Replanned: "
            f"{format_datetime(shipment.get('last_replanned_at'))}"
        )
        self.info_note.setText(
            "Remarks / Delivery Instructions: "
            f"{shipment.get('note') or shipment.get('planning_note') or '-'}"
        )

        item_count = int(
            stats.get("items") or 0
        )
        total_qty = int(
            stats.get("qty") or 0
        )
        stock_qty = int(
            stats.get("stock_qty") or 0
        )
        production_qty = int(
            stats.get("production_qty")
            or 0
        )
        completed_qty = int(execution_state.ready_qty or 0)
        progress_pct = float(
            stats.get("progress_pct")
            or 0
        )

        self.detail_items_value.setText(
            self._format_int(item_count)
        )
        self.detail_qty_value.setText(
            self._format_int(total_qty)
        )
        self.detail_stock_value.setText(
            self._format_int(stock_qty)
        )
        self.detail_production_value.setText(
            self._format_int(
                production_qty
            )
        )
        self.detail_completed_value.setText(
            self._format_int(
                completed_qty
            )
        )
        self.detail_progress_value.setText(
            f"{progress_pct:.1f}%"
        )
        self.detail_item_count_badge.setText(
            f"{item_count} "
            f"{'item' if item_count == 1 else 'items'}"
        )

        self.detail_table.setSortingEnabled(
            False
        )
        self.detail_table.setRowCount(0)

        display_today = date.today()

        for row_index, raw_row in enumerate(
            rows
        ):
            row = dict(raw_row)
            self.detail_table.insertRow(row_index)

            forecast = detail_item_forecasts.get(int(row.get("id") or 0))
            timeline = item_execution_timeline(
                row,
                today=display_today,
                forecast=forecast,
            )

            raw_reason = str(row.get("schedule_reason") or "").strip()
            reason_parts = []
            if timeline.source:
                reason_parts.append(timeline.source)
            if forecast is not None and getattr(forecast, "effective_daily_capacity", 0.0):
                reason_parts.append(
                    f"{float(forecast.effective_daily_capacity):.1f} pcs/day"
                )
            if forecast is not None and getattr(forecast, "confidence", 0.0):
                reason_parts.append(
                    f"{float(forecast.confidence) * 100.0:.0f}% confidence"
                )
            if raw_reason and "approval" not in raw_reason.lower():
                reason_parts.append(raw_reason)
            reason = " • ".join(reason_parts) or "-"

            production_start_text = (
                self._fmt_date(timeline.production_start_date)
                if timeline.production_start_date is not None
                else "-"
            )
            receive_text = (
                self._fmt_date(timeline.receive_date)
                if timeline.receive_date is not None
                else "No safe date"
            )

            values = [
                row.get("sap_code") or "-",
                row.get("item_description") or "-",
                self._format_int(timeline.quantity),
                self._format_int(timeline.stock_allocated),
                self._format_int(timeline.shortage_qty),
                f"{timeline.completion_pct:.1f}%",
                production_start_text,
                receive_text,
                timeline.state,
            ]

            for column, value in enumerate(values):
                item = self._readonly_item(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                if column != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 1:
                    item.setToolTip(str(value))

                # Stock allocation is the quantity reserved from total stock
                # specifically for this shipment/order line.
                if column == 3:
                    item.setToolTip(
                        "Quantity allocated from total available stock to this shipment item."
                    )

                if column == 4:
                    if timeline.shortage_qty > 0:
                        item.setForeground(QColor("#b45309"))
                        item.setBackground(QColor("#fff7ed"))
                    else:
                        item.setForeground(QColor("#047857"))

                if column == 5:
                    if timeline.completion_pct >= 99.95:
                        item.setForeground(QColor("#047857"))
                        item.setBackground(QColor("#dcfce7"))
                    elif timeline.completion_pct > 0:
                        item.setForeground(QColor("#1d4ed8"))
                        item.setBackground(QColor("#dbeafe"))
                    else:
                        item.setForeground(QColor("#b91c1c"))
                        item.setBackground(QColor("#fee2e2"))
                    item.setToolTip(
                        "Complete % = (Stock Allocated + verified Produced coverage) / Order Qty."
                    )

                if column == 6:
                    if timeline.production_start_date is None:
                        item.setForeground(QColor("#64748b"))
                        if timeline.state == "STOCK ALLOCATED":
                            item.setToolTip(
                                "No production start is required because stock already covers the full order line."
                            )
                    else:
                        item.setForeground(QColor("#1d4ed8"))
                        item.setToolTip(
                            "Production start date. Forecast dates are live planning values and do not overwrite verified history."
                        )

                if column == 7:
                    if timeline.receive_date is None:
                        item.setForeground(QColor("#b91c1c"))
                        item.setBackground(QColor("#fee2e2"))
                    elif timeline.state == "STOCK ALLOCATED":
                        item.setForeground(QColor("#047857"))
                        item.setBackground(QColor("#dcfce7"))
                        item.setToolTip(
                            f"Stock is already allocated; ready/receive date is today ({self._fmt_date(display_today)})."
                        )
                    elif "FORECAST" in timeline.state:
                        item.setForeground(QColor("#1d4ed8"))
                        item.setBackground(QColor("#dbeafe"))
                        item.setToolTip(reason)
                    else:
                        item.setForeground(QColor("#047857"))
                        item.setToolTip(reason)

                if column == 8:
                    state_lower = timeline.state.lower()
                    item.setToolTip(reason)
                    if "blocked" in state_lower:
                        item.setForeground(QColor("#b91c1c"))
                        item.setBackground(QColor("#fee2e2"))
                    elif "forecast" in state_lower:
                        item.setForeground(QColor("#1d4ed8"))
                        item.setBackground(QColor("#dbeafe"))
                    elif any(token in state_lower for token in ("stock", "ready", "scheduled", "produced")):
                        item.setForeground(QColor("#047857"))
                        item.setBackground(QColor("#dcfce7"))
                    else:
                        item.setForeground(QColor("#92400e"))
                        item.setBackground(QColor("#fef3c7"))

                self.detail_table.setItem(row_index, column, item)

        self.detail_table.setSortingEnabled(
            True
        )
        self.stack.setCurrentWidget(
            self.detail_page
        )

    def back_to_list(self) -> None:
        self.refresh_list()
        self.stack.setCurrentWidget(self.list_page)

    def on_detail_selection_changed(
        self,
    ) -> None:
        row = self.detail_table.currentRow()
        self.selected_item_id = None

        if row >= 0:
            item = self.detail_table.item(
                row,
                0,
            )

            if item is not None:
                item_id = item.data(
                    Qt.ItemDataRole.UserRole
                )

                if item_id:
                    self.selected_item_id = int(
                        item_id
                    )

        has_selection = (
            self.selected_item_id
            is not None
        )

        self.edit_item_btn.setEnabled(has_selection)
        self.delete_item_btn.setEnabled(has_selection)
        if hasattr(self, "detail_edit_item_action"):
            self.detail_edit_item_action.setEnabled(has_selection)
            self.detail_delete_item_action.setEnabled(has_selection)

    def open_new_shipment_page(self) -> None:
        if callable(self.on_new_shipment):
            try:
                self.on_new_shipment()
                return
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Open Shipment Order Failed",
                    str(exc),
                )
                return

        main_window = self.window()

        navigate = getattr(
            main_window,
            "navigate",
            None,
        )
        order_index = getattr(
            main_window,
            "ORDER_ENTRY_INDEX",
            None,
        )
        order_page = getattr(
            main_window,
            "order_entry_page",
            None,
        )

        if (
            callable(navigate)
            and order_index is not None
        ):
            if order_page is not None:
                clear_form = getattr(
                    order_page,
                    "clear_form",
                    None,
                )
                if callable(clear_form):
                    clear_form()

            navigate(order_index)

            if order_page is not None:
                shipment_name_input = getattr(
                    order_page,
                    "shipment_name_input",
                    None,
                )
                if shipment_name_input is not None:
                    shipment_name_input.setFocus()
            return

        QMessageBox.warning(
            self,
            "Shipment Orders Unavailable",
            (
                "The Shipment Orders page could not "
                "be opened from this screen."
            ),
        )

    def create_shipment(self) -> None:
        dialog = ShipmentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        if not data["shipment_no"]:
            QMessageBox.warning(self, "Shipment Required", "Please enter shipment ID / name.")
            return
        if not data["customer_name"]:
            data["customer_name"] = data["shipment_no"]
        try:
            with engine.begin() as connection:
                shipment_id = connection.execute(
                    text(
                        """
                        INSERT INTO mpps_shipments
                        (
                            shipment_no,
                            shipment_name,
                            customer_name,
                            shipment_date,
                            manager_order_date,
                            target_date,
                            plan_date,
                            target_date_is_manual,
                            target_date_source,
                            factory_can_receive_date,
                            factory_out_date,
                            delivery_status,
                            planning_status,
                            planning_note,
                            delay_days,
                            early_days,
                            status,
                            note,
                            updated_at
                        )
                        VALUES
                        (
                            :shipment_no,
                            :shipment_name,
                            :customer_name,
                            :shipment_date,
                            :manager_order_date,
                            :manager_order_date,
                            :manager_order_date,
                            TRUE,
                            'Manual',
                            NULL,
                            NULL,
                            'Pending Planning',
                            'Pending Replan',
                            'Shipment created; waiting for cumulative planning.',
                            0,
                            0,
                            :status,
                            :note,
                            CURRENT_TIMESTAMP
                        )
                        RETURNING id
                        """
                    ),
                    data,
                ).scalar_one()
            self.refresh_list()
            self.open_shipment_detail(int(shipment_id))
        except Exception as exc:
            QMessageBox.critical(self, "Create Failed", str(exc))

    def edit_selected_shipment(self) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if not self.selected_shipment_id:
            QMessageBox.information(self, "Select Shipment", "Please select a shipment row first.")
            return
        self._edit_shipment_header(int(self.selected_shipment_id))

    def edit_current_shipment_header(self) -> None:
        if self.current_shipment_id:
            self._edit_shipment_header(int(self.current_shipment_id))
            self.open_shipment_detail(int(self.current_shipment_id))

    def _edit_shipment_header(
        self,
        shipment_id: int,
    ) -> None:
        shipment_row = self.get_shipment(
            shipment_id
        )
        if not shipment_row:
            return
        shipment = dict(shipment_row)

        dialog = ShipmentDialog(
            self,
            shipment,
        )
        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return
        data = dialog.get_data()
        data["id"] = shipment_id

        if not data["shipment_no"]:
            QMessageBox.warning(
                self,
                "Shipment Required",
                "Please enter shipment ID / name.",
            )
            return
        if not data["customer_name"]:
            data["customer_name"] = (
                data["shipment_no"]
            )

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            shipment_no =
                                :shipment_no,
                            shipment_name =
                                :shipment_name,
                            customer_name =
                                :customer_name,
                            shipment_date =
                                :shipment_date,
                            manager_order_date =
                                :manager_order_date,
                            status = :status,
                            note = :note,
                            planning_status =
                                'Pending Replan',
                            planning_note =
                                'Shipment header changed; '
                                'cumulative replanning requested.',
                            factory_can_receive_date = NULL,
                            factory_out_date = NULL,
                            delivery_status =
                                'Pending Planning',
                            delay_days = 0,
                            early_days = 0,
                            last_replanned_at = NULL,
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    data,
                )

            self.planner.replan_all_open_shipments(
                trigger_reason=(
                    "shipment_header_edited_"
                    f"{shipment_id}"
                ),
                created_by=(
                    "shipment_details"
                ),
            )
            self.refresh_list()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Edit Failed",
                str(exc),
            )

    def move_selected_shipment_date(self, delta_days: int) -> None:
        if not self.selected_shipment_id:
            self.on_list_selection_changed()
        if not self.selected_shipment_id:
            QMessageBox.information(
                self,
                "Select Shipment",
                "Please select a shipment row first.",
            )
            return

        shipment_id = int(self.selected_shipment_id)
        shipment_row = self.get_shipment(shipment_id)
        if not shipment_row:
            return
        shipment = dict(shipment_row)

        if self._record_requires_target_approval(
            shipment
        ):
            QMessageBox.information(
                self,
                "Target Approval Required",
                "This imported shipment has no approved target date. "
                "Open Shipment Details and use Change Target Date to "
                "approve a manual target date first.",
            )
            return

        if shipment.get("target_date") is None:
            QMessageBox.information(
                self,
                "Target Date Missing",
                "This shipment has no target date to move.",
            )
            return

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            target_date =
                                target_date
                                + (
                                    :delta_days
                                    * INTERVAL '1 day'
                                  ),
                            plan_date =
                                target_date
                                + (
                                    :delta_days
                                    * INTERVAL '1 day'
                                  ),
                            target_date_is_manual = TRUE,
                            target_date_source = 'Manual Approved',
                            factory_can_receive_date = NULL,
                            factory_out_date = NULL,
                            delivery_status =
                                'Pending Planning',
                            planning_status =
                                'Pending Replan',
                            delay_days = 0,
                            early_days = 0,
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE id = :shipment_id
                        """
                    ),
                    {
                        "shipment_id": shipment_id,
                        "delta_days": delta_days,
                    },
                )

            self.planner.replan_all_open_shipments(
                trigger_reason=(
                    "shipment_priority_date_moved_"
                    f"{shipment_id}"
                ),
                created_by="shipment_orders",
            )
            self.refresh_list()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Move Date Failed",
                str(exc),
            )

    def add_item(self) -> None:
        if not self.current_shipment_id:
            QMessageBox.information(
                self,
                "Shipment Required",
                "Open a shipment before adding items.",
            )
            return

        shipment_id = int(
            self.current_shipment_id
        )

        dialog = ExistingShipmentAddItemsDialog(
            shipment_id,
            self,
        )

        if (
            dialog.exec()
            == QDialog.DialogCode.Accepted
        ):
            self.refresh_list()
            self.open_shipment_detail(
                shipment_id
            )

    def edit_selected_item(self) -> None:
        if not self.selected_item_id:
            self.on_detail_selection_changed()

        if not self.selected_item_id:
            QMessageBox.information(
                self,
                "Select Item",
                "Please select an item row first.",
            )
            return

        item_id = int(
            self.selected_item_id
        )
        item_row = self.get_shipment_item(
            item_id
        )
        if not item_row:
            return

        original = dict(item_row)

        dialog = ShipmentItemDialog(
            self,
            item=original,
        )
        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        data = dialog.get_data()

        if (
            not data["sap_code"]
            or not data["item_description"]
        ):
            QMessageBox.warning(
                self,
                "Item Required",
                "Please select a valid approved item.",
            )
            return

        shipment_id = int(
            self.current_shipment_id
        )
        same_sap_code = (
            str(original.get("sap_code") or "").strip()
            == str(data.get("sap_code") or "").strip()
        )
        preserved_produced_qty = (
            max(0, int(original.get("produced_qty") or 0))
            if same_sap_code
            else 0
        )

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipment_items
                        SET
                            sap_code = :sap_code,
                            item_description =
                                :item_description,
                            quantity = :quantity,
                            note = :note,
                            start_date = NULL,
                            end_date = NULL,
                            receive_date = NULL,
                            item_receive_date = NULL,
                            item_status = 'Pending',
                            schedule_reason =
                                'Awaiting automatic cumulative replanning.',
                            stock_allocated_qty = 0,
                            produced_qty =
                                :produced_qty,
                            completed_qty =
                                LEAST(
                                    GREATEST(:quantity, 0),
                                    GREATEST(
                                        :produced_qty,
                                        0
                                    )
                                ),
                            production_required_qty =
                                GREATEST(
                                    :quantity
                                    - GREATEST(
                                        :produced_qty,
                                        0
                                    ),
                                    0
                                ),
                            allocated_cavity_count = 0,
                            allocated_cavities = 0,
                            daily_capacity = 0,
                            production_days = 0,
                            progress_pct = CASE
                                WHEN :quantity > 0
                                THEN ROUND(
                                    (
                                        LEAST(
                                            :quantity,
                                            GREATEST(
                                                :produced_qty,
                                                0
                                            )
                                        )::NUMERIC
                                        / :quantity
                                    ) * 100,
                                    2
                                )
                                ELSE 0
                            END,
                            remaining_qty =
                                GREATEST(
                                    :quantity
                                    - GREATEST(
                                        :produced_qty,
                                        0
                                    ),
                                    0
                                ),
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE id = :item_id
                        """
                    ),
                    {
                        "item_id": item_id,
                        "sap_code": data["sap_code"],
                        "item_description": (
                            data["item_description"]
                        ),
                        "quantity": data["quantity"],
                        "note": data["note"],
                        "produced_qty": preserved_produced_qty,
                    },
                )

            self.planner.replan_all_open_shipments(
                trigger_reason=(
                    "shipment_item_edited_"
                    f"{item_id}"
                ),
                created_by="shipment_details",
            )

            self.recalculate_shipment_factory_out_date(
                shipment_id
            )
            self.refresh_list()
            self.open_shipment_detail(
                shipment_id
            )

        except Exception as exc:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            UPDATE mpps_shipment_items
                            SET
                                sap_code = :sap_code,
                                item_description =
                                    :item_description,
                                quantity = :quantity,
                                start_date =
                                    :start_date,
                                end_date =
                                    :end_date,
                                receive_date =
                                    :receive_date,
                                item_receive_date =
                                    :item_receive_date,
                                item_status =
                                    :item_status,
                                note = :note,
                                schedule_reason =
                                    :schedule_reason,
                                stock_allocated_qty =
                                    :stock_allocated_qty,
                                production_required_qty =
                                    :production_required_qty,
                                allocated_cavity_count =
                                    :allocated_cavity_count,
                                allocated_cavities =
                                    :allocated_cavities,
                                daily_capacity =
                                    :daily_capacity,
                                production_days =
                                    :production_days,
                                progress_pct =
                                    :progress_pct,
                                remaining_qty =
                                    :remaining_qty,
                                updated_at =
                                    CURRENT_TIMESTAMP
                            WHERE id = :item_id
                            """
                        ),
                        {
                            "item_id": item_id,
                            "sap_code": original.get(
                                "sap_code"
                            ),
                            "item_description": original.get(
                                "item_description"
                            ),
                            "quantity": original.get(
                                "quantity"
                            ),
                            "start_date": original.get(
                                "start_date"
                            ),
                            "end_date": original.get(
                                "end_date"
                            ),
                            "receive_date": original.get(
                                "receive_date"
                            ),
                            "item_receive_date": original.get(
                                "item_receive_date"
                            ),
                            "item_status": original.get(
                                "item_status"
                            ),
                            "note": original.get(
                                "note"
                            ),
                            "schedule_reason": original.get(
                                "schedule_reason"
                            ),
                            "stock_allocated_qty": original.get(
                                "stock_allocated_qty"
                            ),
                            "production_required_qty": original.get(
                                "production_required_qty"
                            ),
                            "allocated_cavity_count": original.get(
                                "allocated_cavity_count"
                            ),
                            "allocated_cavities": original.get(
                                "allocated_cavities"
                            ),
                            "daily_capacity": original.get(
                                "daily_capacity"
                            ),
                            "production_days": original.get(
                                "production_days"
                            ),
                            "progress_pct": original.get(
                                "progress_pct"
                            ),
                            "remaining_qty": original.get(
                                "remaining_qty"
                            ),
                        },
                    )
            except Exception:
                pass

            QMessageBox.critical(
                self,
                "Edit Item Failed",
                "The item change could not be replanned, "
                "so the previous item values were restored.\n\n"
                f"Reason: {exc}",
            )

    def delete_selected_item(self) -> None:
        if not self.selected_item_id:
            self.on_detail_selection_changed()
        if not self.selected_item_id:
            QMessageBox.information(self, "Select Item", "Please select an item row to delete.")
            return
        item_id = int(self.selected_item_id)
        answer = QMessageBox.question(
            self,
            "Delete Shipment Item",
            "Delete the selected shipment item from this order?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        DELETE FROM planning_resource_reservations
                        WHERE shipment_item_id = :item_id
                        """
                    ),
                    {"item_id": item_id},
                )

                connection.execute(
                    text(
                        """
                        DELETE FROM shipment_stock_allocations
                        WHERE shipment_item_id = :item_id
                        """
                    ),
                    {"item_id": item_id},
                )

                result = connection.execute(
                    text(
                        """
                        DELETE FROM mpps_shipment_items
                        WHERE id = :item_id
                        RETURNING id
                        """
                    ),
                    {"item_id": item_id},
                )

                deleted_id = result.scalar_one_or_none()

                if deleted_id is None:
                    raise RuntimeError(
                        "Selected shipment item was not deleted."
                    )
            replan_error = ""
            try:
                self.planner.replan_all_open_shipments(
                    trigger_reason=(
                        "shipment_item_deleted_"
                        f"{item_id}"
                    ),
                    created_by="shipment_details",
                )
            except Exception as planner_exc:
                replan_error = str(planner_exc)

            if self.current_shipment_id:
                self.recalculate_shipment_factory_out_date(
                    int(self.current_shipment_id)
                )
                self.open_shipment_detail(
                    int(self.current_shipment_id)
                )
            self.refresh_list()

            if replan_error:
                QMessageBox.warning(
                    self,
                    "Item Deleted — Replan Required",
                    "The item was deleted, but automatic replanning "
                    "did not complete. Run Production Planning before "
                    "using delivery dates.\n\n"
                    f"Reason: {replan_error}",
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete Item Failed",
                str(exc),
            )

    def delete_current_shipment(self) -> None:
        if not self.current_shipment_id:
            QMessageBox.warning(
                self,
                "Shipment Missing",
                "No shipment is currently open.",
            )
            return

        shipment_id = int(
            self.current_shipment_id
        )

        try:
            with engine.begin() as connection:
                shipment = connection.execute(
                    text(
                        """
                        SELECT
                            id,
                            shipment_no,
                            shipment_name,
                            customer_name,
                            status
                        FROM mpps_shipments
                        WHERE id = :shipment_id
                        LIMIT 1
                        """
                    ),
                    {
                        "shipment_id": shipment_id,
                    },
                ).mappings().first()

                item_count = connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM mpps_shipment_items
                        WHERE shipment_id = :shipment_id
                        """
                    ),
                    {
                        "shipment_id": shipment_id,
                    },
                ).scalar_one()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Shipment Lookup Failed",
                str(exc),
            )
            return

        if not shipment:
            QMessageBox.warning(
                self,
                "Shipment Not Found",
                "This shipment no longer exists.",
            )
            self.back_to_list()
            return

        first_confirmation = QMessageBox.question(
            self,
            "Delete Entire Shipment",
            (
                "Delete the complete shipment and "
                "all its items?\n\n"
                f"Shipment Name: "
                f"{shipment['shipment_name'] or shipment['shipment_no']}\n"
                f"Shipment ID: "
                f"{shipment['shipment_no']}\n"
                f"Customer: "
                f"{shipment['customer_name']}\n"
                f"Items: {int(item_count or 0)}\n\n"
                "This will also remove related "
                "planning reservations and stock "
                "allocations."
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )

        if (
            first_confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        final_confirmation = QMessageBox.question(
            self,
            "Permanent Deletion",
            (
                "This action cannot be undone.\n\n"
                f"Permanently delete shipment "
                f"{shipment['shipment_name'] or shipment['shipment_no']} "
                f"(ID: {shipment['shipment_no']})?"
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )

        if (
            final_confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            with engine.begin() as connection:
                cleanup_tables = (
                    "planning_resource_reservations",
                    "shipment_stock_allocations",
                    "mpps_cavity_plan_rows",
                )

                for table_name in cleanup_tables:
                    has_shipment_column = (
                        connection.execute(
                            text(
                                """
                                SELECT EXISTS (
                                    SELECT 1
                                    FROM information_schema.columns
                                    WHERE table_schema = 'public'
                                      AND table_name = :table_name
                                      AND column_name = 'shipment_id'
                                )
                                """
                            ),
                            {
                                "table_name": table_name,
                            },
                        ).scalar_one()
                    )

                    if has_shipment_column:
                        connection.execute(
                            text(
                                f"""
                                DELETE FROM {table_name}
                                WHERE shipment_id
                                    = :shipment_id
                                """
                            ),
                            {
                                "shipment_id": shipment_id,
                            },
                        )

                connection.execute(
                    text(
                        """
                        DELETE FROM mpps_shipment_items
                        WHERE shipment_id = :shipment_id
                        """
                    ),
                    {
                        "shipment_id": shipment_id,
                    },
                )

                deleted_id = connection.execute(
                    text(
                        """
                        DELETE FROM mpps_shipments
                        WHERE id = :shipment_id
                        RETURNING id
                        """
                    ),
                    {
                        "shipment_id": shipment_id,
                    },
                ).scalar_one_or_none()

                if deleted_id is None:
                    raise RuntimeError(
                        "No shipment record was deleted."
                    )

            deleted_shipment_no = str(
                shipment["shipment_no"]
            )

            replan_error = ""
            try:
                self.planner.replan_all_open_shipments(
                    trigger_reason=(
                        "shipment_deleted_"
                        f"{shipment_id}"
                    ),
                    created_by="shipment_details",
                )
            except Exception as planner_exc:
                replan_error = str(planner_exc)

            self.current_shipment_id = None
            self.selected_shipment_id = None
            self.selected_item_id = None

            self.refresh_list()
            self.stack.setCurrentWidget(
                self.list_page
            )

            QMessageBox.information(
                self,
                "Shipment Deleted",
                (
                    f"Shipment "
                    f"{deleted_shipment_no} "
                    "was deleted successfully."
                    + (
                        "\n\nAutomatic replanning did not complete. "
                        "Run Production Planning before relying on "
                        "delivery dates.\nReason: "
                        + replan_error
                        if replan_error
                        else ""
                    )
                ),
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete Shipment Failed",
                str(exc),
            )

    def get_shipment(self, shipment_id: int | None):
        if not shipment_id:
            return None
        with engine.begin() as connection:
            return connection.execute(text("SELECT * FROM mpps_shipments WHERE id = :id LIMIT 1;"), {"id": shipment_id}).mappings().first()

    def get_shipment_item(self, item_id: int | None):
        if not item_id:
            return None
        with engine.begin() as connection:
            return connection.execute(text("SELECT * FROM mpps_shipment_items WHERE id = :id LIMIT 1;"), {"id": item_id}).mappings().first()

    def _readonly_item(self, value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _style_status(self, item: QTableWidgetItem, status: str) -> None:
        font = QFont("Segoe UI")
        font.setBold(True)
        item.setFont(font)
        if status in {"Completed"}:
            item.setForeground(QColor("#047857"))
            item.setBackground(QColor("#dcfce7"))
        elif status in {"Cancelled", "On Hold"}:
            item.setForeground(QColor("#b45309"))
            item.setBackground(QColor("#fef3c7"))
        elif status in {"In Progress", "In Production"}:
            item.setForeground(QColor("#1d4ed8"))
            item.setBackground(QColor("#dbeafe"))
        else:
            item.setForeground(QColor("#334155"))

    def _fmt_date(self, value) -> str:
        if value is None:
            return "-"
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        text_value = str(value)
        if " " in text_value:
            return text_value.split(" ", 1)[0]
        return text_value

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"

    def on_list_cell_double_clicked(
        self,
        row: int,
        column: int,
    ) -> None:
        item = self.list_table.item(
            row,
            0,
        )

        if item is None:
            return

        shipment_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        if shipment_id:
            self.selected_shipment_id = int(
                shipment_id
            )
            if column == 2:
                self.edit_target_date_for_shipment(
                    int(shipment_id)
                )
            else:
                self.open_shipment_detail(
                    int(shipment_id)
                )

    def on_detail_cell_double_clicked(
        self,
        row: int,
        column: int,
    ) -> None:
        id_item = self.detail_table.item(
            row,
            0,
        )
        sap_item = self.detail_table.item(
            row,
            0,
        )

        if id_item is None:
            return

        item_id = id_item.data(
            Qt.ItemDataRole.UserRole
        )
        if item_id:
            self.selected_item_id = int(
                item_id
            )

        if column == 0:
            sap_code = (
                sap_item.text().strip()
                if sap_item is not None
                else ""
            )
            self.open_item_resource_control_center(
                sap_code,
                self.selected_item_id,
            )
            return

        if column == 1:
            self.edit_selected_item()

    def open_item_resource_control_center(
        self,
        sap_code: str,
        shipment_item_id: int | None = None,
    ) -> None:
        if not str(sap_code or "").strip():
            QMessageBox.warning(
                self,
                "SAP Code Required",
                "The selected shipment item has no valid SAP code.",
            )
            return

        if self.item_resource_page is None:
            self.item_resource_page = (
                ItemResourceControlCenterPage(
                    current_user=self.current_user,
                    on_back=(
                        self.back_from_item_resource_control_center
                    ),
                    on_open_master=(
                        self.open_resource_master_page
                    ),
                )
            )
            self.stack.addWidget(
                self.item_resource_page
            )

        self.item_resource_page.load_item(
            str(sap_code).strip(),
            shipment_item_id,
        )
        self.stack.setCurrentWidget(
            self.item_resource_page
        )

    def back_from_item_resource_control_center(
        self,
    ) -> None:
        self.stack.setCurrentWidget(
            self.detail_page
        )

    def open_resource_master_page(
        self,
        target: str,
    ) -> None:
        index_attributes = {
            "molds": "MOLD_MASTER_V2_INDEX",
            "casings": "CASING_MASTER_V2_INDEX",
            "cavities": "CAVITIES_MASTER_INDEX",
            "lines": "OVEN_MASTER_INDEX",
        }
        attribute_name = index_attributes.get(
            str(target or "").strip().lower()
        )
        if not attribute_name:
            return

        candidate = self
        main_window = None
        while candidate is not None:
            if (
                hasattr(candidate, "navigate")
                and hasattr(candidate, attribute_name)
            ):
                main_window = candidate
                break
            candidate = candidate.parentWidget()

        if main_window is None:
            candidate = self.window()
            if (
                hasattr(candidate, "navigate")
                and hasattr(candidate, attribute_name)
            ):
                main_window = candidate

        if main_window is None:
            QMessageBox.information(
                self,
                "Resource Management",
                "The selected master-data module could not be located.",
            )
            return

        page_index = getattr(
            main_window,
            attribute_name,
            None,
        )
        if page_index is None:
            QMessageBox.information(
                self,
                "Resource Management",
                "The selected master-data module is unavailable.",
            )
            return

        main_window.navigate(int(page_index))

    def change_current_target_date(
        self,
    ) -> None:
        if not self.current_shipment_id:
            QMessageBox.information(
                self,
                "Shipment Required",
                "Open a shipment before changing its Target Date.",
            )
            return

        self.edit_target_date_for_shipment(
            int(self.current_shipment_id)
        )

    def edit_target_date_for_shipment(
        self,
        shipment_id: int,
    ) -> None:
        shipment_row = self.get_shipment(
            shipment_id
        )
        if not shipment_row:
            return

        shipment = dict(shipment_row)
        current_source = str(
            shipment.get(
                "target_date_source"
            )
            or ""
        ).strip()
        current_auto = (
            not bool(
                shipment.get(
                    "target_date_is_manual"
                )
            )
            and (
                shipment.get("target_date")
                is None
                or current_source.lower().startswith(
                    "auto"
                )
                or current_source.lower().startswith(
                    "automatic"
                )
            )
        )
        current_target = (
            shipment.get("target_date")
            or date.today()
        )
        factory_out = (
            shipment.get("factory_out_date")
            or shipment.get(
                "factory_can_receive_date"
            )
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(
            "Shipment Target & Schedule Control"
        )
        dialog.setMinimumWidth(650)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )
        layout.setSpacing(14)

        title = QLabel(
            "Shipment Target & Schedule Control"
        )
        title.setObjectName("SectionTitle")

        shipment_label = QLabel(
            "Shipment: "
            f"{shipment.get('shipment_name') or shipment.get('shipment_no') or shipment_id}"
        )
        shipment_label.setObjectName(
            "InfoLabel"
        )

        current_label = QLabel(
            "Current Target: "
            f"{self._fmt_date(shipment.get('target_date'))}"
            f"  |  Source: {current_source or '-'}"
        )
        current_label.setObjectName(
            "InfoLabel"
        )

        out_label = QLabel(
            "Current Factory Can Out: "
            f"{self._fmt_date(factory_out)}"
        )
        out_label.setObjectName(
            "InfoLabel"
        )

        note = QLabel(
            "Auto Target calculates the earliest feasible Factory Can Out "
            "date from cumulative stock, mold, casing and cavity capacity. "
            "Manual Target locks the selected date and changes shipment "
            "priority. Saving always replans the complete active queue."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)

        automatic_checkbox = QCheckBox(
            "Use Auto Target = earliest feasible Factory Can Out date"
        )
        automatic_checkbox.setChecked(
            current_auto
        )

        date_label = QLabel(
            "Manual Target / Priority Date"
        )
        date_label.setObjectName(
            "InfoLabel"
        )

        target_editor = QDateEdit()
        target_editor.setCalendarPopup(True)
        target_editor.setDisplayFormat(
            "yyyy-MM-dd"
        )
        target_editor.setMinimumDate(
            QDate(2000, 1, 1)
        )
        target_editor.setMaximumDate(
            QDate(2100, 12, 31)
        )
        target_editor.setDate(
            QDate(
                current_target.year,
                current_target.month,
                current_target.day,
            )
        )

        buffer_label = QLabel(
            "Dispatch / handling buffer after Factory Can Receive"
        )
        buffer_label.setObjectName(
            "InfoLabel"
        )
        dispatch_buffer = QSpinBox()
        dispatch_buffer.setRange(0, 30)
        dispatch_buffer.setSuffix(
            " day"
        )
        dispatch_buffer.setSpecialValueText(
            "0 days"
        )
        dispatch_buffer.setValue(
            max(
                0,
                int(
                    shipment.get(
                        "dispatch_buffer_days"
                    )
                    or 0
                ),
            )
        )

        reason_label = QLabel(
            "Reason / scheduling note"
        )
        reason_label.setObjectName(
            "InfoLabel"
        )
        reason_input = QLineEdit()
        reason_input.setPlaceholderText(
            "Optional reason for manual date change or auto reset"
        )

        def sync_editor_state(
            checked: bool,
        ) -> None:
            target_editor.setEnabled(
                not checked
            )
            date_label.setEnabled(
                not checked
            )

        automatic_checkbox.toggled.connect(
            sync_editor_state
        )
        sync_editor_state(
            automatic_checkbox.isChecked()
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Save
        ).setText(
            "Save & Replan"
        )
        buttons.accepted.connect(
            dialog.accept
        )
        buttons.rejected.connect(
            dialog.reject
        )

        layout.addWidget(title)
        layout.addWidget(shipment_label)
        layout.addWidget(current_label)
        layout.addWidget(out_label)
        layout.addWidget(note)
        layout.addWidget(
            automatic_checkbox
        )
        layout.addWidget(date_label)
        layout.addWidget(target_editor)
        layout.addWidget(buffer_label)
        layout.addWidget(dispatch_buffer)
        layout.addWidget(reason_label)
        layout.addWidget(reason_input)
        layout.addWidget(buttons)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        auto_target = (
            automatic_checkbox.isChecked()
        )
        new_target = (
            None
            if auto_target
            else target_editor.date().toPython()
        )
        target_source = (
            "Auto Earliest Feasible Factory Out"
            if auto_target
            else "Manual Approved"
        )

        self._save_target_mode_and_replan(
            shipment_id=shipment_id,
            new_target=new_target,
            target_source=target_source,
            is_manual=not auto_target,
            dispatch_buffer_days=(
                dispatch_buffer.value()
            ),
            change_note=(
                reason_input.text().strip()
            ),
        )

    def _set_shipment_auto_target(
        self,
        shipment_id: int,
        *,
        confirmation_required: bool,
    ) -> None:
        shipment_row = self.get_shipment(
            shipment_id
        )
        if not shipment_row:
            return
        shipment = dict(shipment_row)

        if confirmation_required:
            reply = QMessageBox.question(
                self,
                "Reset to Auto Target",
                "Clear the locked target date and calculate the earliest "
                "feasible Factory Can Out date? All active shipments will "
                "be replanned.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._save_target_mode_and_replan(
            shipment_id=shipment_id,
            new_target=None,
            target_source=(
                "Auto Earliest Feasible Factory Out"
            ),
            is_manual=False,
            dispatch_buffer_days=max(
                0,
                int(
                    shipment.get(
                        "dispatch_buffer_days"
                    )
                    or 0
                ),
            ),
            change_note=(
                "Reset to automatic earliest feasible "
                "Factory Can Out scheduling."
            ),
        )

    def _save_target_mode_and_replan(
        self,
        *,
        shipment_id: int,
        new_target,
        target_source: str,
        is_manual: bool,
        dispatch_buffer_days: int,
        change_note: str,
    ) -> None:
        shipment_row = self.get_shipment(
            shipment_id
        )
        if not shipment_row:
            return
        shipment = dict(shipment_row)

        header_fields = [
            "target_date",
            "plan_date",
            "status",
            "planning_status",
            "planning_note",
            "target_date_is_manual",
            "target_date_source",
            "dispatch_buffer_days",
            "factory_can_receive_date",
            "factory_out_date",
            "delivery_status",
            "delay_days",
            "early_days",
            "last_replanned_at",
        ]
        old_values = {
            field: shipment.get(field)
            for field in header_fields
        }

        with engine.begin() as connection:
            item_snapshots = [
                dict(row)
                for row in connection.execute(
                    text(
                        """
                        SELECT
                            id,
                            start_date,
                            end_date,
                            item_status,
                            allocated_cavity_count,
                            allocated_cavities,
                            daily_capacity,
                            production_days,
                            receive_date,
                            item_receive_date,
                            planning_note,
                            schedule_reason,
                            factory_out_reason,
                            planning_version
                        FROM mpps_shipment_items
                        WHERE shipment_id = :shipment_id
                        ORDER BY id
                        """
                    ),
                    {
                        "shipment_id": shipment_id
                    },
                ).mappings().all()
            ]

        planning_note = (
            change_note
            or (
                "Manual target date saved; cumulative "
                "planning requested."
                if is_manual
                else "Auto Target requested; earliest feasible "
                "Factory Can Out calculation requested."
            )
        )

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipments
                        SET
                            target_date = :target_date,
                            plan_date = COALESCE(
                                :target_date,
                                shipment_date,
                                CURRENT_DATE
                            ),
                            target_date_is_manual =
                                :target_date_is_manual,
                            target_date_source =
                                :target_date_source,
                            dispatch_buffer_days =
                                :dispatch_buffer_days,
                            status = CASE
                                WHEN LOWER(
                                    COALESCE(status, '')
                                ) IN (
                                    'imported review',
                                    'review required',
                                    'draft import',
                                    'excel review hold'
                                )
                                THEN 'Planned'
                                ELSE status
                            END,
                            planning_status =
                                'Pending Replan',
                            planning_note =
                                :planning_note,
                            factory_can_receive_date = NULL,
                            factory_out_date = NULL,
                            delivery_status =
                                'Pending Planning',
                            delay_days = 0,
                            early_days = 0,
                            last_replanned_at = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :shipment_id
                        """
                    ),
                    {
                        "shipment_id": shipment_id,
                        "target_date": new_target,
                        "target_date_is_manual": is_manual,
                        "target_date_source": target_source,
                        "dispatch_buffer_days": max(
                            0,
                            int(
                                dispatch_buffer_days
                                or 0
                            ),
                        ),
                        "planning_note": planning_note,
                    },
                )
                connection.execute(
                    text(
                        """
                        UPDATE mpps_shipment_items
                        SET
                            start_date = NULL,
                            end_date = NULL,
                            item_status = 'Pending',
                            allocated_cavity_count = 0,
                            allocated_cavities = 0,
                            daily_capacity = 0,
                            production_days = 0,
                            receive_date = NULL,
                            item_receive_date = NULL,
                            planning_note =
                                'Waiting for cumulative replanning.',
                            schedule_reason =
                                'Waiting for cumulative replanning.',
                            factory_out_reason = '',
                            planning_version = 0,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE shipment_id = :shipment_id
                        """
                    ),
                    {
                        "shipment_id": shipment_id
                    },
                )

            result = self.planner.replan_all_open_shipments(
                trigger_reason=(
                    "shipment_manual_target_"
                    if is_manual
                    else "shipment_auto_target_"
                )
                + f"{shipment_id}",
                created_by="shipment_schedule_control",
            )

        except Exception as exc:
            restore_error = ""
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            UPDATE mpps_shipments
                            SET
                                target_date = :target_date,
                                plan_date = :plan_date,
                                status = :status,
                                planning_status =
                                    :planning_status,
                                planning_note =
                                    :planning_note,
                                target_date_is_manual =
                                    :target_date_is_manual,
                                target_date_source =
                                    :target_date_source,
                                dispatch_buffer_days =
                                    :dispatch_buffer_days,
                                factory_can_receive_date =
                                    :factory_can_receive_date,
                                factory_out_date =
                                    :factory_out_date,
                                delivery_status =
                                    :delivery_status,
                                delay_days = :delay_days,
                                early_days = :early_days,
                                last_replanned_at =
                                    :last_replanned_at,
                                updated_at =
                                    CURRENT_TIMESTAMP
                            WHERE id = :shipment_id
                            """
                        ),
                        {
                            "shipment_id": shipment_id,
                            **old_values,
                        },
                    )

                    if item_snapshots:
                        connection.execute(
                            text(
                                """
                                UPDATE mpps_shipment_items
                                SET
                                    start_date = :start_date,
                                    end_date = :end_date,
                                    item_status = :item_status,
                                    allocated_cavity_count =
                                        :allocated_cavity_count,
                                    allocated_cavities =
                                        :allocated_cavities,
                                    daily_capacity =
                                        :daily_capacity,
                                    production_days =
                                        :production_days,
                                    receive_date =
                                        :receive_date,
                                    item_receive_date =
                                        :item_receive_date,
                                    planning_note =
                                        :planning_note,
                                    schedule_reason =
                                        :schedule_reason,
                                    factory_out_reason =
                                        :factory_out_reason,
                                    planning_version =
                                        :planning_version,
                                    updated_at =
                                        CURRENT_TIMESTAMP
                                WHERE id = :id
                                """
                            ),
                            item_snapshots,
                        )
            except Exception as restore_exc:
                restore_error = (
                    "\n\nRollback warning: "
                    f"{restore_exc}"
                )

            QMessageBox.critical(
                self,
                "Target Scheduling Failed",
                "The shipment could not be replanned. The previous "
                "shipment and item values were restored.\n\n"
                f"Reason: {exc}"
                f"{restore_error}",
            )
            return

        self.refresh_list()
        self.open_shipment_detail(
            shipment_id
        )

        updated = dict(
            self.get_shipment(
                shipment_id
            )
            or {}
        )
        actual_target = updated.get(
            "target_date"
        )
        actual_out = updated.get(
            "factory_out_date"
        )
        actual_status = updated.get(
            "planning_status"
        )

        QMessageBox.information(
            self,
            (
                "Manual Target Saved"
                if is_manual
                else "Auto Target Scheduled"
            ),
            (
                f"Target Source: {target_source}\n"
                f"Target Date: {self._fmt_date(actual_target)}\n"
                f"Factory Can Out: {self._fmt_date(actual_out)}\n"
                f"Planning Status: {actual_status or '-'}\n"
                f"Planning Run: {result.planning_run_id or '-'}"
            ),
        )

class ShipmentDetailsPage(ShipmentOrdersPage):
    def __init__(
        self,
        current_user=None,
        on_new_shipment=None,
        *args,
        **kwargs,
    ):
        super().__init__(
            current_user=current_user,
            on_new_shipment=on_new_shipment,
        )



# MPPS V25 SHIPMENT PORTFOLIO CLEAN COLUMNS
_mpps_v25_original_setup_list_table = (
    ShipmentDetailsPage._setup_list_table
)


def _mpps_v25_setup_list_table(self) -> None:
    # Preserve all existing table setup, calculations and data indexes.
    _mpps_v25_original_setup_list_table(self)

    # Cleaner user-facing portfolio: duplicate decision-output columns are
    # hidden, while their underlying data remains available to KPIs/filters.
    hidden_headers = {
        "Risk",
        "Delivery Status",
    }

    model = self.list_table.model()

    for column in range(self.list_table.columnCount()):
        label = str(
            model.headerData(
                column,
                Qt.Orientation.Horizontal,
            )
            or ""
        ).strip()

        if label in hidden_headers:
            self.list_table.setColumnHidden(
                column,
                True,
            )

    self.list_table.horizontalHeader().setStretchLastSection(
        True
    )


ShipmentDetailsPage._setup_list_table = (
    _mpps_v25_setup_list_table
)


# MPPS V26 SHIPMENT COMMAND CENTER UI POLISH
_mpps_v26_original_init = ShipmentDetailsPage.__init__
_mpps_v26_original_setup_list_table = (
    ShipmentDetailsPage._setup_list_table
)


def _mpps_v26_header_map(table):
    result = {}
    model = table.model()

    for column in range(table.columnCount()):
        label = str(
            model.headerData(
                column,
                Qt.Orientation.Horizontal,
            )
            or ""
        ).strip()
        if label:
            result[label] = column

    return result


def _mpps_v26_setup_list_table(self) -> None:
    _mpps_v26_original_setup_list_table(self)

    table = self.list_table
    header = table.horizontalHeader()
    columns = _mpps_v26_header_map(table)

    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection
    )
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(40)

    table_css = (
        "QTableWidget {"
        "background:#ffffff;"
        "alternate-background-color:#f8fafc;"
        "gridline-color:#e2e8f0;"
        "border:1px solid #dbe4f0;"
        "border-radius:10px;"
        "selection-background-color:#dbeafe;"
        "selection-color:#0f172a;"
        "}"
        "QTableWidget::item {"
        "padding:5px 8px;"
        "}"
        "QTableWidget::item:selected {"
        "background:#dbeafe;"
        "color:#0f172a;"
        "border-top:1px solid #bfdbfe;"
        "border-bottom:1px solid #bfdbfe;"
        "}"
        "QHeaderView::section {"
        "background:#edf3f9;"
        "color:#172033;"
        "border:none;"
        "border-right:1px solid #dbe4f0;"
        "border-bottom:1px solid #dbe4f0;"
        "padding:9px 7px;"
        "font-weight:900;"
        "}"
    )
    table.setStyleSheet(
        table.styleSheet() + table_css
    )

    header.setMinimumHeight(42)
    header.setDefaultAlignment(
        Qt.AlignmentFlag.AlignCenter
    )
    header.setStretchLastSection(False)

    fixed_widths = {
        "Priority": 72,
        "Target": 108,
        "Factory Can Out": 132,
        "Delivery Variance": 128,
        "Qty": 88,
        "Stock": 88,
        "Coverage": 100,
        "Prod Gap": 108,
    }

    for label, width in fixed_widths.items():
        column = columns.get(label)
        if column is None:
            continue
        header.setSectionResizeMode(
            column,
            QHeaderView.ResizeMode.Fixed,
        )
        table.setColumnWidth(column, width)

    shipment_column = columns.get("Shipment")
    if shipment_column is not None:
        header.setSectionResizeMode(
            shipment_column,
            QHeaderView.ResizeMode.Stretch,
        )

    for label, column in columns.items():
        item = table.horizontalHeaderItem(column)
        if item is None:
            continue
        if label == "Shipment":
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            )
        else:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )


def _mpps_v26_find_metric_frame(label):
    parent = label.parentWidget()

    while parent is not None:
        if isinstance(parent, QFrame):
            return parent
        parent = parent.parentWidget()

    return None


def _mpps_v26_polish_page(self) -> None:
    metric_names = {
        "Visible Shipments",
        "Shipment Qty",
        "Stock Coverage",
        "Production Gap",
        "Critical / Late",
        "Needs Review",
    }

    for label in self.findChildren(QLabel):
        text_value = label.text().strip()

        if text_value in metric_names:
            label.setStyleSheet(
                label.styleSheet()
                + (
                    "color:#64748b;"
                    "font-size:8.5pt;"
                    "font-weight:800;"
                )
            )

            frame = _mpps_v26_find_metric_frame(label)
            if frame is not None:
                frame.setMinimumHeight(70)

        if "LIVE OVEN" in text_value:
            label.setMinimumWidth(145)
            label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

    for combo in self.findChildren(QComboBox):
        current = combo.currentText().strip()

        if current.startswith("Risk:"):
            combo.setMinimumWidth(160)
            combo.setMaximumWidth(180)
            combo.setMinimumHeight(38)
        elif current.startswith("Promise:"):
            combo.setMinimumWidth(190)
            combo.setMaximumWidth(210)
            combo.setMinimumHeight(38)
        elif current.startswith("Stock:"):
            combo.setMinimumWidth(160)
            combo.setMaximumWidth(180)
            combo.setMinimumHeight(38)
        elif current.startswith("Target:"):
            combo.setMinimumWidth(165)
            combo.setMaximumWidth(185)
            combo.setMinimumHeight(38)

    for edit in self.findChildren(QLineEdit):
        placeholder = edit.placeholderText().lower()

        if "search shipment" in placeholder:
            edit.setMinimumHeight(38)
            edit.setMinimumWidth(420)

    for button in self.findChildren(QPushButton):
        caption = button.text().strip().lower()

        if caption in {"clear", "refresh"}:
            button.setMinimumHeight(38)
        elif caption.startswith("actions"):
            button.setMinimumHeight(38)
            button.setMinimumWidth(105)

    page_css = (
        "QLineEdit {"
        "border-radius:9px;"
        "}"
        "QComboBox {"
        "border-radius:9px;"
        "padding-left:9px;"
        "}"
        "QPushButton {"
        "border-radius:9px;"
        "font-weight:850;"
        "}"
    )
    self.setStyleSheet(
        self.styleSheet() + page_css
    )


def _mpps_v26_init(self, *args, **kwargs):
    _mpps_v26_original_init(
        self,
        *args,
        **kwargs,
    )
    QTimer.singleShot(
        0,
        lambda: _mpps_v26_polish_page(self),
    )


ShipmentDetailsPage._setup_list_table = (
    _mpps_v26_setup_list_table
)
ShipmentDetailsPage.__init__ = _mpps_v26_init


# MPPS V27 SHIPMENT DETAIL FINAL UI POLISH
_mpps_v27_original_init = ShipmentDetailsPage.__init__


def _mpps_v27_table_header_map(table):
    result = {}
    model = table.model()

    for column in range(table.columnCount()):
        label = str(
            model.headerData(
                column,
                Qt.Orientation.Horizontal,
            )
            or ""
        ).strip()

        if label:
            result[label] = column

    return result


def _mpps_v27_polish_item_table(self):
    target_headers = {
        "SAP Code",
        "Item Description",
        "Qty",
        "Stock Allocated",
        "Shortage",
        "Complete %",
        "Production Start",
        "Receive / Finish",
        "State",
    }

    for table in self.findChildren(QTableWidget):
        columns = _mpps_v27_table_header_map(table)

        if not target_headers.issubset(
            set(columns)
        ):
            continue

        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumHeight(42)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(42)
        table.setAlternatingRowColors(True)

        fixed_widths = {
            "SAP Code": 112,
            "Qty": 72,
            "Stock Allocated": 116,
            "Shortage": 88,
            "Complete %": 96,
            "Production Start": 126,
            "Receive / Finish": 126,
            "State": 136,
        }

        for label, width in fixed_widths.items():
            column = columns[label]
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )
            table.setColumnWidth(
                column,
                width,
            )

        desc_col = columns[
            "Item Description"
        ]
        header.setSectionResizeMode(
            desc_col,
            QHeaderView.ResizeMode.Stretch,
        )

        for label, column in columns.items():
            item = table.horizontalHeaderItem(
                column
            )
            if item is None:
                continue

            if label == "Item Description":
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

        table_css = (
            "QTableWidget {"
            "background:#ffffff;"
            "alternate-background-color:#f8fafc;"
            "gridline-color:#e2e8f0;"
            "border:1px solid #dbe4f0;"
            "border-radius:10px;"
            "selection-background-color:#dbeafe;"
            "selection-color:#0f172a;"
            "}"
            "QTableWidget::item {"
            "padding:6px 8px;"
            "}"
            "QTableWidget::item:selected {"
            "background:#dbeafe;"
            "color:#0f172a;"
            "}"
            "QHeaderView::section {"
            "background:#edf3f9;"
            "color:#172033;"
            "border:none;"
            "border-right:1px solid #dbe4f0;"
            "border-bottom:1px solid #dbe4f0;"
            "padding:9px 7px;"
            "font-weight:900;"
            "}"
        )
        table.setStyleSheet(
            table.styleSheet()
            + table_css
        )


def _mpps_v27_clean_detail_text(self):
    for label in self.findChildren(QLabel):
        value = label.text().strip()
        normalized = value.lower()

        # Keep the source concept, remove long workbook/hash/file details.
        if (
            "latest oven excel" in normalized
            and (
                "xls-" in normalized
                or ".xlsx" in normalized
                or " • " in value
            )
        ):
            label.setText(
                "LATEST OVEN EXCEL"
            )
            label.setObjectName(
                "DetailSourceBadge"
            )
            label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            label.setMinimumWidth(150)
            label.setMaximumWidth(180)

        # Technical audit line is kept in backend/history but not shown
        # in the operational detail view.
        if (
            normalized.startswith(
                "last replanned:"
            )
            or (
                "final shipment snapshot"
                in normalized
                and ".xlsx" in normalized
            )
        ):
            label.hide()

        # Remove the long explanatory subtitle beside the item schedule.
        if (
            "stock allocation" in normalized
            and "shortage" in normalized
            and "production timing" in normalized
        ):
            label.hide()

        # Softer late emphasis without changing the actual value.
        if (
            "days late" in normalized
            and any(ch.isdigit() for ch in value)
        ):
            label.setStyleSheet(
                label.styleSheet()
                + (
                    "color:#b42318;"
                    "font-weight:900;"
                )
            )


def _mpps_v27_polish_metric_cards(self):
    for frame in self.findChildren(QFrame):
        if frame.objectName() == "MetricCard":
            frame.setMinimumHeight(68)

    for label in self.findChildren(QLabel):
        if label.objectName() == "MetricLabel":
            label.setStyleSheet(
                label.styleSheet()
                + (
                    "color:#64748b;"
                    "font-size:8.5pt;"
                    "font-weight:800;"
                )
            )

        if label.objectName() == "MetricValue":
            label.setStyleSheet(
                label.styleSheet()
                + (
                    "color:#0f172a;"
                    "font-weight:950;"
                )
            )


def _mpps_v27_apply_polish(self):
    _mpps_v27_clean_detail_text(self)
    _mpps_v27_polish_metric_cards(self)
    _mpps_v27_polish_item_table(self)

    self.setStyleSheet(
        self.styleSheet()
        + (
            "QLabel#DetailSourceBadge {"
            "background:#eff6ff;"
            "color:#1d4ed8;"
            "border:1px solid #bfdbfe;"
            "border-radius:9px;"
            "padding:7px 11px;"
            "font-size:8.5pt;"
            "font-weight:900;"
            "}"
        )
    )


def _mpps_v27_init(self, *args, **kwargs):
    _mpps_v27_original_init(
        self,
        *args,
        **kwargs,
    )

    # Run after page construction. A second pass catches detail labels
    # populated immediately after initial async shipment loading.
    QTimer.singleShot(
        0,
        lambda: _mpps_v27_apply_polish(self),
    )
    QTimer.singleShot(
        900,
        lambda: _mpps_v27_apply_polish(self),
    )


ShipmentDetailsPage.__init__ = _mpps_v27_init


# MPPS V27.1 SHIPMENT DETAIL HEADER CLEANUP
_mpps_v27_1_original_init = ShipmentDetailsPage.__init__


def _mpps_v27_1_hide_header_extras(self) -> None:
    for widget in self.findChildren(QWidget):
        text_getter = getattr(widget, "text", None)

        if not callable(text_getter):
            continue

        try:
            value = str(text_getter() or "").strip()
        except Exception:
            continue

        normalized = value.lower()

        if (
            normalized.startswith("xls-final")
            or normalized.startswith("last replanned:")
            or (
                "final shipment snapshot" in normalized
                and ".xlsx" in normalized
            )
            or (
                "latest oven excel" in normalized
                and "crown tyres" in normalized
            )
        ):
            widget.hide()
            continue

        if normalized in {
            "delayed",
            "forecast",
            "actions",
            "actions ▼",
            "actions ▾",
        }:
            widget.hide()
            continue


def _mpps_v27_1_init(self, *args, **kwargs):
    _mpps_v27_1_original_init(
        self,
        *args,
        **kwargs,
    )

    QTimer.singleShot(
        0,
        lambda: _mpps_v27_1_hide_header_extras(self),
    )
    QTimer.singleShot(
        500,
        lambda: _mpps_v27_1_hide_header_extras(self),
    )
    QTimer.singleShot(
        1200,
        lambda: _mpps_v27_1_hide_header_extras(self),
    )


ShipmentDetailsPage.__init__ = _mpps_v27_1_init
