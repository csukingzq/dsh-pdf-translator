"""Source-grounded, non-destructive document structure resolution.

Recognition pages are immutable inputs. Exclusion is a render decision, never
deletion. All callers (translation, offline render and review) use this module.
"""
import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import pymupdf

STRUCTURE_VERSION = 'document-structure-v5'
# Evidence format changes independently: resolver upgrades must not buy the
# same vision observations again. The initial format shares the v1 identifier.
SOURCE_EVIDENCE_VERSION = 'document-structure-v1'
ROLES = {'body', 'heading', 'running_header', 'running_footer', 'page_number',
         'footnote', 'body_label', 'toc_entry', 'caption'}
MARGINAL = {'running_header', 'running_footer', 'page_number'}
LABEL = re.compile(r'^(?:(?:\d+(?:\.\d+)*|[IVXLCDM]+)[.)：:]?\s*)?'
                   r'(?:定理|引理|定义|证明|例题|例|命题|推论|评注|程序|输出|'
                   r'Theorem\b|Lemma\b|Definition\b|Proof\b|Example\b|'
                   r'Proposition\b|Corollary\b|Remark\b)', re.I)
TOC_TITLE = re.compile(r'^(?:contents|table\s+of\s+contents|目\s*[录錄])$', re.I)
CHAPTER_TITLE = re.compile(r'^(?:chapter\s+(?:\d+|[ivxlcdm]+)\b|第\s*[\d一二三四五六七八九十百〇零两]+\s*章(?=[\s:：]|$))', re.I)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def title_text(text):
    return re.sub(r'^\s*#{1,6}\s*', '', text, flags=re.M).strip().strip('* ')


def normal(text):
    text = unicodedata.normalize('NFKC', title_text(text)).casefold()
    text = re.sub(r'^chapter\s+(\d+)\s*[:.]?\s*', r'\1 ', text)
    text = re.sub(r'^第\s*(\d+)\s*章\s*', r'\1 ', text)
    return ''.join(c for c in text if c.isalnum())


def similarity(a, b):
    a, b = normal(a), normal(b)
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b).ratio()


def number_key(text):
    text = title_text(text)
    chapter = re.match(r'^chapter\s+(\d+|[ivxlcdm]+)\b', text, re.I)
    if chapter:
        return 'number', str(_page_number(chapter[1])[1])
    chinese = re.match(r'^第\s*([\d一二三四五六七八九十百]+)\s*章', text)
    if chinese:
        value = chinese[1]
        if not value.isdigit():
            digits = dict(zip('一二三四五六七八九', range(1,10)))
            value = str((digits.get(value.split('十')[0],1)*10 + digits.get(value.split('十')[-1],0)) if '十' in value else digits.get(value,value))
        return 'number', value
    section = re.match(r'^[^\w\d]*(\d+(?:\.\d+)*)(?:[.*]|\s)', text)
    return ('number', section[1]) if section else None


def numbered_level(text):
    text = title_text(text)
    if CHAPTER_TITLE.match(text):
        return 1
    if re.match(r'^§\s*\d+[.*]?\s*\S', text):
        return 2
    match = re.match(r'^(\d+(?:\.\d+)+)\.?\s+\S', text)
    return min(6, match[1].count('.') + 1) if match else None


def is_body_label(text):
    text = title_text(text)
    return bool(LABEL.match(text) or re.match(
        r'^(?:\d+(?:\.\d+)+\s*节[。.:：]?\s*$|(?:\d+\([a-z]\)\s*的)?图\s*[（(\d]|(?:\([a-z]\)\s*)?(?:程序|输出|评注)\s*$)', text, re.I))


def valid_box(box):
    return (isinstance(box, list) and len(box) == 4
            and all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in box)
            and box[0] < box[2] and box[1] < box[3])


def _read(path):
    try:
        return json.loads(Path(path).read_text('utf-8'))
    except (OSError, ValueError):
        return None


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    temp.replace(path)


def validate_analysis(data, requested):
    """Reject malformed or invented page IDs before accepting model evidence."""
    if not isinstance(data, dict) or not isinstance(data.get('pages'), list):
        raise ValueError('结构分析缺少 pages')
    found = set()
    for page in data['pages']:
        n = page.get('page')
        if type(n) is not int or n not in requested or n in found:
            raise ValueError('结构分析页码无效')
        found.add(n)
        if type(page.get('is_contents')) is not bool:
            raise ValueError('结构分析缺少目录标记')
        if not isinstance(page.get('printed_page', ''), str):
            raise ValueError('印刷页码必须为字符串')
        for region in page.get('regions', []):
            if (region.get('role') not in ROLES or not valid_box(region.get('bbox'))
                    or not isinstance(region.get('source_text'), str)
                    or not region['source_text'].strip()):
                raise ValueError('结构区域无效')
        for entry in page.get('entries', []):
            if (type(entry.get('level')) is not int or not 1 <= entry['level'] <= 6
                    or not isinstance(entry.get('title'), str) or not entry['title'].strip()
                    or not isinstance(entry.get('printed_page'), str)):
                raise ValueError('目录条目无效')
    if found != set(requested):
        raise ValueError('结构分析遗漏页面')
    return data['pages']


def _page_number(label):
    label = label.strip().lower()
    if re.fullmatch(r'\d+', label):
        return 'arabic', int(label)
    if re.fullmatch(r'[ivxlcdm]+', label):
        values = dict(i=1, v=5, x=10, l=50, c=100, d=500, m=1000)
        total, previous = 0, 0
        for c in reversed(label):
            value = values[c]
            total += -value if value < previous else value
            previous = max(previous, value)
        return 'roman', total
    return None


def contents_block(block, info):
    """Identify printed contents material without absorbing surrounding prose."""
    source = title_text(block['source_text'])
    if TOC_TITLE.fullmatch(source) or _page_number(source) or block.get('role_candidate') in (
            'toc_entry', 'page_number', 'running_header', 'running_footer'):
        return True
    key = normal(source)
    if not key:
        return False
    for region in info.get('regions', []):
        if (region['role'] == 'toc_entry' and normal(region['source_text']) == key
                and _intersection(block['bbox'], region['bbox']) > 0):
            return True
    # One recognition block can contain multiple rows or a title without its
    # separately extracted folio. A mention of a chapter inside prose is kept.
    for entry in info['entries']:
        name = normal(entry['title'])
        folio = normal(entry['printed_page'])
        if name and (key == name or (folio and name+folio in key) or
                     (block['kind'] == 'table' and name in key)):
            return True
    return bool(re.search(r'[.·…]{2,}\s*(?:\d+|[ivxlcdm]+)\s*$', source, re.I))


def page_segments(anchors):
    """Do not extrapolate across gaps: only observed consistent runs are mapped."""
    segments = []
    for physical, label in sorted(anchors):
        parsed = _page_number(label)
        if parsed is None:
            continue
        style, number = parsed
        offset = physical - number
        if (segments and segments[-1]['style'] == style and segments[-1]['offset'] == offset
                and physical > segments[-1]['physical_end']):
            segments[-1]['physical_end'] = physical
            segments[-1]['printed_end'] = number
        else:
            segments.append(dict(style=style, offset=offset, physical_start=physical,
                                 physical_end=physical, printed_start=number, printed_end=number))
    return segments


def native_contents(pages):
    """Recover leader-separated entries when structural observations are unavailable."""
    continued = False
    indents = []
    for info in pages.values():
        if info.get('entries'):
            continued = True
            continue
        lines = info['lines']
        title = any(TOC_TITLE.fullmatch(line['source_text']) for line in lines)
        if title:
            indents = []
        if not (continued or title or info.get('is_contents')):
            continue
        entries = []
        for line in lines:
            row = re.fullmatch(r'(.+?)\s*(?:[.·…\s]*[.·…]{2,}[.·…\s]*|\s{2,})(\d+|[ivxlcdm]+)',
                               line['source_text'], re.I)
            if row:
                entries.append((line['bbox'][0], row[1].strip(), row[2]))
        continued = bool(entries)
        if entries:
            for left, _, _ in sorted(entries):
                if not any(abs(left-x) < .015 for x in indents):
                    indents.append(left)
            indents.sort()
            info.update(is_contents=True, entries=[dict(title=t, printed_page=folio,
                level=min(6, 1+min(range(len(indents)), key=lambda i:abs(indents[i]-x))))
                for x,t,folio in entries])


def build_source_index(source, selected, cache=None, analysis_config=None, analyze=None):
    """Read all bookmarks/native pages; optionally inspect bounded scan samples.

    ``analyze`` accepts [(physical_page, png_bytes)] and returns validated JSON.
    Passing None guarantees no network (offline render and review).
    """
    source = Path(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    config = analysis_config or {}
    key = fingerprint([STRUCTURE_VERSION, source_hash, sorted(selected), config])
    path = Path(cache)/('source-index-'+key+'.json') if cache else None
    old = _read(path) if path else None
    if old and old.get('key') == key and (analyze is None or old.get('analysis_complete')):
        return old
    index = dict(version=STRUCTURE_VERSION, key=key, source_hash=source_hash,
                 analysis_config=config, nodes=[], pages={}, diagnostics=[], page_map=[])
    with pymupdf.open(source) as doc:
        index['page_count'] = len(doc)
        stack = []
        for position, entry in enumerate(doc.get_toc(simple=False)):
            level, title, page = entry[:3]
            if not 1 <= page <= len(doc):
                continue
            while stack and stack[-1]['level'] >= level:
                stack.pop()
            node = dict(id=f'outline-{position}', title=title, page=page,
                        level=max(1, min(6, level)), parent_id=stack[-1]['id'] if stack else None,
                        evidence='bookmark')
            dest = entry[3].get('to') if len(entry) > 3 else None
            if dest is not None:
                node['y'] = max(0, min(1, dest.y/doc[page-1].rect.height))
            index['nodes'].append(node)
            stack.append(node)
        for n, sheet in enumerate(doc, 1):
            lines = []
            for block in sheet.get_text('dict', flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
                for line in block.get('lines', []):
                    text = ''.join(s['text'] for s in line['spans']).strip()
                    box = [line['bbox'][0]/sheet.rect.width, line['bbox'][1]/sheet.rect.height,
                           line['bbox'][2]/sheet.rect.width, line['bbox'][3]/sheet.rect.height]
                    box = [min(1, max(0, x)) for x in box]
                    if text and valid_box(box):
                        lines.append(dict(source_text=text, bbox=box,
                                          font_size=max(s['size'] for s in line['spans']),
                                          superscripts=[dict(text=s['text'],bbox=[s['bbox'][0]/sheet.rect.width,
                                              s['bbox'][1]/sheet.rect.height,s['bbox'][2]/sheet.rect.width,s['bbox'][3]/sheet.rect.height])
                                              for s in line['spans'] if s['flags'] & 1],
                                          bold=any(s['flags'] & 16 for s in line['spans'])))
            index['pages'][str(n)] = dict(lines=lines, regions=[], printed_page='', is_contents=False)
        contents = [n['page'] for n in index['nodes'] if TOC_TITLE.match(n['title'].strip())]
        if contents:
            start = min(contents)
            end = min([n['page'] for n in index['nodes'] if n['page'] > start] or [start+12])
            probes = set(range(start, min(end, start+12, len(doc)+1)))
        else:
            probes = set(range(1, min(20, len(doc))+1))
        probes.update(int(n) for n, info in index['pages'].items()
                      if any(TOC_TITLE.fullmatch(line['source_text']) for line in info['lines']))
        # Bound extra sampling; translation itself supplies the remaining pages.
        for n in sorted(set(selected))[:1] + sorted(set(selected))[-1:]:
            probes.update(p for p in (n-1, n, n+1) if 1 <= p <= len(doc))
        probes.update(n['page'] for n in index['nodes'] if n['page'] in selected)
        # Native contents are also sent to the structure reader: font/text alone
        # cannot reliably establish an unnumbered table of contents hierarchy.
        observations = []
        observation_root = Path(cache)/('source-observations-'+fingerprint([SOURCE_EVIDENCE_VERSION, source_hash, config])) if cache else None
        inspected = set()
        while probes:
            inspected.update(probes)
            pending = []
            for n in sorted(probes):
                cached = _read(observation_root/f'{n}.json') if observation_root else None
                if cached:
                    try:
                        observations.extend(validate_analysis({'pages':[cached]}, [n]))
                        continue
                    except (ValueError, KeyError, TypeError):
                        pass
                pending.append(n)
            if not analyze:
                if pending and any(not index['pages'][str(n)]['lines'] for n in selected):
                    index['diagnostics'].append(dict(reason='structure_analysis_unavailable',
                        detail='离线模式仅使用书签、文字层和已有识别结果。'))
                # A previous run may have cached a long contents section.
                pending = []
            for offset in range(0, len(pending), 4):
                group = pending[offset:offset+4]
                images = [(n, doc[n-1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes('png')) for n in group]
                try:
                    accepted = validate_analysis(analyze(images), group)
                    observations.extend(accepted)
                    if observation_root:
                        for observation in accepted:
                            _write(observation_root/f'{observation["page"]}.json', observation)
                except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
                    index['diagnostics'].append(dict(reason='structure_analysis_failed', pages=group,
                                                      detail=type(exc).__name__))
            probes = {o['page']+1 for o in observations if o['is_contents'] and o['page'] < len(doc)} - inspected
        for observation in observations:
            index['pages'][str(observation['page'])].update(observation)
        native_contents(index['pages'])
        anchors = [(o['page'], o.get('printed_page', '')) for o in observations]
        for n, page in index['pages'].items():
            candidates = [l['source_text'].strip() for l in page['lines']
                          if (l['bbox'][3] < .12 or l['bbox'][1] > .88) and _page_number(l['source_text'])]
            if len(candidates) == 1:
                anchors.append((int(n), candidates[0]))
        index['page_map'] = page_segments(set(anchors))
        toc_entries = [(int(n), e) for n, info in index['pages'].items() if info['is_contents']
                       for e in info.get('entries', [])]
        toc_stack = []
        used_nodes = set()
        for ordinal, (toc_page, entry) in enumerate(toc_entries):
            available = [n for n in index['nodes'] if n['id'] not in used_nodes]
            matches = [n for n in available if similarity(n['title'], entry['title']) >= .85]
            key_number = number_key(entry['title'])
            if key_number:
                matches = [n for n in matches if number_key(n['title']) in (None,key_number)]
            # Disambiguate repeated section names by their enclosing chapter.
            while toc_stack and toc_stack[-1]['level'] >= entry['level']:
                toc_stack.pop()
            parent = toc_stack[-1] if toc_stack else None
            if parent:
                matches = [n for n in matches if n['parent_id'] == parent['id']]
                if not matches and key_number:
                    # Bookmarks sometimes expand a printed mathematical symbol
                    # into words. Require the same parent, number, level and a
                    # substantial shared title; never match a number globally.
                    matches = [n for n in available if n['parent_id'] == parent['id']
                               and n['level'] == entry['level'] and number_key(n['title']) == key_number
                               and similarity(n['title'],entry['title']) >= .6]
            if not matches:
                parsed = _page_number(entry['printed_page'])
                targets = [] if parsed is None else [s['offset']+parsed[1] for s in index['page_map']
                    if s['style']==parsed[0] and s['printed_start']<=parsed[1]<=s['printed_end']]
                # A unique title on a mapped page can recover a bookmark even
                # when the PDF outline flattened the printed hierarchy.
                matches = [n for n in available if n.get('page') in targets
                           and similarity(n['title'],entry['title']) >= .98]
                if not matches:
                    exact = [n for n in available if normal(n['title']) == normal(entry['title'])]
                    if len(exact) == 1:
                        matches = exact
            parsed = _page_number(entry['printed_page'])
            mapped = [] if parsed is None else [s['offset']+parsed[1] for s in index['page_map']
                if s['style']==parsed[0] and s['printed_start']<=parsed[1]<=s['printed_end']]
            located = [n for n in matches if n.get('page') in mapped]
            if located:
                matches = located
            matches.sort(key=lambda n:similarity(n['title'],entry['title']), reverse=True)
            if len(matches)>1 and similarity(matches[0]['title'],entry['title'])-similarity(matches[1]['title'],entry['title']) >= .05:
                matches=matches[:1]
            if len(matches) == 1:
                node = matches[0]
                if node['level'] != entry['level']:
                    index['diagnostics'].append(dict(reason='toc_bookmark_conflict', node=node['id'], page=toc_page))
                node.update(printed_page=entry['printed_page'], toc_title=entry['title'],
                            level=entry['level'], parent_id=parent['id'] if parent else None)
            else:
                parsed = _page_number(entry['printed_page'])
                targets = [] if parsed is None else [s['offset']+parsed[1] for s in index['page_map']
                    if s['style'] == parsed[0] and s['printed_start'] <= parsed[1] <= s['printed_end']]
                node = dict(id=f'toc-{ordinal}', title=entry['title'], level=entry['level'],
                            page=targets[0] if len(set(targets)) == 1 else None,
                            printed_page=entry['printed_page'], parent_id=parent['id'] if parent else None,
                            evidence='visual_contents')
                index['nodes'].append(node)
            entry['node_id'] = node['id']
            used_nodes.add(node['id'])
            toc_stack.append(node)
        anchors.extend((n['page'],n['printed_page']) for n in index['nodes'] if n.get('page') and n.get('printed_page'))
        index['page_map'] = page_segments(set(anchors))
        index['analysis_complete'] = bool(analyze) and not any(d['reason']=='structure_analysis_failed' for d in index['diagnostics'])
    if path:
        _write(path, index)
    return index


def _intersection(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def _source_text(block, page_evidence):
    if block.get('source_text', '').strip():
        return block['source_text']
    lines = [l for l in page_evidence.get('lines', [])
             if _intersection(l['bbox'], block['bbox']) >=
             (l['bbox'][2]-l['bbox'][0])*(l['bbox'][3]-l['bbox'][1])*.6]
    return ' '.join(l['source_text'] for l in lines) or title_text(block['markdown'])


def _edge(block):
    x0, y0, x1, y1 = block.get('source_bbox', block['bbox'])
    if y1-y0 > .065 or len(block.get('source_text', block['markdown'])) > 160:
        return None
    return 'top' if y1 <= .12 else 'bottom' if y0 >= .88 else None


def _running_key(text):
    return re.sub(r'\d+', '#', normal(text))


def native_regions(lines):
    """Join baseline fragments, but never bridge the gap to a folio."""
    result = list(lines)
    rows = []
    for line in sorted(lines, key=lambda l:(round(l['bbox'][1], 2), l['bbox'][0])):
        row = next((r for r in rows if abs(r[0]['bbox'][1]-line['bbox'][1]) < .004), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)
    for row in rows:
        if len(row)>1 and any(_page_number(l['source_text']) for l in row):
            ordered = sorted(row,key=lambda l:l['bbox'][0])
            result.append(dict(source_text=' '.join(l['source_text'] for l in ordered),
                bbox=[min(l['bbox'][0] for l in row),min(l['bbox'][1] for l in row),max(l['bbox'][2] for l in row),max(l['bbox'][3] for l in row)],
                font_size=max(l.get('font_size',0) for l in row)))
        group = []
        for line in sorted(row, key=lambda l:l['bbox'][0]):
            if group and line['bbox'][0]-group[-1]['bbox'][2] > .045:
                group = []
            group.append(line)
            if len(group)>1:
                result.append(dict(source_text=' '.join(l['source_text'] for l in group),
                    font_size=max(l.get('font_size',0) for l in group),
                    bbox=[min(l['bbox'][0] for l in group), min(l['bbox'][1] for l in group),
                          max(l['bbox'][2] for l in group), max(l['bbox'][3] for l in group)]))
    return result


def locate_source(block, regions):
    candidates = []
    for region in regions:
        box = region['bbox']
        area = (box[2]-box[0])*(box[3]-box[1])
        score = similarity(block['source_text'], region['source_text'])
        near = abs((box[1]+box[3]-block['bbox'][1]-block['bbox'][3])/2) <= .02
        if score >= .94 and (_intersection(box, block['bbox']) >= area*.3 or (score==1 and near)):
            candidates.append((score, region))
    candidates = list({(score,tuple(region['bbox'])):(score,region) for score,region in candidates}.values())
    exact = [pair for pair in candidates if pair[0]==1]
    if len(exact)==1:
        return exact[0][1]['bbox']
    candidates.sort(key=lambda pair:pair[0], reverse=True)
    if candidates and (len(candidates)==1 or candidates[0][0]-candidates[1][0] >= .03):
        return candidates[0][1]['bbox']
    return None


def validate_override(value):
    if not isinstance(value, dict) or value.get('role') not in ROLES:
        raise ValueError('结构覆盖 role 无效')
    if value['role'] == 'heading' and (type(value.get('heading_level')) is not int or not 1 <= value['heading_level'] <= 6):
        raise ValueError('结构覆盖 heading_level 必须为 1–6')
    if 'parent_id' in value and value['parent_id'] is not None and not isinstance(value['parent_id'], str):
        raise ValueError('结构覆盖 parent_id 无效')
    return {k: value[k] for k in ('role', 'heading_level', 'parent_id') if k in value}


def resolve_document_structure(raw_pages, source_index, overrides=None):
    """Return a canonical copy, a tree and diagnostics; never mutate inputs."""
    pages = copy.deepcopy(raw_pages)
    index = source_index or {}
    overrides = overrides or {}
    nodes = copy.deepcopy(index.get('nodes', []))
    diagnostics = copy.deepcopy(index.get('diagnostics', []))
    groups = defaultdict(list)
    native_margins = defaultdict(list)
    native_bands = defaultdict(set)
    for number, evidence in index.get('pages', {}).items():
        for line in native_regions(evidence.get('lines', [])):
            pseudo = dict(line, markdown=line['source_text'])
            edge = _edge(pseudo)
            if edge:
                native_margins[(_running_key(line['source_text']), edge)].append(dict(pseudo,page=int(number)))
                if line.get('font_size'):
                    native_bands[(round(line['bbox'][1],2), round(line['font_size']),edge)].add(int(number))
    all_blocks = []
    legacy_pages = []
    for page in pages:
        number = page['page']
        evidence = index.get('pages', {}).get(str(number), {})
        page.pop('contents_entries', None)
        if evidence.get('is_contents'):
            page['contents_entries'] = copy.deepcopy(evidence.get('entries', []))
            # Review documents saved before v0.7 did not store this association.
            for entry in page['contents_entries']:
                if 'node_id' not in entry:
                    same = [n for n in nodes if entry['title'] in (n['title'], n.get('toc_title'))
                            and n.get('printed_page') == entry['printed_page']]
                    if len(same) == 1:
                        entry['node_id'] = same[0]['id']
        if page.get('recognition_schema') != 2:
            legacy_pages.append(number)
        for position, block in enumerate(page['blocks'], 1):
            block.setdefault('id', f'p{number}-b{position}')
            block.setdefault('page', number)
            # Re-resolution consumes immutable recognition, or a review snapshot
            # that records original values. Never interpret generated # as evidence.
            original = block.setdefault('structure_original', {k: copy.deepcopy(block[k]) for k in ('kind', 'markdown', 'bbox')})
            rendered = block.get('structure_rendered', {})
            for field in ('kind', 'markdown', 'bbox'):
                if field in rendered and block[field] != rendered[field]:
                    original[field] = copy.deepcopy(block[field])
            for field in ('kind', 'markdown', 'bbox'):
                block[field] = copy.deepcopy(original[field])
            for field in ('excluded', 'heading_level', 'parent_id', 'structure_node', 'merged_into', 'source_ids', 'chapter_start'):
                block.pop(field, None)
            block['source_text'] = _source_text(block, evidence)
            block.pop('source_bbox', None)
            anchor = locate_source(block, native_regions(evidence.get('lines', [])))
            if not anchor:
                # Independent scan observations can locate a short text inside
                # an over-wide model box. Require exact text and containment;
                # a mixed body/header block must never match on a substring.
                box = block['bbox']
                candidates = [r['bbox'] for r in evidence.get('regions', [])
                    if valid_box(r.get('bbox')) and similarity(r.get('source_text',''),block['source_text']) >= .98
                    and box[0]-.01 <= r['bbox'][0] < r['bbox'][2] <= box[2]+.01
                    and box[1]-.01 <= r['bbox'][1] < r['bbox'][3] <= box[3]+.01
                    and box[3]-box[1] <= .06]
                if len(candidates) == 1:
                    anchor = candidates[0]
            if anchor:
                block['source_bbox'] = anchor
            block.update(role='body', excluded=False, decision_source='preserved', evidence=[], structure_warnings=[])
            all_blocks.append(block)
            edge = _edge(block)
            if edge:
                groups[(_running_key(block['source_text']), edge)].append(block)
    if legacy_pages:
        diagnostics.append(dict(reason='legacy_recognition', pages=legacy_pages,
                                detail='旧识别可能已省略内容；结构重算不能恢复缺失文字。'))

    # Assign each outline node to one concrete occurrence, preferring body over
    # an identical running title. Page-only bookmarks are not positive matches.
    matches = {}
    for node in nodes:
        candidates = []
        for block in all_blocks:
            if block.get('status') == 'source_image' or block['kind'] not in {'paragraph', 'heading'}:
                continue
            if node.get('page') is not None and block['page'] != node['page']:
                continue
            page_info = index.get('pages', {}).get(str(block['page']), {})
            if page_info.get('is_contents'):
                continue
            score = max(similarity(block['source_text'], node['title']),
                        similarity(block['source_text'], node.get('toc_title', '')))
            if number_key(block['source_text']) and number_key(node['title']) and number_key(block['source_text']) != number_key(node['title']):
                continue
            # Unmapped TOC entries need a unique complete title, never numbering alone.
            if score < .84:
                continue
            edge = _edge(block)
            # A page edge alone is not evidence against a real section title.
            # Penalize independently located repeated running regions only.
            box = block.get('source_bbox', block['bbox'])
            repeated = [b for b in native_margins.get((_running_key(block['source_text']), edge), [])
                        if abs(b['bbox'][1]-box[1]) < .012]
            if edge and (len({b['page'] for b in repeated}) >= 3 or
                         block.get('role_candidate') in MARGINAL):
                score -= .25
            if node.get('y') is not None and abs(box[1]-node['y']) < .15:
                score -= min(.1, abs(block['bbox'][1]-node['y'])/4)
            candidates.append((score, block['id'], [block]))
        for page in pages:
            if node.get('page') is not None and page['page'] != node['page']:
                continue
            if index.get('pages', {}).get(str(page['page']), {}).get('is_contents'):
                continue
            for first, second in zip(page['blocks'], page['blocks'][1:]):
                if (any(b['kind'] not in {'heading', 'paragraph'} or b.get('status') == 'source_image'
                        or b.get('role_candidate') in MARGINAL for b in (first, second))
                        or second['bbox'][3] <= .12
                        or not 0 <= second['bbox'][1]-first['bbox'][3] <= .025):
                    continue
                joined = first['source_text']+' '+second['source_text']
                score = max(similarity(joined, node['title']), similarity(joined, node.get('toc_title', '')))
                if score >= .9 and all(similarity(b['source_text'], node['title']) < .84 for b in (first, second)):
                    candidates.append((score, first['id'], [first, second]))
        candidates.sort(key=lambda t: (-t[0], t[1]))
        if candidates and candidates[0][0] >= .8:
            if len(candidates) > 1 and candidates[0][0]-candidates[1][0] < .05:
                diagnostics.append(dict(reason='ambiguous_outline_match', node=node['id'], page=node.get('page')))
            elif all(b['id'] not in matches for b in candidates[0][2]):
                for b in candidates[0][2]:
                    matches[b['id']] = node
            else:
                diagnostics.append(dict(reason='multiple_outline_nodes', block=candidates[0][1]))
    matched_nodes = {n['id'] for n in matches.values()}
    selected_pages = {p['page'] for p in pages}
    has_contents = any(p.get('is_contents') for p in index.get('pages', {}).values())
    for node in nodes:
        contents_node = (TOC_TITLE.fullmatch(node['title'].strip()) and
                         index.get('pages', {}).get(str(node.get('page')), {}).get('is_contents'))
        if not contents_node and node.get('page') in selected_pages and node['id'] not in matched_nodes:
            diagnostics.append(dict(reason='outline_heading_not_found', node=node['id'], page=node['page']))
    for block in all_blocks:
        number = block['page']
        page_info = index.get('pages', {}).get(str(number), {})
        edge = _edge(block)
        node = matches.get(block['id'])
        override = overrides.get(block['id'], block.get('structure_override'))
        role = block.get('role_candidate')
        def warn(reason):
            block['structure_warnings'].append(reason)
            diagnostics.append(dict(page=number, block=block['id'], bbox=block['bbox'], reason=reason))
        def decide(role, source, level=None, parent=None):
            block.update(role=role, decision_source=source, excluded=role in MARGINAL)
            block['evidence'].append(source)
            if role == 'heading':
                block.update(kind='heading', heading_level=level, parent_id=parent,
                             markdown='#'*level+' '+title_text(block['markdown']).replace('\n', ' '))
                if (CHAPTER_TITLE.match(title_text(block['source_text']))
                        or (has_contents and level == 1 and (node or source == 'review_override'))):
                    block['chapter_start'] = True
            elif block['kind'] == 'heading':
                block.update(kind='paragraph', markdown='**'+title_text(block['markdown'])+'**')
        if override is not None:
            override = validate_override(override)
            block['structure_override'] = override
            decide(override['role'], 'review_override', override.get('heading_level'), override.get('parent_id'))
            if override['role'] == 'heading':
                manual = node or dict(id='manual-'+block['id'],title=block['source_text'],page=number)
                manual.update(level=override['heading_level'],parent_id=override.get('parent_id'),evidence='review_override')
                if node is None:
                    nodes.append(manual)
                block['structure_node'] = manual['id']
            elif node:
                node['override_role'] = override['role']
                node['excluded_from_outline'] = True
            continue
        if page_info.get('is_contents') and page_info.get('entries') and contents_block(block, page_info):
            decide('toc_entry', 'rebuilt_contents')
            block['excluded'] = True
            continue
        if block.get('status') == 'source_image' or block['kind'] in {'figure', 'table', 'equation', 'uncertain'}:
            block['role'] = block['kind']
            continue
        if block['kind'] == 'footnote' or '[^' in block['markdown']:
            block['role'] = 'footnote' if block['kind'] == 'footnote' else 'body'
            continue
        if node:
            decide('heading', 'outline_title_match', node['level'], node.get('parent_id'))
            block['structure_node'] = node['id']
            continue
        if page_info.get('is_contents') and not page_info.get('entries') and not TOC_TITLE.match(block['source_text'].strip()):
            decide('toc_entry', 'contents_page')
            continue
        if is_body_label(block['source_text']) or is_body_label(block['markdown']):
            decide('body_label', 'semantic_label')
            if re.match(r'^\d+(?:\.\d+){2,}', title_text(block['source_text'])):
                warn('numbered_label_without_outline')
            continue
        if role in {'caption', 'toc_entry', 'body_label', 'footnote'}:
            decide(role, 'recognition_role')
            continue
        # Independent region evidence must match both text and the complete box.
        region_roles = []
        for region in page_info.get('regions', []):
            box, other = block.get('source_bbox', block['bbox']), region['bbox']
            area = (box[2]-box[0])*(box[3]-box[1])
            # Independent vision passes have coordinate jitter. Only compact
            # marginal blocks can use this tolerance, with the same source text
            # and the same edge; it never expands a deletion band over prose.
            near_margin = (edge and _edge(dict(region,markdown=region['source_text'])) == edge
                           and abs((box[1]+box[3]-other[1]-other[3])/2) <= .035
                           and abs((box[0]+box[2]-other[0]-other[2])/2) <= .12)
            if (_intersection(box, other) >= area*.8 or near_margin) and similarity(block['source_text'], region['source_text']) >= .85:
                region_roles.append(region['role'])
        peers = groups.get((_running_key(block['source_text']), edge), []) if edge else []
        peers = [b for b in peers if abs(b['bbox'][1]-block['bbox'][1]) <= .025
                 and abs(b['bbox'][0]-block['bbox'][0]) <= .12
                 and b['id'] not in matches and b.get('role_candidate') not in {'footnote', 'body_label', 'caption'}]
        repeat = len({b['page'] for b in peers}) >= 3
        tight = block.get('source_bbox', block['bbox'])
        native_peers = [b for b in native_margins.get((_running_key(block['source_text']),edge), [])
                        if abs(b['bbox'][1]-tight[1]) <= .012
                        and abs(b['bbox'][0]-tight[0]) <= .12]
        native_repeat = len({b['page'] for b in native_peers}) >= 3
        native_match = any(b['page']==number and similarity(b['source_text'],block['source_text'])>=.85
                           and _intersection(b['bbox'],tight) >=
                           (tight[2]-tight[0])*(tight[3]-tight[1])*.8
                           for b in native_peers)
        # Short-lived section headers still share the book's running band and
        # smaller font. This evidence is independent of the model's role label.
        font_weights = defaultdict(int)
        note_boxes = [b.get('source_bbox',b['bbox']) for b in all_blocks if b['page']==number
                      and (b['kind']=='footnote' or b.get('role_candidate')=='footnote')]
        for line in page_info.get('lines', []):
            # Long notes can contain more characters than the body. They must
            # not make the running header look like the page's normal font.
            box=line['bbox']
            if box[1]<.1 or any(n[0]-.01<=box[0] and box[2]<=n[2]+.01
                               and n[1]-.01<=box[1] and box[3]<=n[3]+.01 for n in note_boxes):
                continue
            font_weights[round(line.get('font_size',0))] += len(line['source_text'])
        body_font = max(font_weights,key=font_weights.get) if font_weights else 0
        small_native = any(b['page']==number and b.get('font_size',body_font)<body_font*.9 for b in native_peers)
        band_match = any(b['page']==number and b.get('font_size',body_font)<body_font*.9
            and len(native_bands[(round(b['bbox'][1],2),round(b.get('font_size',0)),edge)])>=3
            for b in native_peers)
        native_repeat = (native_repeat or band_match) and (small_native or not body_font)
        if edge=='bottom' and role=='running_footer' and 'source_bbox' in block:
            small = [l for l in page_info.get('lines',[]) if similarity(l['source_text'],block['source_text'])>=.94
                     and l.get('font_size',body_font)<body_font*.9]
            if small:
                region_roles.append(role)
        numeric = _page_number(block['source_text'])
        sequence = False
        if numeric and (peers or native_peers):
            support = defaultdict(set)
            for b in peers+native_peers:
                parsed = _page_number(b['source_text'])
                if parsed and parsed[0] == numeric[0]:
                    support[b['page']-parsed[1]].add(b['page'])
            offset = number-numeric[1]
            # Evaluate the candidate's run, not unanimity of every numeric glyph.
            sequence = len(support[offset]) >= 3 and (native_match or repeat)
            if index.get('page_map'):
                sequence = sequence and any(s['style']==numeric[0] and s['offset']==offset
                    and s['physical_start'] <= number <= s['physical_end'] for s in index['page_map'])
        structural_start = any(n.get('page') == number and n['level'] == 1 for n in nodes)
        protected_heading = (role == 'heading' or (structural_start and block['kind'] == 'heading')) and not (native_repeat and native_match)
        if edge and not protected_heading and (sequence or
                (repeat and not numeric and (role in MARGINAL or any(r in MARGINAL for r in region_roles))) or
                (native_repeat and native_match and not numeric) or
                (role in MARGINAL and role in region_roles)):
            decide('page_number' if numeric else 'running_header' if edge == 'top' else 'running_footer',
                   'page_sequence' if sequence else 'native_repeated_region' if native_repeat and native_match else 'repeated_margin' if repeat else 'independent_region')
            continue
        if role in MARGINAL or (edge and repeat):
            warn('uncertain_margin_or_mixed_block')
        if block['kind'] == 'heading' or role == 'heading':
            if edge:
                warn('unconfirmed_edge_heading')
            level = numbered_level(block['source_text']) or numbered_level(block['markdown'])
            original = re.match(r'^\s*(#{1,6})\s', block['markdown'])
            level = level or (len(original[1]) if original else 1)
            parents = [n for n in nodes if n.get('page') is not None and n['page'] <= number and n['level'] < level]
            parent = max(parents,key=lambda n:(n['page'],n['level']))['id'] if parents else None
            decide('heading', 'provisional_recognition', level, parent)
            provisional = dict(id='candidate-'+block['id'], title=block['source_text'], page=number,
                               level=level, parent_id=parent, evidence='provisional_recognition')
            nodes.append(provisional)
            block['structure_node'] = provisional['id']
            warn('unconfirmed_heading_hierarchy')
        else:
            block['excluded'] = False
    # Group only adjacent fragments explicitly tied to the same structure node;
    # retain every source block and provenance, even when rendering a single title.
    for page in pages:
        previous = None
        for block in page['blocks']:
            if (previous and block.get('structure_node') and block.get('structure_node') == previous.get('structure_node')
                    and block['role'] == previous['role'] == 'heading'
                    and 0 <= block['bbox'][1]-previous['bbox'][3] <= .025):
                if block['id'] not in previous.get('translation_source_ids', []):
                    previous['markdown'] += ' '+title_text(block['markdown'])
                previous.setdefault('source_ids', [previous['id']]).append(block['id'])
                block.update(excluded=True, merged_into=previous['id'])
            else:
                previous = block
        page['structure_version'] = STRUCTURE_VERSION
        for block in page['blocks']:
            block['structure_rendered'] = {k:copy.deepcopy(block[k]) for k in ('kind','markdown','bbox')}
    from semantic_document import bind_notes
    visible_nodes = {b.get('structure_node') for b in all_blocks if b['role'] == 'heading' and not b['excluded']}
    for p in pages:
        for entry in p.get('contents_entries', []):
            if entry.get('node_id') not in visible_nodes:
                diagnostics.append(dict(reason='contents_target_not_in_output', page=p['page'], title=entry['title']))
        if 'contents_entries' in p and not p['contents_entries']:
            diagnostics.append(dict(reason='contents_entries_unavailable', page=p['page']))
    notes, note_diagnostics = bind_notes(pages, index)
    diagnostics.extend(note_diagnostics)
    for page in pages:
        for block in page['blocks']:
            if block.get('translation_warning'):
                diagnostics.append(dict(page=block['page'],block=block['id'],bbox=block['bbox'],
                                        reason='translation_failed',detail=block['translation_warning']))
            block['structure_rendered'] = {k:copy.deepcopy(block[k]) for k in ('kind','markdown','bbox')}
    return dict(pages=pages, tree=nodes, notes=notes, diagnostics=diagnostics, version=STRUCTURE_VERSION,
                key=fingerprint([STRUCTURE_VERSION, index.get('key'), raw_pages, overrides]))


def resolve_cached(raw_pages, source_index, cache, overrides=None):
    from semantic_document import VERSION as SEMANTIC_VERSION
    key = fingerprint([STRUCTURE_VERSION, SEMANTIC_VERSION, source_index, raw_pages, overrides or {}])
    path = Path(cache)/('structure-'+key+'.json')
    value = _read(path)
    if value and value.get('cache_key') == key:
        return value
    value = resolve_document_structure(raw_pages, source_index, overrides)
    value['cache_key'] = key
    _write(path, value)
    return value
