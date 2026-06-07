from pathlib import Path


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

code = file_path.read_text(encoding="utf-8")

replacements = [
    (
        "sidebar.setFixedWidth(300)",
        "sidebar.setFixedWidth(320)",
    ),
    (
        "layout.setContentsMargins(22, 24, 22, 24)",
        "layout.setContentsMargins(20, 16, 20, 18)",
    ),
    (
        """brand.setWordWrap(True)

        subtitle = QLabel("Excel Replacement • MPPS • Oven Planning")""",
        """brand.setWordWrap(True)
        brand.setMinimumHeight(72)
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel("Excel Replacement • MPPS • Oven Planning")""",
    ),
    (
        """subtitle.setWordWrap(True)

        layout.addWidget(brand)""",
        """subtitle.setWordWrap(True)
        subtitle.setMinimumHeight(34)

        layout.addWidget(brand)""",
    ),
]

for old, new in replacements:
    if old not in code:
        print(f"Warning: block not found: {old[:60]}")
    else:
        code = code.replace(old, new)

file_path.write_text(code, encoding="utf-8")

print("Sidebar polish patch completed.")
print("Sidebar width increased and brand title clipping fix applied.")