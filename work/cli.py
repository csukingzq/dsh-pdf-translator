"""JSON stdin/stdout bridge. Progress goes to stderr; secrets never enter argv."""
import contextlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def exclusive(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    handle = (data_dir/'.translation.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('此输出目录已有翻译任务运行；请等待完成或更换 dataDir。') from None
    try:
        yield
    finally:
        handle.close()


def load_config(path):
    cfg = json.loads(Path(path).read_text('utf-8-sig')) if Path(path).exists() else {}
    for field, env in [('api_key','DSH_PDF_API_KEY'), ('base_url','DSH_PDF_BASE_URL'), ('model','DSH_PDF_MODEL')]:
        if os.environ.get(env):
            cfg[field] = os.environ[env]
    return cfg


def execute(request, on_progress=None):
    operation = request.get('operation', 'translate')
    if operation in {'review','reviewRecover'}:
        from review_pipeline import execute as review, recover
        data_dir = Path(request.get('dataDir') or ROOT).resolve()
        with exclusive(data_dir):
            return recover(data_dir) if operation == 'reviewRecover' else review(request)
    if operation in {'cacheList', 'cacheClear'}:
        from cache_ops import cache_list, clear_cache
        data_dir = Path(request.get('dataDir') or ROOT).resolve()
        if operation == 'cacheList':
            return {'entries':cache_list(data_dir)}
        with exclusive(data_dir):
            return clear_cache(data_dir, request['identity'])
    import pymupdf
    import bs4  # Verify the renderer's HTML dependency before any model request.
    from latex_renderer import binaries
    from document_pipeline import page_indices, run_document
    operation = request.get('operation', 'translate')
    if operation == 'doctor':
        try:
            pandoc, tectonic = binaries()
            renderer = {'ready':True, 'pandoc':pandoc, 'tectonic':tectonic}
        except RuntimeError as exc:
            renderer = {'ready':False, 'error':str(exc)}
        config_path = Path(request.get('configPath') or ROOT/'config.json')
        cfg = load_config(config_path)
        data_dir = Path(request.get('dataDir') or ROOT).resolve()
        return {'python':sys.executable, 'pymupdf':pymupdf.__version__, 'renderer':renderer,
                'model_configured':bool(cfg.get('api_key') and cfg.get('model') and cfg.get('base_url')),
                'recognition':'ai-only', 'local_ocr':False,
                'plugin_root':str(ROOT), 'data_dir':str(data_dir), 'config_path':str(config_path.resolve()),
                'runtime_dir':os.environ.get('DSH_PDF_RUNTIME_DIR') or str(ROOT/'runtime')}
    source = Path(request['pdf']).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.pdf':
        raise ValueError('找不到指定的 PDF 文件。')
    with pymupdf.open(source) as doc:
        if doc.needs_pass:
            raise ValueError('请先解密 PDF。')
        indices = page_indices(request.get('pages') or 'all', len(doc))
        if operation == 'inspect':
            return {'path':str(source), 'pages':len(doc), 'selected_pages':[i+1 for i in indices],
                    'bytes':source.stat().st_size}
    if operation != 'translate':
        raise ValueError('未知操作。')
    cfg = load_config(request.get('configPath') or ROOT/'config.json')
    if not cfg.get('base_url') or not cfg.get('model') or (not request.get('renderOnly') and not cfg.get('api_key')):
        raise ValueError('请在 config.json 或 DSH_PDF_* 环境变量中配置支持图片输入的模型服务。')
    binaries()  # Fail before spending tokens if the compiler is unavailable.
    data_dir = Path(request.get('dataDir') or ROOT).expanduser().resolve()
    with exclusive(data_dir):
        output = run_document(source, request.get('pages') or 'all', cfg,
            workers=request.get('workers', 4), render_only=request.get('renderOnly', False),
            image_quality=request.get('imageQuality', 'safe'), thinking=request.get('thinking'), data_dir=data_dir,
            output_dir=request.get('outputDir'), on_progress=on_progress)
    report_path = output.with_suffix('.report.json')
    report = json.loads(report_path.read_text('utf-8'))
    return {'output':str(output), 'project':str(output.with_suffix('')), 'report':str(report_path),
            'markdown':report.get('markdown',str(Path(report['cache'])/'translated.md')), 'status':report['status'],
            'pages':report['source_pages'], 'usage':report['usage'],
            'review_blocks':report['source_image_units'], 'issues':report.get('issues', []),
            'document':report.get('document'), 'canonical_document':report.get('canonical_document')}


def main():
    request = json.load(sys.stdin)
    output_stream = sys.stdout
    def event(value):
        output_stream.write(json.dumps(value, ensure_ascii=False)+'\n')
        output_stream.flush()
    streaming = request.get('events') is True
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request, (lambda value:event({'type':'progress', 'value':value})) if streaming else None)
        event({'type':'result', 'value':result} if streaming else result)
    except Exception as exc:
        message = str(exc)
        try:
            key = load_config(request.get('configPath') or ROOT/'config.json').get('api_key')
            if key:
                message = message.replace(key, '[REDACTED]')
        except Exception:
            pass
        event({'type':'error', 'error':message} if streaming else {'error':message})
        sys.exit(1)


if __name__ == '__main__':
    main()
