"""Run in the isolated MinerU environment; ordinary bridge CI can skip these."""
import contextlib
from io import BytesIO
import unittest
import unicodedata
from importlib.util import find_spec

AVAILABLE = find_spec('docvortex') is not None


@unittest.skipUnless(AVAILABLE, 'requires isolated MinerU environment')
class MineruMathTests(unittest.TestCase):
    def render(self, patched):
        from reportlab.pdfgen.canvas import Canvas
        from docvortex.render._internal.pdf.formula import FormulaRenderer
        from mineru_math import text_formula_glyphs
        stream=BytesIO()
        canvas=Canvas(stream,pagesize=(600,250))
        samples=[r'n\geq0', r'\frac{1}{4-\frac{1}{4}}=\frac{1}{3}',
                 r'\sum_{k=2}^{\infty}2^{-k}', r'\sqrt{a^2+b^2}',
                 r'\left(\frac{a}{b}\right)^{n}', r'\alpha+\beta=\gamma']
        with text_formula_glyphs() if patched else contextlib.nullcontext():
            renderer=FormulaRenderer()
            for i, latex in enumerate(samples):
                vector=renderer.render(latex,inline=True,font_size=14)
                vector.drawing.drawOn(canvas,20+(i%3)*190,180-(i//3)*95)
            canvas.save()
        return stream.getvalue()

    def test_same_math_geometry_and_visible_glyphs_with_extractable_text(self):
        import pypdfium2
        from PIL import Image, ImageChops, ImageStat
        from pypdf import PdfReader
        original=self.render(False)
        patched=self.render(True)
        text=unicodedata.normalize('NFKC',PdfReader(BytesIO(patched)).pages[0].extract_text())
        self.assertIn('n',text)
        self.assertIn('≥',text)
        self.assertIn('α',text)
        fonts=PdfReader(BytesIO(patched)).pages[0]['/Resources']['/Font']
        self.assertTrue(any('DSHMinerUMath' in str(f.get_object().get('/BaseFont')) for f in fonts.values()))
        images=[]
        for data in (original,patched):
            with pypdfium2.PdfDocument(data) as doc:
                images.append(doc[0].render(scale=3).to_pil().convert('RGB'))
        diff=ImageChops.difference(*images)
        # Text hinting can change edge pixels, not glyph shapes or positions.
        self.assertLess(sum(ImageStat.Stat(diff).mean)/3,1.0)
        a=ImageChops.difference(images[0],Image.new('RGB',images[0].size,'white')).getbbox()
        b=ImageChops.difference(images[1],Image.new('RGB',images[1].size,'white')).getbbox()
        self.assertTrue(all(abs(x-y)<=2 for x,y in zip(a,b)), (a,b))

    def test_scoped_patch_restores_upstream_on_failure(self):
        from ziafont.glyph import SimpleGlyph
        from docvortex.render._internal.pdf import formula
        from mineru_math import text_formula_glyphs
        original=(SimpleGlyph.place,formula._append_svg_element)
        with self.assertRaises(RuntimeError):
            with text_formula_glyphs():
                raise RuntimeError('test')
        self.assertEqual((SimpleGlyph.place,formula._append_svg_element),original)

    def test_inline_formula_reading_order_and_multiline_geometry(self):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        from docvortex.render._internal.pdf.inline import _PdfParaParser
        from docvortex.render._internal.pdf.formula import FormulaRenderer, InlineFormulaImage
        from docvortex.render._internal.pdf.renderer import _PdfCanvas
        from mineru_math import text_formula_glyphs
        from pypdf import PdfReader
        import pypdfium2
        from PIL import ImageChops, ImageStat
        rendered=[]
        for patched in (False,True):
            data=BytesIO()
            with text_formula_glyphs() if patched else contextlib.nullcontext():
                canvas=_PdfCanvas(data,pagesize=(350,220),document_title='test')
                renderer=FormulaRenderer()
                formulas={key:InlineFormulaImage(renderer.render(latex,inline=True,font_size=12))
                          for key,latex in [('f',r'n\geq0'),('g',r'b_i')]}
                style=ParagraphStyle('test',fontName='Helvetica',fontSize=12,leading=18)
                parser=_PdfParaParser(formulas)
                style,frags,_=parser.parse('Before <img src="f"/> after the first formula. '
                    'Some words make this paragraph wrap onto another line. '
                    'Binary digits <img src="g"/> are zero or one.',style)
                para=Paragraph('',style,frags=frags)
                para.wrap(240,200)
                para.drawOn(canvas,30,100)
                canvas.save()
            rendered.append(data.getvalue())
        text=unicodedata.normalize('NFKC',PdfReader(BytesIO(rendered[1])).pages[0].extract_text())
        self.assertLess(text.index('Before'),text.index('n'))
        self.assertLess(text.index('n'),text.index('after'))
        self.assertLess(text.index('Binary'),text.index('b',text.index('Binary')))
        images=[]
        for pdf in rendered:
            with pypdfium2.PdfDocument(pdf) as doc:
                images.append(doc[0].render(scale=3).to_pil().convert('RGB'))
        self.assertLess(sum(ImageStat.Stat(ImageChops.difference(*images)).mean)/3,1.0)


if __name__ == '__main__':
    unittest.main()
