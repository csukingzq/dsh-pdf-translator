import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ContentStream, DecodedStreamObject, DictionaryObject,
                           NameObject)

from mt2math import has_mt2, isolate_shared_fonts, protect_operators, raw_bytes


def shows(ops):
    """Flatten text shows without losing TJ positioning numbers or text bytes."""
    result = []
    for args, op in ops:
        if op in (b'Tj', b'TJ'):
            values = args[:1] if op == b'Tj' else args[0]
            for item in values:
                item = raw_bytes(item) if isinstance(item, (str, bytes)) else item
                if isinstance(item, bytes) and result and isinstance(result[-1], bytes):
                    result[-1] += item
                else:
                    result.append(item)
    return result


class OperatorTest(unittest.TestCase):
    def test_math_gate(self):
        self.assertTrue(has_mt2(['ABCDEF+MT2MIT']))
        self.assertFalse(has_mt2(['Times-Roman', 'MT2Text', 'OtherMT2MIT']))

    def test_operator_aliases_preserve_prose_bytes_kerning_and_unselected_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'operators.pdf'
            writer = PdfWriter()
            fonts = DictionaryObject()
            # Structural fixture: font programs are shared opaque streams.
            program = DecodedStreamObject()
            program.set_data(b'font fixture')
            descriptor = writer._add_object(DictionaryObject({
                NameObject('/FontFile3'): writer._add_object(program)}))
            for key, name in [('R', 'Times-Roman'), ('I', 'Times-Italic'), ('M', 'MT2MIT')]:
                fonts[NameObject('/' + key)] = writer._add_object(DictionaryObject({
                    NameObject('/Type'): NameObject('/Font'),
                    NameObject('/Subtype'): NameObject('/Type1'),
                    NameObject('/BaseFont'): NameObject('/' + name),
                    NameObject('/Encoding'): NameObject('/MacRomanEncoding'),
                    NameObject('/FontDescriptor'): descriptor}))
            resources = writer._add_object(DictionaryObject({NameObject('/Font'): fonts}))
            data = (b'BT /R 10 Tf (cos) Tj /M 10 Tf (x/) Tj '
                    b'/R 10 Tf [(,where) -250 (\337) 12] TJ /M 10 Tf (.x/) Tj '
                    b'/R 10 Tf (,\337) Tj /M 10 Tf (.x/) Tj '
                    b'/R 10 Tf (floating prose) Tj /M 10 Tf (x) Tj '
                    b'/R 10 Tf (\337oating) Tj /M 10 Tf (.x/) Tj '
                    b'/I 10 Tf (x) Tj /M 10 Tf (C1) Tj '
                    b'/I 10 Tf (Hint) Tj /M 10 Tf (x) Tj '
                    b'/R 10 Tf (sin) Tj ET BT (ordinary text) Tj ET')
            content = DecodedStreamObject()
            content.set_data(data)
            for _ in range(2):
                page = writer.add_blank_page(300, 400)
                page[NameObject('/Resources')] = resources
                page[NameObject('/Contents')] = writer._add_object(content)
            writer.write(path)
            writer.close()
            with PdfReader(path) as before:
                original = shows(ContentStream(before.pages[0].get_contents(), before).operations)
            self.assertEqual(protect_operators(path, [0]), 4)
            with PdfReader(path) as after:
                ops = ContentStream(after.pages[0].get_contents(), after).operations
                self.assertEqual(shows(ops), original)
                self.assertEqual(after.pages[1].get_contents().get_data(), data)
                self.assertEqual(len(after.pages[1]['/Resources']['/Font']), 3)
                current = None
                protected, ordinary = [], []
                for args, op in ops:
                    if op == b'Tf':
                        current = str(args[0])
                    elif op in (b'Tj', b'TJ'):
                        values = args[:1] if op == b'Tj' else args[0]
                        text = b''.join(raw_bytes(v) for v in values)
                        (protected if current.startswith('/DSHMathOperator') else ordinary).append(text)
                self.assertEqual(protected, [b'cos', b'\xdf', b'\xdf', b'x'])
                self.assertIn(b'floating prose', ordinary)
                self.assertIn(b'\xdfoating', ordinary)
                self.assertIn(b'Hint', ordinary)
                self.assertIn(b'ordinary text', ordinary)
            before = path.read_bytes()
            self.assertEqual(protect_operators(path, [0]), 0)
            self.assertEqual(path.read_bytes(), before)
            # Font dictionaries shared across pages lose descent metadata in
            # BabelDOC's parser. Isolate references without changing glyphs.
            self.assertEqual(isolate_shared_fonts(path, [0]), 3)
            with PdfReader(path) as after:
                first = after.pages[0]['/Resources']['/Font']
                second = after.pages[1]['/Resources']['/Font']
                for key in ('/R', '/I', '/M'):
                    self.assertNotEqual(first[key].indirect_reference, second[key].indirect_reference)
                    self.assertEqual(first[key], second[key])
                self.assertEqual(after.pages[1].get_contents().get_data(), data)
                self.assertEqual(shows(ContentStream(after.pages[0].get_contents(), after).operations), original)
            before = path.read_bytes()
            self.assertEqual(isolate_shared_fonts(path, [0]), 0)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
