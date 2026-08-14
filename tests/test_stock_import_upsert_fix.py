from __future__ import annotations

import unittest

from app.services.intelligent_excel_import_service import IntelligentExcelImportService


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def one(self):
        return self._row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self.row = row
        self.sql = []

    def execute(self, statement, params=None):
        self.sql.append((str(statement), dict(params or {})))
        return _FakeResult(self.row)


class StockImportUpsertFixTests(unittest.TestCase):
    def _run_native_upsert(self, table_name, key_fields, values, after_row):
        service = IntelligentExcelImportService(project_root='.')
        service._fetch_existing = lambda *args, **kwargs: None  # type: ignore[method-assign]
        changes = []
        service._record_change = lambda *args, **kwargs: changes.append(args)  # type: ignore[method-assign]
        session = _FakeSession(after_row)

        service._upsert_with_change(
            session,
            99,
            table_name,
            key_fields,
            values,
        )
        self.assertEqual(len(session.sql), 1)
        self.assertEqual(len(changes), 1)
        return session.sql[0][0]

    def test_sap_stock_uses_atomic_conflict_upsert(self):
        sql = self._run_native_upsert(
            'mpps_sap_stock_items',
            {'sap_code': '6000139'},
            {'sap_code': '6000139', 'tyre_description': 'TEST', 'fg_stock': 5},
            {'id': 1, 'sap_code': '6000139', 'tyre_description': 'TEST', 'fg_stock': 5},
        )
        self.assertIn('ON CONFLICT (sap_code) DO UPDATE', sql)

    def test_legacy_stock_uses_atomic_conflict_upsert(self):
        sql = self._run_native_upsert(
            'mpps_stock_items',
            {'material_code': '6000139'},
            {'material_code': '6000139', 'item_description': 'TEST', 'fg_stock': 5},
            {'id': 1, 'material_code': '6000139', 'item_description': 'TEST', 'fg_stock': 5},
        )
        self.assertIn('ON CONFLICT (material_code) DO UPDATE', sql)

    def test_daily_stock_uses_composite_conflict_upsert(self):
        sql = self._run_native_upsert(
            'mpps_daily_stock_entries',
            {'stock_date': '2026-08-10', 'sap_code': '6000139'},
            {
                'stock_date': '2026-08-10',
                'sap_code': '6000139',
                'tyre_description': 'TEST',
                'fg_qty': 5,
            },
            {
                'id': 1,
                'stock_date': '2026-08-10',
                'sap_code': '6000139',
                'tyre_description': 'TEST',
                'fg_qty': 5,
            },
        )
        self.assertIn('ON CONFLICT (stock_date, sap_code) DO UPDATE', sql)


if __name__ == '__main__':
    unittest.main()
