"""Document-wide note identities and immutable, bounded translation units.

No renderer or network dependencies. Source geometry remains attached to every
fragment; page boundaries do not define translation batches.
"""
import copy
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = 'semantic-v3'
SUPERSCRIPTS = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
DEFINITION = re.compile(r'^\s*\[\^([^\]]+)\]:\s*')
PROTECTED = re.compile(r'\$\$[\s\S]*?\$\$|(?<!\$)\$[^$\n]+\$|\[\^[^\]]+\]|`[^`]+`')


def marker_of(block):
    original = re.match(r'^\s*([*†‡])', block.get('source_text',''))
    if original:
        return original[1]
    match = DEFINITION.match(block.get('markdown', ''))
    if match and not match[1].startswith('note-'):
        return match[1]
    if block.get('note_marker'):
        return block['note_marker']
    source = block.get('source_text', '').translate(str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789'))
    match = re.match(r'^\s*(\d{1,3}|[*†‡§¶])(?=\D|$)', source)
    return match[1] if match else None


def marker_pattern(marker):
    escaped = re.escape(marker)
    forms = [r'\[\^' + escaped + r'\](?!:)',
             r'\$\s*\^\{?' + escaped + r'\}?\s*\$']
    if marker.isdecimal():
        forms.append(re.escape(marker.translate(SUPERSCRIPTS)))
    else:
        # Bare symbols are accepted only as terminal note markers, not operators.
        forms.append(escaped + r'(?=\s*$)')
    return re.compile('|'.join(forms))


def bind_notes(pages, source_index=None):
    """Mutate a *derived* document only; never silently turn a note into prose."""
    diagnostics, notes = [], []
    for page in pages:
        page['semantic_document'] = True
    blocks = [b for p in pages for b in p['blocks']]
    by_id = {b['id']: b for b in blocks}
    markers = {b['id']:marker_of(b) for b in blocks}
    for b in blocks:
        for field in ('note_id', 'note_anchors', 'note_marker', 'note_unlinked'):
            b.pop(field, None)
    previous_note = None
    previous_fragment = None
    for b in blocks:
        if b.get('role') != 'footnote' and b['kind'] != 'footnote':
            continue
        if (previous_note and previous_fragment['page'] + 1 == b['page']
                and previous_fragment.get('continues_next') and b.get('continues_previous')
                and markers[b['id']] in (None, markers[previous_note['id']])):
            if b['id'] not in previous_note.get('translation_source_ids', []):
                previous_note['markdown'] += ' ' + DEFINITION.sub('', b['markdown'])
            previous_note.setdefault('source_ids', [previous_note['id']]).append(b['id'])
            b.update(excluded=True, merged_into=previous_note['id'])
        else:
            previous_note = b
        previous_fragment = b
    for b in blocks:
        if b.get('excluded') or b.get('status') == 'source_image':
            continue
        if b.get('role') != 'footnote' and b['kind'] != 'footnote':
            continue
        b.update(kind='footnote', role='footnote')
        marker = markers[b['id']]
        note_id = 'note-' + b['id']
        override = b.get('note_override')
        original = b.get('source_text','').strip()
        if (override is None and re.match(r'^(?:\d{4}-\d{3}[\dXx]|©|Copyright)', original, re.I)
                and re.search(r'doi|rights reserved|copyright|©', original, re.I)):
            b.update(note_id=note_id, note_marker=None, note_anchors=[], note_unlinked=False,
                     note_type='publication', markdown=DEFINITION.sub('',b['markdown']).strip())
            notes.append(dict(id=note_id,block=b['id'],marker=None,anchors=[],type='publication'))
            continue
        b.pop('note_type',None)
        candidates = [a for a in blocks if a['page'] == b['page'] and a is not b
                      and not a.get('excluded') and a.get('role') not in {'footnote', 'heading'}
                      and a['kind'] == 'paragraph']
        pattern = re.compile(marker_pattern(marker).pattern + '|'+re.escape('[^'+note_id+']')) if marker else None
        anchors = [a for a in candidates if pattern and pattern.search(a['markdown'])]
        if marker in {'*','†','‡'}:
            for a in candidates:
                if is_author_list(a.get('source_text','')):
                    author_marker=re.compile(re.escape(marker)+r'(?=\s*[,;，；]|\s*$)')
                    if author_marker.search(a['markdown']):
                        if a not in anchors: anchors.append(a)
        if not anchors and marker:
            evidence = (source_index or {}).get('pages',{}).get(str(b['page']),{})
            superscripts = [s for line in evidence.get('lines',[]) for s in line.get('superscripts',[])
                            if s['text'].strip() == marker]
            plain = re.compile(r'(?<![\d.])'+re.escape(marker)+r'(?![\d.])')
            for a in candidates:
                box=a['bbox']
                supported=any(box[0]<=s['bbox'][0]<=s['bbox'][2]<=box[2]
                              and box[1]<=s['bbox'][1]<=s['bbox'][3]<=box[3] for s in superscripts)
                if supported and len(plain.findall(a['markdown']))==1:
                    a['markdown']=plain.sub('[^'+note_id+']',a['markdown'])
                    anchors.append(a)
        if override is not None:
            ids = override.get('anchors', [])
            if (not isinstance(ids, list) or len(ids) != len(set(ids))
                    or any(i not in by_id or by_id[i]['kind'] != 'paragraph' for i in ids)):
                raise ValueError('脚注覆盖包含无效正文 ID')
            anchors = [by_id[i] for i in ids]
        # Two separate notes with the same page marker are ambiguous, not a merge.
        siblings = [a for a in blocks if a is not b and a['page'] == b['page']
                    and not a.get('excluded') and (a.get('role') == 'footnote' or a['kind'] == 'footnote')
                    and marker and markers[a['id']] == marker]
        if siblings and override is None:
            anchors = []
        b.update(note_id=note_id, note_marker=marker, note_anchors=[a['id'] for a in anchors],
                 note_unlinked=not bool(anchors))
        body = DEFINITION.sub('', b['markdown']).strip()
        if anchors:
            for a in anchors:
                replacement = '[^' + note_id + ']'
                author_marker = (re.compile(re.escape(marker)+r'(?=\s*[,;，；]|\s*$)')
                                 if marker in {'*','†','‡'} and is_author_list(a.get('source_text','')) else None)
                if author_marker and author_marker.search(a['markdown']):
                    a['markdown'] = author_marker.sub(lambda _:replacement,a['markdown'].replace(replacement,''))
                elif pattern and pattern.search(a['markdown']):
                    a['markdown'] = pattern.sub(lambda _: replacement, a['markdown'])
                elif replacement not in a['markdown']:
                    a['markdown'] += replacement
            b['markdown'] = '[^' + note_id + ']: ' + body
        else:
            b['markdown'] = body
            diagnostics.append(dict(page=b['page'], block=b['id'], bbox=b['bbox'],
                                    reason='unlinked_footnote', marker=marker))
        notes.append(dict(id=note_id, block=b['id'], marker=marker, anchors=b['note_anchors']))
    defined = {n['id'] for n in notes if n['anchors']}
    for b in blocks:
        if b.get('excluded'):
            continue
        for ref in sorted(set(re.findall(r'\[\^([^\]]+)\](?!:)',b['markdown'])) - defined):
            diagnostics.append(dict(page=b['page'],block=b['id'],bbox=b['bbox'],
                                    reason='unresolved_note_reference',marker=ref))
    return notes, diagnostics


def protect(text):
    values = []
    def replace(match):
        key = '⟦KEEP' + str(len(values)) + '⟧'
        values.append((key, match[0]))
        return key
    return PROTECTED.sub(replace, text), values


def restore(text, values):
    expected = Counter(k for k, _ in values)
    if Counter(re.findall(r'⟦KEEP\d+⟧', text)) != expected:
        raise ValueError('翻译改变了公式或引用占位符')
    for key, value in values:
        text = text.replace(key, value)
    if re.search(r'!\[|<\s*(?:script|iframe|img)|\\(?:input|include|write|def)\b', text):
        raise ValueError('翻译返回了不允许的对象或命令')
    return text


def retry_payload(payload, batch, failures):
    """On the last attempt, keep damaged placeholders out of the model's output."""
    units, slots = [], {}
    for u, row in zip(batch, payload['units']):
        if '占位符' not in failures.get(u['id'], '') or len(u['protected']) < 2:
            units.append(row)
            continue
        pieces = re.split(r'(⟦KEEP\d+⟧)', row['text'])
        slots[u['id']] = []
        for i, piece in enumerate(pieces):
            if i % 2 or not re.search(r'[A-Za-z]', piece):
                slots[u['id']].append((None, piece))
            else:
                key = f"{u['id']}/text-{i}"
                units.append(dict(row, id=key, text=piece))
                slots[u['id']].append((key, piece))
    return dict(payload, units=units), slots


def units_for(pages, tree):
    nodes = {n['id']: n for n in tree}
    context, units = [], []
    previous_page = None
    for p in pages:
        if previous_page is None or p['page'] != previous_page + 1:
            prior = [n for n in tree if n.get('page') is not None and n['page'] < p['page']
                     and not n.get('excluded_from_outline')]
            node = max(prior,key=lambda n:(n['page'],n.get('level',1))) if prior else None
            context, seen = [], set()
            while node and node['id'] not in seen:
                seen.add(node['id'])
                context.insert(0,node.get('title',''))
                node=nodes.get(node.get('parent_id'))
        previous_page=p['page']
        for b in p['blocks']:
            if b.get('excluded'):
                continue
            if b.get('role') == 'heading':
                node = nodes.get(b.get('structure_node'))
                path, seen = [], set()
                while node and node['id'] not in seen:
                    seen.add(node['id'])
                    path.insert(0, node.get('title', ''))
                    node = nodes.get(node.get('parent_id'))
                context = path or [b.get('source_text', '')]
            if b['kind'] not in {'paragraph', 'heading', 'footnote'}:
                continue
            # Recognition Markdown retains math syntax; source_text is evidence.
            raw = b['markdown']
            prefix = DEFINITION.match(raw)
            heading = re.match(r'^#{1,6}\s+', raw)
            fixed = prefix[0] if prefix else heading[0] if heading else ''
            raw = raw[len(fixed):]
            protected, values = protect(raw)
            # Split only at sentence boundaries outside protected objects.
            sentences = re.split(r'(?<=[.!?。！？])\s+', protected)
            fragments, current = [], ''
            for sentence in sentences:
                if current and len(current + sentence) > 6000:
                    fragments.append(current)
                    current = ''
                current += (' ' if current else '') + sentence
            if current:
                fragments.append(current)
            for i, fragment in enumerate(fragments):
                units.append(dict(id=b['id'] + ':' + str(i), block=b['id'], page=b['page'],
                    text=fragment, protected=[v for v in values if v[0] in fragment],
                    prefix=fixed if i == 0 else '', chapter=list(context),
                    role=b.get('role', 'body'), role_candidate=b.get('role_candidate'), anchors=b.get('note_anchors', []),
                    continues_previous=b.get('continues_previous', False),
                    continues_next=b.get('continues_next', False)))
    previous = None
    for u in units:
        u['paragraph_id'] = u['block']
        if (previous and u['role'] == previous['role'] == 'body'
                and previous['page'] + 1 == u['page'] and previous['continues_next']
                and u['continues_previous'] and previous['chapter'] == u['chapter']):
            u['paragraph_id'] = previous['paragraph_id']
        if u['role'] != 'footnote':
            previous = u
    return units


def batches_for(units):
    batches, batch, budget = [], [], 0
    for unit in units:
        # Conservative token budget: CJK characters cost more than Latin text.
        cost = sum(1 if ord(c) > 127 else .33 for c in unit['text'])
        if batch and (len(batch) >= 8 or budget + cost > 2000
                      or unit['chapter'] != batch[0]['chapter']):
            batches.append(batch)
            batch, budget = [], 0
        batch.append(unit)
        budget += cost
    if batch:
        batches.append(batch)
    return batches


def is_author_list(text):
    """Conservative exemption for comma-separated personal names, not prose."""
    parts = text.split(',')
    if len(parts) < 2:
        return False
    names = 0
    for part in parts:
        words = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", part)
        words = [w for w in words if w not in {'a', 'b', 'c', 'd', 'and'}]
        if not words:  # separate affiliation/star marker
            continue
        if not 2 <= len(words) <= 5 or not all(w[0].isupper() for w in words):
            return False
        names += 1
    return names >= 2


def translate_document(pages, tree, cache, model_config, request, glossary=None, workers=4):
    """Translate fixed IDs; failed batches preserve originals with diagnostics."""
    pages = copy.deepcopy(pages)
    units = units_for(pages, tree)
    by_id = {b['id']: b for p in pages for b in p['blocks']}
    translated, diagnostics = {}, []
    folder = Path(cache)/'semantic-translations'
    folder.mkdir(parents=True, exist_ok=True)
    def run_batch(batch):
        start = units.index(batch[0])
        end = units.index(batch[-1]) + 1
        anchor_ids = {a for u in batch for a in u['anchors']}
        note_context = [dict(id=u['id'], text=u['text']) for u in units
                        if u['block'] in anchor_ids or any(a in {b['block'] for b in batch} for a in u['anchors'])]
        payload = dict(chapter=batch[0]['chapter'], glossary=glossary or {},
                       previous=units[start-1]['text'][-2000:] if start and batch[0]['page']-units[start-1]['page']<=1 else '',
                       following=units[end]['text'][:2000] if end < len(units) and units[end]['page']-batch[-1]['page']<=1 else '',
                       note_context=[dict(n,text=n['text'][:2000]) for n in note_context[:8]],
                       units=[dict(id=u['id'], text=u['text'], paragraph_id=u['paragraph_id']) for u in batch])
        key = hashlib.sha256(json.dumps([VERSION, model_config, payload], ensure_ascii=False,
                                       sort_keys=True).encode()).hexdigest()
        path = folder/(key+'.json')
        error = None
        accepted = {}
        accepted_raw = {}
        failures = {}
        for attempt in range(3):
            try:
                if any(sum(1 if ord(c)>127 else .33 for c in u['text'])>2000 for u in batch):
                    raise ValueError('超长单元缺少安全句子边界，需要人工拆分')
                query, slots = retry_payload(payload, batch, failures) if attempt == 2 else (payload, {})
                response = json.loads(path.read_text('utf-8')) if path.exists() else request(query, error)
                rows = response['units']
                if len(rows) != len(query['units']) or {r['id'] for r in rows} != {r['id'] for r in query['units']}:
                    raise ValueError('翻译单元 ID 缺失或重复')
                values = {r['id']: r['text'] for r in rows}
                for key, fragments in slots.items():
                    if any(not isinstance(values[k], str) or not values[k].strip() for k, _ in fragments if k):
                        raise ValueError('翻译返回空片段')
                    values[key] = ''.join(values[k] if k else original for k, original in fragments)
                failures = {}
                for u in batch:
                    if u['id'] in accepted:
                        continue
                    try:
                        value = restore(values[u['id']], u['protected'])
                        if not value.strip():
                            raise ValueError('翻译返回空内容')
                        is_reference = any(re.search(r'references|bibliography|参考文献', title, re.I) for title in u['chapter'])
                        publication = (u.get('role_candidate') == 'running_footer'
                                       and re.search(r'©|copyright|\bDOI\b|\bISBN\b', u['text'], re.I))
                        if (not is_reference and not publication and not is_author_list(u['text']) and len(re.findall('[A-Za-z]', u['text'])) > 40
                                and not re.search('[\u4e00-\u9fff]', values[u['id']])):
                            raise ValueError('英文正文未翻译，保留原文等待核验')
                        accepted[u['id']] = value
                        accepted_raw[u['id']] = values[u['id']]
                    except (ValueError, KeyError, TypeError) as exc:
                        failures[u['id']] = str(exc)
                if failures:
                    raise ValueError('; '.join(f'{key}: {value}' for key, value in failures.items()))
                translated.update(accepted)
                temp = path.with_suffix('.tmp')
                # Cache complete units with their placeholders, including valid
                # neighbours retained from earlier attempts.
                cached = {'units':[dict(id=u['id'], text=accepted_raw[u['id']]) for u in batch]}
                temp.write_text(json.dumps(cached, ensure_ascii=False), 'utf-8')
                temp.replace(path)
                break
            except (ValueError, KeyError, TypeError, TimeoutError, ConnectionError) as exc:
                error = str(exc)
                if path.exists():
                    path.unlink()
        else:
            for u in batch:
                if u['id'] in accepted:
                    translated[u['id']] = accepted[u['id']]
                    continue
                error = failures.get(u['id'], error)
                translated[u['id']] = restore(u['text'], u['protected'])
                by_id[u['block']]['translation_warning'] = error
                diagnostics.append(dict(page=u['page'], block=u['block'], reason='translation_failed', detail=error))
    with ThreadPoolExecutor(max_workers=max(1,min(8,workers))) as pool:
        list(pool.map(run_batch, batches_for(units)))
    diagnostics.sort(key=lambda d:(d['page'],d['block']))
    grouped = {}
    for u in units:
        grouped.setdefault(u['block'], []).append(u['prefix'] + translated[u['id']])
    for identifier, fragments in grouped.items():
        b = by_id[identifier]
        b['markdown'] = ' '.join(fragments)
        b['translation_version'] = VERSION
        b['translation_source_ids'] = list(b.get('source_ids',[b['id']]))
        # Re-resolution must restore the accepted translation, not source prose.
        b['structure_original']['markdown'] = b['markdown']
        b['structure_rendered']['markdown'] = b['markdown']
    return dict(pages=pages, units=units, diagnostics=diagnostics, version=VERSION)
