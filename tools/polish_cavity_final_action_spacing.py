from pathlib import Path

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Make action column wider and cleaner.
text = text.replace(
    "self.table.setColumnWidth(5, 190)",
    "self.table.setColumnWidth(5, 230)",
)

# More professional Edit/Delete button sizes.
text = text.replace(
    "min-width: 72px;",
    "min-width: 78px;",
)

text = text.replace(
    "min-width: 82px;",
    "min-width: 88px;",
)

# Increase row height slightly for manager-level readability.
text = text.replace(
    "self.table.setRowHeight(row_index, 54)",
    "self.table.setRowHeight(row_index, 58)",
)

# Center action buttons with cleaner spacing.
text = text.replace(
'''            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(10)
''',
'''            action_layout.setContentsMargins(8, 6, 8, 6)
            action_layout.setSpacing(12)
'''
)

path.write_text(text, encoding="utf-8")
print("Final action spacing polish applied.")
