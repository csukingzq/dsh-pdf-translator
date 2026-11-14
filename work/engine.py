"""Run pdf2zh-next in a dedicated process.

The bridge (``cli.py``) stays import-light; the engine's heavy imports and its
own multiprocessing children live in ``engine_host.py``. Progress and results
come back as JSON lines on the host's stdout, so no rich/tqdm output has to be
parsed.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import errors
import progress

HOST = Path(__file__).resolve().with_name('engine_host.py')
TAIL_LIMIT = 8000


class EngineError(RuntimeError):
    pass


def _environment():
    env = dict(os.environ)
    env.update({
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONUTF8': '1',
        'PYTHONUNBUFFERED': '1',
        'NO_COLOR': '1',
        'TERM': 'dumb',
        'COLUMNS': '100',
        'PYTHONWARNINGS': 'ignore',
    })
    return env


def run(request, on_progress=None):
    """Stream the engine and return ``{mono, dual, seconds, ...}``.

    Raises EngineError with an actionable message when the engine fails or
    produces no result. Cancellation is handled by the caller killing the whole
    process tree, which is why this function never needs its own signal handler.
    """
    if not HOST.is_file():
        raise EngineError('插件缺少 work/engine_host.py，请重新安装插件。')
    started = time.monotonic()
    state = progress.preparing()
    result = None
    failure = ''
    failure_kind = ''
    # The engine can spend a long time importing BabelDOC and downloading
    # assets before the first stage event. Keep the panel ticking instead of
    # showing a frozen "preparing" row.
    heartbeat = threading.Event()
    if on_progress:
        on_progress(dict(state))

    def beat():
        while not heartbeat.wait(2.0):
            if on_progress:
                tick = dict(state)
                tick['elapsedSeconds'] = round(time.monotonic() - started, 1)
                on_progress(tick)

    threading.Thread(target=beat, daemon=True).start()
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8', errors='replace') as sink:
        try:
            process = subprocess.Popen(
                [sys.executable, '-u', str(HOST)], cwd=str(HOST.parent.parent),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sink,
                text=True, encoding='utf-8', errors='replace', env=_environment(),
            )
        except OSError as exc:
            raise EngineError(f'无法启动翻译引擎：{exc}。请打开 PDF 翻译面板点击“一键准备环境”。') from None
        try:
            process.stdin.write(json.dumps(request, ensure_ascii=False))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        if process.stdout is None:
            raise EngineError('翻译引擎没有输出通道。')
        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get('type')
                if kind in {'progress', 'result', 'error'}:
                    heartbeat.set()
                if kind == 'progress':
                    state = progress.map_event(event, state)
                    state['elapsedSeconds'] = round(time.monotonic() - started, 1)
                    if on_progress:
                        on_progress(dict(state))
                elif kind == 'result':
                    result = event
                elif kind == 'error':
                    failure = str(event.get('message') or '')
                    failure_kind = str(event.get('kind') or '')
        finally:
            heartbeat.set()
            try:
                process.stdout.close()
            except OSError:
                pass
        code = process.wait()
        sink.seek(0)
        tail = errors.clean(sink.read()[-TAIL_LIMIT:])
    if failure:
        # "engine-missing" is already a user-facing sentence from the host.
        if failure_kind == 'engine-missing':
            raise EngineError(failure)
        raise EngineError(errors.explain(failure, tail))
    if not result:
        raise EngineError(errors.explain(f'', tail) if tail else f'翻译引擎已退出（退出码 {code}）但未返回结果。')
    if on_progress:
        state = progress.completed(state)
        state['elapsedSeconds'] = round(time.monotonic() - started, 1)
        on_progress(dict(state))
    result.setdefault('seconds', round(time.monotonic() - started, 2))
    result['tail'] = tail
    return result
