"""User-directed cache maintenance. Never called automatically or by an AI tool."""
import json
import os
import re
import shutil
from pathlib import Path


def root_path(data_dir):
    base = Path(data_dir).resolve()
    for item in [base/'work', base/'work/document-cache']:
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('缓存根目录含链接，拒绝操作。')
    return base/'work/document-cache'


def safe_tree(root, target):
    root = root.resolve()
    if target.is_symlink() or (hasattr(target, 'is_junction') and target.is_junction()):
        raise ValueError('缓存含链接，拒绝清理。')
    resolved = target.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError('清理范围超出文档缓存。')
    for base, dirs, files in os.walk(target, followlinks=False):
        for name in dirs + files:
            item = Path(base)/name
            if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                raise ValueError('缓存含链接，拒绝清理。')
            if not item.resolve().is_relative_to(root):
                raise ValueError('缓存路径超出允许范围。')
    return resolved


def cache_list(data_dir):
    root = root_path(data_dir)
    if not root.exists():
        return []
    rows = []
    for folder in root.iterdir():
        if not re.fullmatch('[a-f0-9]{16}', folder.name) or not folder.is_dir():
            continue
        blocked = ''
        try:
            safe_tree(root, folder)
        except ValueError as exc:
            blocked = str(exc)
        files = [] if blocked else [p for p in folder.rglob('*') if p.is_file()]
        requests = sorted((p for p in files if p.name == 'request.json'), key=lambda p:p.stat().st_mtime, reverse=True)
        source = ''
        if requests:
            try:
                source = json.loads(requests[0].read_text('utf-8'))['source']
            except (ValueError, KeyError):
                pass
        rows.append({'id':folder.name, 'name':Path(source).name or folder.name, 'source':source,
                     'bytes':sum(p.stat().st_size for p in files),
                     'lastUsed':max((p.stat().st_mtime for p in files), default=folder.stat().st_mtime)*1000,
                     'blocked':blocked})
    return sorted(rows, key=lambda r:r['lastUsed'], reverse=True)


def preserve_legacy_exports(data_dir, target):
    """Migrate legacy Markdown references before deleting their source crops."""
    data_dir = Path(data_dir)
    roots = [data_dir/'outputs']
    registry = data_dir/'work/export-roots.json'
    if registry.exists():
        roots += [Path(p) for p in json.loads(registry.read_text('utf-8'))]
    for output_root in set(roots):
        if not output_root.exists():
            continue
        for report_path in output_root.rglob('*.report.json'):
            report = json.loads(report_path.read_text('utf-8'))
            cache = Path(report.get('cache', '')).resolve()
            if not cache.is_relative_to(target.resolve()):
                continue
            markdown = Path(report.get('markdown') or cache/'translated.md')
            if not markdown.resolve().is_relative_to(target.resolve()) and markdown.is_file():
                continue  # v0.2 exports already own their assets.
            if not markdown.is_file():
                raise ValueError('旧成果缺少 Markdown，无法补齐独立资源，已保留缓存：'+str(report_path))
            asset_dir = report_path.parent/(report_path.stem+'.assets')
            asset_dir.mkdir(exist_ok=True)
            shutil.copyfile(markdown, asset_dir/'translated.md')
            if (cache/'crops').exists():
                shutil.copytree(cache/'crops', asset_dir/'crops', dirs_exist_ok=True)
            if (cache/'document.json').exists():
                shutil.copyfile(cache/'document.json', asset_dir/'document.json')
            report['markdown'] = str(asset_dir/'translated.md')
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')


def clear_cache(data_dir, identity):
    if not re.fullmatch('[a-f0-9]{16}', identity):
        raise ValueError('无效缓存文档标识。')
    root = root_path(data_dir)
    target = root/identity
    if not target.exists():
        return {'cleared':False, 'id':identity}
    safe_tree(root, target)
    preserve_legacy_exports(data_dir, target)
    safe_tree(root, target)
    shutil.rmtree(target)
    return {'cleared':True, 'id':identity}
