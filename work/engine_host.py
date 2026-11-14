"""Drive pdf2zh-next / BabelDOC inside the plugin's virtual environment.

Design notes
------------
* Runs as its own process so the bridge (``cli.py``) never imports BabelDOC and
  so killing the process tree stops the engine and its worker processes.
* The API key is read from ``config.json`` here; it is never passed on a
  command line and never handed to another process.
* Engine chatter (rich progress bars, warnings) is redirected to stderr before
  importing the engine; only JSON events use stdout.
* ``if __name__ == '__main__'`` is mandatory: the engine spawns worker
  processes on Windows, which re-import this module.
"""
import asyncio
import contextlib
import json
import sys
import time
import traceback
from pathlib import Path

WORK = Path(__file__).resolve().parent
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

import engine_config  # noqa: E402
import errors  # noqa: E402
import progress  # noqa: E402

EVENTS = sys.__stdout__


def emit(event):
    EVENTS.write(json.dumps(event, ensure_ascii=False) + '\n')
    EVENTS.flush()


def load_config(path):
    return engine_config.load_config(path)


def version():
    try:
        from importlib.metadata import version as package_version
        return package_version('pdf2zh-next')
    except Exception:
        try:
            import pdf2zh_next
            return str(getattr(pdf2zh_next, '__version__', ''))
        except Exception:
            return ''


def settings_from(request):
    """Build the engine's SettingsModel from the plugin request."""
    from pdf2zh_next.config.model import BasicSettings
    from pdf2zh_next.config.model import PDFSettings
    from pdf2zh_next.config.model import SettingsModel
    from pdf2zh_next.config.model import TranslationSettings
    from pdf2zh_next.config.translate_engine_model import OpenAICompatibleSettings

    config = load_config(request['configPath'])
    prepared = {
        'input': request['input'],
        'run_dir': request['run_dir'],
        'engine_dir': request['engine_dir'],
    }
    host = engine_config.host_request(config, request, prepared)
    Path(host['engine_dir']).mkdir(parents=True, exist_ok=True)
    settings = SettingsModel(
        basic=BasicSettings(input_files={host['input']}),
        translation=TranslationSettings(
            lang_in=host['lang_in'],
            lang_out=host['lang_out'],
            output=host['engine_dir'],
            qps=host['qps'],
            pool_max_workers=host['pool_max_workers'],
            ignore_cache=False,
        ),
        pdf=PDFSettings(
            pages=None if host['pages'] == 'all' else host['pages'],
            no_dual=False,
            no_mono=False,
            watermark_output_mode='no_watermark',
            translate_table_text=False,
        ),
        translate_engine_settings=OpenAICompatibleSettings(
            openai_compatible_base_url=host['base_url'],
            openai_compatible_model=host['model'],
            openai_compatible_api_key=host['api_key'],
        ),
        report_interval=host['report_interval'],
    )
    settings.validate_settings()
    return settings, host


async def translate(request):
    from pdf2zh_next.high_level import do_translate_async_stream

    settings, host = settings_from(request)
    async for event in do_translate_async_stream(settings, host['input']):
        kind = event.get('type')
        if kind == 'finish':
            return finish(event, host)
        if kind == 'error':
            raise RuntimeError(str(event.get('error') or '翻译引擎执行失败。'))
        if kind in progress.PROGRESS_TYPES:
            emit({'type': 'progress', **progress.map_event(event)})
    raise RuntimeError('翻译引擎没有返回结果。')


def finish(event, host):
    result = event.get('translate_result')
    mono = getattr(result, 'no_watermark_mono_pdf_path', None) or getattr(result, 'mono_pdf_path', None)
    dual = getattr(result, 'no_watermark_dual_pdf_path', None) or getattr(result, 'dual_pdf_path', None)
    payload = {
        'type': 'result',
        'mono': str(mono) if mono else None,
        'dual': str(dual) if dual else None,
        'seconds': float(getattr(result, 'total_seconds', 0) or 0),
        'token_usage': event.get('token_usage') or {},
        'version': version(),
        'lang_in': host['lang_in'],
        'lang_out': host['lang_out'],
    }
    emit(payload)
    return payload


def main():
    started = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        try:
            request = json.load(sys.stdin)
        except ValueError as exc:
            emit({'type': 'error', 'message': f'翻译引擎请求无效：{exc}'})
            return 1
        try:
            import pdf2zh_next  # noqa: F401
        except Exception as exc:
            emit({'type': 'error', 'kind': 'engine-missing', 'message': (
                '未找到 pdf2zh-next 翻译引擎，请打开 PDF 翻译面板点击“一键准备环境”后重试。'
                f'\nPython：{sys.executable}\n原因：{errors.clean(exc)}')})
            return 1
        try:
            asyncio.run(translate(request))
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            print(f'engine failed after {time.monotonic() - started:.1f}s', file=sys.stderr)
            # The bridge classifies the raw engine message and appends the tail.
            emit({'type': 'error', 'message': str(exc) or exc.__class__.__name__})
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
