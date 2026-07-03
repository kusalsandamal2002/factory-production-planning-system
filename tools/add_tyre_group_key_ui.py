from pathlib import Path
import re

path = Path("app/ui/tyre_item_master_page.py")
text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1) Ensure imports exist.
# ------------------------------------------------------------
if "from sqlalchemy import text" not in text:
    text = "from sqlalchemy import text\n" + text

if "from app.database import engine" not in text:
    text = "from app.database import engine\n" + text

# ------------------------------------------------------------
# 2) Add page to stack.
# Current indexes:
# 0 overview
# 1 tyre item data
# 2 tyre size
# 3 curing time
# 4 tyre group key mapping
# ------------------------------------------------------------
if "self.stack.addWidget(self._build_tyre_group_key_page())" not in text:
    if "self.stack.addWidget(self._build_curing_time_page())" in text:
        text = text.replace(
            "self.stack.addWidget(self._build_curing_time_page())",
            "self.stack.addWidget(self._build_curing_time_page())\n        self.stack.addWidget(self._build_tyre_group_key_page())",
            1,
        )
    else:
        text = text.replace(
            "self.stack.addWidget(self._build_tyre_size_page())",
            "self.stack.addWidget(self._build_tyre_size_page())\n        self.stack.addWidget(self._build_tyre_group_key_page())",
            1,
        )

# ------------------------------------------------------------
# 3) Add overview card after Curing Time card.
# ------------------------------------------------------------
if '"Tyre Group Key Mapping"' not in text:
    insert_block = '''            (
                "GROUP KEY",
                "Tyre Group Key Mapping",
                "Group same tyres under one process key and attach multiple SAP codes.",
                self._open_tyre_group_key,
                True,
            ),
'''

    target_title = '"Production / Curing Time"'
    pos = text.find(target_title)
    if pos == -1:
        raise SystemExit("Could not find Production / Curing Time card.")

    tuple_end = text.find("            ),", pos)
    if tuple_end == -1:
        raise SystemExit("Could not find end of Production / Curing Time card tuple.")

    tuple_end += len("            ),\n")
    text = text[:tuple_end] + insert_block + text[tuple_end:]

# ------------------------------------------------------------
# 4) Add Tyre Group Key page methods.
# ------------------------------------------------------------
if "def _build_tyre_group_key_page(self)" not in text:
    marker = "    def _open_item_data(self) -> None:\n"
    if marker not in text:
        marker = "    def _open_curing_time(self) -> None:\n"

    if marker not in text:
        raise SystemExit("Could not find insertion marker for group key page methods.")

    methods = r'''    def _build_tyre_group_key_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._tyre_group_key_header())
        layout.addWidget(self._tyre_group_key_section(), 1)

        root.addWidget(card, 1)
        return page

    def _tyre_group_key_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Master Data  /  Tyre Item Master  /  Tyre Group Key Mapping")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Tyre Group Key Mapping")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Same-size and same-process tyres are grouped under one process key. Multiple SAP codes can use one production rule set.")
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

    def _tyre_group_key_section(self) -> QFrame:
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

        subtitle = QLabel("Group Key = Tyre Size | Pattern | Layer | Color. Action shows SAP codes attached to that group.")
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.group_key_count_badge = QLabel("0 Groups")
        self.group_key_count_badge.setObjectName("CountBadge")
        self.group_key_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.group_key_search_input = QLineEdit()
        self.group_key_search_input.setPlaceholderText("Search group key, tyre size, pattern, layer, color...")
        self.group_key_search_input.setMinimumWidth(390)
        self.group_key_search_input.textChanged.connect(self._refresh_tyre_group_key_table)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self._refresh_tyre_group_key_table)

        top.addLayout(title_area, 1)
        top.addWidget(self.group_key_count_badge)
        top.addWidget(self.group_key_search_input)
        top.addWidget(refresh_button)

        self.group_key_table = QTableWidget(0, 9)
        self.group_key_table.setHorizontalHeaderLabels([
            "Group Key",
            "Tyre Size",
            "Pattern",
            "Layer",
            "Color",
            "SAP Count",
            "Normal Curing",
            "Handling",
            "Action",
        ])
        self.group_key_table.verticalHeader().setVisible(False)
        self.group_key_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_key_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.group_key_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)

        self.group_key_table.setColumnWidth(1, 125)
        self.group_key_table.setColumnWidth(2, 95)
        self.group_key_table.setColumnWidth(3, 85)
        self.group_key_table.setColumnWidth(4, 85)
        self.group_key_table.setColumnWidth(5, 95)
        self.group_key_table.setColumnWidth(6, 125)
        self.group_key_table.setColumnWidth(7, 95)
        self.group_key_table.setColumnWidth(8, 130)

        layout.addLayout(top)
        layout.addWidget(self.group_key_table, 1)

        return section

    def _open_tyre_group_key(self) -> None:
        self.stack.setCurrentIndex(4)
        self._refresh_tyre_group_key_table()

    def _list_tyre_group_keys(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                g.id,
                g.group_key,
                g.tyre_size,
                g.pattern,
                g.layer,
                g.color,
                g.normal_curing_minutes,
                g.short_cycle_curing_minutes,
                g.handling_minutes,
                COUNT(i.sap_code) AS sap_count
            FROM tyre_process_groups g
            LEFT JOIN tyre_process_group_items i ON i.group_id = g.id
        """

        params = {}

        if search:
            sql += """
                WHERE LOWER(g.group_key) LIKE :search
                   OR LOWER(g.tyre_size) LIKE :search
                   OR LOWER(g.pattern) LIKE :search
                   OR LOWER(g.layer) LIKE :search
                   OR LOWER(g.color) LIKE :search
            """
            params["search"] = f"%{search}%"

        sql += """
            GROUP BY
                g.id,
                g.group_key,
                g.tyre_size,
                g.pattern,
                g.layer,
                g.color,
                g.normal_curing_minutes,
                g.short_cycle_curing_minutes,
                g.handling_minutes
            ORDER BY COUNT(i.sap_code) DESC, g.group_key
            LIMIT 500
        """

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def _refresh_tyre_group_key_table(self) -> None:
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
                row.get("pattern", ""),
                row.get("layer", ""),
                row.get("color", ""),
                row.get("sap_count", 0),
                self._group_number_text(row.get("normal_curing_minutes", 0)),
                self._group_number_text(row.get("handling_minutes", 0)),
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

            self.group_key_table.setCellWidget(row_index, 8, action_widget)

    def _show_group_sap_codes(self, group_id: int) -> None:
        try:
            with engine.connect() as conn:
                group = conn.execute(
                    text("""
                        SELECT group_key
                        FROM tyre_process_groups
                        WHERE id = :group_id
                    """),
                    {"group_id": group_id},
                ).mappings().first()

                rows = conn.execute(
                    text("""
                        SELECT sap_code, description
                        FROM tyre_process_group_items
                        WHERE group_id = :group_id
                        ORDER BY sap_code
                        LIMIT 120
                    """),
                    {"group_id": group_id},
                ).mappings().all()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load SAP codes.\n\n{exc}")
            return

        group_key = group["group_key"] if group else ""

        lines = []
        for row in rows:
            lines.append(f'{row["sap_code"]}  -  {row["description"]}')

        if not lines:
            lines.append("No SAP codes linked.")

        message = "\n".join(lines)

        if len(rows) >= 120:
            message += "\n\nShowing first 120 SAP codes only."

        QMessageBox.information(
            self,
            "SAP Codes in Group",
            f"Group Key:\n{group_key}\n\nSAP Codes:\n{message}",
        )

    def _group_number_text(self, value) -> str:
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
# 5) Refresh branch for group key page.
# ------------------------------------------------------------
if "elif current_index == 4 and hasattr(self, \"group_key_table\")" not in text:
    text = text.replace(
'''        elif current_index == 3 and hasattr(self, "curing_table"):
            self._refresh_curing_table()
''',
'''        elif current_index == 3 and hasattr(self, "curing_table"):
            self._refresh_curing_table()
        elif current_index == 4 and hasattr(self, "group_key_table"):
            self._refresh_tyre_group_key_table()
''',
    )

path.write_text(text, encoding="utf-8")
print("Tyre Group Key Mapping UI added.")
