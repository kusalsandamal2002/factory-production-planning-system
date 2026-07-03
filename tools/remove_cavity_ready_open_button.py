from pathlib import Path
import re

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Header hint wording.
text = text.replace(
    'hint = QLabel("Click a card to open the detailed cavity board.")',
    'hint = QLabel("Select a production line card to view cavity details.")',
)

# Remove READY / ATTENTION badge block from line cards.
text = re.sub(
    r'''
\s*badge\s*=\s*QLabel\("ATTENTION"\s+if\s+attention\s+else\s+"READY"\)
\s*badge\.setAlignment\(Qt\.AlignmentFlag\.AlignCenter\)
\s*badge\.setObjectName\("BadgeWarning"\s+if\s+attention\s+else\s+"BadgeReady"\)
''',
    "\n",
    text,
    flags=re.VERBOSE,
)

text = re.sub(
    r'\n\s*top\.addWidget\(badge\)\n',
    "\n",
    text,
)

# Remove Open button block from card footer.
text = re.sub(
    r'''
\s*open_button\s*=\s*QPushButton\("Open"\)
\s*open_button\.setObjectName\("PrimaryButton"\)
\s*open_button\.clicked\.connect\(lambda\s+checked=False,\s+name=line_name:\s+self\._open_line_board\(name\)\)
''',
    "\n",
    text,
    flags=re.VERBOSE,
)

text = re.sub(
    r'\n\s*footer\.addWidget\(open_button\)\n',
    "\n",
    text,
)

# Make footer wording clearer.
text = text.replace(
    'availability = QLabel(f"{free_percent}% ready availability")',
    'availability = QLabel(f"{free_percent}% free capacity - click card to open board")',
)

# Remove unused badge stylesheet blocks to keep file clean.
text = re.sub(
    r'''
\s*QLabel\#BadgeReady\s*\{.*?\}
''',
    "\n",
    text,
    flags=re.S | re.VERBOSE,
)

text = re.sub(
    r'''
\s*QLabel\#BadgeWarning\s*\{.*?\}
''',
    "\n",
    text,
    flags=re.S | re.VERBOSE,
)

path.write_text(text, encoding="utf-8")
print("Removed READY badge and Open button from Cavities cards.")
