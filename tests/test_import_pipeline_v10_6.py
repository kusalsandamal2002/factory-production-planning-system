from pathlib import Path
import unittest


class ImportPipelineV106Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path('app/ui/raw_excel_viewer_page.py').read_text(encoding='utf-8')

    def test_progress_pipeline_is_rendered_under_progress_bar(self):
        progress_pos = self.source.index('source_layout.addWidget(self.progress)')
        pipeline_pos = self.source.index('self.pipeline_frame = QFrame()', progress_pos)
        root_pos = self.source.index('root.addWidget(source_card)', pipeline_pos)
        self.assertLess(progress_pos, pipeline_pos)
        self.assertLess(pipeline_pos, root_pos)
        self.assertIn('LIVE DATA PIPELINE', self.source)
        self.assertIn('CURRENT DATA STAGE:', self.source)

    def test_pipeline_has_professional_commit_stages(self):
        for stage in (
            'Schema / Archive', 'Shipments', 'Oven / Shift', 'Materials',
            'Opening Stock', 'Actuals + AI', 'Replan', 'Commit',
        ):
            self.assertIn(stage, self.source)

    def test_task_badge_distinguishes_commit_analyze_and_rollback(self):
        self.assertIn('COMMITTING UPDATE', self.source)
        self.assertIn('ANALYZING', self.source)
        self.assertIn('ROLLING BACK', self.source)

    def test_failed_pipeline_states_rollback_safely(self):
        self.assertIn('FAILED / ROLLED BACK', self.source)
        self.assertIn('No partial workbook update was committed', self.source)


if __name__ == '__main__':
    unittest.main()
