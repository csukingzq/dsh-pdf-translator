"""Small run registry used by the cache panel.

Only metadata is stored here; translated PDFs stay in the user's output
directory and are never removed by cache maintenance.
"""
import json
import os
import time
from pathlib import Path

MAX_ENTRIES = 200
_FILE = Path('work') / 'runs.json'


def _path(data_dir):
    return Path(data_dir) / _FILE


def load(data_dir):
    path = _path(data_dir)
    try:
        data = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict) and row.get('identity') and row.get('runDir')]


def _save(data_dir, rows):
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(rows[-MAX_ENTRIES:], ensure_ascii=False, indent=2), 'utf-8')
    os.replace(temp, path)


def record(data_dir, entry):
    rows = [row for row in load(data_dir) if row.get('runDir') != entry['runDir']]
    rows.append({
        'identity': str(entry['identity']),
        'source': str(entry.get('source') or ''),
        'name': str(entry.get('name') or ''),
        'runDir': str(entry['runDir']),
        'output': str(entry.get('output') or ''),
        'dual': str(entry.get('dual') or ''),
        'pages': str(entry.get('pages') or 'all'),
        'bytes': int(entry.get('bytes') or 0),
        'at': int(entry.get('at') or time.time() * 1000),
    })
    _save(data_dir, rows)
    return rows[-1]


def forget(data_dir, identity):
    rows = load(data_dir)
    keep = [row for row in rows if row.get('identity') != identity]
    if len(keep) != len(rows):
        _save(data_dir, keep)
    return len(rows) - len(keep)
