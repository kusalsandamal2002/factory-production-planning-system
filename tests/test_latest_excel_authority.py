from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.intelligent_excel_import_service import IntelligentExcelImportService
from app.services.workbook_continuous_sync_service import (
    ShipmentGroup,
    WorkbookContinuousSyncService,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _LatestSession:
    def __init__(self, latest):
        self.latest = latest

    def execute(self, *_args, **_kwargs):
        return _ScalarResult(self.latest)


class LatestExcelAuthorityTests(unittest.TestCase):
    def test_newest_workbook_is_live_authority(self):
        service = WorkbookContinuousSyncService('.')
        analysis = SimpleNamespace(plan_date='2026-08-04')
        mode, reason, latest = service.resolve_mode(
            _LatestSession(date(2026, 8, 3)),
            analysis,
            {'authoritative_latest_shipments': True},
        )
        self.assertEqual(mode, 'LIVE')
        self.assertEqual(latest, date(2026, 8, 3))
        self.assertIn('FINAL/authoritative', reason)

    def test_older_workbook_can_never_replace_latest_live_shipments(self):
        service = WorkbookContinuousSyncService('.')
        analysis = SimpleNamespace(plan_date='2026-08-02')
        mode, reason, _ = service.resolve_mode(
            _LatestSession(date(2026, 8, 4)),
            analysis,
            {'authoritative_latest_shipments': True},
        )
        self.assertEqual(mode, 'HISTORICAL')
        self.assertIn('older than', reason)

    def test_authoritative_shipment_number_is_deterministic(self):
        group = ShipmentGroup(
            shipment_column='BY',
            shipment_name='CTR 001',
            source_status='ACTIVE',
            source_target_date=date(2026, 8, 8),
            source_date_class='',
            items={'6000139': {'quantity': 10}},
            total_qty=10,
            item_count=1,
            base_key='CTR 001',
        )
        first = WorkbookContinuousSyncService._authoritative_shipment_no(
            date(2026, 8, 4), group
        )
        second = WorkbookContinuousSyncService._authoritative_shipment_no(
            date(2026, 8, 4), group
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith('XLS-FINAL-20260804-'))

    def test_importer_defaults_to_latest_excel_authority(self):
        source = open(
            'app/services/intelligent_excel_import_service.py',
            'r', encoding='utf-8'
        ).read()
        self.assertIn('"authoritative_latest_shipments": True', source)
        self.assertIn('change["action"] in {"UPDATE", "DELETE"}', source)

    def test_previous_excel_live_queue_is_archived_before_delete(self):
        source = open(
            'app/services/workbook_continuous_sync_service.py',
            'r', encoding='utf-8'
        ).read()
        archive_pos = source.index('INSERT INTO excel_authoritative_shipment_archive')
        delete_pos = source.index('DELETE FROM mpps_shipments', archive_pos)
        self.assertLess(archive_pos, delete_pos)
        self.assertIn("OR COALESCE(shipment_no, '') LIKE 'XLS-SYNC-%'", source)
        self.assertIn("OR COALESCE(shipment_no, '') LIKE 'XLS-FINAL-%'", source)


if __name__ == '__main__':
    unittest.main()
