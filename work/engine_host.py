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
import tempfile
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
            only_include_translated_page=host['pages'] != 'all',
            no_dual=False,
            no_mono=False,
            watermark_output_mode='no_watermark',
            translate_table_text=False,
            formular_font_pattern=host['formular_font_pattern'],
            formular_char_pattern=host['formular_char_pattern'],
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

    if request.get('cache_dir'):
        configure_cache(request['cache_dir'])
    settings, host = settings_from(request)
    stream = (translate_math(settings, host, request.get('math_compatibility', False),
                             request.get('preserve_formula_offsets', False))
              if request.get('math_compatibility') or request.get('structured_layout')
              else do_translate_async_stream(settings, host['input']))
    async for event in stream:
        kind = event.get('type')
        if kind == 'finish':
            return finish(event, host)
        if kind == 'error':
            raise RuntimeError(str(event.get('error') or '翻译引擎执行失败。'))
        if kind in progress.PROGRESS_TYPES:
            emit({'type': 'progress', **progress.map_event(event)})
    raise RuntimeError('翻译引擎没有返回结果。')


def configure_cache(folder):
    """Isolate translation databases, while retaining shared models and fonts.

    The bridge runs one document per host process. Rebind both pinned engines'
    databases before creating any translators or starting worker threads.
    """
    from pdf2zh_next.translator import cache as pdf_cache
    from babeldoc.translator import cache as babel_cache

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    # Include interrupted engine scratch files in the same document's cleanup.
    temporary = folder / 'temporary'
    temporary.mkdir(exist_ok=True)
    tempfile.tempdir = str(temporary)
    for name, cache in [('pdf2zh', pdf_cache), ('babeldoc', babel_cache)]:
        cache.db.close()
        cache.db.init(str(folder / f'{name}.v1.db'),
                      pragmas={'journal_mode': 'wal', 'busy_timeout': 1000})
        cache.db.create_tables([cache._TranslationCache], safe=True)


async def translate_math(settings, host, math_compatibility=True, preserve_formula_offsets=False):
    """Use the engine's config adapter with a guarded layout model.

    Already isolated by engine.py, so this path does not need pdf2zh-next's
    additional multiprocessing wrapper (which cannot carry a custom model).
    """
    from pdf2zh_next.high_level import create_babeldoc_config
    from babeldoc.format.pdf.high_level import async_translate
    from mathlayout import MathLayoutModel
    from structured_layout import StructuredLayoutModel
    from translation_guard import TranslationGuard

    config = create_babeldoc_config(settings, Path(host['input']))
    # MT2 glyphs have unusual metrics. Re-estimating their offsets can detach
    # subscripts and wrap fragments; keep their original relative geometry.
    if preserve_formula_offsets:
        config.skip_formula_offset_calculation = True
    same_translator = config.term_extraction_translator is config.translator
    config.translator = TranslationGuard(config.translator)
    config.term_extraction_translator = (config.translator if same_translator else
                                        TranslationGuard(config.term_extraction_translator))
    math_model = MathLayoutModel(config.doc_layout_model) if math_compatibility else None
    model = StructuredLayoutModel(math_model or config.doc_layout_model)
    config.doc_layout_model = model
    async for event in async_translate(config):
        if event.get('type') == 'finish':
            event['diagnostics'] = model.diagnostics()
            event['diagnostics']['invalidTextRetries'] = config.translator.retries + (
                0 if same_translator else config.term_extraction_translator.retries)
            event['token_usage'] = {
                'main': token_usage(config.translator),
                'term': token_usage(config.term_extraction_translator)
                if config.term_extraction_translator is not config.translator else {},
            }
            if config.term_extraction_translator is config.translator:
                usage = getattr(config, 'term_extraction_token_usage', None) or {}
                if usage:
                    event['token_usage']['term'] = {
                        'total': int(usage.get('total_tokens', 0)),
                        'prompt': int(usage.get('prompt_tokens', 0)),
                        'completion': int(usage.get('completion_tokens', 0)),
                        'cache_hit_prompt': int(usage.get('cache_hit_prompt_tokens', 0)),
                    }
        yield event
        if event.get('type') in ('finish', 'error'):
            return


def token_usage(translator):
    fields = {'total': 'token_count', 'prompt': 'prompt_token_count',
              'completion': 'completion_token_count', 'cache_hit_prompt': 'cache_hit_prompt_token_count'}
    values = {key: getattr(translator, field, 0) for key, field in fields.items()}
    return {key: int(getattr(value, 'value', value) or 0) for key, value in values.items()}


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
        'diagnostics': event.get('diagnostics') or {},
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
