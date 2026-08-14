from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app.services.intelligent_excel_import_service import IntelligentExcelImportService
from app.services.workbook_continuous_sync_service import (
    ShipmentGroup,
    WorkbookContinuousSyncService,
)


class _MappingsResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class _IdentitySession:
    def __init__(self):
        self.identity = None
        self.calls = 0

    def execute(self, statement, params=None):
        self.calls += 1
        return _MappingsResult(self.identity)


class _Ledger:
    def __init__(self, session):
        self.session = session
        self.calls = []

    def _upsert_with_change(self, session, run_id, table_name, key_fields, values):
        self.calls.append((run_id, table_name, dict(key_fields), dict(values)))
        self.session.identity = {
            "id": 77,
            "source_family": values["source_family"],
            "identity_key": values["identity_key"],
            "base_key": values["base_key"],
            "canonical_shipment_id": None,
        }


class ShipmentNoResultSelfHealTests(unittest.TestCase):
    def test_identity_registry_uses_atomic_natural_key_upsert(self):
        self.assertEqual(
            IntelligentExcelImportService._NATIVE_UPSERT_KEYS["excel_shipment_identities"],
            ("source_family", "identity_key"),
        )

    def test_missing_identity_is_recreated_instead_of_one_raising(self):
        service = WorkbookContinuousSyncService(project_root='.')
        session = _IdentitySession()
        ledger = _Ledger(session)
        group = ShipmentGroup(
            shipment_column="AA",
            shipment_name="TEST SHIPMENT",
            source_status="ACTIVE",
            source_target_date=None,
            source_date_class="",
            items={"6000139": {"quantity": 10}},
            total_qty=10,
            item_count=1,
            base_key="TEST SHIPMENT",
            identity_key="OVEN-TEST123",
        )
        analysis = SimpleNamespace(
            workbook_hash="abc",
            workbook_name="OVEN SHEET PLAN AUGUST 04-2026.xlsx",
        )

        row = service._ensure_identity_row(
            session,
            ledger=ledger,
            import_run_id=5,
            group=group,
            analysis=analysis,
            plan_date=date(2026, 8, 4),
        )

        self.assertEqual(row["id"], 77)
        self.assertEqual(len(ledger.calls), 1)
        self.assertEqual(ledger.calls[0][1], "excel_shipment_identities")
        self.assertEqual(
            ledger.calls[0][2],
            {
                "source_family": service.SOURCE_FAMILY,
                "identity_key": "OVEN-TEST123",
            },
        )

    def test_shipment_sync_has_no_mapping_one_assumptions(self):
        source = open(
            'app/services/workbook_continuous_sync_service.py',
            'r',
            encoding='utf-8',
        ).read()
        self.assertNotIn('.mappings().one()', source)


if __name__ == '__main__':
    unittest.main()
