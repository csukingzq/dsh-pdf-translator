"""Turn engine failures into actionable Chinese messages.

The engine emits provider errors (HTTP status, SDK exceptions) and layout
errors in free text. Unknown failures keep a cleaned tail of the engine output
so a report never hides the real cause, while the API key is redacted by the
caller.
"""
import re

_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|[\x00-\x08\x0b-\x1f\x7f]')

_RULES = (
    (r'\b401\b|\b403\b|unauthorized|invalid api key|incorrect api key|invalid_api_key|authentication|permission denied',
     '模型接口拒绝访问（401/403）。请检查 API 密钥是否有效、接口地址是否正确。'),
    (r'\b402\b|insufficient (?:balance|quota)|quota exceeded|余额不足|exceeded your current quota',
     '模型账户余额或额度不足。请充值或更换密钥后重试。'),
    (r'\b429\b|rate limit|too many requests|requests per min|qps',
     '模型接口限流（429）。请稍后重试，或减少并发页数。'),
    (r'timed? ?out|timeout|readtimeout|apitimeout',
     '请求模型接口超时。请检查网络/代理，或稍后用更少的页数重试。'),
    (r'connection (?:error|refused|reset|aborted)|connect timeout|network|ssl|proxy|getaddrinfo|name or service not known',
     '无法连接模型接口。请检查代理、DNS 与接口地址。'),
    (r'model\b.*?(?:not found|does not exist|not exist|invalid)|invalid model|unknown model|no such model|模型不存在',
     '模型名称无效。请检查配置中的模型名。'),
    (r'context length|maximum context|token limit|too many tokens|context window',
     '文本超出模型上下文长度。请更换支持更长上下文的模型。'),
    (r'scanned|no text (?:layer|found)|image[- ]only|需要 ?ocr|ocr',
     '该 PDF 可能是扫描件，没有可翻译的文本层。请先做 OCR 或改用带文本层的 PDF。'),
    (r'font.*(?:missing|not found|subset)|glyph|字体',
     '字体处理失败。请确认系统已安装中文字体后重试。'),
    (r'\b5\d\d\b|bad gateway|service unavailable|internal server error',
     '模型接口返回服务端错误（5xx）。请稍后重试，或检查接口地址、代理与模型服务状态。'),
    (r'database is locked|sqlite|\.db.*locked|cache.*locked',
     '翻译缓存被占用。请关闭其他正在翻译的任务后重试。'),
    (r'file is being used|being used by another process|permission denied.*pdf|cannot access the file',
     'PDF 或输出文件被其他程序占用。请关闭阅读器或同步盘后重试。'),
    (r'no space|disk full|磁盘',
     '磁盘空间不足。请清理空间后重试。'),
)


def clean(text, limit=1200):
    text = _ANSI.sub('', str(text or ''))
    text = ' '.join(text.split())
    return text[:limit]


def explain(message, tail=''):
    """Return one user-facing sentence plus the cleaned original tail."""
    raw = clean(message)
    extra = clean(tail)
    probe = (raw + '\n' + extra).lower()
    for pattern, explanation in _RULES:
        if re.search(pattern, probe, re.IGNORECASE):
            detail = raw or extra
            return explanation + (f'\n引擎输出：{detail}' if detail else '')
    if raw:
        return raw
    if extra:
        return '翻译引擎执行失败。\n引擎输出：' + extra
    return '翻译引擎执行失败，请查看运行日志后重试。'
