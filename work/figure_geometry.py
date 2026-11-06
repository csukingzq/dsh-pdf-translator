"""Conservative, offline figure boundaries grounded in native PDF objects.

The recognition rectangle is a search seed, not proof that every label fits.
No OCR, model calls, source edits or document-specific coordinates are used.
"""
import re
import pymupdf

VERSION = 'figure-geometry-v3'
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
    def warn(reason, unsafe=None):
        result['unsafe'] = (reason in {'figure_overlaps_prose','figure_label_crosses_safe_region','figure_boundary_touches_prose_or_search_limit'} if unsafe is None else unsafe)
        result['diagnostics'].append(reason)
        return result
    transform=page.rotation_matrix
    lines=[]
    prose_lines=set()
    for block in page.get_text('dict',flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
        block_lines=[]
        for line in block.get('lines',[]):
            text=''.join(s['text'] for s in line['spans']).strip()
            if text:
                entry=(pymupdf.Rect(line['bbox'])*transform,text)
                lines.append(entry);block_lines.append(entry)
        if len(block_lines)>1 and any(len(t)>55 or CAPTION.match(t) for _,t in block_lines):
            prose_lines.update(tuple(r) for r,_ in block_lines)
    # Match complete raster objects before imposing seed-based search limits.
    # A model rectangle may cut off entire axes, while adjacent-column prose
    # must not veto an independently located image.
    candidates=[]
    for info in page.get_image_info():
        rect=pymupdf.Rect(info['bbox'])*transform
        area=rect.get_area()
        intersection=(rect & seed).get_area()
        if (area > 0 and area < bounds.get_area()*.80 and min(rect.width,rect.height)>20
                and intersection/max(seed.get_area(),1) >= .55 and intersection/area >= .55):
            candidates.append((intersection,rect))
    candidates.sort(key=lambda pair:pair[0],reverse=True)
    if candidates and (len(candidates)==1 or candidates[0][0]>1.8*candidates[1][0]):
        rect=candidates[0][1]
        # Text outside the raster may be a separate axis label. In that case
        # use the general geometry resolver instead of discarding those labels.
        external=[(r,t) for r,t in lines if r.intersects(expand(rect,5))
                  and not rect.contains(r) and not CAPTION.match(t)]
        overlaid_prose=[t for r,t in lines if rect.contains(r) and len(t)>55]
        if not external and not overlaid_prose:
            tight=expand(rect,1)&bounds
            result.update(bbox=[tight.x0/bounds.width,tight.y0/bounds.height,
                                tight.x1/bounds.width,tight.y1/bounds.height],
                          decision='complete_native_image',graphic_objects=1,label_regions=0)
            return result
    dx=min(bounds.width*.10,max(24,seed.width*.20))
    dy=min(bounds.height*.08,max(24,seed.height*.50))
    search=pymupdf.Rect(seed.x0-dx,seed.y0-dy,seed.x1+dx,seed.y1+dy)&bounds
    # Captions and prose are barriers, including captions whose first line was
    # split into separate native fragments. Never grow a crop through prose.
    barriers=[]
    for rect,text in lines:
        if CAPTION.match(text) or len(text)>55 or tuple(rect) in prose_lines:
            # Expanded search margins may cross the gutter: neighboring-column
            # prose cannot define the vertical limits of this figure.
            if rect.x1 <= seed.x0 or rect.x0 >= seed.x1:
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
    oversized_native=False
    for drawing in page.get_drawings():
        rect=pymupdf.Rect(drawing['rect'])*transform
        # Zero-area strokes are real graphic objects too.
        rect=expand(rect,max(.3,float(drawing.get('width') or 0)/2))
        if rect.intersects(seed):
            if search.contains(rect):objects.append(rect)
            else:oversized=True;oversized_native=True
        elif search.contains(rect):
            objects.append(rect)
    for info in page.get_image_info():
        rect=pymupdf.Rect(info['bbox'])*transform
        if rect.intersects(seed):
            if search.contains(rect):objects.append(rect)
            else:
                oversized=True
                oversized_native = oversized_native or rect.get_area()<bounds.get_area()*.8
        elif search.contains(rect):objects.append(rect)
    # A full-page scan is not an independently located figure. Preserve the
    # requested region and explicitly require visual review, never claim proof.
    if oversized:
        return warn('figure_object_exceeds_search_region', unsafe=oversized_native)
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
    label_region=expand(envelope,24)&search
    for rect,text in lines:
        if CAPTION.match(text) or len(text)>55 or tuple(rect) in prose_lines or not label_region.intersects(rect):continue
        if any(abs(rect.y0-b.y0)<3 and abs(rect.y1-b.y1)<3 for b in barriers):continue
        if search.contains(rect):labels.append(rect)
        elif rect.intersects(envelope):return warn('figure_label_crosses_safe_region')
    tight=expand(union(selected+labels),2)&bounds
    if not search.contains(tight):
        return warn('figure_boundary_touches_prose_or_search_limit')
    result.update(bbox=[tight.x0/bounds.width,tight.y0/bounds.height,tight.x1/bounds.width,tight.y1/bounds.height],
                  decision='native_graphics_and_labels',graphic_objects=len({tuple(r) for r in selected}),label_regions=len(labels))
    return result
