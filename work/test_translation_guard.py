from types import SimpleNamespace
import unittest
from translation_guard import TranslationGuard


class GuardTest(unittest.TestCase):
    def test_damaged_cache_is_bypassed_and_repaired(self):
        for damaged in ('相\ufffd\ufffd位置', r'{"output":"相\ufffd位置"}'):
            calls, saved = [], []
            def translate(text, **kwargs):
                calls.append(kwargs)
                return '相对位置' if kwargs['ignore_cache'] else damaged
            original = SimpleNamespace(llm_translate=translate, ignore_cache=False,
                                       cache=SimpleNamespace(set=lambda *args: saved.append(args)), name='test')
            guarded = TranslationGuard(original)
            self.assertEqual(guarded.llm_translate('source', rate_limit_params={'x': 1}), '相对位置')
            self.assertEqual([c['ignore_cache'] for c in calls], [False, True])
            self.assertEqual(saved, [('source', '相对位置')])
            self.assertEqual(guarded.retries, 1)
            self.assertEqual(guarded.name, 'test')

    def test_valid_text_unchanged_and_retry_is_bounded(self):
        calls = []
        def translate(text, **kwargs):
            calls.append(text)
            return text
        guarded = TranslationGuard(SimpleNamespace(translate=translate))
        self.assertEqual(guarded.translate('公式 x + y'), '公式 x + y')
        self.assertEqual(len(calls), 1)
        with self.assertRaises(RuntimeError):
            guarded.translate('\ufffd')
        self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
