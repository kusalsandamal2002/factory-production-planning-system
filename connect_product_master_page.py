from pathlib import Path


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

code = file_path.read_text(encoding="utf-8")


replacements = [
    (
        """from app.ui.order_entry_page import OrderEntryPage
""",
        """from app.ui.order_entry_page import OrderEntryPage
from app.ui.product_master_page import ProductMasterPage
""",
    ),
    (
        """    ADMIN_CONTROL_INDEX = 9
    PLACEHOLDER_INDEX = 10
""",
        """    ADMIN_CONTROL_INDEX = 9
    PRODUCT_MASTER_INDEX = 10
    PLACEHOLDER_INDEX = 11
""",
    ),
    (
        """        self.admin_control_page = create_admin_control_page(
            open_callback=self.open_module_action
        )
        self.placeholder_page = PlaceholderPage(
""",
        """        self.admin_control_page = create_admin_control_page(
            open_callback=self.open_module_action
        )
        self.product_master_page = ProductMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
    ),
    (
        """        self.stack.addWidget(self._wrap_scroll(self.admin_control_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
        """        self.stack.addWidget(self._wrap_scroll(self.admin_control_page))
        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
    ),
    (
        """            self.TIRE_STOCK_INDEX: self.tire_stock_page,
        }
""",
        """            self.TIRE_STOCK_INDEX: self.tire_stock_page,
            self.PRODUCT_MASTER_INDEX: self.product_master_page,
        }
""",
    ),
    (
        '''            "product_master": (
                self.PLACEHOLDER_INDEX,
                "Product Master",
                "Manage material codes, descriptions, product groups, weights, bead and band links.",
            ),
''',
        '''            "product_master": (
                self.PRODUCT_MASTER_INDEX,
                None,
                None,
            ),
''',
    ),
    (
        """        if index == self.STOCK_PLANNING_INDEX:
            self.navigate(self.STOCK_PLANNING_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
""",
        """        if index == self.STOCK_PLANNING_INDEX:
            self.navigate(self.STOCK_PLANNING_INDEX)
            return

        if index == self.PRODUCT_MASTER_INDEX:
            self.navigate(self.PRODUCT_MASTER_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
""",
    ),
]


for old, new in replacements:
    if old not in code:
        print("Warning: expected block not found. Maybe already patched:")
        print(old[:120])
    else:
        code = code.replace(old, new)

file_path.write_text(code, encoding="utf-8")

print("Product Master page connected successfully.")
print("Factory Data Center -> Product Master -> Open will now load the real Product Master page.")