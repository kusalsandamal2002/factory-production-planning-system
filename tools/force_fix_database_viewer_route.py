from pathlib import Path
import re

path = Path("app/ui/main_window.py")
content = path.read_text(encoding="utf-8")

viewer_file = Path("app/ui/admin_database_viewer_page.py")
if not viewer_file.exists():
    raise SystemExit("Missing app/ui/admin_database_viewer_page.py")

# Import AdminDatabaseViewerPage
import_line = "from app.ui.admin_database_viewer_page import AdminDatabaseViewerPage"
if import_line not in content:
    lines = content.splitlines()
    insert_at = None

    for i, line in enumerate(lines):
        if line.startswith("from app.ui."):
            insert_at = i + 1

    if insert_at is None:
        raise SystemExit("Could not find app.ui import section in main_window.py")

    lines.insert(insert_at, import_line)
    content = "\n".join(lines) + "\n"

# Add direct show method. This does NOT depend on stack indexes.
if "def _show_admin_database_viewer_page(self) -> None:" not in content:
    method = '''
    def _show_admin_database_viewer_page(self) -> None:
        if not hasattr(self, "admin_database_viewer_page"):
            self.admin_database_viewer_page = None

        if not hasattr(self, "admin_database_viewer_container"):
            self.admin_database_viewer_container = None

        if self.admin_database_viewer_page is None:
            self.admin_database_viewer_page = AdminDatabaseViewerPage(self.current_user)
            self.admin_database_viewer_container = self._wrap_scroll(
                self.admin_database_viewer_page
            )
            self.stack.addWidget(self.admin_database_viewer_container)

        self.stack.setCurrentWidget(self.admin_database_viewer_container)

        if hasattr(self.admin_database_viewer_page, "load_tables_once"):
            self.admin_database_viewer_page.load_tables_once()

'''

    marker = re.search(r"\n    def open_module_action\(self,\s*action_key[^)]*\).*?:\n", content)
    if not marker:
        raise SystemExit("Could not find open_module_action method.")

    content = content[:marker.start()] + "\n" + method + content[marker.start():]

# Force database_viewer route at the TOP of open_module_action.
pattern = re.compile(
    r"(    def open_module_action\(self,\s*action_key[^)]*\).*?:\n)(.*?)(?=\n    def |\Z)",
    re.DOTALL,
)

match = pattern.search(content)
if not match:
    raise SystemExit("Could not locate open_module_action body.")

header = match.group(1)
body = match.group(2)

# Remove old database_viewer direct route blocks if any.
body = re.sub(
    r'\s*if action_key == ["\']database_viewer["\']:\n'
    r'(?:\s{12}.*\n)*?'
    r'\s{12}return\n',
    "\n",
    body,
)

route = '''        if action_key == "database_viewer":
            self._show_admin_database_viewer_page()
            return

'''

new_function = header + route + body.lstrip("\n")
content = content[:match.start()] + new_function + content[match.end():]

path.write_text(content, encoding="utf-8")
print("Database Viewer card route fixed successfully.")
