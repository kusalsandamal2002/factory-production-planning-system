from pathlib import Path

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

old = 'numbers.addWidget(self._small_stat(str(active), "Active"))'
new = 'numbers.addWidget(self._small_stat(str(breakdown), "Breakdown", warning=breakdown > 0))'

if old not in text:
    raise SystemExit("Could not find the Active metric line. File structure may have changed.")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Cavity card metric changed from Active to Breakdown.")
