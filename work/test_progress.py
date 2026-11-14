import unittest

import progress


class ProgressTest(unittest.TestCase):
    def test_stage_phases(self):
        cases = {
            'LayoutParser': 'analyzing',
            'StylesAndFormulas': 'analyzing',
            'AutomaticTermExtractor': 'glossary',
            'ILTranslator': 'translating',
            'Typesetting': 'typesetting',
        }
        for stage, phase in cases.items():
            self.assertEqual(progress.phase_for(stage), phase)

    def test_unknown_stage_is_analyzing(self):
        self.assertEqual(progress.phase_for('SomeNewStage'), 'analyzing')
        self.assertEqual(progress.phase_for(''), 'analyzing')

    def test_event_mapping(self):
        event = progress.map_event({'type': 'progress_update', 'stage': 'ILTranslator',
                                    'stage_current': 3, 'stage_total': 10, 'overall_progress': 55.6})
        self.assertEqual(event['phase'], 'translating')
        self.assertEqual(event['percent'], 56)
        self.assertEqual((event['completed'], event['total']), (3, 10))

    def test_percent_never_goes_backwards(self):
        first = progress.map_event({'type': 'progress_update', 'stage': 'ILTranslator',
                                    'stage_current': 9, 'stage_total': 10, 'overall_progress': 80})
        second = progress.map_event({'type': 'progress_update', 'stage': 'Typesetting',
                                     'stage_current': 1, 'stage_total': 10, 'overall_progress': 62}, first)
        self.assertGreaterEqual(second['percent'], first['percent'])
        self.assertEqual(second['phase'], 'typesetting')

    def test_typesetting_end_and_completion(self):
        event = progress.map_event({'type': 'progress_end', 'stage': 'Typesetting',
                                    'stage_current': 2, 'stage_total': 2, 'overall_progress': 95})
        self.assertGreaterEqual(event['percent'], 99)
        done = progress.completed({'phase': 'typesetting', 'percent': 90})
        self.assertEqual((done['phase'], done['percent']), ('completed', 100))

    def test_fallback_without_progress_values(self):
        event = progress.map_event({'type': 'progress_start', 'stage': 'LayoutParser'})
        self.assertEqual(event['percent'], 0)
        self.assertEqual(event['total'], 0)


if __name__ == '__main__':
    unittest.main()
