from pathlib import Path
import re

path = Path("app/ui/tyre_item_master_page.py")
text = path.read_text(encoding="utf-8")

# Style: replace separate header/table cards with one main page card and inner data section.
text = text.replace(
    "QFrame#HeaderCard, QFrame#TableCard {",
    "QFrame#PageCard {",
)

# Add inner data section style if missing.
if "QFrame#DataSection" not in text:
    text = text.replace(
        """            QFrame#PageCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
            }
""",
        """            QFrame#PageCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
            }

            QFrame#DataSection {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
""",
    )

# Replace root layout construction to use one page card.
old_root = """        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_table_card(), 1)

        self.refresh()
"""

new_root = """        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        page_card = QFrame()
        page_card.setObjectName("PageCard")

        page_layout = QVBoxLayout(page_card)
        page_layout.setContentsMargins(22, 18, 22, 22)
        page_layout.setSpacing(18)

        page_layout.addLayout(self._build_header())
        page_layout.addWidget(self._build_table_card(), 1)

        root.addWidget(page_card, 1)

        self.refresh()
"""

if old_root not in text:
    raise SystemExit("Could not find root layout block.")

text = text.replace(old_root, new_root)

# Convert _build_header from QFrame to QHBoxLayout.
start = text.find("    def _build_header(self) -> QFrame:")
end = text.find("    def _build_table_card(self) -> QFrame:", start)

if start == -1 or end == -1:
    raise SystemExit("Could not find _build_header/_build_table_card methods.")

new_header = '''    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Master Data  /  Tyre Item Master")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Tyre Item Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Maintain tyre item SAP codes and descriptions. Production rules will be added step by step."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        add_button = QPushButton("+ Add Tyre Item")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_item)

        layout.addLayout(text_area, 1)
        layout.addWidget(add_button)

        return layout

'''

text = text[:start] + new_header + text[end:]

# Convert table card object name to DataSection.
text = text.replace('card.setObjectName("TableCard")', 'card.setObjectName("DataSection")')

# Reduce margins because now it is inside the parent card.
text = text.replace(
    "layout.setContentsMargins(20, 18, 20, 20)",
    "layout.setContentsMargins(18, 16, 18, 18)",
)

path.write_text(text, encoding="utf-8")
print("Tyre Item Data moved inside the Tyre Item Master page card.")
