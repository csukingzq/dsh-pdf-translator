import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import cache_ops
import cli


class _Doc:
    needs_pass = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def __len__(self):
        return 3

    def get_page_fonts(self, index):
        if index == 0:
            return [(505, 'cff', 'Type1', 'DGKPDI+AdvMacMthSyN', 'T1_0', ''),
                    (915, 'cff', 'Type1', 'DGKNNF+AdvOT863180fb', 'T1_1', 'WinAnsiEncoding')]
        return []

    def __getitem__(self, index):
        return self

    def get_text(self, kind):
        return 'ﬃ ¼ ð text'


def fake_pymupdf():
    module = types.ModuleType('pymupdf')
    module.__version__ = '1.26.0'
    module.open = lambda _path: _Doc()
    return module


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'paper.pdf'
        self.source.write_bytes(b'%PDF-1.4 test')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'base_url': 'https://api.example.com/v1', 'model': 'text-model', 'api_key': 'secret-key',
        }), 'utf-8')
        self.data = self.root / 'data'
        self.data.mkdir()
        self.modules = mock.patch.dict(sys.modules, {'pymupdf': fake_pymupdf()})
        self.modules.start()
        self.repair = mock.patch('mathrepair.protect_variables', return_value=4)
        self.protect = self.repair.start()

    def tearDown(self):
        self.modules.stop()
        self.repair.stop()
        self.temp.cleanup()

    def execute(self, request, on_progress=None):
        return cli.execute({'dataDir': str(self.data), 'configPath': str(self.config), **request}, on_progress)

    def test_inspect(self):
        result = self.execute({'operation': 'inspect', 'pdf': str(self.source), 'pages': '1-2'})
        self.assertEqual(result['pages'], 3)
        self.assertEqual(result['selected_pages'], [1, 2])
        with self.assertRaises(ValueError):
            self.execute({'operation': 'inspect', 'pdf': str(self.root / 'missing.pdf')})

    def test_doctor(self):
        with mock.patch.object(cli, 'engine_version', return_value='2.10.2'):
            result = self.execute({'operation': 'doctor'})
        self.assertTrue(result['engine']['ready'])
        self.assertEqual(result['engine']['version'], '2.10.2')
        self.assertEqual(result['engine']['name'], 'pdf2zh-next')
        self.assertTrue(result['model_configured'])
        self.assertEqual(result['config_path'], str(self.config.resolve()))

    def test_unknown_operation(self):
        with self.assertRaises(ValueError):
            self.execute({'operation': 'review'})

    def test_translate_requires_engine(self):
        with mock.patch.object(cli, 'engine_version', return_value=''):
            with self.assertRaisesRegex(ValueError, '一键准备环境'):
                self.execute({'operation': 'translate', 'pdf': str(self.source)})
        self.assertEqual(list((self.root / 'out').glob('*')) if (self.root / 'out').exists() else [], [])

    def test_translate_requires_model_config(self):
        self.config.write_text('{}', 'utf-8')
        with mock.patch.object(cli, 'engine_version', return_value='2.10.2'):
            with self.assertRaisesRegex(ValueError, '面板'):
                self.execute({'operation': 'translate', 'pdf': str(self.source)})

    def test_translate_collects_outputs(self):
        events = []
        seen = {}

        def fake_run(request, on_progress=None):
            seen.update(request)
            engine = Path(request['engine_dir'])
            engine.mkdir(parents=True, exist_ok=True)
            mono = engine / 'p.no_watermark.zh-CN.mono.pdf'
            dual = engine / 'p.no_watermark.zh-CN.dual.pdf'
            mono.write_bytes(b'mono')
            dual.write_bytes(b'dual')
            if on_progress:
                on_progress({'phase': 'translating', 'percent': 50, 'completed': 1, 'total': 2})
            return {'mono': str(mono), 'dual': str(dual), 'seconds': 2.0, 'version': '2.10.2',
                    'lang_in': 'en', 'lang_out': 'zh-CN', 'token_usage': {'total': 1}}

        with mock.patch.object(cli, 'engine_version', return_value='2.10.2'), \
                mock.patch('engine.run', fake_run):
            result = self.execute({'operation': 'translate', 'pdf': str(self.source), 'pages': 'all',
                                   'outputDir': str(self.root / 'out')}, events.append)
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(Path(result['output']).is_file())
        self.assertTrue(Path(result['dual']).is_file())
        self.assertNotIn('report', result)
        self.assertFalse((Path(result['output']).parent / 'report.json').exists())
        self.assertEqual(result['pages'], 3)
        self.assertEqual(events[0]['phase'], 'translating')
        diagnostics = result['diagnostics']
        self.assertIn('AdvMacMthSyN', diagnostics['mathFonts'])
        self.assertTrue(diagnostics['formulaProtected'])
        self.assertEqual(diagnostics['suspiciousChars'], 9)
        self.assertIn('AdvMacMthSyN', seen['formular_font_pattern'])
        self.assertTrue(seen['math_compatibility'])
        self.assertEqual(diagnostics['protectedVariableRuns'], 4)
        self.assertEqual(self.protect.call_args.args[1], [0, 1, 2])
        self.assertTrue(result['warnings'])
        self.assertIn('MathType', result['warnings'][0])
        identity = hashlib.sha256(self.source.read_bytes()).hexdigest()[:16]
        self.assertEqual(Path(seen['cache_dir']), self.data / 'work/pdf2zh-cache' / identity)
        rows = cache_ops.cache_list(self.data)
        self.assertEqual(rows[0]['id'], identity)
        self.assertEqual(rows[0]['name'], 'paper.pdf')

    def test_plain_documents_keep_engine_defaults(self):
        class PlainDoc(_Doc):
            def get_page_fonts(self, index):
                return [(1, 'cff', 'Type1', 'DGKNNF+AdvOT863180fb', 'T1_0', '')]

            def get_text(self, kind):
                return 'plain english prose'

        module = types.ModuleType('pymupdf')
        module.__version__ = '1.26.0'
        module.open = lambda _path: PlainDoc()
        seen = {}

        def fake_run(request, on_progress=None):
            seen.update(request)
            engine = Path(request['engine_dir'])
            engine.mkdir(parents=True, exist_ok=True)
            mono = engine / 'p.mono.pdf'
            dual = engine / 'p.dual.pdf'
            mono.write_bytes(b'mono')
            dual.write_bytes(b'dual')
            return {'mono': str(mono), 'dual': str(dual), 'seconds': 1.0, 'version': '2.10.2'}

        with mock.patch.dict(sys.modules, {'pymupdf': module}), \
                mock.patch.object(cli, 'engine_version', return_value='2.10.2'), \
                mock.patch('engine.run', fake_run):
            result = self.execute({'operation': 'translate', 'pdf': str(self.source),
                                   'outputDir': str(self.root / 'plain')})
        self.assertIsNone(seen['formular_font_pattern'])
        self.assertFalse(seen['math_compatibility'])
        self.protect.assert_not_called()
        self.assertFalse(result['diagnostics']['formulaProtected'])
        self.assertEqual(result['diagnostics']['mathFonts'], [])
        self.assertEqual(result['diagnostics']['suspiciousChars'], 0)
        self.assertEqual(result['warnings'], [])

    def test_failed_translation_discards_run_folder(self):
        def boom(request, on_progress=None):
            raise RuntimeError('engine down')

        out = self.root / 'out'
        with mock.patch.object(cli, 'engine_version', return_value='2.10.2'), \
                mock.patch('engine.run', boom):
            with self.assertRaisesRegex(RuntimeError, 'engine down'):
                self.execute({'operation': 'translate', 'pdf': str(self.source), 'outputDir': str(out)})
        self.assertEqual(list(out.iterdir()) if out.exists() else [], [])

    def test_cache_list_and_clear(self):
        identity = 'a' * 16
        folder = cache_ops.prepare_cache(self.data, identity, self.source)
        (folder / 'pdf2zh.v1.db').write_bytes(b'x' * 10)
        listed = self.execute({'operation': 'cacheList'})
        self.assertEqual([row['id'] for row in listed['entries']], [identity])
        cleared = self.execute({'operation': 'cacheClear', 'identity': identity})
        self.assertTrue(cleared['cleared'])
        self.assertFalse(folder.exists())
        self.assertTrue(self.source.exists())


if __name__ == '__main__':
    unittest.main()
