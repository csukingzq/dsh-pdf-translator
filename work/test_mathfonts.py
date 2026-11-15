import base64
import re
import unittest
from types import SimpleNamespace

import mathfonts

PAGE_FONTS = [
    'DGMCEL+AdvPi1',
    'DGKPBI+AdvOTb92eb7df.I+20',
    'DGMBPK+AdvOTdd3b7348.I+03',
    'DGKNNF+AdvOT863180fb',
    'DGKPDI+AdvMacMthSyN',
    'DGKNNI+AdvOTb92eb7df.I',
    'DGKPDK+AdvMacMthIt',
    'DGKPBH+AdvEls-ent4',
    'DGKPEL+AdvP4C4E46',
    'DGKNOK+AdvOTb83ee1dd.B',
    'DGKNPL+AdvOT863180fb+20',
    'DGKNNH+AdvTA42',
]


class MathFontsTest(unittest.TestCase):
    def test_tex_roman_operators_do_not_protect_a_prose_font(self):
        def page(spans):
            return SimpleNamespace(get_text=lambda _: {'blocks': [{'lines': [{'spans': [
                {'font': font, 'text': text} for font, text in spans]}]}]})
        doc = [page([('CMR7', '1+exp('), ('CMR7', 'BN'), ('CMR7', 'tr'),
                     ('CMR10', 'xx'), ('Times', 'ordinary prose')]),
               page([('CMR10', 'This is ordinary prose'), ('CMR7', 'inf')])]
        self.assertEqual(mathfonts.tex_roman_math_fonts(doc, [0]), ['CMR10', 'CMR7'])
        self.assertEqual(mathfonts.tex_roman_math_fonts(doc, [0, 1]), ['CMR7'])
        self.assertEqual(mathfonts.tex_roman_math_fonts([page([('CMR7', 'if')])], [0]), [])
        self.assertEqual(mathfonts.tex_roman_math_fonts(doc, [0, 20]), [])

    def test_base_name(self):
        self.assertEqual(mathfonts.base_name('DGKPDI+AdvMacMthSyN'), 'AdvMacMthSyN')
        self.assertEqual(mathfonts.base_name('DGKPBI+AdvOTb92eb7df.I+20'), '20')
        self.assertEqual(mathfonts.base_name(''), '')
        encoded = 'BASE64:' + base64.b64encode(b'ABC+AdvP4C4E46').decode()
        self.assertEqual(mathfonts.base_name(encoded), 'AdvP4C4E46')
        self.assertEqual(mathfonts.base_name('BASE64:not-base64!'), '')

    def test_detect_real_page_fonts(self):
        self.assertEqual(
            mathfonts.detect(PAGE_FONTS),
            ['AdvPi1', 'AdvMacMthSyN', 'AdvMacMthIt', 'AdvEls-ent4', 'AdvP4C4E46'],
        )

    def test_body_fonts_are_not_math(self):
        self.assertEqual(mathfonts.detect(['AdvOT863180fb', 'AdvOTb92eb7df.I', 'AdvTA42', 'Arial']), [])

    def test_pattern_keeps_defaults_and_adds_families(self):
        pattern = mathfonts.formula_font_pattern(PAGE_FONTS)
        self.assertIsNotNone(pattern)
        for default in ('CM[^RB]', '(MS|XY|MT|BL|RM|EU|LA|RS)[A-Z]', 'LCIRCLE', 'TeX-', '.*Sym', '.*Math',
                        'AdvP4C4E74', 'AdvPSSym', 'AdvP4C4E59'):
            self.assertIn(default, pattern)
        for family in ('AdvMacMthSyN', 'AdvMacMthIt', 'AdvEls-ent4', 'AdvPi1', 'AdvP4C4E46'):
            self.assertTrue(re.match(pattern, family), family)
        self.assertFalse(re.match(pattern, 'AdvOT863180fb'))
        self.assertFalse(re.match(pattern, 'Arial'))

    def test_no_suspects_means_engine_default(self):
        self.assertIsNone(mathfonts.formula_font_pattern(['AdvOT863180fb']))
        self.assertIsNone(mathfonts.formula_font_pattern([]))

    def test_suspicious_chars(self):
        self.assertEqual(mathfonts.suspicious_chars('ﬃ ¼ ð Þ x'), 4)
        self.assertEqual(mathfonts.suspicious_chars('plain text'), 0)

    def test_diagnostics(self):
        info = mathfonts.diagnostics(PAGE_FONTS, 7)
        self.assertTrue(info['formulaProtected'])
        self.assertEqual(info['suspiciousChars'], 7)
        self.assertIn('AdvMacMthSyN', info['mathFonts'])


if __name__ == '__main__':
    unittest.main()
