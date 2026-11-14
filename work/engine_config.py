"""Translate plugin settings into pdf2zh-next settings.

Everything here is plain data so it can be unit tested without the engine
installed. ``engine_host.py`` turns the result into the engine's pydantic
models; the API key only ever crosses that one in-process boundary because the
host reads ``config.json`` itself instead of receiving a secret over argv.
"""
import json
import os
import re
from pathlib import Path

DEFAULT_LANG_IN = 'en'
DEFAULT_LANG_OUT = 'zh-CN'
DEFAULT_WORKERS = 4
DEFAULT_QPS = 4
ENGINE_NAME = 'pdf2zh-next'
PLACEHOLDER_MODEL = re.compile(r'^REPLACE', re.IGNORECASE)
_LANG = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,15}$')
_ENV = {
    'api_key': 'DSH_PDF_API_KEY',
    'base_url': 'DSH_PDF_BASE_URL',
    'model': 'DSH_PDF_MODEL',
    'lang_in': 'DSH_PDF_LANG_IN',
    'lang_out': 'DSH_PDF_LANG_OUT',
}


def load_config(path):
    """Read config.json, then let DSH_PDF_* environment variables override it.

    Both the bridge and the engine host must load it the same way, otherwise a
    user who configured the API through environment variables would pass the
    bridge's check and fail inside the engine.
    """
    path = Path(path)
    config = json.loads(path.read_text('utf-8-sig')) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError('config.json 顶层必须是对象。')
    for field, name in _ENV.items():
        if os.environ.get(name):
            config[field] = os.environ[name]
    return config


def _text(value):
    return str(value or '').strip()


def model_config(config):
    """Validated provider settings. Raises before any paid request."""
    base_url = _text(config.get('base_url')).rstrip('/')
    model = _text(config.get('model'))
    api_key = _text(config.get('api_key'))
    if not base_url and not model:
        raise ValueError('请先在 PDF 翻译面板填写接口地址、模型名称和 API 密钥。')
    if not base_url:
        raise ValueError('请填写模型接口地址，例如 https://api.deepseek.com/v1。')
    if not re.match(r'^https?://[^\s/]+', base_url, re.IGNORECASE):
        raise ValueError('接口地址必须以 http:// 或 https:// 开头。')
    if not model:
        raise ValueError('请填写模型名称。')
    if PLACEHOLDER_MODEL.match(model):
        raise ValueError('请把示例模型名替换成真实的文本翻译模型。')
    if not api_key:
        raise ValueError('请填写 API 密钥。')
    return {'base_url': base_url, 'model': model, 'api_key': api_key}


def configured(config):
    """Non-raising readiness probe for doctor/status."""
    try:
        model_config(config)
    except ValueError:
        return False
    return True


def language(config, name, fallback):
    value = _text(config.get(name)) or fallback
    if not _LANG.fullmatch(value):
        raise ValueError(f'{name} 不是有效的语言代码。')
    return value


def workers(request):
    value = request.get('workers')
    if value is None or value == '':
        return DEFAULT_WORKERS
    if isinstance(value, bool):
        raise ValueError('workers 必须是 1 至 8 的整数。')
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValueError('workers 必须是 1 至 8 的整数。')
    if not 1 <= number <= 8:
        raise ValueError('workers 必须是 1 至 8 的整数。')
    return number


def qps(config):
    value = config.get('qps')
    if value is None or value == '':
        return DEFAULT_QPS
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_QPS
    return max(1, min(200, number))


def host_request(config, request, prepared):
    """Full request for engine_host.py (includes the key, never argv)."""
    model = model_config(config)
    return {
        'engine': ENGINE_NAME,
        'input': str(prepared['input']),
        'run_dir': str(prepared['run_dir']),
        'engine_dir': str(prepared['engine_dir']),
        'pages': _text(request.get('pages')) or 'all',
        'lang_in': language(config, 'lang_in', DEFAULT_LANG_IN),
        'lang_out': language(config, 'lang_out', DEFAULT_LANG_OUT),
        'pool_max_workers': workers(request),
        'qps': qps(config),
        'report_interval': 0.2,
        # config.json wins over auto-detection; empty means "engine default".
        'formular_font_pattern': _text(config.get('formular_font_pattern')) or _text(request.get('formular_font_pattern')) or None,
        'formular_char_pattern': _text(config.get('formular_char_pattern')) or None,
        'base_url': model['base_url'],
        'model': model['model'],
        'api_key': model['api_key'],
    }
