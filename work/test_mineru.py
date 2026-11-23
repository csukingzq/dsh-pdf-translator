import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
import cache_ops
import mineru_cli


class MineruPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows CI may expose TEMP through an 8.3 alias (RUNNER~1).
        # Production inspection resolves it to the canonical long path.
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'book.pdf'
        with pymupdf.open() as doc:
            for n in range(1, 6):
                page = doc.new_page()
                page.insert_text((50, 50), f'Original page {n}')
            doc.save(self.source)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'base_url':'https://example.invalid/v1', 'model':'text', 'api_key':'secret'}))
        self.args = {'pdf':str(self.source), 'pages':'2-4', 'outputDir':str(self.root / 'outputs')}
        self.worker_calls = 0

    def worker(self, source, target, data_dir, progress):
        self.worker_calls += 1
        with pymupdf.open(source) as doc:
            self.assertEqual(len(doc), 3)
            self.assertIn('Original page 2', doc[0].get_text())
            self.assertIn('Original page 4', doc[2].get_text())
            doc.save(target)

    def engine(self, request, progress):
        self.assertEqual(request['pages'], 'all')
        identity=hashlib.sha256(self.source.read_bytes()).hexdigest()[:16]
        self.assertEqual(Path(request['cache_dir']).name, identity)
        folder=Path(request['engine_dir'])
        folder.mkdir()
        with pymupdf.open(request['input']) as doc:
            self.assertEqual(len(doc), 3)
            doc.save(folder / 'mono.pdf')
            doc.save(folder / 'dual.pdf')
        if progress:
            progress({'phase':'translating', 'percent':50})
        return {'mono':str(folder/'mono.pdf'), 'dual':str(folder/'dual.pdf')}

    def run_pipeline(self, **kwargs):
        return mineru_cli.translate(self.args, self.root, self.config, **kwargs)

    @patch('cli.engine_version', return_value='2.10.2')
    def test_selection_exports_and_recognition_cache(self, _):
        import engine
        progress=[]
        original=self.source.read_bytes()
        with patch.object(mineru_cli, 'run_worker', side_effect=self.worker), patch.object(engine, 'run', side_effect=self.engine):
            first=self.run_pipeline(on_progress=progress.append)
            second=self.run_pipeline()
        self.assertEqual(first['selected_pages'], [2,3,4])
        self.assertEqual(first['source'], str(self.source))
        self.assertEqual(first['pages'], 3)
        self.assertFalse(first['recognition_cached'])
        self.assertTrue(second['recognition_cached'])
        self.assertEqual(self.worker_calls, 1)
        self.assertEqual(self.source.read_bytes(), original)
        exported=list(Path(first['output_dir']).iterdir())
        self.assertEqual(len(exported), 3)
        for name in ('mineru','output','dual'):
            with pymupdf.open(first[name]) as doc:
                self.assertEqual(len(doc), 3)
        self.assertEqual([p['percent'] for p in progress], [5,50,75,100])
        rows=cache_ops.cache_list(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], str(self.source))
        self.assertEqual(rows[0]['engine'], 'mineru')
        cache_ops.clear_cache(self.root, rows[0]['id'])
        self.assertTrue(Path(first['mineru']).is_file())
        self.assertFalse(cache_ops.cache_list(self.root))

    @patch('cli.engine_version', return_value='2.10.2')
    def test_standard_does_not_reuse_basic_recognition(self, _):
        import engine
        with patch.object(mineru_cli, 'run_worker', side_effect=self.worker), patch.object(engine, 'run', side_effect=self.engine):
            with patch.object(mineru_cli, 'TIER', 'basic'):
                self.run_pipeline()
            standard=self.run_pipeline()
            again=self.run_pipeline()
        self.assertEqual(standard['mineru_tier'], 'standard')
        self.assertFalse(standard['recognition_cached'])
        self.assertTrue(again['recognition_cached'])
        self.assertEqual(self.worker_calls, 2)

    @patch('cli.engine_version', return_value='2.10.2')
    def test_failed_translation_retains_recognition_and_retry_reuses_it(self, _):
        import engine
        with patch.object(mineru_cli, 'run_worker', side_effect=self.worker), patch.object(engine, 'run', side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(RuntimeError, '识别 PDF 已保留'):
                self.run_pipeline()
        files=list((self.root/'outputs').rglob('*.*'))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.endswith('-mineru.pdf'))
        with patch.object(mineru_cli, 'run_worker', side_effect=AssertionError('cache miss')), patch.object(engine, 'run', side_effect=self.engine):
            self.assertTrue(self.run_pipeline()['recognition_cached'])

    @patch('cli.engine_version', return_value='2.10.2')
    def test_invalid_recognition_never_calls_translator(self, _):
        import engine
        def invalid(source,target,*args):
            Path(target).write_bytes(b'not a PDF')
        with patch.object(mineru_cli, 'run_worker', side_effect=invalid), patch.object(engine,'run') as translator:
            with self.assertRaisesRegex(RuntimeError, '有效 PDF'):
                self.run_pipeline()
            translator.assert_not_called()


if __name__ == '__main__':
    unittest.main()
