import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cache_ops
import index


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_record_load_forget(self):
        index.record(self.data, {'identity': 'a' * 16, 'source': 'D:/x/a.pdf', 'name': 'a.pdf',
                                 'runDir': 'D:/out/a_1', 'bytes': 10, 'at': 1000})
        index.record(self.data, {'identity': 'a' * 16, 'source': 'D:/x/a.pdf', 'name': 'a.pdf',
                                 'runDir': 'D:/out/a_2', 'bytes': 20, 'at': 2000})
        rows = index.load(self.data)
        self.assertEqual(len(rows), 2)
        self.assertEqual(index.forget(self.data, 'a' * 16), 2)
        self.assertEqual(index.load(self.data), [])

    def test_record_replaces_same_run(self):
        for size in (10, 30):
            index.record(self.data, {'identity': 'b' * 16, 'runDir': 'D:/out/b', 'bytes': size})
        rows = index.load(self.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['bytes'], 30)

    def test_corrupt_registry_is_ignored(self):
        index._path(self.data).parent.mkdir(parents=True, exist_ok=True)
        index._path(self.data).write_text('{not json', 'utf-8')
        self.assertEqual(index.load(self.data), [])


class CacheOpsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / 'data'
        self.identity = 'c' * 16
        self.source = Path(self.temp.name) / 'paper.pdf'
        self.source.write_bytes(b'original')
        self.folder = cache_ops.prepare_cache(self.data, self.identity, self.source)
        (self.folder / 'pdf2zh.v1.db').write_bytes(b'x' * 100)

    def tearDown(self):
        self.temp.cleanup()

    def test_list_counts_cache_not_exports_or_legacy_registry(self):
        index.record(self.data, {'identity': 'd' * 16, 'name': 'legacy.pdf', 'bytes': 50000, 'runDir': 'D:/exports/legacy'})
        rows = cache_ops.cache_list(self.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], self.identity)
        self.assertEqual(rows[0]['name'], 'paper.pdf')
        self.assertEqual(rows[0]['bytes'], sum(p.stat().st_size for p in self.folder.iterdir()))
        self.assertEqual(rows[0]['blocked'], '')

    def test_clear_all_models_of_one_document_only(self):
        (self.folder / 'babeldoc.v1.db').write_bytes(b'model-2')
        other = cache_ops.prepare_cache(self.data, 'd' * 16, self.source)
        exported = self.data / 'outputs/translated.pdf'
        exported.parent.mkdir()
        exported.write_bytes(b'export')
        ocr = self.data / 'work/document-cache' / self.identity
        ocr.mkdir(parents=True)
        (ocr / 'translated.md').write_text('OCR', 'utf-8')
        with mock.patch.object(cache_ops, 'engine_cache_dir') as shared:
            self.assertTrue(cache_ops.clear_cache(self.data, self.identity)['cleared'])
            shared.assert_not_called()
        self.assertFalse(self.folder.exists())
        self.assertTrue(other.exists())
        self.assertEqual(exported.read_bytes(), b'export')
        self.assertEqual(self.source.read_bytes(), b'original')
        self.assertTrue((ocr / 'translated.md').exists())
        self.assertFalse(cache_ops.clear_cache(self.data, self.identity)['cleared'])

    def test_rejects_shared_root_and_traversal(self):
        for identity in ['engine', '..', '../' + self.identity, '']:
            with self.assertRaises(ValueError):
                cache_ops.clear_cache(self.data, identity)
        self.assertTrue(self.folder.exists())

    def test_nested_links_protect_the_whole_document(self):
        original = cache_ops.safe_tree
        with mock.patch.object(cache_ops, 'safe_tree', side_effect=ValueError('缓存含链接')):
            self.assertTrue(cache_ops.cache_list(self.data)[0]['blocked'])
            with self.assertRaises(ValueError):
                cache_ops.clear_cache(self.data, self.identity)
            with self.assertRaises(ValueError):
                cache_ops.prepare_cache(self.data, self.identity, self.source)
        original(cache_ops.root_path(self.data), self.folder)
        self.assertTrue(self.folder.exists())

    def test_root_link_is_rejected(self):
        root = cache_ops.root_path(self.data)
        original = Path.is_symlink
        with mock.patch.object(Path, 'is_symlink', lambda p: p == root or original(p)):
            with self.assertRaises(ValueError):
                cache_ops.cache_list(self.data)
            with self.assertRaises(ValueError):
                cache_ops.clear_cache(self.data, self.identity)


if __name__ == '__main__':
    unittest.main()
