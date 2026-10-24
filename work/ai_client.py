"""Small OpenAI-compatible vision transport; no MinerU or upstream imports."""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit


class PipelineError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


@dataclass
class LlmConfig:
    base_url: str
    api_key: str
    model: str


def chat_completions_url(base):
    if urlsplit(base).scheme not in ('https', 'http'):
        raise ValueError('模型接口必须为 HTTP(S) 地址。')
    base = base.rstrip('/')
    return base if base.endswith('/chat/completions') else base + '/chat/completions'


def strip_wrapping_code_fence(text):
    text = text.strip()
    match = re.fullmatch(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    return match[1].strip() if match else text


def json_request(method, url, headers, payload, timeout=300):
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Provider responses may echo request content or credentials: expose status only.
        raise PipelineError(f'模型接口返回 HTTP {exc.code}；请检查图片输入支持、模型名称及配额。', exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PipelineError('无法连接模型接口或请求超时。') from None
