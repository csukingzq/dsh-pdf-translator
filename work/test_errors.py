import unittest

import errors


class ExplainTest(unittest.TestCase):
    def test_auth(self):
        message = errors.explain('Error code: 401 - invalid api key')
        self.assertIn('API 密钥', message)

    def test_rate_limit(self):
        self.assertIn('限流', errors.explain('429 Too Many Requests'))

    def test_timeout_and_network(self):
        self.assertIn('超时', errors.explain('ReadTimeout: request timed out'))
        self.assertIn('连接', errors.explain('ConnectionError: getaddrinfo failed'))

    def test_model_and_context(self):
        self.assertIn('模型名称', errors.explain('model gpt-x does not exist'))
        self.assertIn('上下文', errors.explain('maximum context length exceeded'))

    def test_scanned_and_cache(self):
        self.assertIn('扫描件', errors.explain('no text layer found'))
        self.assertIn('缓存', errors.explain('database is locked'))

    def test_server_errors(self):
        self.assertIn('服务端', errors.explain('Error code: 502'))
        self.assertIn('服务端', errors.explain('Internal Server Error'))

    def test_unknown_keeps_original_tail(self):
        message = errors.explain('some unexpected failure', 'traceback ... ')
        self.assertIn('some unexpected failure', message)

    def test_empty_failure_still_actionable(self):
        self.assertIn('失败', errors.explain(''))

    def test_clean_strips_ansi_and_collapses(self):
        self.assertEqual(errors.clean('\x1b[31merror\x1b[0m  happened\nnow'), 'error happened now')

    def test_result_includes_engine_tail(self):
        message = errors.explain('429 rate limit', 'rich bar noise')
        self.assertIn('引擎输出', message)


if __name__ == '__main__':
    unittest.main()
