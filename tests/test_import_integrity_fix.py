from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.services.workbook_continuous_sync_service import (
    WorkbookContinuousSyncService,
    _shipment_no,
)
from app.utils.import_error_utils import extract_task_error_reason


class ImportIntegrityFixTests(unittest.TestCase):
    def test_error_dialog_ignores_sqlalchemy_help_url(self):
        details = """Traceback (most recent call last):
psycopg.errors.UniqueViolation: duplicate key value violates unique constraint \"mpps_shipments_shipment_no_key\"
DETAIL: Key (shipment_no)=(XLS-SYNC-ABC) already exists.
[SQL: INSERT INTO mpps_shipments ...]
(Background on this error at: https://sqlalche.me/e/20/gkpj)
"""
        reason = extract_task_error_reason(details)
        self.assertIn("duplicate key value violates unique constraint", reason)
        self.assertNotIn("sqlalche.me/e/", reason)

    def test_legacy_shipment_lookup_checks_identity_and_stable_number(self):
        identity_key = "OVEN-ABCDEF1234567890"
        expected = {"id": 44, "shipment_no": _shipment_no(identity_key)}
        result_proxy = Mock()
        result_proxy.mappings.return_value.first.return_value = expected
        session = Mock()
        session.execute.return_value = result_proxy

        row = WorkbookContinuousSyncService._find_legacy_canonical_shipment(
            session,
            identity_key,
        )

        self.assertEqual(row, expected)
        _, params = session.execute.call_args.args
        self.assertEqual(params["identity_key"], identity_key)
        self.assertEqual(params["shipment_no"], _shipment_no(identity_key))
        self.assertEqual(
            params["source_family"],
            WorkbookContinuousSyncService.SOURCE_FAMILY,
        )


if __name__ == "__main__":
    unittest.main()
