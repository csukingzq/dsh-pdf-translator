"""Conservative, document-wide heading levels from numbering and PDF evidence."""
import re
from collections import Counter

import pymupdf


def heading_text(text):
    return re.sub(r'^\s*#{1,6}\s*', '', text).strip()


def numbered_level(text):
    text = heading_text(text).strip('* ')
    if re.match(r'^(?:第\s*[\d一二三四五六七八九十百]+\s*章(?:\s|$)|Chapter\s+\d+\b)', text, re.I):
        return 1
    match = re.match(r'^(\d+(?:\.\d+)+)\.?\s+\S', text)
    return min(6, match[1].count('.') + 1) if match else None


def is_body_label(text):
    text = heading_text(text).strip('* ')
    return bool(re.match(
        r'^(?:(?:定理|引理|定义|证明|例题|例|命题|推论)\s*(?:\d|[：:.]|$)'
        r'|(?:Theorem|Lemma|Definition|Proof|Example|Corollary)\b'
        r'|\d+(?:\.\d+)+\s*节[。.:：]?\s*$'
        r'|(?:\d+\([a-z]\)\s*的)?图\s*[（(\d]'
        r'|(?:\([a-z]\)\s*)?(?:程序|输出|评注)\s*$)', text, re.I))


def normalize_headings(pages, source=None):
    """Update canonical blocks, so Markdown, PDF and review use the same levels.

    Bookmarks are matched one-to-one by page and nearby destination, never by
    page alone. Font evidence only demotes unnumbered/body labels; scanned pages
    without text retain the model's hierarchy unless numbering is explicit.
    """
    headings = [(page, block) for page in pages for block in page['blocks']
                if block['kind'] == 'heading' and block.get('status') != 'source_image']
    if not headings:
        return []
    evidence, outlines = {}, {}
    document_sizes = Counter()
    if source is not None:
        with pymupdf.open(source) as doc:
            toc = doc.get_toc(simple=False)
            for page in pages:
                number = page.get('page')
                if not isinstance(number, int) or not 1 <= number <= len(doc):
                    continue
                sheet = doc[number - 1]
                spans = [s for b in sheet.get_text('dict')['blocks']
                         for line in b.get('lines', []) for s in line['spans'] if s['text'].strip()]
                sizes = Counter()
                for span in spans:
                    sizes[round(span['size'], 1)] += len(span['text'].strip())
                document_sizes.update(sizes)
                body_size = sizes.most_common(1)[0][0] if sizes else 0
                blocks = [b for b in page['blocks'] if b['kind'] == 'heading']
                pairs = []
                for idx, entry in enumerate(toc):
                    dest = entry[3].get('to')
                    if entry[2] != number or dest is None or entry[3].get('kind') != pymupdf.LINK_GOTO:
                        continue
                    for block in blocks:
                        distance = abs(block['bbox'][1] - dest.y / sheet.rect.height)
                        if distance <= .045:
                            pairs.append((distance, idx, id(block), entry[0]))
                used = set()
                for _, idx, key, level in sorted(pairs):
                    if idx not in used and key not in outlines:
                        outlines[key] = max(1, min(6, level))
                        used.add(idx)
                for block in blocks:
                    box = block['bbox']
                    rect = pymupdf.Rect(box[0]*sheet.rect.width, box[1]*sheet.rect.height,
                                       box[2]*sheet.rect.width, box[3]*sheet.rect.height)
                    selected = [s for s in spans if (pymupdf.Rect(s['bbox']) & rect).get_area()
                                >= pymupdf.Rect(s['bbox']).get_area() * .25]
                    if selected:
                        # Ignore later prose when the model's bbox includes it.
                        top = min(s['bbox'][1] for s in selected)
                        first = [s for s in selected if abs(s['bbox'][1]-top) < 3]
                        weights = Counter()
                        for span in first:
                            style = (round(span['size'], 1), bool(span['flags'] & 16), bool(span['flags'] & 2))
                            weights[style] += len(span['text'].strip())
                        evidence[id(block)] = (weights.most_common(1)[0][0], body_size)
    styles = {}
    for _, block in headings:
        level = outlines.get(id(block)) or numbered_level(block['markdown'])
        if level and id(block) in evidence and not is_body_label(block['markdown']):
            style = evidence[id(block)][0]
            styles.setdefault(style, Counter())[level] += 1
    changes = []
    document_body = document_sizes.most_common(1)[0][0] if document_sizes else 0
    for page, block in headings:
        before = block['markdown']
        title = heading_text(before)
        level = outlines.get(id(block))
        label = is_body_label(title)
        if level is None:
            level = numbered_level(title)
            if id(block) in evidence:
                style, body = evidence[id(block)]
                body = max(body, document_body)
                if not level and style in styles:
                    level = styles[style].most_common(1)[0][0]
                elif not level and body and style[0] <= body * 1.08 and not style[1]:
                    label = True
            if label:
                block['kind'] = 'paragraph'
                block['markdown'] = '**' + title.strip('*') + '**'
            else:
                original = re.match(r'^\s*(#{1,6})\s', before)
                level = level or (len(original[1]) if original else 1)
        if block['kind'] == 'heading':
            block['markdown'] = '#' * level + ' ' + title
        if block['markdown'] != before:
            changes.append({'block': block.get('id'), 'page': page.get('page'),
                            'before': before, 'after': block['markdown']})
    return changes
