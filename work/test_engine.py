import tempfile
import unittest
from pathlib import Path
from unittest import mock

import engine

RESULT_HOST = '''
import json, sys
json.load(sys.stdin)
print("noise that is not json")
print(json.dumps({"type": "progress", "stage": "LayoutParser", "stage_current": 0,
                  "stage_total": 2, "overall_progress": 10}), flush=True)
print(json.dumps({"type": "progress", "stage": "ILTranslator", "stage_current": 1,
                  "stage_total": 2, "overall_progress": 50}), flush=True)
print(json.dumps({"type": "result", "mono": "m.pdf", "dual": "d.pdf", "seconds": 1.5,
                  "version": "2.9.0", "lang_in": "en", "lang_out": "zh-CN"}), flush=True)
sys.stderr.write("engine stderr tail\\n")
sys.exit(0)
'''

ERROR_HOST = '''
import json, sys
json.load(sys.stdin)
print(json.dumps({"type": "error", "message": "Error code: 401 - invalid api key"}), flush=True)
sys.stderr.write("traceback noise\\n")
sys.exit(1)
'''

MISSING_HOST = '''
import json, sys
json.load(sys.stdin)
print(json.dumps({"type": "error", "kind": "engine-missing",
                  "message": "未找到 pdf2zh-next 翻译引擎，请打开面板点击“一键准备环境”。"}), flush=True)
sys.exit(1)
'''

SILENT_HOST = '''
import json, sys
json.load(sys.stdin)
sys.stderr.write("crashed before any event\\n")
sys.exit(3)
'''


class EngineRunTest(unittest.TestCase):
    def run_host(self, text, request=None):
        with tempfile.TemporaryDirectory() as tmp:
            host = Path(tmp) / 'fake_host.py'
            host.write_text(text, 'utf-8')
            events = []
            with mock.patch.object(engine, 'HOST', host):
                outcome = engine.run(request or {'probe': True}, events.append)
            return outcome, events

    def test_parses_progress_and_result(self):
        result, events = self.run_host(RESULT_HOST)
        self.assertEqual(result['mono'], 'm.pdf')
        self.assertEqual(result['dual'], 'd.pdf')
        self.assertAlmostEqual(result['seconds'], 1.5)
        self.assertIn('stderr tail', result['tail'])
        phases = [event['phase'] for event in events]
        self.assertEqual(phases[0], 'analyzing')
        self.assertIn('translating', phases)
        self.assertEqual(phases[-1], 'completed')
        self.assertEqual(events[-1]['percent'], 100)

    def test_error_is_classified_with_engine_tail(self):
        with self.assertRaises(engine.EngineError) as raised:
            self.run_host(ERROR_HOST)
        self.assertIn('API 密钥', str(raised.exception))

    def test_missing_engine_message_passes_through(self):
        with self.assertRaises(engine.EngineError) as raised:
            self.run_host(MISSING_HOST)
        self.assertIn('一键准备环境', str(raised.exception))

    def test_silent_failure_uses_stderr(self):
        with self.assertRaises(engine.EngineError) as raised:
            self.run_host(SILENT_HOST)
        self.assertIn('crashed before any event', str(raised.exception))

    def test_missing_host_script_is_reported(self):
        with mock.patch.object(engine, 'HOST', Path('missing-engine-host.py')):
            with self.assertRaisesRegex(engine.EngineError, 'engine_host'):
                engine.run({})


if __name__ == '__main__':
    unittest.main()
