from pathlib import Path
import re

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Compact Edit button style.
text = re.sub(
    r'''QPushButton#EditButton\s*\{
.*?
\}
''',
    '''QPushButton#EditButton {
                background: #eef2f7;
                color: #0f172a;
                border: 1px solid #d8e2ee;
                border-radius: 9px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
                min-width: 58px;
                max-width: 64px;
            }
''',
    text,
    flags=re.S,
)

# Compact Delete button style.
text = re.sub(
    r'''QPushButton#DeleteButton\s*\{
.*?
\}
''',
    '''QPushButton#DeleteButton {
                background: #fff1f2;
                color: #b91c1c;
                border: 1px solid #fecdd3;
                border-radius: 9px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
                min-width: 66px;
                max-width: 72px;
            }
''',
    text,
    flags=re.S,
)

# Keep hover styles clean.
if "QPushButton#EditButton:hover" not in text:
    text = text.replace(
        '''QPushButton#DeleteButton {
                background: #fff1f2;
                color: #b91c1c;
                border: 1px solid #fecdd3;
                border-radius: 9px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
                min-width: 66px;
                max-width: 72px;
            }
''',
        '''QPushButton#DeleteButton {
                background: #fff1f2;
                color: #b91c1c;
                border: 1px solid #fecdd3;
                border-radius: 9px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
                min-width: 66px;
                max-width: 72px;
            }

            QPushButton#EditButton:hover {
                background: #e2e8f0;
            }

            QPushButton#DeleteButton:hover {
                background: #ffe4e6;
            }
''',
    )

# Reduce action column width.
text = re.sub(
    r"self\.table\.setColumnWidth\(5,\s*\d+\)",
    "self.table.setColumnWidth(5, 170)",
    text,
)

# Reduce row height slightly.
text = text.replace(
    "self.table.setRowHeight(row_index, 58)",
    "self.table.setRowHeight(row_index, 54)",
)

# Compact action cell margins/spacings.
text = re.sub(
    r'''action_layout\.setContentsMargins\([^)]+\)
\s*action_layout\.setSpacing\(\d+\)
''',
    '''action_layout.setContentsMargins(6, 5, 6, 5)
            action_layout.setSpacing(8)
''',
    text,
)

path.write_text(text, encoding="utf-8")
print("Compact professional action buttons applied.")
