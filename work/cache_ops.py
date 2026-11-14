"""User-directed cache maintenance. Never called automatically or by an AI tool.

The new kernel keeps one shared translation cache for every document (BabelDOC
stores it in ``~/.cache/babeldoc``), so cache maintenance is split in two:
documents are listed read-only from the run registry, and only the shared
engine cache can be cleared. Exported PDFs are never touched here.
"""
import os
import shutil
from pathlib import Path

from index import forget, load as load_runs

ENGINE_ID = 'engine'
ENGINE_LABEL = '翻译引擎共享缓存（BabelDOC）'


def engine_cache_dir():
    return Path.home() / '.cache' / 'babeldoc'


def _is_link(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def _assert_under(root, target):
    root, target = Path(root).resolve(), Path(target).resolve()
    if target != root and not target.is_relative_to(root):
        raise ValueError('缓存路径超出允许范围。')
    return target


def _walk_guard(root):
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            item = Path(base) / name
            if _is_link(item):
                raise ValueError('缓存含链接，拒绝清理。')


def tree_size(root):
    root = Path(root)
    if not root.is_dir() or _is_link(root):
        return 0
    total = 0
    for base, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            try:
                item = Path(base) / name
                if not _is_link(item):
                    total += item.stat().st_size
            except OSError:
                continue
    return total


def cache_list(data_dir):
    rows = []
    documents = {}
    for entry in load_runs(data_dir):
        identity = entry['identity']
        row = documents.get(identity)
        if row is None:
            documents[identity] = row = {
                'id': identity,
                'name': entry.get('name') or Path(entry.get('source') or '').name or identity,
                'source': entry.get('source') or '',
                'bytes': 0,
                'lastUsed': 0,
                'blocked': '',
            }
        row['bytes'] += int(entry.get('bytes') or 0)
        row['lastUsed'] = max(row['lastUsed'], int(entry.get('at') or 0))
    rows.extend(documents.values())

    engine = engine_cache_dir()
    blocked = ''
    try:
        if _is_link(engine):
            blocked = '引擎缓存目录含链接，拒绝清理。'
    except OSError:
        blocked = ''
    rows.append({
        'id': ENGINE_ID,
        'name': ENGINE_LABEL,
        'source': str(engine),
        'bytes': tree_size(engine),
        'lastUsed': int(engine.stat().st_mtime * 1000) if engine.exists() else 0,
        'blocked': blocked,
    })
    return sorted(rows, key=lambda row: row['lastUsed'], reverse=True)


def clear_cache(data_dir, identity):
    if identity == ENGINE_ID:
        return _clear_engine_cache()
    removed = forget(data_dir, identity)
    return {'cleared': bool(removed), 'id': identity, 'shared': False}


def _clear_engine_cache():
    engine = engine_cache_dir()
    if not engine.exists():
        return {'cleared': False, 'id': ENGINE_ID, 'shared': True}
    if _is_link(engine):
        raise ValueError('引擎缓存目录是链接，拒绝清理。')
    _assert_under(engine.parent, engine)
    if engine.name != 'babeldoc' or engine.parent.name != '.cache':
        raise ValueError('引擎缓存目录异常，拒绝清理。')
    _walk_guard(engine)
    shutil.rmtree(engine)
    return {'cleared': True, 'id': ENGINE_ID, 'shared': True, 'bytes': 0}
