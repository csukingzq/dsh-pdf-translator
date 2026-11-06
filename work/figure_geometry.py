"""Conservative, offline figure boundaries grounded in native PDF objects.

The recognition rectangle is a search seed, not proof that every label fits.
No OCR, model calls, source edits or document-specific coordinates are used.
"""
import re
import pymupdf

VERSION = 'figure-geometry-v1'
CAPTION = re.compile(r'^\s*(?:Fig(?:ure)?\.?\s*\d|Table\s*\d|[图表]\s*\d)', re.I)


def expand(rect, amount):
    return pymupdf.Rect(rect.x0-amount,rect.y0-amount,rect.x1+amount,rect.y1+amount)


def union(rects):
    return pymupdf.Rect(min(r.x0 for r in rects),min(r.y0 for r in rects),
                        max(r.x1 for r in rects),max(r.y1 for r in rects))


def resolve_figure_crop(page, bbox):
    """Return an auditable crop; ambiguous evidence preserves the input box."""
    bounds=page.rect
    seed=pymupdf.Rect(bbox[0]*bounds.width,bbox[1]*bounds.height,
                      bbox[2]*bounds.width,bbox[3]*bounds.height)
    result=dict(version=VERSION,original_bbox=list(bbox),bbox=list(bbox),
                decision='unverified',diagnostics=[])
    def warn(reason):
        result['diagnostics'].append(reason)
        return result
    transform=page.rotation_matrix
    lines=[]
    for block in page.get_text('dict',flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
        for line in block.get('lines',[]):
            text=''.join(s['text'] for s in line['spans']).strip()
            if text:
                lines.append((pymupdf.Rect(line['bbox'])*transform,text))
    dx=min(bounds.width*.10,max(24,seed.width*.20))
    dy=min(bounds.height*.08,max(24,seed.height*.50))
    search=pymupdf.Rect(seed.x0-dx,seed.y0-dy,seed.x1+dx,seed.y1+dy)&bounds
    # Captions and prose are barriers, including captions whose first line was
    # split into separate native fragments. Never grow a crop through prose.
    barriers=[]
    for rect,text in lines:
        if CAPTION.match(text) or len(text)>55:
            if rect.x1 < search.x0 or rect.x0 > search.x1:
                continue
            barriers.append(rect)
            if rect.y1 <= (seed.y0+seed.y1)/2:
                search.y0=max(search.y0,rect.y1+1)
            elif rect.y0 >= (seed.y0+seed.y1)/2:
                search.y1=min(search.y1,rect.y0-1)
            else:
                return warn('figure_overlaps_prose')
    objects=[]
    oversized=False
    for drawing in page.get_drawings():
        rect=pymupdf.Rect(drawing['rect'])*transform
        # Zero-area strokes are real graphic objects too.
        rect=expand(rect,max(.3,float(drawing.get('width') or 0)/2))
        if rect.intersects(seed):
            if search.contains(rect):objects.append(rect)
            else:oversized=True
        elif search.contains(rect):
            objects.append(rect)
    for info in page.get_image_info():
        rect=pymupdf.Rect(info['bbox'])*transform
        if rect.intersects(seed):
            if search.contains(rect):objects.append(rect)
            else:oversized=True
        elif search.contains(rect):objects.append(rect)
    # A full-page scan is not an independently located figure. Preserve the
    # requested region and explicitly require visual review, never claim proof.
    if oversized:
        return warn('figure_object_exceeds_search_region')
    selected=[r for r in objects if r.intersects(seed)]
    if not selected:
        return warn('figure_native_geometry_unavailable')
    # Include disconnected arrow heads and rasterized rules near the seed;
    # text cannot pull the envelope recursively into adjacent paragraphs.
    envelope=union(selected)
    for _ in range(3):
        attached=[r for r in objects if r.intersects(expand(envelope,10))]
        enlarged=union(selected+attached)
        if tuple(enlarged)==tuple(envelope):break
        selected+=attached;envelope=enlarged
    labels=[]
    label_region=expand(union([envelope,seed]),16)&search
    for rect,text in lines:
        if CAPTION.match(text) or len(text)>55 or not label_region.intersects(rect):continue
        if any(abs(rect.y0-b.y0)<3 and abs(rect.y1-b.y1)<3 for b in barriers):continue
        if search.contains(rect):labels.append(rect)
        elif rect.intersects(envelope):return warn('figure_label_crosses_safe_region')
    tight=expand(union(selected+labels),2)&bounds
    if not search.contains(tight):
        return warn('figure_boundary_touches_prose_or_search_limit')
    result.update(bbox=[tight.x0/bounds.width,tight.y0/bounds.height,tight.x1/bounds.width,tight.y1/bounds.height],
                  decision='native_graphics_and_labels',graphic_objects=len({tuple(r) for r in selected}),label_regions=len(labels))
    return result
