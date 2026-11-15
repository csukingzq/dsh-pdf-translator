"""Retry damaged model responses instead of typesetting replacement glyphs."""
import re
import threading

BAD_TEXT = re.compile('\ufffd|\\\\ufffd', re.IGNORECASE)


class TranslationGuard:
    def __init__(self, translator):
        self.translator = translator
        self.retries = 0
        self._lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.translator, name)

    def _call(self, method, text, ignore_cache=False, rate_limit_params=None):
        call = getattr(self.translator, method)
        result = call(text, ignore_cache=ignore_cache, rate_limit_params=rate_limit_params)
        if not isinstance(result, str) or not BAD_TEXT.search(result):
            return result
        with self._lock:
            self.retries += 1
        result = call(text, ignore_cache=True, rate_limit_params=rate_limit_params)
        if not isinstance(result, str) or BAD_TEXT.search(result):
            raise RuntimeError('模型译文包含损坏字符，重试后仍未恢复，请重试该页。')
        # Replace only this damaged entry; leave other cached translations intact.
        if not (ignore_cache or getattr(self.translator, 'ignore_cache', False)):
            try:
                self.translator.cache.set(text, result)
            except Exception:
                pass
        return result

    def translate(self, text, ignore_cache=False, rate_limit_params=None):
        return self._call('translate', text, ignore_cache, rate_limit_params)

    def llm_translate(self, text, ignore_cache=False, rate_limit_params=None):
        return self._call('llm_translate', text, ignore_cache, rate_limit_params)
