from pathlib import Path
import re

path = Path("app/ui/tyre_item_master_page.py")
text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1) Repository SELECT should include curing fields.
# ------------------------------------------------------------
if "normal_curing_minutes" not in re.search(r"SELECT.*?FROM tyre_item_master", text, flags=re.S).group(0):
    text = text.replace(
        "SELECT id, sap_code, description, tyre_size, status",
        "SELECT id, sap_code, description, tyre_size, normal_curing_minutes, short_cycle_curing_minutes, handling_minutes, status",
    )
    text = text.replace(
        "SELECT id, sap_code, description, status",
        "SELECT id, sap_code, description, tyre_size, normal_curing_minutes, short_cycle_curing_minutes, handling_minutes, status",
    )

# ------------------------------------------------------------
# 2) Ensure DB columns exist in ensure_table.
# ------------------------------------------------------------
if "ADD COLUMN IF NOT EXISTS normal_curing_minutes" not in text:
    insert_after = '''            conn.execute(text("""
                ALTER TABLE tyre_item_master
                ADD COLUMN IF NOT EXISTS tyre_size VARCHAR(128) NOT NULL DEFAULT ''
            """))
'''
    addition = insert_after + '''
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
'''
    if insert_after in text:
        text = text.replace(insert_after, addition, 1)

# ------------------------------------------------------------
# 3) Add curing page to stack after tyre size page.
# ------------------------------------------------------------
if "self.stack.addWidget(self._build_curing_time_page())" not in text:
    text = text.replace(
        "self.stack.addWidget(self._build_tyre_size_page())",
        "self.stack.addWidget(self._build_tyre_size_page())\n        self.stack.addWidget(self._build_curing_time_page())",
        1,
    )

# ------------------------------------------------------------
# 4) Enable Curing Time module card.
# ------------------------------------------------------------
text = re.sub(
    r'''            \(
                "CURING TIME",
                "Production / Curing Time",
                "([^"]*)",
                None,
                False,
            \),''',
    '''            (
                "CURING TIME",
                "Production / Curing Time",
                "Maintain normal curing time, short cycle placeholder and handling time.",
                self._open_curing_time,
                True,
            ),''',
    text,
    count=1,
)

# ------------------------------------------------------------
# 5) Add curing page methods if missing.
# ------------------------------------------------------------
if "def _build_curing_time_page(self)" not in text:
    marker = "    def _open_item_data(self) -> None:\n"
    if marker not in text:
        raise SystemExit("Could not find _open_item_data marker.")

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

        subtitle = QLabel("Maintain normal curing time and handling time imported from Tire production time with curing cycle.xlsx.")
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

        title = QLabel("SAP Code / Description / Curing Time")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Short Cycle is kept as 0 for now. We will import it later when source data is ready.")
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
        self.curing_table.setColumnWidth(2, 155)
        self.curing_table.setColumnWidth(3, 175)
        self.curing_table.setColumnWidth(4, 125)
        self.curing_table.setColumnWidth(5, 130)

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

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._manage_item(item_id))

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

'''
    text = text.replace(marker, methods + marker, 1)

# ------------------------------------------------------------
# 6) Refresh method should load correct search for curing page.
# ------------------------------------------------------------
text = text.replace(
'''            if current_index == 3 and hasattr(self, "curing_search_input"):
                search_text = self.curing_search_input.text().strip()
''',
'''            if current_index == 3 and hasattr(self, "curing_search_input"):
                search_text = self.curing_search_input.text().strip()
''',
)

# If refresh method does not know curing table, add it after tyre_size branch.
if "elif current_index == 3 and hasattr(self, \"curing_table\")" not in text:
    text = text.replace(
'''        elif current_index == 2 and hasattr(self, "tyre_size_table"):
            self._refresh_tyre_size_table()
''',
'''        elif current_index == 2 and hasattr(self, "tyre_size_table"):
            self._refresh_tyre_size_table()
        elif current_index == 3 and hasattr(self, "curing_table"):
            self._refresh_curing_table()
''',
    )

path.write_text(text, encoding="utf-8")
print("Production / Curing Time UI enabled.")
