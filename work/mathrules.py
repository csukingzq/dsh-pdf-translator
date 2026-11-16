"""Give TeX rule strokes an area so BabelDOC can attach them to formulas.

Horizontal, solid, butt-cap black strokes are equivalent to filled rectangles.
Thin single-pixel image-mask rules are likewise converted in their fill colour.
BabelDOC 0.7.1 can leave zero-height strokes at their source positions when
moving formula glyphs. Preserve their visible geometry using a rectangle.
Only the disposable input and selected pages are modified. Shared Form
XObjects are copied per invocation, never modified in place.
"""
from pathlib import Path
import re

# Long rules commonly belong to algorithm/table frames. Giving those an area
# can make the engine move a frame edge with nearby formula text. Keep this
# compatibility pass deliberately limited to short rules (one inch at 1:1).
MAX_RULE_LENGTH = 72


def has_tex_math(fonts):
    return any(re.search(r'(?:^|\+)CM(?:MI|SY|EX)\d+', name, re.I) for name in fonts)


def solid_rule_mask(image, matrix):
    """Recognise an unfiltered one-pixel stencil stretched into a thin rule.

    A stencil paints in the current nonstroking colour, exactly like a filled
    rectangle. Decode inversion and the first (only meaningful) bit determine
    whether it paints at all. Ordinary images and transparent masks stay images.
    """
    settings = image.get('settings', {})
    allowed = {'/IM', '/ImageMask', '/W', '/Width', '/H', '/Height',
               '/BPC', '/BitsPerComponent', '/D', '/Decode', '/I', '/Interpolate'}
    if set(settings) - allowed:
        return False
    mask = settings.get('/IM', settings.get('/ImageMask', False))
    if not getattr(mask, 'value', mask):
        return False
    if (settings.get('/W', settings.get('/Width')) != 1
            or settings.get('/H', settings.get('/Height')) != 1
            or settings.get('/BPC', settings.get('/BitsPerComponent', 1)) != 1):
        return False
    data = image.get('data', b'')
    decode = list(settings.get('/D', settings.get('/Decode', [0, 1])))
    if len(data) != 1 or decode not in ([0, 1], [1, 0]):
        return False
    bit = data[0] >> 7
    if decode[bit] != 0:
        return False
    a, b, c, d, _, _ = map(float, matrix)
    return b == c == 0 and 0 < abs(d) < abs(a) / 4 and abs(a) <= MAX_RULE_LENGTH


def normalize_rules(path, indices, allow_color_rules=False):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject
    from pypdf.generic import FloatObject, NameObject, NumberObject

    path = Path(path)
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)

    def rewrite(obj, page=False, ancestors=()):
        stream = ContentStream(obj.get_contents() if page else obj, writer)
        resources = DictionaryObject(obj.get('/Resources', {}).get_object()
                                   if obj.get('/Resources') is not None else {})
        xobjects = DictionaryObject(resources.get('/XObject', {}).get_object()
                                    if resources.get('/XObject') is not None else {})
        ops, out, stack = stream.operations, [], []
        black, safe, changed = True, True, 0
        cap, dash = 0, []
        path_open = False
        path_before = []
        for i, (args, op) in enumerate(ops):
            path_before.append(path_open)
            if op in (b'm', b'l', b'c', b'v', b'y', b'h', b're'):
                path_open = True
            elif op in (b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*', b'n'):
                path_open = False
            if (op == b'INLINE IMAGE' and not path_open and i >= 2
                    and ops[i - 2][1] == b'q' and ops[i - 1][1] == b'cm'
                    and solid_rule_mask(args, ops[i - 1][0])):
                out.extend([([NumberObject(v) for v in (0, 0, 1, 1)], b're'), ([], b'f')])
                changed += 1
                continue
            if op == b'q':
                stack.append((black, safe, cap, dash))
            elif op == b'Q':
                black, safe, cap, dash = stack.pop() if stack else (False, False, None, [1])
            elif op == b'J':
                cap = int(args[0])
            elif op == b'd':
                dash = list(args[0])
            elif op == b'G':
                black = float(args[0]) == 0
            elif op in (b'RG', b'K', b'CS', b'SC', b'SCN'):
                black = False
            elif op == b'gs':
                # Stroke and fill alpha/blending may differ. Do not guess.
                states = resources.get('/ExtGState')
                state = states.get_object().get(args[0]) if states is not None else None
                state = state.get_object() if state is not None else {}
                benign = {'/Type', '/OPM', '/op', '/OP', '/BG2', '/UCR2', '/SM', '/SA'}
                disabled = lambda key: not getattr(state.get(key, False), 'value', state.get(key, False))
                safe = (safe and allow_color_rules and bool(state) and not (set(state) - benign)
                        and all(disabled(k) for k in ('/op', '/OP', '/SA'))
                        and all(state.get(k, '/Default') == '/Default' for k in ('/BG2', '/UCR2')))
            if op == b'Do' and black and safe and len(ancestors) < 12:
                ref = xobjects.get(args[0])
                child = ref.get_object() if ref is not None else None
                identity = id(child)
                if (child is not None and child.get('/Subtype') == '/Form'
                        and '/Resources' in child and '/Group' not in child
                        and identity not in ancestors):
                    data, child_resources, n = rewrite(child, ancestors=(*ancestors, identity))
                    if n:
                        clone = DecodedStreamObject()
                        clone.update({k: v for k, v in child.items()
                                      if k not in ('/Length', '/Filter', '/DecodeParms')})
                        clone.set_data(data)
                        clone[NameObject('/Resources')] = child_resources
                        name = NameObject(f'/DSHRule{len(xobjects)}')
                        while name in xobjects:
                            name = NameObject(str(name) + '_')
                        xobjects[name] = writer._add_object(clone)
                        args = [name]
                        changed += n
            # MT2 books use short ICC-coloured strokes without TeX's explicit
            # dash/cap operators. Match the whole isolated path and transfer
            # the stroke colour space/components to fill, inside its q/Q.
            if (allow_color_rules and page and op == b'S' and safe and cap == 0 and not dash
                    and i >= 7 and i + 1 < len(ops) and ops[i + 1][1] == b'Q'
                    and not path_before[i - 2]
                    and [o for _, o in ops[i - 7:i]] == [b'q', b'cm', b'CS', b'SCN', b'w', b'm', b'l']):
                _, matrix, space, colour, width, start, end = [a for a, _ in ops[i - 7:i]]
                h = float(width[0])
                length = abs(float(end[0]) - float(start[0]))
                definition = resources.get('/ColorSpace', {}).get_object() if resources.get('/ColorSpace') is not None else {}
                definition = definition.get(space[0])
                definition = definition.get_object() if definition is not None else space[0]
                components = {'/DeviceGray': 1, '/DeviceRGB': 3, '/DeviceCMYK': 4}.get(str(definition))
                if isinstance(definition, list) and len(definition) == 2 and definition[0] == '/ICCBased':
                    components = definition[1].get_object().get('/N')
                if (components in (1, 3, 4) and len(colour) == components
                        and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in colour)
                        and matrix[1] == matrix[2] == 0
                        and float(start[1]) == float(end[1]) and 4 * h < length <= MAX_RULE_LENGTH and h > 0):
                    rect = [min(float(start[0]), float(end[0])), float(start[1]) - h / 2, length, h]
                    out = out[:-2]
                    out.extend([(space, b'cs'), (colour, b'scn'),
                                ([FloatObject(v) for v in rect], b're'), ([], b'f')])
                    changed += 1
                    continue
            if (op == b'S' and black and safe and i >= 5 and not path_before[i - 2]
                    and [o for _, o in ops[i - 5:i]] == [b'd', b'J', b'w', b'm', b'l']):
                rule_dash, rule_cap, width, start, end = [a for a, _ in ops[i - 5:i]]
                h = float(width[0])
                if (not rule_dash[0] and rule_cap[0] == 0 and h > 0
                        and float(start[1]) == float(end[1])
                        and 4 * h < abs(float(end[0]) - float(start[0])) <= MAX_RULE_LENGTH):
                    x = min(float(start[0]), float(end[0]))
                    length = abs(float(end[0]) - float(start[0]))
                    rect = [x, float(start[1]) - h / 2, length, h]
                    out = out[:-2]  # Remove the single move/line path.
                    out.extend([([], b'q'), ([NumberObject(0)], b'g'),
                                ([FloatObject(v) for v in rect], b're'),
                                ([], b'f'), ([], b'Q')])
                    changed += 1
                    continue
            out.append((args, op))
        if xobjects:
            resources[NameObject('/XObject')] = xobjects
        stream.operations = out
        return stream.get_data(), resources, changed

    count = 0
    try:
        for index in indices:
            page = writer.pages[index]
            data, resources, n = rewrite(page, page=True)
            if n:
                content = DecodedStreamObject()
                content.set_data(data)
                page[NameObject('/Contents')] = writer._add_object(content)
                page[NameObject('/Resources')] = resources
                count += n
        if count:
            temp = path.with_suffix('.rules.tmp.pdf')
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
    return count
