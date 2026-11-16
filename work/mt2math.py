"""Keep roman operators next to MT2 glyphs inside the same formula.

Only font aliases on the disposable copy change; text bytes and positioning
stay identical. Whole prose runs are never assigned a mathematical font.
"""
import re
from pathlib import Path

from mathfonts import base_name

MT2 = re.compile(r'MT2(?:MI|SY|EX)[A-Z0-9]*$')
OPERATORS = {'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'sinh', 'cosh', 'tanh',
             'exp', 'log', 'ln', 'lim', 'min', 'max', 'sup', 'inf', 'det',
             'dim', 'ker', 'cond', 'fl', 'eps', 'e', 'i'}
BOUNDARIES = (b'Tf', b'ET', b'BT', b'q', b'Q', b'Do')


def isolate_shared_fonts(path, indices):
    """Avoid BabelDOC 0.7.1 losing font descents on subsequent MT2 pages.

    Clone only the small font dictionaries. Embedded programs, descriptors,
    encodings and glyph positions remain identical; unselected pages retain
    their resources. Already page-local font dictionaries need no changes.
    """
    from collections import Counter
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject

    path = Path(path)
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)
    changed = 0
    try:
        usage = Counter()
        for page in writer.pages:
            resources = page['/Resources'] if '/Resources' in page else {}
            fonts = resources['/Font'] if '/Font' in resources else {}
            usage.update(id(f.get_object()) for f in fonts.values())
        for index in indices:
            page = writer.pages[index]
            resources = page['/Resources'] if '/Resources' in page else {}
            fonts = resources['/Font'] if '/Font' in resources else {}
            if not has_mt2(str(f.get_object().get('/BaseFont', '')).lstrip('/') for f in fonts.values()):
                continue
            shared = [k for k, f in fonts.items() if usage[id(f.get_object())] > 1]
            if not shared:
                continue
            resources, fonts = DictionaryObject(resources), DictionaryObject(fonts)
            resources[NameObject('/Font')] = fonts
            page[NameObject('/Resources')] = resources
            for key in shared:
                fonts[key] = writer._add_object(DictionaryObject(fonts[key].get_object()))
                changed += 1
        if changed:
            temp = path.with_suffix('.fonts.tmp.pdf')
            try:
                writer.write(temp)
                reader.close()
                writer.close()
                temp.replace(path)
            finally:
                if temp.exists():
                    temp.unlink()
    finally:
        reader.close()
        writer.close()
    return changed


def has_mt2(fonts):
    return any(MT2.fullmatch(base_name(name)) for name in fonts)


def raw_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        try:
            return value.original_bytes
        except AttributeError:
            return value.encode('latin1')
    return b''


def run_bytes(ops):
    data = b''
    for args, op in ops:
        if op in (b"'", b'"'):
            return None
        values = args[:1] if op == b'Tj' else args[0] if op == b'TJ' else []
        data += b''.join(raw_bytes(v) for v in values)
    return data


def protect_operators(path, indices):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (ArrayObject, ByteStringObject, ContentStream,
                               DictionaryObject, NameObject)

    path = Path(path)
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)
    changed = 0
    try:
        for index in indices:
            page = writer.pages[index]
            resources = page.get('/Resources')
            if resources is None:
                continue
            resources = resources.get_object()
            fonts = resources.get('/Font')
            if fonts is None:
                continue
            fonts = fonts.get_object()
            names = {key: base_name(str(ref.get_object().get('/BaseFont', '')).lstrip('/'))
                     for key, ref in fonts.items()}
            math_ids = {key for key, name in names.items() if MT2.fullmatch(name)}
            if not math_ids:
                continue
            resources, fonts = DictionaryObject(resources), DictionaryObject(fonts)
            resources[NameObject('/Font')] = fonts
            page[NameObject('/Resources')] = resources
            content = ContentStream(page.get_contents(), writer)
            ops = content.operations
            aliases, replacements = {}, {}

            def alias(original):
                if original not in aliases:
                    key = NameObject('/DSHMathOperator' + str(len(aliases)))
                    while key in fonts:
                        key = NameObject(str(key) + '_')
                    font = DictionaryObject(fonts[original].get_object())
                    font[NameObject('/BaseFont')] = NameObject(f'/DSHMathOperator-{index}-{len(aliases)}')
                    if font.get('/FontDescriptor') is not None:
                        descriptor = DictionaryObject(font['/FontDescriptor'].get_object())
                        descriptor[NameObject('/FontName')] = font['/BaseFont']
                        font[NameObject('/FontDescriptor')] = writer._add_object(descriptor)
                    fonts[key] = writer._add_object(font)
                    aliases[original] = key
                return aliases[original]

            for pos, (args, op) in enumerate(ops):
                if op != b'Tf' or names.get(args[0]) not in ('Times-Roman', 'Times-Italic'):
                    continue
                end = pos + 1
                while end < len(ops) and ops[end][1] not in BOUNDARIES:
                    end += 1
                # Require a neighbouring MT2 run. Font resets are preserved.
                if end == len(ops) or ops[end][1] != b'Tf' or ops[end][0][0] not in math_ids:
                    continue
                font = fonts[args[0]].get_object()
                descriptor = font.get('/FontDescriptor')
                descriptor = descriptor.get_object() if descriptor is not None else {}
                if not any(key in descriptor for key in ('/FontFile', '/FontFile2', '/FontFile3')):
                    # Renaming an unembedded standard font could change the
                    # viewer's fallback face. Only alias embedded programs.
                    continue
                encoding = font.get('/Encoding', '/StandardEncoding')
                if font.get('/ToUnicode') is not None or encoding not in (
                        '/MacRomanEncoding', '/WinAnsiEncoding', '/StandardEncoding'):
                    continue
                data = run_bytes(ops[pos + 1:end])
                if data is None:
                    continue
                codec = 'mac_roman' if encoding == '/MacRomanEncoding' else 'cp1252' if encoding == '/WinAnsiEncoding' else 'ascii'
                try:
                    text = data.decode(codec).replace('\ufb02', 'fl').strip()
                except UnicodeError:
                    continue
                whole = (text in OPERATORS if names[args[0]] == 'Times-Roman'
                         else bool(re.fullmatch('[A-Za-z]', text)))
                if whole:
                    replacements[pos] = [([alias(args[0]), args[1]], b'Tf')]
                    changed += 1
                    continue
                # MacRoman's fl ligature often ends a prose run ("where fl(").
                # Split just that terminal glyph; preserve prose and TJ kerning.
                if encoding != '/MacRomanEncoding' or not data.endswith(b'\xdf'):
                    continue
                next_end = end + 1
                while next_end < len(ops) and ops[next_end][1] not in BOUNDARIES:
                    next_end += 1
                following = run_bytes(ops[end + 1:next_end])
                if not following or not following.lstrip().startswith(b'.'):
                    continue  # MT2MIT maps the opening parenthesis to a period.
                for at in range(end - 1, pos, -1):
                    values, show = ops[at]
                    if show not in (b'Tj', b'TJ'):
                        continue
                    items = list(values[:1] if show == b'Tj' else values[0])
                    last = next((j for j in range(len(items)-1, -1, -1)
                                 if isinstance(items[j], (str, bytes)) and raw_bytes(items[j])), None)
                    if last is None:
                        continue
                    raw = raw_bytes(items[last])
                    if not raw.endswith(b'\xdf'):
                        break
                    before = items[:last] + ([ByteStringObject(raw[:-1])] if raw[:-1] else [])
                    after = [ByteStringObject(b'\xdf')] + items[last + 1:]
                    replacements[at] = ([([ArrayObject(before)], b'TJ')] if before else []) + [
                        ([alias(args[0]), args[1]], b'Tf'), ([ArrayObject(after)], b'TJ'),
                        ([args[0], args[1]], b'Tf')]
                    changed += 1
                    break
            if replacements:
                content.operations = [op for i, old in enumerate(ops) for op in replacements.get(i, [old])]
                # A content stream may be shared with an unselected page.
                page[NameObject('/Contents')] = writer._add_object(content)
        if changed:
            temp = path.with_suffix('.operators.tmp.pdf')
            try:
                writer.write(temp)
                reader.close()
                writer.close()
                temp.replace(path)
            finally:
                if temp.exists():
                    temp.unlink()
    finally:
        reader.close()
        writer.close()
    return changed
