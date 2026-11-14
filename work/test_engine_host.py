import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

WORK = Path(__file__).resolve().parent
HOST = WORK / 'engine_host.py'

FAKE_MODEL = '''
class _Base:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def validate_settings(self):
        return None


class BasicSettings(_Base):
    pass


class PDFSettings(_Base):
    pass


class TranslationSettings(_Base):
    pass


class SettingsModel(_Base):
    pass
'''

FAKE_ENGINE_MODEL = '''
from pdf2zh_next.config.model import _Base


class OpenAICompatibleSettings(_Base):
    pass
'''

FAKE_HIGH_LEVEL = '''
import json
import os
from pathlib import Path
from types import SimpleNamespace


async def do_translate_async_stream(settings, file):
    engine_dir = Path(settings.translation.output)
    engine_dir.mkdir(parents=True, exist_ok=True)
    (engine_dir / 'mono.pdf').write_bytes(b'mono')
    (engine_dir / 'dual.pdf').write_bytes(b'dual')
    record = {
        'file': str(file),
        'lang_in': settings.translation.lang_in,
        'lang_out': settings.translation.lang_out,
        'pages': settings.pdf.pages,
        'pool': settings.translation.pool_max_workers,
        'qps': settings.translation.qps,
        'watermark': settings.pdf.watermark_output_mode,
        'model': settings.translate_engine_settings.openai_compatible_model,
        'base_url': settings.translate_engine_settings.openai_compatible_base_url,
        'api_key': settings.translate_engine_settings.openai_compatible_api_key,
        'input_files': sorted(settings.basic.input_files),
    }
    Path(os.environ['FAKE_ENGINE_RECORD']).write_text(json.dumps(record), 'utf-8')
    yield {'type': 'progress_start', 'stage': 'LayoutParser', 'stage_current': 0,
           'stage_total': 2, 'overall_progress': 0}
    yield {'type': 'progress_update', 'stage': 'ILTranslator', 'stage_current': 1,
           'stage_total': 2, 'overall_progress': 50}
    yield {'type': 'finish',
           'translate_result': SimpleNamespace(mono_pdf_path=engine_dir / 'mono.pdf',
                                              dual_pdf_path=engine_dir / 'dual.pdf',
                                              no_watermark_mono_pdf_path=engine_dir / 'mono.pdf',
                                              no_watermark_dual_pdf_path=engine_dir / 'dual.pdf',
                                              total_seconds=3.5),
           'token_usage': {'total': 7}}
'''


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), 'utf-8')


def write_fake_engine(root):
    fake = root / 'fake'
    write(fake / 'pdf2zh_next' / '__init__.py', '__version__ = "9.9.9"\n')
    write(fake / 'pdf2zh_next' / 'config' / '__init__.py', '')
    write(fake / 'pdf2zh_next' / 'config' / 'model.py', FAKE_MODEL)
    write(fake / 'pdf2zh_next' / 'config' / 'translate_engine_model.py', FAKE_ENGINE_MODEL)
    write(fake / 'pdf2zh_next' / 'high_level.py', FAKE_HIGH_LEVEL)
    return fake


def run_host(request, fake, record, extra=None):
    env = dict(os.environ)
    env.update({'PYTHONPATH': str(fake), 'FAKE_ENGINE_RECORD': str(record),
                'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
    if extra:
        env.update(extra)
    result = subprocess.run([sys.executable, '-u', str(HOST)], input=json.dumps(request),
                            capture_output=True, text=True, encoding='utf-8',
                            env=env, cwd=str(WORK), timeout=120)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return result, events


class EngineHostTest(unittest.TestCase):
    def test_host_protocol_with_fake_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_engine(root)
            config = root / 'config.json'
            config.write_text(json.dumps({'base_url': 'https://api.example.com/v1',
                                          'model': 'text-model', 'api_key': 'sk-secret-value'}), 'utf-8')
            source = root / 'source.pdf'
            source.write_bytes(b'%PDF-1.4 test')
            run_dir = root / 'run'
            run_dir.mkdir()
            record = root / 'record.json'

            request = {
                'configPath': str(config),
                'input': str(source),
                'run_dir': str(run_dir),
                'engine_dir': str(run_dir / '_engine'),
                'pages': '1-2',
                'workers': 3,
            }
            result, events = run_host(request, fake, record)
            self.assertEqual(result.returncode, 0, result.stderr)
            progress = [event for event in events if event['type'] == 'progress']
            self.assertEqual([event['phase'] for event in progress], ['analyzing', 'translating'])
            self.assertEqual(progress[1]['percent'], 50)
            final = [event for event in events if event['type'] == 'result'][0]
            self.assertEqual(final['mono'], str(run_dir / '_engine' / 'mono.pdf'))
            self.assertEqual(final['dual'], str(run_dir / '_engine' / 'dual.pdf'))
            self.assertAlmostEqual(final['seconds'], 3.5)
            self.assertEqual(final['lang_out'], 'zh-CN')
            self.assertNotIn('sk-secret-value', result.stdout)

            used = json.loads(record.read_text('utf-8'))
            self.assertEqual(used['lang_in'], 'en')
            self.assertEqual(used['lang_out'], 'zh-CN')
            self.assertEqual(used['pages'], '1-2')
            self.assertEqual(used['pool'], 3)
            self.assertEqual(used['qps'], 4)
            self.assertEqual(used['watermark'], 'no_watermark')
            self.assertEqual(used['model'], 'text-model')
            self.assertEqual(used['base_url'], 'https://api.example.com/v1')
            self.assertEqual(used['api_key'], 'sk-secret-value')
            self.assertEqual(used['input_files'], [str(source)])

    def test_host_reads_environment_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_engine(root)
            source = root / 'source.pdf'
            source.write_bytes(b'%PDF-1.4 test')
            run_dir = root / 'run'
            run_dir.mkdir()
            record = root / 'record.json'
            request = {'configPath': str(root / 'missing.json'), 'input': str(source),
                       'run_dir': str(run_dir), 'engine_dir': str(run_dir / '_engine'), 'pages': 'all'}
            result, events = run_host(request, fake, record, {
                'DSH_PDF_API_KEY': 'env-key', 'DSH_PDF_MODEL': 'env-model',
                'DSH_PDF_BASE_URL': 'https://api.example.com/v1',
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            used = json.loads(record.read_text('utf-8'))
            self.assertEqual(used['api_key'], 'env-key')
            self.assertEqual(used['model'], 'env-model')
            self.assertEqual(used['base_url'], 'https://api.example.com/v1')
            self.assertTrue(any(event['type'] == 'result' for event in events))

    def test_host_reports_missing_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / 'broken'
            write(broken / 'pdf2zh_next' / '__init__.py', 'raise ImportError("simulated missing engine")\n')
            config = root / 'config.json'
            config.write_text('{}', 'utf-8')
            request = {'configPath': str(config), 'input': str(root / 'x.pdf'),
                       'run_dir': str(root), 'engine_dir': str(root / '_engine'),
                       'pages': 'all'}
            env = dict(os.environ)
            env.update({'PYTHONPATH': str(broken), 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
            result = subprocess.run([sys.executable, '-u', str(HOST)], input=json.dumps(request),
                                    capture_output=True, text=True, encoding='utf-8',
                                    env=env, cwd=str(WORK), timeout=120)
            self.assertNotEqual(result.returncode, 0)
            events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            failures = [event for event in events if event['type'] == 'error']
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]['kind'], 'engine-missing')
            self.assertIn('pdf2zh-next', failures[0]['message'])
            self.assertIn('一键准备环境', failures[0]['message'])


if __name__ == '__main__':
    unittest.main()
