from datetime import date
import unittest

from app.services.operational_source_service import OperationalSourceService


class OperationalSourceV102Tests(unittest.TestCase):
    def test_newer_committed_import_beats_older_live_sync(self):
        candidate = OperationalSourceService._pick_newest_candidate([
            {
                'plan_date': date(2026, 8, 4),
                'sync_run_id': 5,
                'import_run_id': 5,
                'sync_confirmed': True,
                'authority': 'LIVE SYNC',
            },
            {
                'plan_date': date(2026, 8, 10),
                'import_run_id': 10,
                'sync_confirmed': False,
                'authority': 'COMMITTED IMPORT',
            },
        ])
        self.assertEqual(candidate['plan_date'], date(2026, 8, 10))

    def test_same_date_prefers_live_sync_confirmation(self):
        candidate = OperationalSourceService._pick_newest_candidate([
            {
                'plan_date': date(2026, 8, 10),
                'import_run_id': 10,
                'sync_confirmed': False,
                'authority': 'COMMITTED IMPORT',
            },
            {
                'plan_date': date(2026, 8, 10),
                'sync_run_id': 11,
                'import_run_id': 10,
                'sync_confirmed': True,
                'authority': 'LIVE SYNC',
            },
        ])
        self.assertTrue(candidate['sync_confirmed'])
        self.assertEqual(candidate['authority'], 'LIVE SYNC')

    def test_older_historical_candidate_never_moves_cutoff_backwards(self):
        candidate = OperationalSourceService._pick_newest_candidate([
            {'plan_date': date(2026, 8, 10), 'import_run_id': 10, 'sync_confirmed': True},
            {'plan_date': date(2025, 11, 30), 'import_run_id': 99, 'sync_confirmed': False},
        ])
        self.assertEqual(candidate['plan_date'], date(2026, 8, 10))


if __name__ == '__main__':
    unittest.main()
