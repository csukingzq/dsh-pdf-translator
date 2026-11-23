"""Keep MinerU's formula glyphs as embedded PDF text for PDF2zh.

DocVortex 0.6.26 outlines every ZiaMath glyph. BabelDOC cannot attach an
outlined inline variable to a translated paragraph. Preserve the same glyph
IDs, font, positions and sizes, but emit text operators for real font glyphs.
Rules and synthetic stretchy glyphs retain the upstream vector renderer.
The patch is scoped to this worker's render call, never installed sources.
"""
from contextlib import contextmanager
import hashlib
from io import BytesIO
from xml.etree import ElementTree


@contextmanager
def text_formula_glyphs():
    from fontTools.ttLib import TTFont as FontToolsFont
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import ttfonts
    from reportlab.graphics.shapes import Group, String
    from ziafont.glyph import SimpleGlyph
    from docvortex.render._internal.pdf import formula
    from docvortex.render._internal.pdf.renderer import _PdfCanvas
    from reportlab.platypus import paragraph
    from reportlab.lib.rl_accel import fp_str
    from ziamath.nodes.moperator import Moperator
    from ziafont.fonttypes import BBox

    original_place = SimpleGlyph.place
    original_append = formula._append_svg_element
    original_cmap = ttfonts.makeToUnicodeCMap
    original_line = paragraph._putFragLine
    original_image = _PdfCanvas.drawImage
    original_operator_setup = Moperator._setup
    fonts = {}
    failures = []

    def operator_setup(node, **kwargs):
        original_operator_setup(node, **kwargs)
        # ZiaMath 0.13 excludes stretchy fences from its measuring pass by
        # leaving bbox.ymin=999 / ymax=-999. A scripted or nested fence then
        # uses that inverted box as real geometry, inflating the formula to
        # ~2000 pt. DocVortex fits it into its source box at sub-point size.
        # An excluded operator must instead have a neutral vertical extent.
        box = node.bbox
        if kwargs.get('nostretch') and box.ymax < box.ymin:
            node.bbox = BBox(box.xmin, box.xmax, 0.0, 0.0)

    def font_for(glyph):
        filename = str(glyph.font.info.filename)
        if filename not in fonts:
            font = FontToolsFont(filename)
            order = font.getGlyphOrder()
            name = 'DSHMinerUMath' + hashlib.sha256(filename.encode()).hexdigest()[:10]
            cmap = CmapSubtable.newSubtable(12)
            cmap.platformID, cmap.platEncID, cmap.language = 3, 10, 0
            cmap.cmap = dict(font.getBestCmap())
            cmap.cmap.update({0xF0000 + i: glyph_name for i, glyph_name in enumerate(order)})
            # Put our complete cmap first so ReportLab chooses it consistently.
            font['cmap'].tables = [cmap] + [t for t in font['cmap'].tables
                if (t.platformID, t.platEncID, t.language) != (3, 10, 0)]
            for name_id in (1, 4, 6):
                font['name'].setName(name, name_id, 3, 1, 0x409)
                font['name'].setName(name, name_id, 1, 0, 0)
            data = BytesIO()
            font.save(data)
            data.seek(0)
            pdfmetrics.registerFont(TTFont(name, data))
            fonts[filename] = name, len(order)
        return fonts[filename]

    def place(glyph, x, y, point_size):
        # Synthetic glyphs (e.g. an assembled tall bracket) have no source GID.
        if glyph.index < 0:
            return original_place(glyph, x, y, point_size)
        try:
            name, count = font_for(glyph)
        except Exception as exc:
            failures.append(str(exc))
            raise
        if glyph.index >= count:
            return original_place(glyph, x, y, point_size)
        chars = sorted(glyph.char, key=ord)
        char = chars[0] if chars else chr(0xF0000 + glyph.index)
        return ElementTree.Element('dsh-glyph', {'x': str(x), 'y': str(y),
            'size': str(point_size), 'font': name, 'text': char})

    def append(parent, element, *, inherited, node_counter, path_budget):
        if element.tag != 'dsh-glyph':
            return original_append(parent, element, inherited=inherited,
                                   node_counter=node_counter, path_budget=path_budget)
        node_counter[0] += 1
        if node_counter[0] > formula._MAX_SVG_NODES:
            raise formula.PdfFormulaError('Formula glyph limit exceeded')
        group = Group()
        # SVG's downward Y axis is inverted by the parent. Invert glyph text
        # again, leaving its baseline at ZiaMath's exact original coordinates.
        group.transform = (1, 0, 0, -1, float(element.get('x')), float(element.get('y')))
        text = String(0, 0, element.get('text'), fontName=element.get('font'),
                      fontSize=float(element.get('size')),
                      fillColor=formula._parse_color(element.get('fill', inherited.get('fill', 'black'))))
        group.add(text)
        parent.add(group)

    SimpleGlyph.place = place
    formula._append_svg_element = append
    def unicode_cmap(fontname, subset):
        result = original_cmap(fontname, subset)
        # ReportLab 5.1 formats astral characters as five hex digits, whereas
        # PDF ToUnicode requires UTF-16BE surrogate pairs.
        for i, code in enumerate(subset):
            if code > 0xFFFF:
                result = result.replace(f'<{i:02X}> <{code:04X}>',
                    f'<{i:02X}> <{chr(code).encode("utf-16-be").hex().upper()}>')
        return result
    ttfonts.makeToUnicodeCMap = unicode_cmap
    def put_line(cur_x, tx, *args, **kwargs):
        previous = getattr(tx._canvas, '_dsh_formula_tx', None)
        tx._canvas._dsh_formula_tx = tx
        try:
            return original_line(cur_x, tx, *args, **kwargs)
        finally:
            tx._canvas._dsh_formula_tx = previous

    def draw_image(canvas, image, *args, **kwargs):
        tx = getattr(canvas, '_dsh_formula_tx', None)
        if tx is None or not isinstance(image, formula.InlineFormulaImage):
            return original_image(canvas, image, *args, **kwargs)
        start = len(canvas._code)
        result = original_image(canvas, image, *args, **kwargs)
        drawing = canvas._code[start:]
        del canvas._code[start:]
        # ReportLab normally emits inline images before the entire paragraph's
        # buffered text. Interleave at this exact fragment instead, otherwise
        # PDF2zh sees all variables before the prose and moves them together.
        # q/Q in the vector drawing preserves text state; restore only the line
        # matrix before ReportLab's next relative setXPos command.
        tx._code.extend(['ET', *drawing, 'BT',
                         '1 0 0 1 %s Tm' % fp_str(tx._x0, tx.XtraState.cur_y)])
        return result

    paragraph._putFragLine = put_line
    _PdfCanvas.drawImage = draw_image
    Moperator._setup = operator_setup
    try:
        yield
        if failures:
            raise RuntimeError('MinerU 公式字体转换失败：' + failures[0])
    finally:
        SimpleGlyph.place = original_place
        formula._append_svg_element = original_append
        ttfonts.makeToUnicodeCMap = original_cmap
        paragraph._putFragLine = original_line
        _PdfCanvas.drawImage = original_image
        Moperator._setup = original_operator_setup
