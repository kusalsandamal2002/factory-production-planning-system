from pathlib import Path
import re

path = Path("app/ui/tyre_item_master_page.py")
text_data = path.read_text(encoding="utf-8")

# Replace group key section UI: remove curing/handling columns and show actual key components.
section_pattern = r'''    def _tyre_group_key_section\(self\) -> QFrame:
.*?
    def _open_tyre_group_key\(self\) -> None:
'''

section_replacement = r'''    def _tyre_group_key_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("Tyre Process Groups")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Group Key = Tyre Size | Rim/Width | Product Family | Construction | Tread | Layer | Color | STD Flag.")
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.group_key_count_badge = QLabel("0 Groups")
        self.group_key_count_badge.setObjectName("CountBadge")
        self.group_key_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.group_key_search_input = QLineEdit()
        self.group_key_search_input.setPlaceholderText("Search group key, size, family, construction, tread...")
        self.group_key_search_input.setMinimumWidth(390)
        self.group_key_search_input.textChanged.connect(self._refresh_tyre_group_key_table)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self._refresh_tyre_group_key_table)

        top.addLayout(title_area, 1)
        top.addWidget(self.group_key_count_badge)
        top.addWidget(self.group_key_search_input)
        top.addWidget(refresh_button)

        self.group_key_table = QTableWidget(0, 11)
        self.group_key_table.setHorizontalHeaderLabels([
            "Group Key",
            "Tyre Size",
            "Rim/Width",
            "Family",
            "Construction",
            "Tread",
            "Layer",
            "Color",
            "STD Flag",
            "SAP Count",
            "Action",
        ])
        self.group_key_table.verticalHeader().setVisible(False)
        self.group_key_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_key_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.group_key_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for col in range(1, 11):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        self.group_key_table.setColumnWidth(1, 110)
        self.group_key_table.setColumnWidth(2, 90)
        self.group_key_table.setColumnWidth(3, 105)
        self.group_key_table.setColumnWidth(4, 145)
        self.group_key_table.setColumnWidth(5, 75)
        self.group_key_table.setColumnWidth(6, 80)
        self.group_key_table.setColumnWidth(7, 85)
        self.group_key_table.setColumnWidth(8, 90)
        self.group_key_table.setColumnWidth(9, 90)
        self.group_key_table.setColumnWidth(10, 120)

        layout.addLayout(top)
        layout.addWidget(self.group_key_table, 1)

        return section

    def _open_tyre_group_key(self) -> None:
'''

text_data, count = re.subn(section_pattern, section_replacement, text_data, count=1, flags=re.S)

if count != 1:
    raise SystemExit("Could not replace _tyre_group_key_section. Need inspect file.")

list_pattern = r'''    def _list_tyre_group_keys\(self, search_text: str = ""\) -> list\[dict\]:
.*?
    def _refresh_tyre_group_key_table\(self\) -> None:
'''

list_replacement = r'''    def _list_tyre_group_keys(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                g.id,
                g.group_key,
                g.tyre_size,
                COALESCE(g.rim_width, '') AS rim_width,
                COALESCE(g.product_family, '') AS product_family,
                COALESCE(g.construction_type, '') AS construction_type,
                g.pattern AS tread_pattern,
                g.layer,
                g.color,
                COALESCE(g.standard_type, '') AS standard_type,
                COUNT(i.sap_code) AS sap_count
            FROM tyre_process_groups g
            LEFT JOIN tyre_process_group_items i ON i.group_id = g.id
        """

        params = {}

        if search:
            sql += """
                WHERE LOWER(g.group_key) LIKE :search
                   OR LOWER(g.tyre_size) LIKE :search
                   OR LOWER(COALESCE(g.rim_width, '')) LIKE :search
                   OR LOWER(COALESCE(g.product_family, '')) LIKE :search
                   OR LOWER(COALESCE(g.construction_type, '')) LIKE :search
                   OR LOWER(g.pattern) LIKE :search
                   OR LOWER(g.layer) LIKE :search
                   OR LOWER(g.color) LIKE :search
                   OR LOWER(COALESCE(g.standard_type, '')) LIKE :search
            """
            params["search"] = f"%{search}%"

        sql += """
            GROUP BY
                g.id,
                g.group_key,
                g.tyre_size,
                g.rim_width,
                g.product_family,
                g.construction_type,
                g.pattern,
                g.layer,
                g.color,
                g.standard_type
            ORDER BY COUNT(i.sap_code) DESC, g.group_key
        """

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def _refresh_tyre_group_key_table(self) -> None:
'''

text_data, count = re.subn(list_pattern, list_replacement, text_data, count=1, flags=re.S)

if count != 1:
    raise SystemExit("Could not replace _list_tyre_group_keys. Need inspect file.")

refresh_pattern = r'''    def _refresh_tyre_group_key_table\(self\) -> None:
.*?
    def _show_group_sap_codes\(self, group_id: int\) -> None:
'''

refresh_replacement = r'''    def _refresh_tyre_group_key_table(self) -> None:
        try:
            search_text = ""
            if hasattr(self, "group_key_search_input"):
                search_text = self.group_key_search_input.text().strip()

            rows = self._list_tyre_group_keys(search_text)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load tyre group keys.\n\n{exc}")
            rows = []

        self.group_key_count_badge.setText(f"{len(rows)} Groups")
        self.group_key_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.group_key_table.setRowHeight(row_index, 56)

            values = [
                row.get("group_key", ""),
                row.get("tyre_size", ""),
                row.get("rim_width", ""),
                row.get("product_family", ""),
                row.get("construction_type", ""),
                row.get("tread_pattern", ""),
                row.get("layer", ""),
                row.get("color", ""),
                row.get("standard_type", ""),
                row.get("sap_count", 0),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.group_key_table.setItem(row_index, col, item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            view_button = QPushButton("View SAP")
            view_button.setObjectName("ManageButton")
            view_button.clicked.connect(lambda checked=False, group_id=row["id"]: self._show_group_sap_codes(group_id))

            action_layout.addStretch()
            action_layout.addWidget(view_button)
            action_layout.addStretch()

            self.group_key_table.setCellWidget(row_index, 10, action_widget)

    def _show_group_sap_codes(self, group_id: int) -> None:
'''

text_data, count = re.subn(refresh_pattern, refresh_replacement, text_data, count=1, flags=re.S)

if count != 1:
    raise SystemExit("Could not replace _refresh_tyre_group_key_table. Need inspect file.")

path.write_text(text_data, encoding="utf-8")
print("Tyre Group Key Mapping UI updated: curing/handling removed, key parts added.")
