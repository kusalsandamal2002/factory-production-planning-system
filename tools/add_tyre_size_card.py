from pathlib import Path
import re

path = Path("app/ui/tyre_item_master_page.py")
text = path.read_text(encoding="utf-8")

helper = r'''
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


'''

if "def guess_tyre_size(description: str)" not in text:
    text = text.replace("from app.database import engine\n", "from app.database import engine\n\n\n" + helper)

# Ensure tyre_size column in repository table setup.
if "ADD COLUMN IF NOT EXISTS tyre_size" not in text:
    text = text.replace(
'''            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''
            """))
''',
'''            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''
            """))

            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS tyre_size VARCHAR(128) NOT NULL DEFAULT ''
            """))
''',
    )

text = text.replace(
    "SELECT id, sap_code, description, status",
    "SELECT id, sap_code, description, tyre_size, status",
)

# Patch create item to save tyre size.
text = text.replace(
'''                    INSERT INTO tyre_item_master (sap_code, description, status)
                    VALUES (:sap_code, :description, 'Active')
''',
'''                    INSERT INTO tyre_item_master (sap_code, description, tyre_size, status)
                    VALUES (:sap_code, :description, :tyre_size, 'Active')
''',
)

text = text.replace(
'''                {"sap_code": sap_code, "description": description},
''',
'''                {
                    "sap_code": sap_code,
                    "description": description,
                    "tyre_size": guess_tyre_size(description),
                },
''',
    1,
)

# Patch update item to update tyre size.
text = text.replace(
'''                    SET sap_code = :sap_code,
                        description = :description,
                        updated_at = CURRENT_TIMESTAMP
''',
'''                    SET sap_code = :sap_code,
                        description = :description,
                        tyre_size = :tyre_size,
                        updated_at = CURRENT_TIMESTAMP
''',
)

text = text.replace(
'''                {"id": item_id, "sap_code": sap_code, "description": description},
''',
'''                {
                    "id": item_id,
                    "sap_code": sap_code,
                    "description": description,
                    "tyre_size": guess_tyre_size(description),
                },
''',
    1,
)

# Add tyre size page to stack.
if "self.stack.addWidget(self._build_tyre_size_page())" not in text:
    text = text.replace(
        "self.stack.addWidget(self._build_item_data_page())",
        "self.stack.addWidget(self._build_item_data_page())\n        self.stack.addWidget(self._build_tyre_size_page())",
    )

# Add Tyre Size module card after Item Data card.
if '"Tyre Size Data"' not in text:
    text = text.replace(
'''            (
                "ITEM DATA",
                "Tyre Item Data",
                "Maintain SAP code and tyre description table.",
                self._open_item_data,
                True,
            ),
''',
'''            (
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
''',
    )

# Add tyre size detail page methods.
if "def _build_tyre_size_page(self)" not in text:
    marker = "    def _open_item_data(self) -> None:\n"

    methods = r'''    def _build_tyre_size_page(self) -> QWidget:
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

        breadcrumb = QLabel("Master Data  /  Tyre Item Master  /  Tyre Size")
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

'''
    if marker not in text:
        raise SystemExit("Could not find _open_item_data marker.")

    text = text.replace(marker, methods + marker)

# Refresh search handling.
text = text.replace(
'''            search_text = self.search_input.text().strip() if hasattr(self, "search_input") else ""
            self.items = self.repo.list_items(search_text=search_text)
''',
'''            search_text = ""

            if hasattr(self, "stack") and self.stack.currentIndex() == 2 and hasattr(self, "tyre_size_search_input"):
                search_text = self.tyre_size_search_input.text().strip()
            elif hasattr(self, "search_input"):
                search_text = self.search_input.text().strip()

            self.items = self.repo.list_items(search_text=search_text)
''',
)

# Refresh tyre size table.
text = text.replace(
'''        if hasattr(self, "table"):
            self._refresh_table()
''',
'''        if hasattr(self, "table"):
            self._refresh_table()

        if hasattr(self, "tyre_size_table"):
            self._refresh_tyre_size_table()
''',
)

path.write_text(text, encoding="utf-8")
print("Tyre Size card and detail page added.")
