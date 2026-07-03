from pathlib import Path
import re

path = Path("app/ui/tyre_item_master_page.py")
text = path.read_text(encoding="utf-8")

# 1) DB columns add in ensure_table.
if "normal_curing_minutes" not in text:
    text = text.replace(
'''            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS tyre_size VARCHAR(128) NOT NULL DEFAULT ''
            """))
''',
'''            conn.execute(text("""
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
''',
    )

# 2) SELECT fields add.
text = text.replace(
    "SELECT id, sap_code, description, tyre_size, status",
    "SELECT id, sap_code, description, tyre_size, normal_curing_minutes, short_cycle_curing_minutes, handling_minutes, status",
)

# 3) Add stack page.
if "self.stack.addWidget(self._build_curing_time_page())" not in text:
    text = text.replace(
        "self.stack.addWidget(self._build_tyre_size_page())",
        "self.stack.addWidget(self._build_tyre_size_page())\n        self.stack.addWidget(self._build_curing_time_page())",
    )

# 4) Enable Production / Curing Time card.
text = text.replace(
'''            (
                "CURING TIME",
                "Production / Curing Time",
                "Maintain curing cycle, handling time, day rate and night rate.",
                None,
                False,
            ),
''',
'''            (
                "CURING TIME",
                "Production / Curing Time",
                "Maintain normal curing, short cycle curing and handling time.",
                self._open_curing_time,
                True,
            ),
''',
)

# 5) Add repository update method before delete_item.
if "def update_curing_time(" not in text:
    text = text.replace(
'''    def delete_item(self, item_id: int) -> None:
''',
'''    def update_curing_time(
        self,
        item_id: int,
        normal_curing_minutes: float,
        short_cycle_curing_minutes: float,
        handling_minutes: float,
    ) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tyre_item_master
                    SET normal_curing_minutes = :normal_curing_minutes,
                        short_cycle_curing_minutes = :short_cycle_curing_minutes,
                        handling_minutes = :handling_minutes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": item_id,
                    "normal_curing_minutes": normal_curing_minutes,
                    "short_cycle_curing_minutes": short_cycle_curing_minutes,
                    "handling_minutes": handling_minutes,
                },
            )

    def delete_item(self, item_id: int) -> None:
''',
    )

# 6) Add CuringTimeDialog before TyreItemMasterPage.
if "class CuringTimeDialog" not in text:
    marker = "\n\nclass TyreItemMasterPage(QWidget):"
    dialog = r'''

class CuringTimeDialog(QDialog):
    def __init__(self, parent=None, row: dict | None = None):
        super().__init__(parent)
        self.row = row or {}

        self.setWindowTitle("Edit Curing Time")
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

        title = QLabel("Edit Production / Curing Time")
        title.setStyleSheet("color: #0f172a; font-size: 17pt; font-weight: 950;")
        root.addWidget(title)

        item_label = QLabel(f"{self.row.get('sap_code', '')} - {self.row.get('description', '')}")
        item_label.setStyleSheet("color: #475569; font-size: 9pt; font-weight: 700;")
        item_label.setWordWrap(True)
        root.addWidget(item_label)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(14)

        self.normal_input = QLineEdit()
        self.normal_input.setPlaceholderText("Normal curing minutes")
        self.normal_input.setText(self._number_text(self.row.get("normal_curing_minutes", 0)))

        self.short_input = QLineEdit()
        self.short_input.setPlaceholderText("Short cycle curing minutes")
        self.short_input.setText(self._number_text(self.row.get("short_cycle_curing_minutes", 0)))

        self.handling_input = QLineEdit()
        self.handling_input.setPlaceholderText("Handling minutes")
        self.handling_input.setText(self._number_text(self.row.get("handling_minutes", 0)))

        form.addWidget(QLabel("Normal Curing Min"), 0, 0)
        form.addWidget(self.normal_input, 0, 1)

        form.addWidget(QLabel("Short Cycle Curing Min"), 1, 0)
        form.addWidget(self.short_input, 1, 1)

        form.addWidget(QLabel("Handling Min"), 2, 0)
        form.addWidget(self.handling_input, 2, 1)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _number_text(self, value) -> str:
        try:
            number = float(value or 0)
            if number.is_integer():
                return str(int(number))
            return str(number).rstrip("0").rstrip(".")
        except Exception:
            return ""

    def _number(self, widget: QLineEdit) -> float:
        value = widget.text().strip()

        if not value:
            return 0.0

        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Invalid number: {value}")

    def _accept_if_valid(self) -> None:
        try:
            self.data()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Number", str(exc))
            return

        self.accept()

    def data(self) -> dict:
        return {
            "normal_curing_minutes": self._number(self.normal_input),
            "short_cycle_curing_minutes": self._number(self.short_input),
            "handling_minutes": self._number(self.handling_input),
        }

'''
    if marker not in text:
        raise SystemExit("Could not find TyreItemMasterPage marker.")
    text = text.replace(marker, dialog + marker)

# 7) Insert curing time page methods before _open_item_data.
if "def _build_curing_time_page(self)" not in text:
    marker = "    def _open_item_data(self) -> None:\n"
    methods = r'''    def _build_curing_time_page(self) -> QWidget:
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

        breadcrumb = QLabel("Master Data  /  Tyre Item Master  /  Production Curing Time")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Production / Curing Time")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Maintain normal curing time, short cycle curing time and handling time for each tyre item.")
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

        title = QLabel("Curing Time Rules")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Normal and short cycle curing times are maintained separately.")
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
        self.curing_table.setColumnWidth(2, 150)
        self.curing_table.setColumnWidth(3, 180)
        self.curing_table.setColumnWidth(4, 120)
        self.curing_table.setColumnWidth(5, 140)

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

            manage_button = QPushButton("Edit")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._edit_curing_time(item_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()

            self.curing_table.setCellWidget(row_index, 5, action_widget)

    def _number_text(self, value) -> str:
        try:
            number = float(value or 0)
            if number.is_integer():
                return str(int(number))
            return str(number).rstrip("0").rstrip(".")
        except Exception:
            return ""

    def _edit_curing_time(self, item_id: int) -> None:
        row = self._find_item(item_id)

        if row is None:
            return

        dialog = CuringTimeDialog(self, row=row)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        try:
            self.repo.update_curing_time(
                item_id,
                data["normal_curing_minutes"],
                data["short_cycle_curing_minutes"],
                data["handling_minutes"],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Update Failed", f"Could not update curing time.\n\n{exc}")
            return

        self.refresh()

'''
    if marker not in text:
        raise SystemExit("Could not find _open_item_data marker.")

    text = text.replace(marker, methods + marker)

# 8) Search handling for curing page.
text = text.replace(
'''            if hasattr(self, "stack") and self.stack.currentIndex() == 2 and hasattr(self, "tyre_size_search_input"):
                search_text = self.tyre_size_search_input.text().strip()
            elif hasattr(self, "search_input"):
                search_text = self.search_input.text().strip()
''',
'''            if hasattr(self, "stack") and self.stack.currentIndex() == 3 and hasattr(self, "curing_search_input"):
                search_text = self.curing_search_input.text().strip()
            elif hasattr(self, "stack") and self.stack.currentIndex() == 2 and hasattr(self, "tyre_size_search_input"):
                search_text = self.tyre_size_search_input.text().strip()
            elif hasattr(self, "search_input"):
                search_text = self.search_input.text().strip()
''',
)

# 9) Refresh curing table.
text = text.replace(
'''        if hasattr(self, "tyre_size_table"):
            self._refresh_tyre_size_table()
''',
'''        if hasattr(self, "tyre_size_table"):
            self._refresh_tyre_size_table()

        if hasattr(self, "curing_table"):
            self._refresh_curing_table()
''',
)

path.write_text(text, encoding="utf-8")
print("Production / Curing Time module enabled.")
