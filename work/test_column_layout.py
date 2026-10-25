import tempfile
import unittest
from pathlib import Path

import pymupdf

import column_layout

WORDS = ('dense reconstruction from uncalibrated images without camera poses or intrinsics '
         'is recovered jointly by a single network').split()


def fit_line(width, offset):
    """A full-width line of text, rotated so consecutive lines differ."""
    words, text = [], ''
    index = offset
    while True:
        candidate = (text+' '+WORDS[index % len(WORDS)]).strip()
        if pymupdf.get_text_length(candidate, fontname='helv', fontsize=10) > width-2:
            return text
        text, index = candidate, index+1
        words.append(text)


def make_pdf(path, columns):
    """Write a page whose text sits in the given number of equal columns."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=792)
        margin, gutter = 50, 32
        width = (612-2*margin-(columns-1)*gutter)/columns
        for index in range(columns):
            left = margin+index*(width+gutter)
            for line in range(40):
                page.insert_text((left, 70+line*15), fit_line(width, line*3+index*7),
                                 fontsize=10, fontname='helv')
        doc.save(path)
    return Path(path)


class ColumnLayoutTests(unittest.TestCase):
    def test_two_column_page_reports_gutter_between_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            grid = column_layout.detect(make_pdf(Path(folder)/'two.pdf', 2))
            self.assertEqual(grid['columns'], 2)
            start, end = grid['gutters'][0]
            # 290/612=0.474 to 322/612=0.526
            self.assertAlmostEqual(start, 0.474, delta=0.02)
            self.assertAlmostEqual(end, 0.526, delta=0.02)

    def test_three_column_page_reports_two_gutters(self):
        with tempfile.TemporaryDirectory() as folder:
            grid = column_layout.detect(make_pdf(Path(folder)/'three.pdf', 3))
            self.assertEqual(grid['columns'], 3)
            self.assertEqual(len(grid['gutters']), 2)
            self.assertLess(grid['gutters'][0][1], grid['gutters'][1][0])

    def test_single_column_document_never_marks_spanning(self):
        with tempfile.TemporaryDirectory() as folder:
            grid = column_layout.detect(make_pdf(Path(folder)/'one.pdf', 1))
            self.assertEqual(grid['columns'], 1)
            self.assertEqual(grid['gutters'], [])
            self.assertTrue(column_layout.spans([0.1, 0.5, 0.5, 0.6], grid))

    def test_block_spanning_is_decided_per_box(self):
        grid = {'columns': 2, 'gutters': [[0.47, 0.50]]}
        self.assertFalse(column_layout.spans([0.09, 0.57, 0.48, 0.90], grid))   # left column, sloppy right edge
        self.assertFalse(column_layout.spans([0.51, 0.57, 0.91, 0.66], grid))   # right column
        self.assertTrue(column_layout.spans([0.27, 0.12, 0.74, 0.17], grid))    # centred title
        self.assertTrue(column_layout.spans([0.09, 0.25, 0.91, 0.47], grid))    # wide figure
        self.assertTrue(column_layout.spans([0.30, 0.50, 0.70, 0.60], grid))    # wide table

    def test_page_without_text_layer_falls_back_to_block_boxes(self):
        with pymupdf.open() as doc:
            doc.new_page(width=612, height=792)
            page = doc[0]
            blocks = ([{'bbox':[0.08, 0.10, 0.47, 0.90]}] * 12
                      + [{'bbox':[0.50, 0.10, 0.91, 0.90]}] * 12)
            grid = column_layout.page_grid(page, blocks)
            self.assertEqual(grid['columns'], 2)

    def test_title_page_does_not_outvote_body_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'mixed.pdf'
            with pymupdf.open() as doc:
                title = doc.new_page(width=612, height=792)
                title.insert_text((50, 100), ' '.join(WORDS), fontsize=18, fontname='helv')
                for _ in range(3):
                    page = doc.new_page(width=612, height=792)
                    for left in (50, 322):
                        for line in range(40):
                            page.insert_text((left, 70+line*15), fit_line(240, line*3),
                                             fontsize=10, fontname='helv')
                doc.save(path)
            grid = column_layout.detect(path)
            self.assertEqual(grid['columns'], 2)
            self.assertEqual(grid['pages'][1], 1)


if __name__ == '__main__':
    unittest.main()
