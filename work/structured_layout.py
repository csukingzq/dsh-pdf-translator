"""Preserve rows where large math glyph boxes otherwise join adjacent lines.

Only explicitly recognised English algorithm/theorem blocks are split. Native
text origins are used because CMEX accents and radicals have inflated boxes.
The translated rows still use BabelDOC's formula glyphs and typesetter.
"""
import copy
import re
import statistics


def split_structured_text(result, native):
    blocks = native.get_text('dict')['blocks']
    spans = [span for block in blocks for line in block.get('lines', []) for span in line['spans']]
    replacement = []
    changed = 0
    for box in result.boxes:
        if result.names[box.cls] != 'plain text':
            replacement.append(box)
            continue
        x0, y0, x1, y1 = map(float, box.xyxy)
        region = [s for s in spans if x0 - 2 <= s['origin'][0] <= x1 + 2
                  and y0 <= s['origin'][1] <= y1 + 3]
        text = ' '.join(s['text'] for s in region)
        algorithm = text.count('Require:') >= 2 and ('while' in text or 'return' in text)
        algorithm = algorithm or bool(
            re.search(r'\bInput\s*:', text) and re.search(r'\bOutput\s*:', text)
            and re.search(r'\b(?:for|while)\b', text))
        algorithm = algorithm or bool(
            re.search(r'\b1:\s*(?:repeat|for)\b', text)
            and re.search(r'\b2:', text)
            and re.search(r'\b(?:until|end for|return)\b', text))
        theorem = bool(re.match(r'\s*(?:Theorem|Corollary|Lemma|Proposition)\s+\d', text))
        if not (algorithm or theorem):
            replacement.append(box)
            continue
        prose = [s for s in region if re.search(r'[A-Za-z]{3}', s['text'])]
        if not prose:
            replacement.append(box)
            continue
        size = statistics.median(s['size'] for s in prose)
        baselines = []
        for span in sorted(region, key=lambda s: s['origin'][1]):
            # Raised roots/accents and small subscripts are not new text rows.
            if (span['size'] < size * 0.9 or not span['text'].strip()
                    or re.search(r'(?:CMEX|CMSY)', span.get('font', ''), re.I)):
                continue
            baseline = float(span['origin'][1])
            if not baselines or baseline - baselines[-1] > size * 0.65:
                baselines.append(baseline)
        if len(baselines) < 2:
            replacement.append(box)
            continue
        # A boundary lies between the descent of one line and the next ascent.
        boundaries = [(a + b) / 2 - size * 0.35
                      for a, b in zip(baselines, baselines[1:])]
        bounds = [y0] + [y for y in boundaries if y0 < y < y1] + [y1]
        for top, bottom in zip(bounds, bounds[1:]):
            part = copy.copy(box)
            part.xyxy = (x0, top, x1, bottom)
            replacement.append(part)
        changed += 1
    result.boxes = replacement
    return changed


class StructuredLayoutModel:
    def __init__(self, model):
        self.model = model
        self.corrected_pages = set()
        self.corrected_blocks = 0

    @property
    def stride(self):
        return self.model.stride

    def handle_document(self, pages, pdf, config, save):
        for page, result in self.model.handle_document(pages, pdf, config, save):
            native = pdf[page.page_number]
            if not native.rotation:
                changed = split_structured_text(result, native)
                if changed:
                    self.corrected_pages.add(page.page_number + 1)
                    self.corrected_blocks += changed
            yield page, result

    def diagnostics(self):
        inherited = self.model.diagnostics() if hasattr(self.model, 'diagnostics') else {}
        return {**inherited, 'structuredLayoutPages': sorted(self.corrected_pages),
                'structuredLayoutBlocks': self.corrected_blocks}
