from pathlib import Path

path = Path("app/ui/main_window.py")
content = path.read_text(encoding="utf-8")

def replace_once(old: str, new: str) -> None:
    global content
    if old not in content:
        raise SystemExit(f"Patch marker not found:\n{old}")
    content = content.replace(old, new, 1)

# 1) Import page
if "from app.ui.admin_database_viewer_page import AdminDatabaseViewerPage" not in content:
    marker = "from app.ui.audit_log_page import AuditLogPage"
    replace_once(
        marker,
        marker + "\nfrom app.ui.admin_database_viewer_page import AdminDatabaseViewerPage",
    )

# 2) Add page index
if "ADMIN_DATABASE_VIEWER_INDEX" not in content:
    replace_once(
        "CAVITIES_MASTER_INDEX = 37",
        "CAVITIES_MASTER_INDEX = 37\n    ADMIN_DATABASE_VIEWER_INDEX = 38",
    )

# 3) Add admin role checker
if "def _is_admin_role(self) -> bool:" not in content:
    marker = (
        "    def _is_monthly_stock_only_role(self) -> bool:\n"
        "        return self._is_monthly_stock_manager_role() or self._is_monthly_stock_viewer_role()\n"
    )
    insert = marker + """
    def _is_admin_role(self) -> bool:
        role_name = self._current_role_name().strip().lower()
        return role_name in {"admin", "administrator", "super admin"}

"""
    replace_once(marker, insert)

# 4) Add sidebar nav button under Reports & Admin
if '"Database Viewer", self.ADMIN_DATABASE_VIEWER_INDEX' not in content:
    marker = '        self._add_nav_button(layout, "Admin Settings", self.ADMIN_CONTROL_INDEX)\n'
    insert = (
        marker
        + "        if self._is_admin_role():\n"
        + '            self._add_nav_button(layout, "Database Viewer", self.ADMIN_DATABASE_VIEWER_INDEX)\n'
    )
    replace_once(marker, insert)

# 5) Add lazy page attribute after placeholder_page
if "self.admin_database_viewer_page = None" not in content:
    marker = (
        '        self.placeholder_page = PlaceholderPage(\n'
        '            "Module",\n'
        '            "This module will be connected in the next step.",\n'
        '        )\n'
    )
    insert = marker + "        self.admin_database_viewer_page = None\n"
    replace_once(marker, insert)

# 6) Add placeholder widget to stack at index 38
if "Admin Database Viewer\", \"Admin-only read-only database inspector." not in content:
    marker = "        self.stack.addWidget(self._wrap_scroll(self.cavities_master_page))\n"
    insert = (
        marker
        + '        self.stack.addWidget(self._wrap_scroll(PlaceholderPage("Admin Database Viewer", "Admin-only read-only database inspector.")))\n'
    )
    replace_once(marker, insert)

# 7) Add admin guard and lazy loader call in navigate()
if "if index == self.ADMIN_DATABASE_VIEWER_INDEX and not self._is_admin_role():" not in content:
    marker = "    def navigate(self, index: int) -> None:\n"
    insert = (
        marker
        + "        if index == self.ADMIN_DATABASE_VIEWER_INDEX and not self._is_admin_role():\n"
        + '            QMessageBox.warning(self, "Access Denied", "Only admin users can open Database Viewer.")\n'
        + "            return\n"
        + "        if index == self.ADMIN_DATABASE_VIEWER_INDEX:\n"
        + "            self._ensure_admin_database_viewer_page()\n"
    )
    replace_once(marker, insert)

# 8) Add ensure lazy method before _refresh_page()
if "def _ensure_admin_database_viewer_page(self) -> None:" not in content:
    marker = "    def _refresh_page(self, index: int) -> None:\n"
    method = """
    def _ensure_admin_database_viewer_page(self) -> None:
        if not self._is_admin_role():
            return

        if self.admin_database_viewer_page is not None:
            return

        self.admin_database_viewer_page = AdminDatabaseViewerPage(self.current_user)

        old_widget = self.stack.widget(self.ADMIN_DATABASE_VIEWER_INDEX)
        self.stack.removeWidget(old_widget)
        old_widget.deleteLater()

        self.stack.insertWidget(
            self.ADMIN_DATABASE_VIEWER_INDEX,
            self._wrap_scroll(self.admin_database_viewer_page),
        )

    def _refresh_page(self, index: int) -> None:
"""
    replace_once(marker, method)

# 9) Add page refresh mapping
if "self.ADMIN_DATABASE_VIEWER_INDEX: self.admin_database_viewer_page" not in content:
    marker = "            self.MONTHLY_STOCK_COUNT_INDEX: self.monthly_stock_count_page,\n"
    insert = marker + "            self.ADMIN_DATABASE_VIEWER_INDEX: self.admin_database_viewer_page,\n"
    replace_once(marker, insert)

path.write_text(content, encoding="utf-8")
print("main_window.py patched successfully")
