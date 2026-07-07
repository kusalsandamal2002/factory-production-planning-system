from pathlib import Path
import re

path = Path("app/ui/main_window.py")
content = path.read_text(encoding="utf-8")

if "from app.ui.admin_database_viewer_page import AdminDatabaseViewerPage" not in content:
    marker = "from app.ui.audit_log_page import AuditLogPage"
    if marker not in content:
        raise SystemExit("Import marker not found: AuditLogPage")
    content = content.replace(
        marker,
        marker + "\nfrom app.ui.admin_database_viewer_page import AdminDatabaseViewerPage",
        1,
    )

if "ADMIN_DATABASE_VIEWER_INDEX" not in content:
    index_matches = list(re.finditer(r"^\s{4}[A-Z0-9_]+_INDEX\s*=\s*(\d+)\s*$", content, re.MULTILINE))
    if not index_matches:
        raise SystemExit("Page index constants not found.")
    next_index = max(int(m.group(1)) for m in index_matches) + 1
    last_match = index_matches[-1]
    content = content[:last_match.end()] + f"\n    ADMIN_DATABASE_VIEWER_INDEX = {next_index}" + content[last_match.end():]

if "self.admin_database_viewer_page = None" not in content:
    marker = (
        '        self.placeholder_page = PlaceholderPage(\n'
        '            "Module",\n'
        '            "This module will be connected in the next step.",\n'
        '        )\n'
    )
    if marker not in content:
        raise SystemExit("placeholder_page marker not found.")
    content = content.replace(marker, marker + "        self.admin_database_viewer_page = None\n", 1)

if 'PlaceholderPage("Admin Database Viewer"' not in content:
    marker = "        layout.addWidget(self.stack)\n        return content"
    if marker not in content:
        raise SystemExit("Stack final marker not found.")
    content = content.replace(
        marker,
        '        self.stack.addWidget(self._wrap_scroll(PlaceholderPage("Admin Database Viewer", "Admin-only read-only PostgreSQL table inspector.")))\n'
        + marker,
        1,
    )

if "def _ensure_admin_database_viewer_page(self) -> None:" not in content:
    marker = "    def _refresh_page(self, index: int) -> None:\n"
    if marker not in content:
        raise SystemExit("_refresh_page marker not found.")

    method = '''
    def _ensure_admin_database_viewer_page(self) -> None:
        if getattr(self, "admin_database_viewer_page", None) is not None:
            return

        self.admin_database_viewer_page = AdminDatabaseViewerPage(self.current_user)

        old_widget = self.stack.widget(self.ADMIN_DATABASE_VIEWER_INDEX)
        self.stack.removeWidget(old_widget)
        old_widget.deleteLater()

        self.stack.insertWidget(
            self.ADMIN_DATABASE_VIEWER_INDEX,
            self._wrap_scroll(self.admin_database_viewer_page),
        )

        if hasattr(self.admin_database_viewer_page, "load_tables_once"):
            self.admin_database_viewer_page.load_tables_once()

'''
    content = content.replace(marker, method + marker, 1)

# Force route inside open_module_action
if 'if action_key == "database_viewer":' not in content:
    marker = "    def open_module_action(self, action_key: str) -> None:\n"
    if marker not in content:
        raise SystemExit("open_module_action function not found.")

    route = (
        marker
        + '        if action_key == "database_viewer":\n'
        + "            self._ensure_admin_database_viewer_page()\n"
        + "            self.navigate(self.ADMIN_DATABASE_VIEWER_INDEX)\n"
        + "            return\n\n"
    )

    content = content.replace(marker, route, 1)

# Add refresh map entry only if refresh map exists
if "self.ADMIN_DATABASE_VIEWER_INDEX: self.admin_database_viewer_page" not in content:
    marker = "            self.AUDIT_LOG_INDEX: self.audit_log_page,\n"
    if marker in content:
        content = content.replace(
            marker,
            marker + "            self.ADMIN_DATABASE_VIEWER_INDEX: self.admin_database_viewer_page,\n",
            1,
        )

path.write_text(content, encoding="utf-8")
print("Database Viewer route fixed.")
