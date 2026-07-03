from pathlib import Path
import re

path = Path("app/ui/factory_capacity_page.py")
text = path.read_text(encoding="utf-8")

# Remove the metric section call from the page layout.
text = re.sub(
    r"\n\s*root\.addLayout\(self\._build_metrics\(\)\)\n",
    "\n",
    text,
)

# Remove _build_metrics method.
text = re.sub(
    r"\n\s*def _build_metrics\(self\).*?(?=\n\s*def _build_modules|\n\s*def _module_card|\n\s*def _open_module)",
    "\n",
    text,
    flags=re.S,
)

# Remove _metric_card method if it exists.
text = re.sub(
    r"\n\s*def _metric_card\(self.*?(?=\n\s*def _build_modules|\n\s*def _module_card|\n\s*def _open_module)",
    "\n",
    text,
    flags=re.S,
)

path.write_text(text, encoding="utf-8")
print("Factory Capacity top metric cards removed.")
