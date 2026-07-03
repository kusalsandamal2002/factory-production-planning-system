from pathlib import Path

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Make action buttons bigger/cleaner so Delete is not clipped.
text = text.replace(
'''            QPushButton#BackButton, QPushButton#EditButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
            }
''',
'''            QPushButton#BackButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
            }

            QPushButton#EditButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 72px;
            }
'''
)

text = text.replace(
'''            QPushButton#DeleteButton {
                background: #fee2e2;
                color: #991b1b;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
            }
''',
'''            QPushButton#DeleteButton {
                background: #fee2e2;
                color: #991b1b;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 82px;
            }
'''
)

# Shorten header wording a little.
text = text.replace('"Operational Status"', '"Status"')
text = text.replace('"Assigned Tyre Item"', '"Tyre Item"')

# Give Action column a fixed professional width instead of too small ResizeToContents.
text = text.replace(
'''        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
''',
'''        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 190)
'''
)

# Add a little more spacing between Edit/Delete buttons if current spacing is too tight.
text = text.replace(
"            action_layout.setSpacing(6)",
"            action_layout.setSpacing(10)"
)

path.write_text(text, encoding="utf-8")
print("Cavity detail action column polished.")
