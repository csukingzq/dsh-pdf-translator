"""Page range parsing shared by the panel, tools and the engine host.

The UI validates before enabling Start; the Python bridge validates again so an
agent tool call cannot request pages outside the document.
"""
import re

_RANGE = re.compile(r'\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*')


def parse(spec):
    """Return None for "all", otherwise a list of inclusive 1-based ranges."""
    text = str(spec if spec is not None else '').strip()
    if not text or text.lower() in {'all', '全部'}:
        return None
    text = text.replace(' ', '')
    if not _RANGE.fullmatch(text):
        raise ValueError('页码格式错误，请填写 1-5 或 1,3,5-8。')
    ranges = []
    for part in text.split(','):
        ends = [int(value) for value in part.split('-')]
        first, last = ends[0], ends[-1]
        if first < 1 or last < first:
            raise ValueError('页码超出范围或起始页大于结束页。')
        ranges.append((first, last))
    return ranges


def page_indices(spec, count):
    """Sorted 0-based indices for a validated page spec."""
    if not isinstance(count, int) or count < 0:
        raise ValueError('无效的页数。')
    ranges = parse(spec)
    if ranges is None:
        return list(range(count))
    selected = set()
    for first, last in ranges:
        if last > count:
            raise ValueError(f'页码超出范围，请填写 1–{count} 页。')
        selected.update(range(first - 1, last))
    return sorted(selected)


def collapse(indices):
    """[1, 2, 3, 5] -> "1-3,5"; the form pdf2zh-next accepts for --pages."""
    if not indices:
        raise ValueError('没有可翻译的页面。')
    parts = []
    start = previous = indices[0]
    for value in indices[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(f'{start}-{previous}' if previous > start else str(start))
        start = previous = value
    parts.append(f'{start}-{previous}' if previous > start else str(start))
    return ','.join(parts)


def normalize(spec, count):
    """"all" or a compact 1-based range string for the engine."""
    indices = page_indices(spec, count)
    if not indices:
        raise ValueError('PDF 没有可处理的页面。')
    if len(indices) == count:
        return 'all'
    return collapse([index + 1 for index in indices])
