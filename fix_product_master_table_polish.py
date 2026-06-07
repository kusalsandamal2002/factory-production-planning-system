from pathlib import Path


file_path = Path("app/ui/product_master_page.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/product_master_page.py not found.")

code = file_path.read_text(encoding="utf-8")

code = code.replace(
    """    QTableWidget,
    QTableWidgetItem,
""",
    """    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
""",
)

old_labels = '''        self.table.setHorizontalHeaderLabels(
            [
                "Material Code",
                "Description",
                "Product Group",
                "Avg Weight",
                "Compound Wgt",
                "Bead Type",
                "Band Type",
                "Status",
            ]
        )
'''

new_labels = '''        self.table.setHorizontalHeaderLabels(
            [
                "Material",
                "Description",
                "Group",
                "Avg Wgt",
                "Comp Wgt",
                "Bead",
                "Band",
                "Status",
            ]
        )
'''

code = code.replace(old_labels, new_labels)

old_setup = '''        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        self.table.setColumnWidth(0, 135)
        self.table.setColumnWidth(1, 390)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 150)
        self.table.setColumnWidth(6, 150)
        self.table.setColumnWidth(7, 100)
'''

new_setup = '''        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 115)
        self.table.setColumnWidth(2, 115)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 95)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 85)
        self.table.setColumnWidth(7, 80)
'''

code = code.replace(old_setup, new_setup)

file_path.write_text(code, encoding="utf-8")

print("Product Master table polish completed.")
print("Columns are now compact and description column stretches automatically.")