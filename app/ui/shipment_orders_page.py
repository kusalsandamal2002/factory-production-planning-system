from __future__ import annotations

# STOCK ALLOCATION INTEGRITY V6.2

import csv
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt
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
                        WHERE COALESCE(
                                planning_manager_approval_status,
                                'Pending'
                              ) = 'Approved'
                          AND sap_code IS NOT NULL
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

        self._apply_styles()
        self.ensure_tables()

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
        self.refresh_list()

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; }
            QFrame#Card, QFrame#HeaderCard, QFrame#MetricCard {
                background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;
            }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#SectionTitle { color:#0f172a; font-size:16pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#InfoLabel { color:#334155; font-size:10pt; font-weight:750; }
            QLabel#MetricValue { color:#0f172a; font-size:24pt; font-weight:950; }
            QLabel#MetricLabel { color:#64748b; font-size:9pt; font-weight:850; }
            QLineEdit, QDateEdit, QComboBox, QTextEdit, QSpinBox {
                background:#ffffff; color:#0f172a; border:1px solid #cbd5e1;
                border-radius:10px; padding:9px 12px; font-size:10pt; font-weight:650; min-height:24px;
            }
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {
                border:1px solid #2563eb;
            }
            QPushButton#PrimaryButton { background:#2563eb; color:white; border:none; border-radius:10px; padding:10px 18px; font-weight:950; min-height:26px; }
            QPushButton#PrimaryButton:hover { background:#1d4ed8; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:none; border-radius:10px; padding:10px 18px; font-weight:950; min-height:26px; }
            QPushButton#SecondaryButton:hover { background:#cbd5e1; }
            QPushButton#DangerButton { background:#fee2e2; color:#991b1b; border:none; border-radius:10px; padding:10px 18px; font-weight:950; min-height:26px; }
            QPushButton#DangerButton:hover { background:#fecaca; }
            QTableWidget { background:#ffffff; color:#0f172a; border:1px solid #e2e8f0; border-radius:12px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QTableWidget::item { padding:8px 10px; border:none; }
            QHeaderView::section { background:#f1f5f9; color:#1e293b; border:none; border-right:1px solid #e2e8f0; border-bottom:1px solid #e2e8f0; padding:10px; font-weight:950; }
        """)

    def _build_list_page(self) -> None:
        layout = QVBoxLayout(self.list_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = self._card("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(
            22,
            18,
            22,
            18,
        )
        header_layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(10)

        title_box = QVBoxLayout()

        title = QLabel(
            "Shipment Priority & Delivery Control"
        )
        title.setObjectName("PageTitle")

        hint = QLabel(
            "Shipments are ranked by Target Date. "
            "NO 1 is the shipment that must leave the "
            "factory first."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        self.next_factory_out_label = QLabel(
            "Next Factory Can Out date: -"
        )
        self.next_factory_out_label.setStyleSheet(
            "color:#1d4ed8; font-size:9.5pt; "
            "font-weight:850;"
        )

        self.last_refresh_label = QLabel(
            "Last refreshed: -"
        )
        self.last_refresh_label.setStyleSheet(
            "color:#64748b; font-size:9pt; "
            "font-weight:700;"
        )

        title_box.addWidget(title)
        title_box.addWidget(hint)
        title_box.addWidget(
            self.next_factory_out_label
        )
        title_box.addWidget(
            self.last_refresh_label
        )

        self.new_btn = QPushButton(
            "+ New Shipment"
        )
        self.new_btn.setObjectName(
            "PrimaryButton"
        )
        self.new_btn.clicked.connect(
            self.open_new_shipment_page
        )

        self.open_btn = QPushButton(
            "Open Shipment"
        )
        self.open_btn.setObjectName(
            "SecondaryButton"
        )
        self.open_btn.clicked.connect(
            self.open_selected_shipment
        )

        self.edit_btn = QPushButton(
            "Edit Shipment"
        )
        self.edit_btn.setObjectName(
            "SecondaryButton"
        )
        self.edit_btn.clicked.connect(
            self.edit_selected_shipment
        )

        self.export_btn = QPushButton(
            "Export CSV"
        )
        self.export_btn.setObjectName(
            "SecondaryButton"
        )
        self.export_btn.clicked.connect(
            self.export_visible_shipments
        )

        self.refresh_btn = QPushButton(
            "Refresh"
        )
        self.refresh_btn.setObjectName(
            "SecondaryButton"
        )
        self.refresh_btn.clicked.connect(
            self.refresh_list
        )

        top.addLayout(title_box, 1)
        top.addWidget(self.new_btn)
        top.addWidget(self.open_btn)
        top.addWidget(self.edit_btn)
        top.addWidget(self.export_btn)
        top.addWidget(self.refresh_btn)

        filter_grid = QGridLayout()
        filter_grid.setHorizontalSpacing(10)
        filter_grid.setVerticalSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search shipment name, customer, Shipment ID, "
            "SAP code or item description..."
        )
        self.search_input.textChanged.connect(
            self.refresh_list
        )

        self.promise_filter = QComboBox()
        self.promise_filter.addItem(
            "All delivery promises",
            "all",
        )
        self.promise_filter.addItem(
            "Can meet target",
            "can_meet",
        )
        self.promise_filter.addItem(
            "Cannot meet target",
            "cannot_meet",
        )
        self.promise_filter.addItem(
            "Auto scheduled",
            "auto_scheduled",
        )
        self.promise_filter.addItem(
            "Pending calculation",
            "pending",
        )
        self.promise_filter.addItem(
            "Cancelled",
            "cancelled",
        )
        self.promise_filter.currentIndexChanged.connect(
            self.refresh_list
        )

        self.date_window_filter = QComboBox()
        self.date_window_filter.addItem(
            "All target dates",
            "all",
        )
        self.date_window_filter.addItem(
            "Next 7 days",
            "next_7",
        )
        self.date_window_filter.addItem(
            "Next 30 days",
            "next_30",
        )
        self.date_window_filter.addItem(
            "Past target date",
            "past_due",
        )
        self.date_window_filter.addItem(
            "No target date",
            "no_target",
        )
        self.date_window_filter.currentIndexChanged.connect(
            self.refresh_list
        )

        self.clear_filters_btn = QPushButton(
            "Clear Filters"
        )
        self.clear_filters_btn.setObjectName(
            "SecondaryButton"
        )
        self.clear_filters_btn.clicked.connect(
            self.clear_list_filters
        )

        filter_grid.addWidget(
            QLabel("Search"),
            0,
            0,
        )
        filter_grid.addWidget(
            QLabel("Delivery Promise"),
            0,
            1,
        )
        filter_grid.addWidget(
            QLabel("Target Window"),
            0,
            2,
        )

        filter_grid.addWidget(
            self.search_input,
            1,
            0,
        )
        filter_grid.addWidget(
            self.promise_filter,
            1,
            1,
        )
        filter_grid.addWidget(
            self.date_window_filter,
            1,
            2,
        )
        filter_grid.addWidget(
            self.clear_filters_btn,
            1,
            3,
        )

        filter_grid.setColumnStretch(0, 2)
        filter_grid.setColumnStretch(1, 1)
        filter_grid.setColumnStretch(2, 1)

        schedule_row = QHBoxLayout()
        schedule_row.setSpacing(8)

        schedule_hint = QLabel(
            "Schedule control: double-click Target Date to edit, "
            "or use the quick actions for the selected shipment."
        )
        schedule_hint.setObjectName("Hint")
        schedule_hint.setWordWrap(True)

        self.quick_target_btn = QPushButton(
            "Set Target Date"
        )
        self.quick_target_btn.setObjectName(
            "SecondaryButton"
        )
        self.quick_target_btn.clicked.connect(
            self.change_selected_target_date
        )

        self.quick_auto_target_btn = QPushButton(
            "Reset to Auto Target"
        )
        self.quick_auto_target_btn.setObjectName(
            "SecondaryButton"
        )
        self.quick_auto_target_btn.clicked.connect(
            self.reset_selected_to_auto_target
        )

        self.quick_replan_btn = QPushButton(
            "Replan All"
        )
        self.quick_replan_btn.setObjectName(
            "PrimaryButton"
        )
        self.quick_replan_btn.clicked.connect(
            self.replan_all_from_list
        )

        schedule_row.addWidget(
            schedule_hint,
            1,
        )
        schedule_row.addWidget(
            self.quick_target_btn
        )
        schedule_row.addWidget(
            self.quick_auto_target_btn
        )
        schedule_row.addWidget(
            self.quick_replan_btn
        )

        header_layout.addLayout(top)
        header_layout.addLayout(filter_grid)
        header_layout.addLayout(schedule_row)
        layout.addWidget(header)

        # Hidden compatibility labels.
        # KPI cards were removed from this page,
        # but refresh_list still updates these values.
        self.total_shipments_value = QLabel("0")
        self.total_qty_value = QLabel("0")
        self.stock_allocated_value = QLabel("0")
        self.stock_coverage_value = QLabel("0.0%")
        self.can_meet_value = QLabel("0")
        self.cannot_meet_value = QLabel("0")

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(
            18,
            16,
            18,
            18,
        )
        table_layout.setSpacing(10)

        table_heading = QHBoxLayout()

        table_title = QLabel(
            "Shipment Priority Portfolio"
        )
        table_title.setObjectName(
            "SectionTitle"
        )

        self.rows_count_label = QLabel(
            "0 shipments"
        )
        self.rows_count_label.setStyleSheet(
            "background:#dbeafe; color:#1d4ed8; "
            "border-radius:9px; padding:6px 10px; "
            "font-weight:950;"
        )

        table_heading.addWidget(table_title)
        table_heading.addStretch(1)
        table_heading.addWidget(
            self.rows_count_label
        )

        table_hint = QLabel(
            "Manual/Excel target dates receive priority. Shipments without "
            "an Excel target use the earliest feasible Factory Can Out date as "
            "an editable Auto Target. Double-click Target Date to reschedule."
        )
        table_hint.setObjectName("Hint")
        table_hint.setWordWrap(True)

        self.list_table = QTableWidget(0, 10)
        self.list_table.setHorizontalHeaderLabels([
            "NO",
            "Shipment Name",
            "Shipment ID",
            "Target Date",
            "Target Source",
            "Factory Can Out",
            "Total Quantity",
            "Stock Allocated",
            "Progress %",
            "Status",
        ])
        self._setup_list_table()

        table_layout.addLayout(
            table_heading
        )
        table_layout.addWidget(
            table_hint
        )
        table_layout.addWidget(
            self.list_table,
            1,
        )
        layout.addWidget(
            table_card,
            1,
        )

    def clear_list_filters(self) -> None:
        widgets = (
            self.search_input,
            self.promise_filter,
            self.date_window_filter,
        )

        for widget in widgets:
            widget.blockSignals(True)

        self.search_input.clear()
        self.promise_filter.setCurrentIndex(0)
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
        days = abs(int(variance_days or 0))

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

    def showEvent(self, event) -> None:
        super().showEvent(event)

        if hasattr(self, "search_input"):
            self.refresh_list()

    def _build_detail_page(self) -> None:
        layout = QVBoxLayout(self.detail_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = self._card("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(
            22,
            18,
            22,
            18,
        )
        header_layout.setSpacing(14)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        self.back_btn = QPushButton(
            "← Back to Shipments"
        )
        self.back_btn.setObjectName(
            "SecondaryButton"
        )
        self.back_btn.clicked.connect(
            self.back_to_list
        )

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        self.detail_title = QLabel("Shipment")
        self.detail_title.setObjectName(
            "PageTitle"
        )

        self.detail_subtitle = QLabel(
            "Shipment delivery, production and "
            "item-level execution control"
        )
        self.detail_subtitle.setObjectName(
            "Hint"
        )
        self.detail_subtitle.setWordWrap(True)

        title_box.addWidget(
            self.detail_title
        )
        title_box.addWidget(
            self.detail_subtitle
        )

        self.detail_delivery_badge = QLabel(
            "DELIVERY STATUS"
        )
        self.detail_delivery_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.detail_delivery_badge.setMinimumWidth(
            170
        )

        self.detail_planning_badge = QLabel(
            "PLANNING STATUS"
        )
        self.detail_planning_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.detail_planning_badge.setMinimumWidth(
            145
        )

        title_row.addWidget(
            self.back_btn
        )
        title_row.addLayout(
            title_box,
            1,
        )
        title_row.addWidget(
            self.detail_delivery_badge
        )
        title_row.addWidget(
            self.detail_planning_badge
        )

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.detail_target_source_label = QLabel(
            "Target source: -"
        )
        self.detail_target_source_label.setObjectName(
            "Hint"
        )
        self.detail_target_source_label.setWordWrap(
            True
        )

        self.edit_header_btn = QPushButton(
            "Edit Header"
        )
        self.edit_header_btn.setObjectName(
            "SecondaryButton"
        )
        self.edit_header_btn.clicked.connect(
            self.edit_current_shipment_header
        )

        self.change_target_date_btn = QPushButton(
            "Change Target Date"
        )
        self.change_target_date_btn.setObjectName(
            "SecondaryButton"
        )
        self.change_target_date_btn.setToolTip(
            "Set a manual Target Date or reset to the earliest "
            "feasible Factory Can Out Auto Target"
        )
        self.change_target_date_btn.clicked.connect(
            self.change_current_target_date
        )

        self.add_item_btn = QPushButton(
            "+ Add Item"
        )
        self.add_item_btn.setObjectName(
            "PrimaryButton"
        )
        self.add_item_btn.clicked.connect(
            self.add_item
        )

        self.edit_item_btn = QPushButton(
            "Edit Item"
        )
        self.edit_item_btn.setObjectName(
            "SecondaryButton"
        )
        self.edit_item_btn.clicked.connect(
            self.edit_selected_item
        )
        self.edit_item_btn.setEnabled(False)

        self.delete_item_btn = QPushButton(
            "Delete Item"
        )
        self.delete_item_btn.setObjectName(
            "DangerButton"
        )
        self.delete_item_btn.clicked.connect(
            self.delete_selected_item
        )
        self.delete_item_btn.setEnabled(False)

        self.delete_shipment_btn = QPushButton(
            "Delete Shipment"
        )
        self.delete_shipment_btn.setObjectName(
            "DangerButton"
        )
        self.delete_shipment_btn.setToolTip(
            "Permanently delete this shipment "
            "and all shipment items"
        )
        self.delete_shipment_btn.clicked.connect(
            self.delete_current_shipment
        )

        action_row.addWidget(
            self.detail_target_source_label,
            1,
        )
        action_row.addWidget(
            self.edit_header_btn
        )
        action_row.addWidget(
            self.change_target_date_btn
        )
        action_row.addWidget(
            self.add_item_btn
        )
        action_row.addWidget(
            self.edit_item_btn
        )
        action_row.addWidget(
            self.delete_item_btn
        )
        action_row.addWidget(
            self.delete_shipment_btn
        )

        info = QGridLayout()
        info.setHorizontalSpacing(22)
        info.setVerticalSpacing(9)

        self.info_shipment_name = QLabel(
            "Shipment Name: -"
        )
        self.info_customer = QLabel(
            "Customer / Destination: -"
        )
        self.info_target_date = QLabel(
            "Target / Priority Date: -"
        )
        self.info_factory_receive = QLabel(
            "Factory Can Out: -"
        )
        self.info_last_replanned = QLabel(
            "Last Replanned: -"
        )
        self.info_note = QLabel(
            "Remarks / Delivery Instructions: -"
        )

        info_labels = [
            self.info_shipment_name,
            self.info_customer,
            self.info_target_date,
            self.info_factory_receive,
            self.info_last_replanned,
            self.info_note,
        ]

        for label in info_labels:
            label.setObjectName(
                "InfoLabel"
            )
            label.setWordWrap(True)

        info.addWidget(
            self.info_shipment_name,
            0,
            0,
        )
        info.addWidget(
            self.info_customer,
            0,
            1,
        )
        info.addWidget(
            self.info_target_date,
            1,
            0,
        )
        info.addWidget(
            self.info_factory_receive,
            1,
            1,
        )
        info.addWidget(
            self.info_last_replanned,
            2,
            0,
        )
        info.addWidget(
            self.info_note,
            2,
            1,
        )

        header_layout.addLayout(
            title_row
        )
        header_layout.addLayout(
            action_row
        )
        header_layout.addLayout(
            info
        )
        layout.addWidget(
            header
        )

        delivery_timeline = QHBoxLayout()
        delivery_timeline.setSpacing(12)

        self.detail_target_date_value = QLabel(
            "Pending"
        )
        self.detail_factory_receive_date_value = QLabel(
            "Pending"
        )
        self.detail_delivery_variance_value = QLabel(
            "-"
        )

        delivery_timeline.addWidget(
            self._metric_card(
                self.detail_target_date_value,
                "Target Date",
            )
        )
        delivery_timeline.addWidget(
            self._metric_card(
                self.detail_factory_receive_date_value,
                "Factory Can Out",
            )
        )
        delivery_timeline.addWidget(
            self._metric_card(
                self.detail_delivery_variance_value,
                "Delivery Variance",
            )
        )

        layout.addLayout(
            delivery_timeline
        )

        metrics = QHBoxLayout()
        metrics.setSpacing(12)

        self.detail_items_value = QLabel("0")
        self.detail_qty_value = QLabel("0")
        self.detail_stock_value = QLabel("0")
        self.detail_production_value = QLabel("0")
        self.detail_completed_value = QLabel("0")
        self.detail_progress_value = QLabel("0.0%")

        metrics.addWidget(
            self._metric_card(
                self.detail_items_value,
                "Total Items",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.detail_qty_value,
                "Total Quantity",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.detail_stock_value,
                "Stock Allocated",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.detail_production_value,
                "Production Required",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.detail_completed_value,
                "Completed Quantity",
            )
        )
        metrics.addWidget(
            self._metric_card(
                self.detail_progress_value,
                "Shipment Progress",
            )
        )

        layout.addLayout(
            metrics
        )

        table_card = self._card()
        table_layout = QVBoxLayout(
            table_card
        )
        table_layout.setContentsMargins(
            18,
            16,
            18,
            18,
        )
        table_layout.setSpacing(10)

        table_title_row = QHBoxLayout()

        table_title_box = QVBoxLayout()
        table_title_box.setSpacing(3)

        table_title = QLabel(
            "Shipment Item Execution Details"
        )
        table_title.setObjectName(
            "SectionTitle"
        )

        table_hint = QLabel(
            "All quantities, production capacity, "
            "receive dates and planning reasons are "
            "read directly from the database. "
            "Select a row to edit or delete it."
        )
        table_hint.setObjectName(
            "Hint"
        )
        table_hint.setWordWrap(True)

        table_title_box.addWidget(
            table_title
        )
        table_title_box.addWidget(
            table_hint
        )

        self.detail_item_count_badge = QLabel(
            "0 items"
        )
        self.detail_item_count_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.detail_item_count_badge.setStyleSheet(
            "background:#dbeafe; color:#1d4ed8; "
            "border:1px solid #bfdbfe; "
            "border-radius:10px; padding:7px 12px; "
            "font-weight:900;"
        )

        table_title_row.addLayout(
            table_title_box,
            1,
        )
        table_title_row.addWidget(
            self.detail_item_count_badge
        )

        self.detail_table = QTableWidget(
            0,
            14,
        )
        self.detail_table.setHorizontalHeaderLabels([
            "SAP Code",
            "Item Description",
            "Order Qty",
            "Stock",
            "Production Required",
            "Produced",
            "Completed",
            "Remaining",
            "Cavities",
            "Daily Capacity",
            "Receive Date",
            "Progress",
            "Status",
            "Reason / Note",
        ])

        self._setup_detail_table()

        table_layout.addLayout(
            table_title_row
        )
        table_layout.addWidget(
            self.detail_table,
            1,
        )

        layout.addWidget(
            table_card,
            1,
        )

    def _card(self, name: str = "Card") -> QFrame:
        card = QFrame()
        card.setObjectName(name)
        return card

    def _metric_card(self, value_label: QLabel, label_text: str) -> QFrame:
        card = self._card("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
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
        self.list_table.setWordWrap(True)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.verticalHeader().setDefaultSectionSize(48)

        self.list_table.itemSelectionChanged.connect(
            self.on_list_selection_changed
        )
        self.list_table.cellDoubleClicked.connect(
            self.on_list_cell_double_clicked
        )

        header = self.list_table.horizontalHeader()
        header.setStretchLastSection(False)

        for column in range(
            self.list_table.columnCount()
        ):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            9,
            QHeaderView.ResizeMode.Stretch,
        )

        self.list_table.setColumnWidth(0, 55)
        self.list_table.setColumnWidth(1, 220)
        self.list_table.setColumnWidth(2, 155)
        self.list_table.setColumnWidth(3, 110)
        self.list_table.setColumnWidth(4, 190)
        self.list_table.setColumnWidth(5, 120)
        self.list_table.setColumnWidth(6, 105)
        self.list_table.setColumnWidth(7, 105)
        self.list_table.setColumnWidth(8, 90)
        self.list_table.setColumnWidth(9, 245)

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
            46
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
            0: 105,
            1: 280,
            2: 82,
            3: 78,
            4: 128,
            5: 82,
            6: 86,
            7: 86,
            8: 78,
            9: 105,
            10: 118,
            11: 88,
            12: 110,
            13: 330,
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

    def refresh_list(self) -> None:
        search = (
            self.search_input.text().strip()
            if hasattr(self, "search_input")
            else ""
        )
        promise_filter = (
            self.promise_filter.currentData()
            if hasattr(self, "promise_filter")
            else "all"
        )
        date_window = (
            self.date_window_filter.currentData()
            if hasattr(self, "date_window_filter")
            else "all"
        )

        params = {}
        conditions = ["1 = 1"]

        if search:
            params["search"] = f"%{search}%"
            conditions.append(
                """
                (
                    shipment_no ILIKE :search
                    OR shipment_name ILIKE :search
                    OR customer_name ILIKE :search
                    OR item_search_text ILIKE :search
                )
                """
            )

        if promise_filter != "all":
            params["promise_filter"] = promise_filter
            conditions.append(
                "promise_state = :promise_filter"
            )

        if date_window == "next_7":
            conditions.append(
                """
                target_date BETWEEN CURRENT_DATE
                AND CURRENT_DATE + 7
                """
            )
        elif date_window == "next_30":
            conditions.append(
                """
                target_date BETWEEN CURRENT_DATE
                AND CURRENT_DATE + 30
                """
            )
        elif date_window == "past_due":
            conditions.append(
                """
                target_date < CURRENT_DATE
                """
            )
        elif date_window == "no_target":
            conditions.append(
                "target_date IS NULL"
            )

        where_sql = " AND ".join(
            conditions
        )

        query = f"""
            WITH item_summary AS (
                SELECT
                    shipment_id,
                    COUNT(*) AS item_count,
                    COALESCE(SUM(quantity), 0) AS total_quantity,
                    COALESCE(
                        SUM(
                            GREATEST(
                                0,
                                LEAST(
                                    COALESCE(quantity, 0),
                                    COALESCE(stock_allocated_qty, 0)
                                )
                            )
                        ),
                        0
                    ) AS stock_allocated,
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
                    ) AS latest_receive_date,
                    STRING_AGG(
                        COALESCE(sap_code, '')
                        || ' '
                        || COALESCE(item_description, ''),
                        ' '
                    ) AS item_search_text
                FROM mpps_shipment_items
                GROUP BY shipment_id
            ),
            shipment_base AS (
                SELECT
                    shipment.id AS shipment_pk,
                    shipment.shipment_no,
                    COALESCE(
                        NULLIF(shipment.shipment_name, ''),
                        shipment.shipment_no
                    ) AS shipment_name,
                    shipment.customer_name,
                    shipment.target_date AS target_date,
                    COALESCE(
                        NULLIF(
                            shipment.target_date_source,
                            ''
                        ),
                        'Auto Earliest Feasible Factory Out'
                    ) AS target_date_source,
                    COALESCE(
                        shipment.target_date_is_manual,
                        FALSE
                    ) AS target_date_is_manual,
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
                            ) LIKE 'auto%'
                            OR LOWER(
                                COALESCE(
                                    shipment.target_date_source,
                                    ''
                                )
                            ) LIKE 'automatic%'
                        )
                    ) AS auto_target,
                    CASE
                        WHEN (
                            LOWER(COALESCE(shipment.status, '')) IN (
                                'imported review',
                                'review required',
                                'draft import',
                                'excel review hold'
                            )
                            OR LOWER(
                                COALESCE(shipment.planning_status, '')
                            ) = 'review required'
                            OR LOWER(
                                COALESCE(shipment.target_date_source, '')
                            ) = 'excel import - date missing'
                        )
                        THEN NULL
                        WHEN COALESCE(item.missing_receive_count, 0) > 0
                        THEN NULL
                        ELSE COALESCE(
                            shipment.factory_out_date,
                            (
                                item.latest_receive_date
                                + GREATEST(
                                    0,
                                    COALESCE(
                                        shipment.dispatch_buffer_days,
                                        0
                                    )
                                )
                            ),
                            (
                                shipment.factory_can_receive_date
                                + GREATEST(
                                    0,
                                    COALESCE(
                                        shipment.dispatch_buffer_days,
                                        0
                                    )
                                )
                            )
                        )
                    END AS factory_can_receive_date,
                    COALESCE(item.item_count, 0) AS item_count,
                    COALESCE(
                        item.total_quantity,
                        shipment.total_qty,
                        0
                    ) AS total_quantity,
                    COALESCE(item.stock_allocated, 0) AS stock_allocated,
                    COALESCE(item.item_search_text, '') AS item_search_text,
                    COALESCE(
                        NULLIF(shipment.status, ''),
                        'Planned'
                    ) AS shipment_status,
                    COALESCE(
                        NULLIF(shipment.planning_status, ''),
                        'Pending'
                    ) AS planning_status,
                    (
                        LOWER(COALESCE(shipment.status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(
                            COALESCE(shipment.planning_status, '')
                        ) = 'review required'
                        OR LOWER(
                            COALESCE(shipment.target_date_source, '')
                        ) = 'excel import - date missing'
                    ) AS review_required
                FROM mpps_shipments shipment
                LEFT JOIN item_summary item
                    ON item.shipment_id = shipment.id
            ),
            shipment_ranked AS (
                SELECT
                    shipment_base.*,
                    CASE
                        WHEN LOWER(shipment_status) IN (
                            'cancelled',
                            'canceled'
                        )
                        THEN 'cancelled'
                        WHEN review_required
                        THEN 'review_required'
                        WHEN auto_target
                         AND target_date IS NOT NULL
                         AND factory_can_receive_date IS NOT NULL
                        THEN 'auto_scheduled'
                        WHEN target_date IS NULL
                        OR factory_can_receive_date IS NULL
                        THEN 'pending'
                        WHEN LOWER(planning_status) IN (
                            'blocked',
                            'partially blocked',
                            'pending replan',
                            'pending planning'
                        )
                        THEN 'pending'
                        WHEN factory_can_receive_date <= target_date
                        THEN 'can_meet'
                        ELSE 'cannot_meet'
                    END AS promise_state,
                    CASE
                        WHEN review_required
                          OR target_date IS NULL
                          OR factory_can_receive_date IS NULL
                        THEN 0
                        ELSE (
                            target_date - factory_can_receive_date
                        )
                    END AS variance_days,
                    CASE
                        WHEN total_quantity > 0
                        THEN GREATEST(
                            0,
                            LEAST(
                                100,
                                ROUND(
                                    (
                                        stock_allocated::NUMERIC
                                        / total_quantity
                                    ) * 100,
                                    1
                                )
                            )
                        )
                        ELSE 0
                    END AS stock_progress_pct
                FROM shipment_base
            )
            SELECT *
            FROM shipment_ranked
            WHERE {where_sql}
            ORDER BY
                CASE WHEN review_required THEN 2 ELSE 0 END,
                CASE WHEN auto_target THEN 1 ELSE 0 END,
                target_date ASC NULLS LAST,
                factory_can_receive_date ASC NULLS LAST,
                shipment_pk ASC
        """

        with engine.begin() as connection:
            rows = connection.execute(
                text(query),
                params,
            ).mappings().all()

        total_shipments = len(rows)
        total_quantity = sum(
            int(row["total_quantity"] or 0)
            for row in rows
        )
        stock_allocated = sum(
            int(row["stock_allocated"] or 0)
            for row in rows
        )
        stock_coverage = (
            (
                stock_allocated
                / total_quantity
            ) * 100
            if total_quantity > 0
            else 0.0
        )
        can_meet = sum(
            1
            for row in rows
            if row["promise_state"] == "can_meet"
        )
        cannot_meet = sum(
            1
            for row in rows
            if row["promise_state"]
            == "cannot_meet"
        )

        receive_dates = [
            row["factory_can_receive_date"]
            for row in rows
            if row["factory_can_receive_date"]
            is not None
            and row["promise_state"]
            not in {"cancelled"}
        ]
        next_receive_date = (
            min(receive_dates)
            if receive_dates
            else None
        )

        self.total_shipments_value.setText(
            self._format_int(
                total_shipments
            )
        )
        self.total_qty_value.setText(
            self._format_int(
                total_quantity
            )
        )
        self.stock_allocated_value.setText(
            self._format_int(
                stock_allocated
            )
        )
        self.stock_coverage_value.setText(
            f"{stock_coverage:.1f}%"
        )
        self.can_meet_value.setText(
            self._format_int(can_meet)
        )
        self.cannot_meet_value.setText(
            self._format_int(cannot_meet)
        )
        self.next_factory_out_label.setText(
            "Next Factory Can Out date: "
            f"{self._fmt_date(next_receive_date)}"
        )
        self.last_refresh_label.setText(
            "Last refreshed: "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        )
        self.rows_count_label.setText(
            f"{total_shipments:,} shipment"
            + (
                ""
                if total_shipments == 1
                else "s"
            )
        )

        self.list_table.setRowCount(0)
        self.selected_shipment_id = None

        for row_index, row in enumerate(rows):
            self.list_table.insertRow(
                row_index
            )

            promise_text = (
                self._shipment_promise_text(
                    row["promise_state"],
                    row["variance_days"],
                )
            )

            values = [
                row_index + 1,
                row["shipment_name"],
                row["shipment_no"],
                self._fmt_date(
                    row["target_date"]
                ),
                (
                    "AUTO"
                    if row["auto_target"]
                    else str(
                        row["target_date_source"]
                        or "MANUAL / EXCEL"
                    )
                ),
                self._fmt_date(
                    row["factory_can_receive_date"]
                ),
                self._format_int(
                    row["total_quantity"]
                ),
                self._format_int(
                    row["stock_allocated"]
                ),
                (
                    f"{float(row['stock_progress_pct'] or 0):.1f}%"
                ),
                promise_text,
            ]

            shipment_id = int(
                row["shipment_pk"]
            )

            for column, value in enumerate(values):
                table_item = self._readonly_item(
                    str(value)
                )
                table_item.setData(
                    Qt.ItemDataRole.UserRole,
                    shipment_id,
                )

                if column in {
                    0, 3, 4, 5, 6, 7, 8,
                }:
                    table_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column == 0:
                    number_font = QFont(
                        "Segoe UI"
                    )
                    number_font.setBold(True)
                    table_item.setFont(
                        number_font
                    )
                    table_item.setForeground(
                        QColor("#1d4ed8")
                    )
                    table_item.setBackground(
                        QColor("#dbeafe")
                    )

                if column == 8:
                    progress = float(
                        row["stock_progress_pct"] or 0
                    )
                    progress_font = QFont(
                        "Segoe UI"
                    )
                    progress_font.setBold(True)
                    table_item.setFont(
                        progress_font
                    )

                    if progress >= 100:
                        table_item.setForeground(
                            QColor("#047857")
                        )
                        table_item.setBackground(
                            QColor("#dcfce7")
                        )
                    elif progress > 0:
                        table_item.setForeground(
                            QColor("#1d4ed8")
                        )
                        table_item.setBackground(
                            QColor("#dbeafe")
                        )
                    else:
                        table_item.setForeground(
                            QColor("#64748b")
                        )

                if column == 9:
                    self._style_promise_status(
                        table_item,
                        row["promise_state"],
                    )

                if column in {1, 2, 4, 9}:
                    table_item.setToolTip(
                        str(value)
                    )

                self.list_table.setItem(
                    row_index,
                    column,
                    table_item,
                )

        self.list_table.resizeRowsToContents()

    def on_list_selection_changed(self) -> None:
        self.selected_shipment_id = None

        selection_model = (
            self.list_table.selectionModel()
        )

        if selection_model is None:
            return

        selected_rows = (
            selection_model.selectedRows()
        )

        if selected_rows:
            row_index = (
                selected_rows[0].row()
            )
        else:
            row_index = (
                self.list_table.currentRow()
            )

        if row_index < 0:
            return

        item = self.list_table.item(
            row_index,
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
                        COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date,
                            start_date
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
            )
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

        self.detail_target_source_label.setText(
            f"Target source: {target_source}"
        )

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
                "Pending Planning"
                if factory_out_date is None
                else self._fmt_date(
                    factory_out_date
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
        completed_qty = int(
            stats.get("completed_qty")
            or 0
        )
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

        for row_index, raw_row in enumerate(
            rows
        ):
            row = dict(raw_row)
            self.detail_table.insertRow(
                row_index
            )

            row_progress = float(
                row.get("progress_pct")
                or 0
            )
            status = str(
                row.get("item_status")
                or "Pending"
            )
            receive_date = row.get(
                "item_receive_date"
            )
            reason = str(
                row.get("schedule_reason")
                or "-"
            )

            values = [
                row.get("sap_code") or "-",
                row.get(
                    "item_description"
                ) or "-",
                self._format_int(
                    row.get("quantity")
                    or 0
                ),
                self._format_int(
                    row.get(
                        "stock_allocated_qty"
                    )
                    or 0
                ),
                self._format_int(
                    row.get(
                        "production_required_qty"
                    )
                    or 0
                ),
                self._format_int(
                    row.get("produced_qty")
                    or 0
                ),
                self._format_int(
                    row.get("completed_qty")
                    or 0
                ),
                self._format_int(
                    row.get("remaining_qty")
                    or 0
                ),
                self._format_int(
                    row.get("cavity_count")
                    or 0
                ),
                self._format_int(
                    row.get("daily_capacity")
                    or 0
                ),
                (
                    self._fmt_date(
                        receive_date
                    )
                    if receive_date
                    else "Pending"
                ),
                f"{row_progress:.1f}%",
                status,
                reason,
            ]

            for column, value in enumerate(
                values
            ):
                item = self._readonly_item(
                    str(value)
                )
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    int(row["id"]),
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
                    12,
                }:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column in {
                    1,
                    13,
                }:
                    item.setToolTip(
                        str(value)
                    )

                if (
                    column == 10
                    and receive_date is None
                ):
                    item.setForeground(
                        QColor("#b91c1c")
                    )
                    item.setBackground(
                        QColor("#fee2e2")
                    )

                if column == 11:
                    if row_progress >= 100:
                        item.setForeground(
                            QColor("#047857")
                        )
                        item.setBackground(
                            QColor("#dcfce7")
                        )
                    elif row_progress > 0:
                        item.setForeground(
                            QColor("#1d4ed8")
                        )
                        item.setBackground(
                            QColor("#dbeafe")
                        )

                if column == 12:
                    status_lower = (
                        status.lower()
                    )
                    if any(
                        token in status_lower
                        for token in (
                            "blocked",
                            "failed",
                            "error",
                            "cancel",
                        )
                    ):
                        item.setForeground(
                            QColor("#b91c1c")
                        )
                        item.setBackground(
                            QColor("#fee2e2")
                        )
                    elif any(
                        token in status_lower
                        for token in (
                            "pending",
                            "hold",
                            "unplanned",
                        )
                    ):
                        item.setForeground(
                            QColor("#92400e")
                        )
                        item.setBackground(
                            QColor("#fef3c7")
                        )
                    elif any(
                        token in status_lower
                        for token in (
                            "planned",
                            "ready",
                            "complete",
                        )
                    ):
                        item.setForeground(
                            QColor("#047857")
                        )
                        item.setBackground(
                            QColor("#dcfce7")
                        )

                self.detail_table.setItem(
                    row_index,
                    column,
                    item,
                )

        self.detail_table.setSortingEnabled(
            True
        )
        self.detail_table.resizeRowsToContents()
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

        self.edit_item_btn.setEnabled(
            has_selection
        )
        self.delete_item_btn.setEnabled(
            has_selection
        )

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
            if column == 3:
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

