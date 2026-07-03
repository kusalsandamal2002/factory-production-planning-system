from pathlib import Path

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "self.line_grid.addWidget(card, index // 2, index % 2)",
    "self.line_grid.addWidget(card, index // 3, index % 3)",
)

text = text.replace(
    "for col in range(2):\n            self.line_grid.setColumnStretch(col, 1)",
    "for col in range(3):\n            self.line_grid.setColumnStretch(col, 1)",
)

path.write_text(text, encoding="utf-8")
print("Cavity cards changed back to 3 columns.")
