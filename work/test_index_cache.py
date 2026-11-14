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
        self.engine = Path(self.temp.name) / '.cache' / 'babeldoc'
        self.engine.mkdir(parents=True)
        (self.engine / 'cache.v1.db').write_bytes(b'x' * 100)
        self.patch = mock.patch.object(cache_ops, 'engine_cache_dir', return_value=self.engine)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_list_reports_documents_and_engine(self):
        index.record(self.data, {'identity': 'c' * 16, 'source': 'D:/x/paper.pdf', 'name': 'paper.pdf',
                                 'runDir': 'D:/out/paper', 'bytes': 500, 'at': 5000})
        rows = cache_ops.cache_list(self.data)
        by_id = {row['id']: row for row in rows}
        self.assertIn('engine', by_id)
        self.assertEqual(by_id['engine']['bytes'], 100)
        self.assertEqual(by_id['c' * 16]['name'], 'paper.pdf')
        self.assertEqual(by_id['c' * 16]['bytes'], 500)
        self.assertEqual(by_id['engine']['blocked'], '')

    def test_clear_engine_cache(self):
        index.record(self.data, {'identity': 'd' * 16, 'runDir': 'D:/out/d', 'bytes': 1})
        outcome = cache_ops.clear_cache(self.data, 'engine')
        self.assertTrue(outcome['cleared'])
        self.assertFalse(self.engine.exists())
        self.assertEqual(len(index.load(self.data)), 1)
        self.assertFalse(cache_ops.clear_cache(self.data, 'engine')['cleared'])

    def test_clear_document_only_forgets_metadata(self):
        index.record(self.data, {'identity': 'e' * 16, 'runDir': 'D:/out/e', 'bytes': 1})
        outcome = cache_ops.clear_cache(self.data, 'e' * 16)
        self.assertTrue(outcome['cleared'])
        self.assertFalse(outcome['shared'])
        self.assertEqual(index.load(self.data), [])
        self.assertTrue(self.engine.exists())

    def test_refuses_unexpected_engine_location(self):
        other = self.engine.parent / 'other'
        other.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(cache_ops, 'engine_cache_dir', return_value=other):
            with self.assertRaises(ValueError):
                cache_ops.clear_cache(self.data, 'engine')

    def test_tree_size_ignores_missing_directory(self):
        self.assertEqual(cache_ops.tree_size(self.engine / 'missing'), 0)


if __name__ == '__main__':
    unittest.main()
