import unittest

import pages


class PageIndicesTest(unittest.TestCase):
    def test_all_forms(self):
        for value in (None, '', 'all', 'ALL', '全部', ' all '):
            self.assertEqual(pages.page_indices(value, 3), [0, 1, 2])

    def test_ranges(self):
        self.assertEqual(pages.page_indices('1,3-4', 5), [0, 2, 3])
        self.assertEqual(pages.page_indices('3,1,2', 5), [0, 1, 2])
        self.assertEqual(pages.page_indices('2-2', 3), [1])

    def test_rejects_bad_input(self):
        for value in ('0', '9', '1-9', '-1', '3-1', '1,', '1,,2', '1.5', '1–5', 'all,1', 'x'):
            with self.assertRaises(ValueError, msg=value):
                pages.page_indices(value, 8)

    def test_normalize(self):
        self.assertEqual(pages.normalize('all', 3), 'all')
        self.assertEqual(pages.normalize('2', 3), '2')
        self.assertEqual(pages.normalize('1-2', 3), '1-2')
        self.assertEqual(pages.normalize('1,3', 3), '1,3')
        self.assertEqual(pages.normalize('1-2,3', 3), 'all')
        with self.assertRaises(ValueError):
            pages.normalize('all', 0)

    def test_collapse(self):
        self.assertEqual(pages.collapse([1, 2, 3, 5, 7, 8]), '1-3,5,7-8')
        with self.assertRaises(ValueError):
            pages.collapse([])


if __name__ == '__main__':
    unittest.main()
