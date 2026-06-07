from __future__ import annotations

from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text
from app.database import engine


class ProductionEntryPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_movement_id: int | None = None

        # Widgets
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(date.today())
        self.date_input.dateChanged.connect(self.refresh)

        self.shift_combo = QComboBox()
        self.shift_combo.addItems(["Day Shift", "Night Shift"])

        self.material_combo = QComboBox()
        
        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 999999)
        self.qty_input.setValue(100)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Enter operator note or machine code...")

        self.save_btn = QPushButton("+ Save Production Entry")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_entry)

        self.delete_btn = QPushButton("Reverse Selected")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.void_selected_entry)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.total_produced_value = QLabel("0")
        self.total_runs_value = QLabel("0")

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Log ID", "Time", "Material Code", "Description", "Shift", "Qty", "Operator Note"]
        )

        self._setup_table()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard,
            QFrame#TableCard,
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#MetricTitle {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 850;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 19pt;
                font-weight: 950;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#SectionHint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Metrics grid
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(14)
        metrics_layout.addWidget(self._metric_card("Total Produced (Selected Date)", self.total_produced_value), 1)
        metrics_layout.addWidget(self._metric_card("Production Log Entries", self.total_runs_value), 1)
        root.addLayout(metrics_layout)

        # Controls card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("ControlCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(18, 16, 18, 18)
        ctrl_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Log Daily Production")
        title.setObjectName("SectionTitle")
        hint = QLabel("Select date, shift, material, and quantity. This increases FG stock and updates the audit trail.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        header.addWidget(self.refresh_btn)
        ctrl_layout.addLayout(header)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Date"), 0, 0)
        form.addWidget(self.date_input, 0, 1)
        form.addWidget(QLabel("Shift"), 0, 2)
        form.addWidget(self.shift_combo, 0, 3)

        form.addWidget(QLabel("Material Code"), 1, 0)
        form.addWidget(self.material_combo, 1, 1, 1, 3)

        form.addWidget(QLabel("Quantity"), 2, 0)
        form.addWidget(self.qty_input, 2, 1)
        form.addWidget(QLabel("Note"), 2, 2)
        form.addWidget(self.note_input, 2, 3)

        ctrl_layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.save_btn)
        ctrl_layout.addLayout(button_row)

        root.addWidget(ctrl_card)

        # Table card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_header = QHBoxLayout()
        table_title_box = QVBoxLayout()
        table_title_box.setSpacing(4)
        table_title = QLabel("Daily Production Logs")
        table_title.setObjectName("SectionTitle")
        table_hint = QLabel("Logs recorded on the selected date. Admin and managers can void incorrect entries.")
        table_hint.setObjectName("SectionHint")
        table_title_box.addWidget(table_title)
        table_title_box.addWidget(table_hint)
        table_header.addLayout(table_title_box, 1)
        table_header.addWidget(self.delete_btn)
        table_layout.addLayout(table_header)

        table_layout.addWidget(self.table, 1)
        root.addWidget(table_card, 1)

    def _metric_card(self, title_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        title = QLabel(title_text)
        title.setObjectName("MetricTitle")
        value_label.setObjectName("MetricValue")

        layout.addWidget(title)
        layout.addWidget(value_label)
        return card

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 80)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)

    def refresh(self) -> None:
        try:
            self.load_material_combo()
            self.load_table_data()
        except Exception as exc:
            QMessageBox.critical(self, "Production Entry Error", f"Failed to refresh: {exc}")

    def load_material_combo(self) -> None:
        current_sel = self.material_combo.currentText()
        self.material_combo.blockSignals(True)
        self.material_combo.clear()

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT material_code, item_description
                    FROM mpps_stock_items
                    WHERE is_active = TRUE
                    ORDER BY material_code ASC;
                    """
                )
            ).mappings().all()

        for r in rows:
            self.material_combo.addItem(f"{r['material_code']} - {r['item_description']}", r['material_code'])

        idx = self.material_combo.findText(current_sel)
        if idx >= 0:
            self.material_combo.setCurrentIndex(idx)
        self.material_combo.blockSignals(False)

    def load_table_data(self) -> None:
        selected_date = self.date_input.date().toPython()
        self.selected_movement_id = None
        self.delete_btn.setEnabled(False)

        sql = """
            SELECT
                tsm.id,
                tsm.created_at,
                tsm.tire_type_id,
                tt.tire_code AS material_code,
                tt.tire_name AS description,
                tsm.note,
                tsm.quantity,
                COALESCE(tsm.source_ref, '') AS source_ref
            FROM tire_stock_movements tsm
            JOIN tire_types tt
                ON tt.id = tsm.tire_type_id
            WHERE tsm.movement_date = :movement_date
              AND tsm.movement_type = 'DAILY_PRODUCTION'
              AND tsm.direction = 'IN'
              AND NOT EXISTS (
                    SELECT 1
                    FROM tire_stock_movements reversal
                    WHERE reversal.source_ref = 'VOID-' || tsm.id::TEXT
                      AND reversal.movement_type = 'DAILY_PRODUCTION_REVERSAL'
                      AND reversal.direction = 'OUT'
              )
            ORDER BY tsm.created_at DESC;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), {"movement_date": selected_date}).mappings().all()

        self.table.setRowCount(0)
        total_produced = 0

        for idx, row in enumerate(rows):
            self.table.insertRow(idx)

            time_str = row["created_at"].strftime("%H:%M:%S") if row["created_at"] else "-"
            shift_name = "Night Shift" if "night" in (row["note"] or "").lower() else "Day Shift"
            total_produced += row["quantity"]

            items = [
                str(row["id"]),
                time_str,
                row["material_code"],
                row["description"],
                shift_name,
                str(row["quantity"]),
                row["note"] or "-"
            ]

            for col_idx, text_val in enumerate(items):
                item = QTableWidgetItem(text_val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 1, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.table.setItem(idx, col_idx, item)

        self.total_produced_value.setText(str(total_produced))
        self.total_runs_value.setText(str(len(rows)))
        self.table.resizeRowsToContents()

    def on_selection_changed(self) -> None:
        sel_ranges = self.table.selectedRanges()
        if not sel_ranges:
            self.selected_movement_id = None
            self.delete_btn.setEnabled(False)
            return

        row = sel_ranges[0].topRow()
        item = self.table.item(row, 0)
        if item is not None:
            self.selected_movement_id = item.data(Qt.ItemDataRole.UserRole)
            self.delete_btn.setEnabled(True)

    def save_entry(self) -> None:
        m_idx = self.material_combo.currentIndex()
        if m_idx < 0:
            QMessageBox.warning(self, "Save Entry", "Please select a material code.")
            return

        material_code = self.material_combo.itemData(m_idx)
        selected_date = self.date_input.date().toPython()
        shift = self.shift_combo.currentText()
        qty = self.qty_input.value()
        note = self.note_input.text().strip()
        
        full_note = f"[{shift}] {note}".strip()
        username = self.current_user.username if self.current_user else "anonymous"

        try:
            with engine.begin() as connection:
                # 1. Fetch tire_type_id
                tire_row = connection.execute(
                    text("SELECT id FROM tire_types WHERE tire_code = :code LIMIT 1;"),
                    {"code": material_code}
                ).mappings().first()

                if not tire_row:
                    raise ValueError(f"Tire type not found for material code: {material_code}")

                tire_type_id = tire_row["id"]

                # 2. Insert movement log
                connection.execute(
                    text(
                        """
                        INSERT INTO tire_stock_movements (
                            movement_date,
                            tire_type_id,
                            movement_type,
                            direction,
                            quantity,
                            source_ref,
                            note,
                            created_by
                        )
                        VALUES (
                            :movement_date,
                            :tire_type_id,
                            'DAILY_PRODUCTION',
                            'IN',
                            :quantity,
                            :source_ref,
                            :note,
                            (SELECT id FROM users WHERE username = :username LIMIT 1)
                        );
                        """
                    ),
                    {
                        "movement_date": selected_date,
                        "tire_type_id": tire_type_id,
                        "quantity": qty,
                        "source_ref": f"DAILY-PROD-{selected_date.strftime('%Y%m%d')}",
                        "note": full_note,
                        "username": username
                    }
                )

                # 3. Safely update mpps_stock_items fg_stock
                connection.execute(
                    text(
                        """
                        UPDATE mpps_stock_items
                        SET fg_stock = fg_stock + :qty,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE material_code = :material_code;
                        """
                    ),
                    {"qty": qty, "material_code": material_code}
                )

                # 4. Insert audit log
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (
                            username, action_type, table_name, record_id, new_values, note
                        )
                        VALUES (
                            :username, 'INSERT', 'tire_stock_movements', :record_id, :new_val, :note
                        );
                        """
                    ),
                    {
                        "username": username,
                        "record_id": material_code,
                        "new_val": f"{{'qty': {qty}, 'date': '{selected_date}', 'shift': '{shift}'}}",
                        "note": f"Daily production entry added. Updated mpps_stock_items fg_stock (+{qty})."
                    }
                )

            QMessageBox.information(self, "Success", "Daily production entry logged successfully.")
            self.note_input.clear()
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Logging Entry", f"Database transaction failed: {exc}")

    def void_selected_entry(self) -> None:
        if not self.selected_movement_id:
            return

        ret = QMessageBox.question(
            self,
            "Void Entry Confirmation",
            "Reverse this production entry? The original record will be retained and "
            "an auditable OUT movement will subtract the quantity from stock.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        username = self.current_user.username if self.current_user else "anonymous"

        try:
            with engine.begin() as connection:
                # 1. Fetch movement details
                row = connection.execute(
                    text(
                        """
                        SELECT tsm.quantity, tt.tire_code
                        FROM tire_stock_movements tsm
                        JOIN tire_types tt ON tt.id = tsm.tire_type_id
                        WHERE tsm.id = :id
                          AND tsm.movement_type = 'DAILY_PRODUCTION'
                          AND tsm.direction = 'IN'
                          AND NOT EXISTS (
                                SELECT 1
                                FROM tire_stock_movements reversal
                                WHERE reversal.source_ref = 'VOID-' || tsm.id::TEXT
                                  AND reversal.movement_type = 'DAILY_PRODUCTION_REVERSAL'
                                  AND reversal.direction = 'OUT'
                          );
                        """
                    ),
                    {"id": self.selected_movement_id}
                ).mappings().first()

                if not row:
                    raise ValueError("Selected movement entry no longer exists.")

                qty = row["quantity"]
                material_code = row["tire_code"]

                # 2. Subtract from mpps_stock_items fg_stock safely (ensuring we don't go below 0 or handle if it goes negative)
                connection.execute(
                    text(
                        """
                        UPDATE mpps_stock_items
                        SET fg_stock = GREATEST(fg_stock - :qty, 0),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE material_code = :material_code;
                        """
                    ),
                    {"qty": qty, "material_code": material_code}
                )

                # 3. Preserve the original and create an auditable reversal.
                connection.execute(
                    text(
                        """
                        INSERT INTO tire_stock_movements (
                            movement_date,
                            tire_type_id,
                            movement_type,
                            direction,
                            quantity,
                            source_ref,
                            note,
                            created_by
                        )
                        SELECT
                            movement_date,
                            tire_type_id,
                            'DAILY_PRODUCTION_REVERSAL',
                            'OUT',
                            quantity,
                            'VOID-' || id::TEXT,
                            :note,
                            (SELECT id FROM users WHERE username = :username LIMIT 1)
                        FROM tire_stock_movements
                        WHERE id = :id;
                        """
                    ),
                    {
                        "id": self.selected_movement_id,
                        "note": f"Reversal of daily production movement {self.selected_movement_id}.",
                        "username": username,
                    },
                )

                # 4. Insert audit log
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (
                            username, action_type, table_name, record_id, old_values, note
                        )
                        VALUES (
                            :username, 'UPDATE', 'tire_stock_movements', :record_id, :old_val, :note
                        );
                        """
                    ),
                    {
                        "username": username,
                        "record_id": material_code,
                        "old_val": f"{{'qty': {qty}, 'voided_id': {self.selected_movement_id}}}",
                        "note": (
                            "Daily production entry reversed without deleting history. "
                            f"Updated mpps_stock_items fg_stock (-{qty})."
                        )
                    }
                )

            QMessageBox.information(
                self,
                "Success",
                "Production entry reversed successfully. The original and reversal "
                "remain in the movement history.",
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Voiding Entry", f"Database transaction failed: {exc}")
