from pathlib import Path
import re

module_path = Path("app/ui/module_hub_page.py")
main_path = Path("app/ui/main_window.py")
viewer_path = Path("app/ui/admin_database_viewer_page.py")

if not module_path.exists():
    raise SystemExit("Missing: app/ui/module_hub_page.py")

if not main_path.exists():
    raise SystemExit("Missing: app/ui/main_window.py")

if not viewer_path.exists():
    raise SystemExit(
        "Missing: app/ui/admin_database_viewer_page.py\n"
        "Create AdminDatabaseViewerPage first, then run this patch."
    )

module = module_path.read_text(encoding="utf-8")
main = main_path.read_text(encoding="utf-8")


# ----------------------------
# 1) Add Database Viewer card to Admin Control Center
# ----------------------------
if 'action_key="database_viewer"' not in module:
    audit_card_pattern = re.compile(
        r'(\s*ModuleCard\(\s*title="Audit Log",\s*description="Track who changed master data, stock, demand and schedule records\.",\s*action_key="audit_log",\s*\),)',
        re.MULTILINE,
    )

    database_card = r'''\1
            ModuleCard(
                title="Database Viewer",
                description="View PostgreSQL tables safely with lazy loading, search, pagination and CSV export.",
                action_key="database_viewer",
            ),'''

    module, count = audit_card_pattern.subn(database_card, module, count=1)

    if count == 0:
        raise SystemExit("Could not find Audit Log card marker in module_hub_page.py")

    module_path.write_text(module, encoding="utf-8")
    print("Added Database Viewer card to Admin Control Center.")
else:
    print("Database Viewer card already exists.")


# ----------------------------
# 2) Import AdminDatabaseViewerPage in main_window.py
# ----------------------------
if "from app.ui.admin_database_viewer_page import AdminDatabaseViewerPage" not in main:
    import_marker = "from app.ui.audit_log_page import AuditLogPage"
    if import_marker in main:
        main = main.replace(
            import_marker,
            import_marker + "\nfrom app.ui.admin_database_viewer_page import AdminDatabaseViewerPage",
            1,
        )
    else:
        # Fallback: insert after module_hub_page import block area.
        fallback_marker = "from app.ui.monthly_stock_count_page import MonthlyStockCountPage"
        if fallback_marker not in main:
            raise SystemExit("Could not find import marker in main_window.py")
        main = main.replace(
            fallback_marker,
            "from app.ui.admin_database_viewer_page import AdminDatabaseViewerPage\n" + fallback_marker,
            1,
        )
    print("Added AdminDatabaseViewerPage import.")
else:
    print("AdminDatabaseViewerPage import already exists.")


# ----------------------------
# 3) Add ADMIN_DATABASE_VIEWER_INDEX safely
# ----------------------------
if "ADMIN_DATABASE_VIEWER_INDEX" not in main:
    index_matches = list(re.finditer(r"^\s{4}[A-Z0-9_]+_INDEX\s*=\s*(\d+)\s*$", main, re.MULTILINE))
    if not index_matches:
        raise SystemExit("Could not find page index constants in main_window.py")

    last_match = index_matches[-1]
    next_index = max(int(m.group(1)) for m in index_matches) + 1
    insert_at = last_match.end()
    main = main[:insert_at] + f"\n    ADMIN_DATABASE_VIEWER_INDEX = {next_index}" + main[insert_at:]
    print(f"Added ADMIN_DATABASE_VIEWER_INDEX = {next_index}.")
else:
    print("ADMIN_DATABASE_VIEWER_INDEX already exists.")


# ----------------------------
# 4) Add lazy page attribute
# ----------------------------
if "self.admin_database_viewer_page = None" not in main:
    marker = (
        '        self.placeholder_page = PlaceholderPage(\n'
        '            "Module",\n'
        '            "This module will be connected in the next step.",\n'
        '        )\n'
    )
    if marker not in main:
        raise SystemExit("Could not find placeholder_page marker in main_window.py")

    main = main.replace(marker, marker + "        self.admin_database_viewer_page = None\n", 1)
    print("Added admin_database_viewer_page lazy attribute.")
else:
    print("admin_database_viewer_page lazy attribute already exists.")


# ----------------------------
# 5) Add placeholder widget at end of stack
# ----------------------------
if 'PlaceholderPage("Admin Database Viewer"' not in main:
    marker = "        layout.addWidget(self.stack)\n        return content"
    if marker not in main:
        raise SystemExit("Could not find stack final marker in main_window.py")

    placeholder_line = (
        '        self.stack.addWidget(self._wrap_scroll('
        'PlaceholderPage("Admin Database Viewer", "Admin-only read-only PostgreSQL table inspector.")))\n'
    )
    main = main.replace(marker, placeholder_line + marker, 1)
    print("Added Admin Database Viewer placeholder to stack.")
else:
    print("Admin Database Viewer placeholder already exists.")


# ----------------------------
# 6) Add lazy creator method
# ----------------------------
if "def _ensure_admin_database_viewer_page(self) -> None:" not in main:
    marker = "    def _refresh_page(self, index: int) -> None:\n"
    if marker not in main:
        raise SystemExit("Could not find _refresh_page marker in main_window.py")

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

'''
    main = main.replace(marker, method + marker, 1)
    print("Added lazy creator method.")
else:
    print("Lazy creator method already exists.")


# ----------------------------
# 7) Add page to refresh map
# ----------------------------
if "self.ADMIN_DATABASE_VIEWER_INDEX: self.admin_database_viewer_page" not in main:
    marker = "            self.AUDIT_LOG_INDEX: self.audit_log_page,\n"
    if marker not in main:
        raise SystemExit("Could not find audit_log refresh marker in main_window.py")

    main = main.replace(
        marker,
        marker + "            self.ADMIN_DATABASE_VIEWER_INDEX: self.admin_database_viewer_page,\n",
        1,
    )
    print("Added Database Viewer to refresh map.")
else:
    print("Database Viewer refresh map already exists.")


# ----------------------------
# 8) Route Admin Control card action to Database Viewer page
# ----------------------------
if '"database_viewer"' not in main:
    marker = "        action_map = {\n"
    if marker not in main:
        raise SystemExit("Could not find action_map marker in main_window.py")

    route = (
        '        if action_key == "database_viewer":\n'
        '            self._ensure_admin_database_viewer_page()\n'
        '            self.navigate(self.ADMIN_DATABASE_VIEWER_INDEX)\n'
        '            return\n\n'
    )
    main = main.replace(marker, route + marker, 1)
    print("Added database_viewer action route.")
else:
    print("database_viewer action route already exists.")


main_path.write_text(main, encoding="utf-8")
print("Patch completed successfully.")
