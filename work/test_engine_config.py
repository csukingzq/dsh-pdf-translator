import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import engine_config

CONFIG = {'base_url': 'https://api.example.com/v1/', 'model': 'text-model', 'api_key': 'secret-key'}
PREPARED = {'input': 'D:/runs/source.pdf', 'run_dir': 'D:/runs/run', 'engine_dir': 'D:/runs/run/_engine'}


class LoadConfigTest(unittest.TestCase):
    def test_file_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps(CONFIG), 'utf-8')
            self.assertEqual(engine_config.load_config(path)['model'], 'text-model')

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(engine_config.load_config(Path(tmp) / 'none.json'), {})

    def test_environment_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps(CONFIG), 'utf-8')
            env = {'DSH_PDF_API_KEY': 'env-key', 'DSH_PDF_MODEL': 'env-model',
                   'DSH_PDF_BASE_URL': 'http://127.0.0.1:9/v1', 'DSH_PDF_LANG_OUT': 'zh-TW'}
            with mock.patch.dict(os.environ, env, clear=False):
                config = engine_config.load_config(path)
            self.assertEqual(config['api_key'], 'env-key')
            self.assertEqual(config['model'], 'env-model')
            self.assertEqual(config['base_url'], 'http://127.0.0.1:9/v1')
            self.assertEqual(config['lang_out'], 'zh-TW')

    def test_invalid_top_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text('[]', 'utf-8')
            with self.assertRaises(ValueError):
                engine_config.load_config(path)


class ModelConfigTest(unittest.TestCase):
    def test_valid(self):
        model = engine_config.model_config(CONFIG)
        self.assertEqual(model['base_url'], 'https://api.example.com/v1')
        self.assertEqual(model['model'], 'text-model')
        self.assertTrue(engine_config.configured(CONFIG))

    def test_missing_fields(self):
        for patch in ({'base_url': ''}, {'model': ''}, {'api_key': ''}):
            config = {**CONFIG, **patch}
            self.assertFalse(engine_config.configured(config))
            with self.assertRaises(ValueError):
                engine_config.model_config(config)

    def test_empty_config_points_to_panel(self):
        with self.assertRaisesRegex(ValueError, '面板'):
            engine_config.model_config({})

    def test_bad_scheme_and_placeholder(self):
        with self.assertRaisesRegex(ValueError, 'http'):
            engine_config.model_config({**CONFIG, 'base_url': 'ftp://example.com'})
        with self.assertRaisesRegex(ValueError, '真实'):
            engine_config.model_config({**CONFIG, 'model': 'REPLACE_WITH_A_MODEL'})


class RequestTest(unittest.TestCase):
    def test_workers(self):
        self.assertEqual(engine_config.workers({}), 4)
        self.assertEqual(engine_config.workers({'workers': 1}), 1)
        for value in (0, 9, 2.5, 'x'):
            with self.assertRaises(ValueError):
                engine_config.workers({'workers': value})

    def test_language(self):
        self.assertEqual(engine_config.language(CONFIG, 'lang_in', 'en'), 'en')
        self.assertEqual(engine_config.language({**CONFIG, 'lang_out': 'zh-TW'}, 'lang_out', 'zh-CN'), 'zh-TW')
        with self.assertRaises(ValueError):
            engine_config.language({**CONFIG, 'lang_out': '中文'}, 'lang_out', 'zh-CN')

    def test_qps_bounds(self):
        self.assertEqual(engine_config.qps({}), 4)
        self.assertEqual(engine_config.qps({'qps': 0}), 1)
        self.assertEqual(engine_config.qps({'qps': 'abc'}), 4)
        self.assertEqual(engine_config.qps({'qps': 999}), 200)

    def test_host_request(self):
        request = engine_config.host_request(CONFIG, {'pages': '1-3', 'workers': 2}, PREPARED)
        self.assertEqual(request['pages'], '1-3')
        self.assertEqual(request['pool_max_workers'], 2)
        self.assertEqual(request['lang_out'], 'zh-CN')
        self.assertEqual(request['engine'], 'pdf2zh-next')
        self.assertEqual(request['engine_dir'], PREPARED['engine_dir'])
        self.assertEqual(request['api_key'], 'secret-key')
        self.assertEqual(request['base_url'], 'https://api.example.com/v1')

    def test_host_request_never_uses_argv(self):
        request = engine_config.host_request(CONFIG, {}, PREPARED)
        self.assertNotIn('secret-key', ' '.join(str(value) for key, value in request.items() if key != 'api_key'))

    def test_formula_patterns(self):
        request = {'formular_font_pattern': r'(A|B)'}
        host = engine_config.host_request(CONFIG, request, PREPARED)
        self.assertEqual(host['formular_font_pattern'], '(A|B)')
        self.assertIsNone(host['formular_char_pattern'])

        override = {**CONFIG, 'formular_font_pattern': 'CUSTOM', 'formular_char_pattern': '[ﬃ]'}
        host = engine_config.host_request(override, request, PREPARED)
        self.assertEqual(host['formular_font_pattern'], 'CUSTOM')
        self.assertEqual(host['formular_char_pattern'], '[ﬃ]')

        host = engine_config.host_request(CONFIG, {'formular_font_pattern': ''}, PREPARED)
        self.assertIsNone(host['formular_font_pattern'])


if __name__ == '__main__':
    unittest.main()
