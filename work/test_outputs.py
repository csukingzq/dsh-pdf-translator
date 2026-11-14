import json
import os
import tempfile
import unittest
from pathlib import Path

import outputs


class OutputTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / '有限元特征值问题研究.pdf'
        self.source.write_bytes(b'%PDF-1.4 source')

    def tearDown(self):
        self.temp.cleanup()

    def test_safe_stem(self):
        self.assertEqual(outputs.safe_stem('a/b:c*'), 'a_b_c_')
        self.assertEqual(len(outputs.safe_stem('x' * 200)), 48)
        self.assertEqual(outputs.safe_stem('  '), 'document')

    def test_prepare_copies_short_input(self):
        out = self.root / 'out'
        prepared = outputs.prepare(out, self.source)
        self.assertTrue(prepared['run_dir'].is_dir())
        self.assertEqual(prepared['input'].name, '有限元特征值问题研究.pdf')
        self.assertEqual(prepared['input'].read_bytes(), self.source.read_bytes())
        self.assertEqual(prepared['engine_dir'], prepared['run_dir'] / '_engine')
        self.assertTrue(prepared['run_dir'].name.startswith('有限元特征值问题研究_'))

    def test_collect_moves_files_and_writes_report(self):
        prepared = outputs.prepare(self.root / 'out', self.source)
        engine = prepared['engine_dir']
        engine.mkdir(parents=True)
        mono = engine / 'src.no_watermark.zh-CN.mono.pdf'
        dual = engine / 'src.no_watermark.zh-CN.dual.pdf'
        mono.write_bytes(b'mono')
        dual.write_bytes(b'dual')
        result = outputs.collect(prepared, {
            'mono': str(mono), 'dual': str(dual), 'seconds': 12.5, 'version': '2.10.2',
            'lang_in': 'en', 'lang_out': 'zh-CN', 'token_usage': {'total': 10},
        }, {'source': str(self.source), 'pages': 'all', 'selected_pages': 1,
            'model': 'text-model', 'base_url': 'https://api.example.com/v1',
            'diagnostics': {'mathFonts': ['AdvMacMthSyN'], 'formulaProtected': True, 'suspiciousChars': 0}})
        run = prepared['run_dir']
        self.assertTrue(Path(result['output']).is_file())
        self.assertTrue(Path(result['dual']).is_file())
        self.assertEqual(Path(result['output']).name, '有限元特征值问题研究-mono.pdf')
        self.assertFalse(engine.exists())
        self.assertFalse(prepared['input'].exists())
        report = json.loads(Path(result['report']).read_text('utf-8'))
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['engine'], 'pdf2zh-next')
        self.assertEqual(report['langOut'], 'zh-CN')
        self.assertEqual(report['model'], 'text-model')
        self.assertEqual(report['diagnostics']['mathFonts'], ['AdvMacMthSyN'])
        self.assertTrue(report['diagnostics']['formulaProtected'])
        self.assertGreater(result['bytes'], 0)
        self.assertEqual(Path(result['report']).parent, run)

    def test_collect_tolerates_missing_dual(self):
        prepared = outputs.prepare(self.root / 'out', self.source)
        prepared['engine_dir'].mkdir(parents=True)
        mono = prepared['engine_dir'] / 'mono.pdf'
        mono.write_bytes(b'mono')
        result = outputs.collect(prepared, {'mono': str(mono), 'dual': None}, {'source': str(self.source)})
        self.assertTrue(result['output'])
        self.assertEqual(result['dual'], '')

    def test_collect_fails_without_pdfs(self):
        prepared = outputs.prepare(self.root / 'out', self.source)
        with self.assertRaisesRegex(RuntimeError, '未生成 PDF'):
            outputs.collect(prepared, {'mono': None, 'dual': None}, {'source': str(self.source)})

    def test_prepare_rejects_unwritable_output(self):
        blocker = self.root / 'file.txt'
        blocker.write_text('x', 'utf-8')
        with self.assertRaises(OSError):
            outputs.prepare(blocker, self.source)


if __name__ == '__main__':
    unittest.main()
