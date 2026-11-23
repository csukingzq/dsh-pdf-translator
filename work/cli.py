"""JSON stdin/stdout bridge for the DeepSeek Harness plugin.

Progress and results are JSON lines on stdout; everything else (engine logs,
warnings, tracebacks) is redirected to stderr. Secrets stay in ``config.json``
and are only read by the engine host process.
"""
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def exclusive(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    handle = (data_dir / '.translation.lock').open('a+b')
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
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('此输出目录已有翻译任务运行；请等待完成或更换 dataDir。') from None
    try:
        yield
    finally:
        handle.close()


def load_config(path):
    """Read config.json with DSH_PDF_* environment overrides."""
    import engine_config
    return engine_config.load_config(path)


def engine_version():
    try:
        from importlib.metadata import version
        return version('pdf2zh-next')
    except Exception:
        return ''


def pymupdf_version():
    try:
        import pymupdf
        return pymupdf.__version__
    except Exception:
        return ''


def doctor(request, data_dir, config_path):
    cfg = load_config(config_path)
    version = engine_version()
    return {
        'python': sys.executable,
        'engine': {
            'name': 'pdf2zh-next',
            'ready': bool(version),
            'version': version,
            'module_ready': _module_ready(),
        },
        'pymupdf': pymupdf_version(),
        'model_configured': _model_configured(cfg),
        'plugin_root': str(ROOT),
        'data_dir': str(data_dir),
        'config_path': str(config_path.resolve()),
        'engine_cache_dir': str(_engine_cache_dir()),
        'runtime_dir': os.environ.get('DSH_PDF_RUNTIME_DIR') or str(ROOT / 'runtime'),
    }


def _module_ready():
    import importlib.util
    try:
        return importlib.util.find_spec('pdf2zh_next') is not None
    except Exception:
        return False


def _model_configured(cfg):
    import engine_config
    return engine_config.configured(cfg)


def _engine_cache_dir():
    import cache_ops
    return cache_ops.engine_cache_dir()


def inspect(request):
    import pymupdf
    import pages
    source = Path(request['pdf']).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.pdf':
        raise ValueError('找不到指定的 PDF 文件。')
    with pymupdf.open(source) as doc:
        if doc.needs_pass:
            raise ValueError('请先解密 PDF。')
        count = len(doc)
    indices = pages.page_indices(request.get('pages') or 'all', count)
    return {
        'path': str(source),
        'pages': count,
        'selected_pages': [index + 1 for index in indices],
        'bytes': source.stat().st_size,
    }


def translate(request, data_dir, config_path, on_progress, *, cache_source=None, prepared_output=None, locked=False):
    import engine
    import engine_config
    import cache_ops
    import mathfonts
    import mathrepair
    import mathrules
    import mt2math
    import outputs
    import pages
    import pymupdf

    source = Path(request['pdf']).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.pdf':
        raise ValueError('找不到指定的 PDF 文件。')
    fonts = set()
    sample_text = ''
    with pymupdf.open(source) as doc:
        if doc.needs_pass:
            raise ValueError('请先解密 PDF。')
        count = len(doc)
        indices = pages.page_indices(request.get('pages') or 'all', count)
        tex_roman_fonts = mathfonts.tex_roman_math_fonts(doc, indices)
        for page_index in range(count):
            try:
                for font in doc.get_page_fonts(page_index):
                    if font and len(font) > 3:
                        fonts.add(font[3])
            except Exception:
                continue
        for page_index in indices[:20]:
            try:
                sample_text += doc[page_index].get_text('text')
            except Exception:
                continue
    if not indices:
        raise ValueError('PDF 没有可处理的页面。')
    selected = pages.normalize(request.get('pages') or 'all', count)

    cfg = load_config(config_path)
    model = engine_config.model_config(cfg)
    engine_config.workers(request)
    version = engine_version()
    if not version:
        raise ValueError('未安装 pdf2zh-next 翻译引擎，请打开 PDF 翻译面板点击“一键准备环境”。')

    # MathType/Advance math fonts have broken ToUnicode maps. Protect them as
    # formulas so their glyph runs never reach the model as corrupted prose.
    pattern = None
    try:
        pattern = mathfonts.formula_font_pattern(fonts)
        diagnostics = mathfonts.diagnostics(fonts, mathfonts.suspicious_chars(sample_text))
    except Exception:
        diagnostics = {'mathFonts': [], 'formulaProtected': False, 'suspiciousChars': 0}
    configured_pattern = str(cfg.get('formular_font_pattern') or '').strip()
    if tex_roman_fonts:
        pattern = (pattern or mathfonts.DEFAULT_BROAD_PATTERN)[:-1] + '|' + '|'.join(
            name + r'(?!\d)' for name in tex_roman_fonts) + ')'
    diagnostics['texRomanMathFonts'] = tex_roman_fonts
    diagnostics['formulaProtected'] = bool(pattern or configured_pattern)
    diagnostics['formulaFontPattern'] = bool(configured_pattern)
    warnings = []
    if diagnostics['mathFonts'] or diagnostics['suspiciousChars']:
        warnings.append(
            '检测到 MathType/数学字体：行内公式可能无法完整重排。'
            '可用 pages 参数排除相关页；输出只包含所选页面。')

    output_dir = Path(request.get('outputDir') or (data_dir / 'outputs')).expanduser().resolve()
    cache_root = (data_dir / 'work').resolve()
    if output_dir == cache_root or output_dir.is_relative_to(cache_root):
        raise ValueError('输出目录不能位于插件工作目录内。')
    cache_source = Path(cache_source) if cache_source else source
    identity = hashlib.sha256(cache_source.read_bytes()).hexdigest()[:16]

    with contextlib.nullcontext() if locked else exclusive(data_dir):
        prepared = prepared_output or outputs.prepare(output_dir, source)
        try:
            math_compatibility = bool(diagnostics['mathFonts'])
            diagnostics['protectedVariableRuns'] = (
                mathrepair.protect_variables(prepared['input'], indices)
                if math_compatibility else 0)
            mt2 = mt2math.has_mt2(fonts)
            diagnostics['protectedOperatorRuns'] = (
                mt2math.protect_operators(prepared['input'], indices) if mt2 else 0)
            diagnostics['isolatedFontResources'] = (
                mt2math.isolate_shared_fonts(prepared['input'], indices) if mt2 else 0)
            diagnostics['normalizedRuleLines'] = (
                mathrules.normalize_rules(prepared['input'], indices, allow_color_rules=mt2)
                if mathrules.has_tex_math(fonts) or mt2 else 0)
            result = engine.run({
                'configPath': str(config_path),
                'cache_dir': str(cache_ops.prepare_cache(data_dir, identity, cache_source)),
                'input': str(prepared['input']),
                'run_dir': str(prepared['run_dir']),
                'engine_dir': str(prepared['engine_dir']),
                'pages': selected,
                'workers': request.get('workers'),
                'formular_font_pattern': pattern,
                'math_compatibility': math_compatibility,
                'structured_layout': True,
                'preserve_formula_offsets': mt2,
            }, on_progress)
            diagnostics.update(result.get('diagnostics') or {})
            collected = outputs.collect(prepared, result, {
                'source': str(source),
                'pages': selected,
                'selected_pages': len(indices),
                'model': model['model'],
                'base_url': model['base_url'],
                'diagnostics': diagnostics,
                'warnings': warnings,
            })
        except BaseException:
            # Do not leave a full PDF copy behind for a failed run.
            if prepared_output:
                outputs._cleanup(prepared)
            else:
                outputs.discard(prepared)
            raise
    return {
        'output': collected['output'],
        'dual': collected['dual'],
        'pages': len(indices),
        'selected_pages': [index + 1 for index in indices],
        'status': 'complete',
        'engine': 'pdf2zh-next',
        'engine_version': version,
        'source': str(source),
        'output_dir': str(prepared['run_dir']),
        'seconds': result.get('seconds'),
        'diagnostics': diagnostics,
        'warnings': warnings,
    }


def execute(request, on_progress=None):
    operation = request.get('operation', 'translate')
    data_dir = Path(request.get('dataDir') or ROOT).resolve()
    config_path = Path(request.get('configPath') or ROOT / 'config.json')

    if operation == 'doctor':
        return doctor(request, data_dir, config_path)
    if operation == 'cacheList':
        import cache_ops
        return {'entries': cache_ops.cache_list(data_dir)}
    if operation == 'cacheClear':
        import cache_ops
        with exclusive(data_dir):
            return cache_ops.clear_cache(data_dir, str(request.get('identity') or ''))
    if operation == 'inspect':
        return inspect(request)
    if operation == 'translate':
        return translate(request, data_dir, config_path, on_progress)
    raise ValueError('未知操作。')


def main():
    request = json.load(sys.stdin)
    output = sys.stdout

    def event(value):
        output.write(json.dumps(value, ensure_ascii=False) + '\n')
        output.flush()

    streaming = request.get('events') is True
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request, (lambda value: event({'type': 'progress', 'value': value})) if streaming else None)
        event({'type': 'result', 'value': result} if streaming else result)
    except Exception as exc:
        message = str(exc)
        try:
            key = load_config(request.get('configPath') or ROOT / 'config.json').get('api_key')
            if key:
                message = message.replace(key, '[REDACTED]')
        except Exception:
            pass
        event({'type': 'error', 'error': message} if streaming else {'error': message})
        sys.exit(1)


if __name__ == '__main__':
    main()
