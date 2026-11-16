"""Create the per-run output folder and collect the engine's PDFs.

The source PDF is copied next to the run under a short name because the engine
names its output after the input file: long Chinese titles plus
``.no_watermark.zh-CN.mono.pdf`` would otherwise exceed Windows' path limit.
The copy also guarantees that an output directory equal to the source's
directory can never overwrite the original.
"""
import os
import re
import shutil
import time
import uuid
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_STEM_LIMIT = 48


def safe_stem(name):
    stem = _INVALID.sub('_', str(name or 'document'))
    stem = ' '.join(stem.split()).strip(' .')
    return (stem or 'document')[:_STEM_LIMIT].strip(' .') or 'document'


def _writable(folder):
    probe = folder / ('.write-test-' + uuid.uuid4().hex)
    with probe.open('x', encoding='utf-8') as handle:
        handle.write('')
    probe.unlink()


def prepare(output_dir, source, now=None):
    """Create ``<outputDir>/<stem>_<timestamp>_<id>/`` and copy the source."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _writable(output_dir)
    source = Path(source).resolve()
    stem = safe_stem(source.stem)
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(now))
    run_dir = output_dir / f'{stem}_{stamp}_{uuid.uuid4().hex[:6]}'
    for _ in range(5):
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            run_dir = output_dir / f'{stem}_{stamp}_{uuid.uuid4().hex[:6]}'
    else:
        raise RuntimeError('无法创建输出目录，请更换输出位置后重试。')
    input_copy = run_dir / f'{stem}.pdf'
    shutil.copyfile(source, input_copy)
    return {
        'output_dir': output_dir,
        'run_dir': run_dir,
        'input': input_copy,
        'engine_dir': run_dir / '_engine',
        'stem': stem,
    }


def _move(source, target):
    source = Path(source) if source else None
    if source is None or not source.is_file():
        return None
    os.replace(source, target)
    return target


def collect(prepared, result, meta):
    """Collect only the PDFs; tolerate engines that omit the dual output."""
    run_dir = Path(prepared['run_dir'])
    stem = prepared['stem']
    mono = _move(result.get('mono'), run_dir / f'{stem}-mono.pdf')
    dual = _move(result.get('dual'), run_dir / f'{stem}-dual.pdf')
    if not mono and not dual:
        raise RuntimeError('翻译进程结束但未生成 PDF。' + (('\n引擎输出：' + result['tail']) if result.get('tail') else ''))
    _cleanup(prepared)
    return {
        'output': str(mono) if mono else '',
        'dual': str(dual) if dual else '',
        'bytes': sum(path.stat().st_size for path in (mono, dual) if path and path.exists()),
    }


def discard(prepared):
    """Remove a run folder whose translation failed before producing PDFs."""
    run_dir = Path(prepared.get('run_dir') or '')
    if run_dir.name and run_dir.parent.name and run_dir.is_dir():
        shutil.rmtree(run_dir, ignore_errors=True)


def _cleanup(prepared):
    engine_dir = Path(prepared['engine_dir'])
    if engine_dir.is_dir():
        shutil.rmtree(engine_dir, ignore_errors=True)
    input_copy = Path(prepared['input'])
    if input_copy.exists():
        try:
            input_copy.unlink()
        except OSError:
            pass
