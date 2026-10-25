"""Detect the source page column grid so a reflowed translation keeps its columns.

The vision pass already returns a normalized box for every block, but a linear
Markdown stream loses which blocks sat side by side. Reading the original page
geometry is deterministic and cheap, so the gap between text columns is measured
here and the same grid is applied to every block.
"""
import statistics

import pymupdf

# A text line wider than this is a spanning element (title, table row), not a
# column body line; letting it vote would fill the gutter between columns.
WIDE_LINE_RATIO = 0.62
# Block boxes: a block wider than this cannot belong to one column.
WIDE_BLOCK_RATIO = 0.72
BINS = 200
# A few spanning rows may graze the gutter, so a band is "empty" if almost no
# body line covers it.
EMPTY_SHARE = 0.05
MIN_GUTTER = 0.006
MAX_GUTTER = 0.12
MIN_SIDE_SHARE = 0.15
NESTED_SIDE_SHARE = 0.12
MAX_COLUMNS = 3
MIN_BODY_LINES = 8
# Blocks are reported by the model, so a box that merely grazes the gutter edge
# still belongs to its column. A spanning box has to reach well past the gutter
# centre on both sides.
SPAN_OVERHANG = 0.05
GUTTER_TOLERANCE = 0.004


def _text_lines(page):
    """Normalized (x0, x1) of every non-empty text line on the page."""
    width = page.rect.width
    lines = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text = ''.join(span['text'] for span in line['spans']).strip()
            if not text:
                continue
            lines.append((line['bbox'][0]/width, line['bbox'][2]/width))
    return lines


def _block_lines(blocks):
    """Fallback geometry for pages without a text layer (scanned or vector)."""
    lines = []
    for block in blocks or []:
        box = block.get('bbox')
        if isinstance(box, list) and len(box) == 4:
            lines.append((box[0], box[2]))
    return lines


def _profile(body):
    """Count body lines per horizontal bin, so gaps between columns are visible."""
    profile = [0]*BINS
    for x0, x1 in body:
        first = max(0, min(BINS-1, int(x0*BINS)))
        last = max(first, min(BINS-1, int(x1*BINS)-1))
        for index in range(first, last+1):
            profile[index] += 1
    return profile


def _gutter(body, profile, low, high, share):
    """Widest near-empty band inside [low, high] that separates substantial text."""
    limit = max(1, round(EMPTY_SHARE*len(body)))
    best = None
    index = max(0, int(low*BINS))
    stop = min(BINS, int(high*BINS))
    while index < stop:
        if profile[index] > limit:
            index += 1
            continue
        end = index
        while end < stop and profile[end] <= limit:
            end += 1
        loose_start, loose_end = index/BINS, end/BINS
        left = [x1 for x0, x1 in body if x1 <= loose_start + GUTTER_TOLERANCE]
        right = [x0 for x0, x1 in body if x0 >= loose_end - GUTTER_TOLERANCE]
        if (MIN_GUTTER <= loose_end-loose_start <= MAX_GUTTER
                and len(left) >= share*len(body) and len(right) >= share*len(body)):
            # Ragged edges drift the empty band; the gutter is the space between
            # the last left line and the first right line.
            start, finish = max(left), min(right)
            if MIN_GUTTER <= finish-start <= MAX_GUTTER and (best is None or finish-start > best[2]):
                best = (start, finish, finish-start)
        index = end
    return best


def page_grid(page, blocks=None):
    """Column count and gutter bands for one page."""
    lines = _text_lines(page)
    body = [line for line in lines if line[1]-line[0] < WIDE_LINE_RATIO]
    if len(body) < MIN_BODY_LINES:
        body = [line for line in _block_lines(blocks) if line[1]-line[0] < WIDE_BLOCK_RATIO]
    if len(body) < 3:
        return {'columns': 1, 'gutters': [], 'lines': len(body)}
    profile = _profile(body)
    first = _gutter(body, profile, 0.22, 0.78, MIN_SIDE_SHARE)
    if first is None:
        return {'columns': 1, 'gutters': [], 'lines': len(body)}
    gutters = [first]
    # Three-column journals have a second gutter inside one of the halves.
    for low, high in ((0.0, first[0]), (first[1], 1.0)):
        nested = _gutter(body, profile, low+0.05, high-0.05, NESTED_SIDE_SHARE)
        if nested is not None:
            gutters.append(nested)
            break
    gutters.sort()
    return {'columns': len(gutters)+1, 'gutters': [[round(a, 4), round(b, 4)] for a, b, _ in gutters],
            'lines': len(body)}


def detect(source, pages=None):
    """Document-level grid: dominant column count plus median gutter positions.

    A title page or a full-width figure page must not decide the whole layout,
    so the count is taken from pages that actually carry body text and the
    gutter position is the median over those pages.
    """
    by_page = {}
    with pymupdf.open(source) as doc:
        for page in pages or []:
            index = int(page.get('page', 0))-1
            if 0 <= index < len(doc):
                by_page[index] = page.get('blocks')
        grids = {}
        for index in range(len(doc)):
            grids[index+1] = page_grid(doc[index], by_page.get(index))
    votes = [grid['columns'] for grid in grids.values() if grid['lines'] >= MIN_BODY_LINES]
    columns = max(set(votes), key=votes.count) if votes else 1
    columns = min(columns, MAX_COLUMNS)
    if columns < 2:
        return {'columns': 1, 'gutters': [], 'pages': {p: g['columns'] for p, g in grids.items()}}
    samples = [grid for grid in grids.values() if grid['columns'] == columns and grid['lines'] >= MIN_BODY_LINES]
    gutters = []
    for slot in range(columns-1):
        edges = [grid['gutters'][slot] for grid in samples if len(grid['gutters']) > slot]
        if not edges:
            gutters, columns = [], 1
            break
        gutters.append([round(statistics.median(e[0] for e in edges), 4),
                        round(statistics.median(e[1] for e in edges), 4)])
    return {'columns': columns, 'gutters': gutters,
            'pages': {p: g['columns'] for p, g in grids.items()}}


def grid_for(source, pages=None, override=0):
    """Detected grid, or the manually requested column count.

    A forced count that disagrees with the detected one has no measured gutter
    to trust, so it is split into equal columns instead.
    """
    grid = detect(source, pages)
    override = int(override or 0)
    if not override or override == grid['columns']:
        return grid
    if override < 2:
        return {'columns': 1, 'gutters': [], 'pages': grid['pages']}
    step = 1/override
    return {'columns': override,
            'gutters': [[round(i*step-0.01, 4), round(i*step+0.01, 4)] for i in range(1, override)],
            'pages': grid['pages']}


def spans(bbox, grid):
    """True when the block belongs to the full text width rather than one column."""
    if not grid or grid.get('columns', 1) < 2:
        return True
    if bbox[2]-bbox[0] > WIDE_BLOCK_RATIO:
        return True
    for start, end in grid['gutters']:
        centre = (start+end)/2
        if min(bbox[2]-centre, centre-bbox[0]) > SPAN_OVERHANG:
            return True
    return False
