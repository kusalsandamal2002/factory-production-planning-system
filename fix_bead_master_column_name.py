from pathlib import Path


file_path = Path("app/ui/bead_master_page.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/bead_master_page.py not found.")

code = file_path.read_text(encoding="utf-8")

code = code.replace("bead_usage_per_tyre", "bead_per_tyre")

code = code.replace(
    """
                "Source",
                "Source Row",
""",
    "",
)

code = code.replace(
    """
                source_sheet,
                source_row
""",
    "",
)

code = code.replace(
    """
                row["source_sheet"] or "App",
                self._format_int(row["source_row"]),
""",
    "",
)

code = code.replace(
    """
                        VALUES (
                            :item_code,
                            :bead_type,
                            :bead_per_tyre,
                            :is_active,
                            'Created from Bead Master page.'
                        );
""",
    """
                        VALUES (
                            :item_code,
                            :bead_type,
                            :bead_per_tyre,
                            :is_active
                        );
""",
)

code = code.replace(
    """
                            is_active = :is_active,
                            source_note = 'Edited from Bead Master page.',
                            updated_at = CURRENT_TIMESTAMP
""",
    """
                            is_active = :is_active,
                            updated_at = CURRENT_TIMESTAMP
""",
)

code = code.replace(
    """
                            is_active,
                            source_note
""",
    """
                            is_active
""",
)

code = code.replace(
    """        self.table = QTableWidget(0, 6)""",
    """        self.table = QTableWidget(0, 4)""",
)

code = code.replace(
    """
            [
                "Item Code / Size",
                "Bead Type",
                "Usage / Tyre",
                "Status",
            ]
""",
    """
            [
                "Item Code / Size",
                "Bead Type",
                "Usage / Tyre",
                "Status",
            ]
""",
)

code = code.replace(
    """        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
""",
    "",
)

code = code.replace(
    """        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 95)
""",
    "",
)

file_path.write_text(code, encoding="utf-8")

print("Bead Master page fixed successfully.")
print("Column name changed from bead_usage_per_tyre to bead_per_tyre.")