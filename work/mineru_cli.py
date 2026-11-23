"""MinerU recognition followed by the existing PDF2zh bridge.

Both stages share the original document's cache and lock. Only the selected
pages are sent to MinerU, so page selection cannot be applied twice.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import cli
import cache_ops
import outputs
from mineru_host import VERSION, RENDERER_VERSION, TIER


def python_path(data_dir):
    return Path(data_dir) / '.venv-mineru' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def valid_pdf(path, count):
    import pymupdf
    try:
        with pymupdf.open(path) as pdf:
            return len(pdf) == count and not pdf.needs_pass
    except Exception:
        return False


def run_worker(source, target, data_dir, progress):
    python = python_path(data_dir)
    if not python.is_file():
        raise RuntimeError('未安装 MinerU，请选择 MinerU 引擎并点击“一键准备环境”。')
    runtime = Path(os.environ.get('DSH_PDF_RUNTIME_DIR') or Path(data_dir) / 'runtime')
    env = dict(os.environ, MINERU_HOME=str(runtime / 'mineru'),
               MINERU_MODEL_SOURCE='modelscope', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    # This worker must never inherit an unrelated remote MinerU endpoint/config.
    for key in list(env):
        if key.startswith(('MINERU_API_', 'MINERU_VLM_')) or key in ('MINERU_CONFIG', 'DSH_PDF_API_KEY', 'OPENAI_API_KEY'):
            env.pop(key)
    with tempfile.TemporaryFile() as logs:
        child = subprocess.Popen([str(python), '-u', str(Path(__file__).with_name('mineru_host.py'))],
                                 stdin=subprocess.PIPE, stdout=logs, stderr=logs, env=env,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            child.stdin.write(json.dumps({'source': str(source), 'target': str(target)}).encode('utf-8'))
            child.stdin.close()
            start = time.monotonic()
            while child.poll() is None:
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    progress({'phase': 'recognizing', 'percent': 5,
                              'elapsedSeconds': round(time.monotonic() - start),
                              'stage': 'MinerU 本地识别'})
            if child.returncode:
                logs.seek(0, 2)
                logs.seek(max(0, logs.tell() - 3000))
                tail = logs.read().decode('utf-8', errors='replace')
                raise RuntimeError('MinerU 识别失败：' + tail)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


def translate(request, data_dir, config_path, on_progress=None):
    import pymupdf
    import engine_config
    info = cli.inspect(request)
    source = Path(info['path'])
    selected = info['selected_pages']
    # Validate the paid stage before spending time on local recognition.
    engine_config.model_config(cli.load_config(config_path))
    engine_config.workers(request)
    if not cli.engine_version():
        raise ValueError('未安装 PDF2zh，请先点击“一键准备环境”。')
    output_dir = Path(request.get('outputDir') or data_dir / 'outputs').expanduser().resolve()
    if output_dir.is_relative_to((data_dir / 'work').resolve()):
        raise ValueError('输出目录不能位于插件工作目录内。')
    progress = on_progress or (lambda value: None)
    identity = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    key = hashlib.sha256(json.dumps({'version': VERSION, 'renderer': RENDERER_VERSION, 'tier': TIER, 'pages': selected,
                                    'layout': 'original', 'revision': 5}).encode()).hexdigest()[:20]
    with cli.exclusive(data_dir):
        cache = cache_ops.prepare_cache(data_dir, identity, source) / 'mineru' / key
        cache.mkdir(parents=True, exist_ok=True)
        recognized = cache / 'recognized.pdf'
        cached = valid_pdf(recognized, len(selected))
        progress({'phase': 'recognizing', 'percent': 5, 'stage': '复用 MinerU 识别缓存' if cached else 'MinerU 本地识别'})
        if not cached:
            # Scratch input never includes unselected pages and is never exported.
            with tempfile.TemporaryDirectory(prefix='recognition-', dir=cache) as scratch:
                subset = Path(scratch) / 'input.pdf'
                pending = Path(scratch) / 'recognized.pdf'
                with pymupdf.open(source) as original, pymupdf.open() as doc:
                    for page in selected:
                        doc.insert_pdf(original, from_page=page - 1, to_page=page - 1)
                    doc.save(subset)
                run_worker(subset, pending, data_dir, progress)
                if not valid_pdf(pending, len(selected)):
                    raise RuntimeError('MinerU 未生成与所选页数一致的有效 PDF；未启动翻译。')
                os.replace(pending, recognized)
        progress({'phase': 'recognizing', 'percent': 50, 'completed': len(selected),
                  'total': len(selected), 'unit': '页', 'cached': len(selected) if cached else 0})
        prepared = outputs.prepare(output_dir, source)
        mineru_pdf = prepared['run_dir'] / (prepared['stem'] + '-mineru.pdf')
        shutil.copyfile(recognized, mineru_pdf)
        shutil.copyfile(recognized, prepared['input'])
        def translate_progress(value):
            value = dict(value)
            value['percent'] = min(99, 50 + float(value.get('percent', 0)) / 2)
            progress(value)
        try:
            result = cli.translate({**request, 'pdf': str(mineru_pdf), 'pages': 'all'}, data_dir,
                                   config_path, translate_progress, cache_source=source,
                                   prepared_output=prepared, locked=True)
        except Exception as exc:
            outputs._cleanup(prepared)
            raise RuntimeError(f'识别 PDF 已保留：{mineru_pdf}\nPDF2zh 翻译失败：{exc}') from exc
        result.update(mineru=str(mineru_pdf), source=str(source), selected_pages=selected,
                      mineru_version=VERSION, mineru_tier=TIER, recognition_cached=cached, engine='mineru')
        progress({'phase': 'completed', 'percent': 100})
        return result


def execute(request, on_progress=None):
    data_dir = Path(request.get('dataDir') or cli.ROOT).resolve()
    config_path = Path(request.get('configPath') or cli.ROOT / 'config.json')
    if request.get('operation', 'translate') == 'translate':
        return translate(request, data_dir, config_path, on_progress)
    if request.get('operation') == 'doctor':
        result = cli.doctor(request, data_dir, config_path)
        result['mineru_python'] = str(python_path(data_dir))
        ready = False
        version = ''
        if python_path(data_dir).is_file():
            try:
                probe = subprocess.run([str(python_path(data_dir)), '-c',
                    "from mineru.parser import parse; from mineru.render import render_pdf; import importlib.metadata as m; print(m.version('mineru') + '/' + m.version('docvortex'))"],
                    capture_output=True, text=True, timeout=20,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                version = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ''
                ready = probe.returncode == 0 and version == f'{VERSION}/{RENDERER_VERSION}'
            except (OSError, subprocess.TimeoutExpired):
                pass
        result['mineru'] = {'ready': ready, 'version': version, 'tier': TIER, 'local': True}
        return result
    return cli.execute(request, on_progress)


if __name__ == '__main__':
    # Reuse the JSON-lines boundary and API-key redaction, without duplicating it.
    original_execute = cli.execute
    def dispatch(request, on_progress=None):
        if request.get('operation', 'translate') in ('translate', 'doctor'):
            return execute(request, on_progress)
        return original_execute(request, on_progress)
    cli.execute = dispatch
    cli.main()
