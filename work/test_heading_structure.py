import copy
import tempfile
import unittest
from pathlib import Path

import pymupdf

from heading_structure import normalize_headings, numbered_level


def block(text, bbox=None):
    return {'kind': 'heading', 'markdown': text, 'bbox': bbox or [.1, .1, .9, .15]}


class HeadingStructureTests(unittest.TestCase):
    def test_cross_page_numbering_and_body_labels(self):
        pages = [{'page': 1, 'blocks': [block('# 第3章 数值积分'), block('## 3.1 微分')]},
                 {'page': 7, 'blocks': [block('# 3.2 积分'), block('## 3.2.1 梯形法')]},
                 {'page': 8, 'blocks': [block('# 定理 3.2'), block('### 3.2 节'),
                                       block('# 3(c) 的图（N=50）'), block('### 3.1.2 例题')]}]
        normalize_headings(pages)
        self.assertEqual([b['markdown'] for b in pages[1]['blocks']], ['## 3.2 积分', '### 3.2.1 梯形法'])
        self.assertEqual([b['kind'] for b in pages[2]['blocks']], ['paragraph'] * 3 + ['heading'])
        original = copy.deepcopy(pages)
        self.assertEqual(normalize_headings(pages), [])
        self.assertEqual(original, pages)

    def test_numbering_does_not_confuse_chapter_exercises_or_decimals(self):
        self.assertEqual(numbered_level('第3章 数值积分'), 1)
        self.assertIsNone(numbered_level('第3章习题与上机作业'))
        self.assertIsNone(numbered_level('3(c) 的图'))
        self.assertIsNone(numbered_level('3.14'))

    def test_bookmarks_match_nearby_headings_one_to_one(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.pdf'
            with pymupdf.open() as doc:
                sheet = doc.new_page(width=400, height=600)
                sheet.insert_text((40, 80), 'Exercises', fontsize=14, fontname='tibo')
                sheet.insert_text((40, 140), 'Selected solutions', fontsize=14, fontname='tibo')
                sheet.insert_text((40, 300), 'Comment', fontsize=10, fontname='tiit')
                sheet.insert_text((40, 330), 'Regular body text ' * 4, fontsize=10)
                doc.set_toc([[1, 'Chapter', 1, 25], [2, 'Exercises', 1, 65],
                             [2, 'Selected solutions', 1, 125]])
                doc.save(source)
            pages = [{'page': 1, 'blocks': [block('# 习题', [.08, .10, .9, .15]),
                                          block('### 选解', [.08, .20, .9, .25]),
                                          block('# 说明', [.08, .47, .9, .52])]}]
            normalize_headings(pages, source)
            self.assertEqual([b['markdown'] for b in pages[0]['blocks']], ['## 习题', '## 选解', '**说明**'])

    def test_scanned_unknown_headings_and_source_images_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'scan.pdf'
            with pymupdf.open() as doc:
                doc.new_page()
                doc.save(source)
            image = block('# 3.2 不可识别'); image['status'] = 'source_image'
            pages = [{'page': 1, 'blocks': [block('#### 未编号标题'), image]}]
            original = copy.deepcopy(pages)
            normalize_headings(pages, source)
            self.assertEqual(pages, original)


if __name__ == '__main__':
    unittest.main()
