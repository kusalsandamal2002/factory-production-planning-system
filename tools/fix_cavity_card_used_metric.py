from pathlib import Path

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "busy_or_issue = used + breakdown",
    "used_count = used",
)

text = text.replace(
    'numbers.addWidget(self._small_stat(str(busy_or_issue), "Used / Down", warning=busy_or_issue > 0))',
    'numbers.addWidget(self._small_stat(str(used_count), "Used", warning=used_count > 0))',
)

path.write_text(text, encoding="utf-8")
print("Changed card metric from Used / Down to Used only.")
