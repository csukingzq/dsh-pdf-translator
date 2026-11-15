import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cli import load_config

class ProfileTests(unittest.TestCase):
    def test_ocr_profile_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            config={'model':'legacy','api_key':'legacy-key','auto_repair_rounds':3,
                'engines':{'pdf2zh':{'model':'text','api_key':'text-key'},
                           'ocr':{'model':'vision','api_key':'vision-key'}}}
            path.write_text(json.dumps(config),'utf-8')
            with patch.dict(os.environ,{},clear=True):
                value=load_config(path)
                self.assertEqual(value['model'],'vision')
                self.assertEqual(value['api_key'],'vision-key')
                self.assertEqual(value['auto_repair_rounds'],3)
                del config['engines']['ocr']
                path.write_text(json.dumps(config),'utf-8')
                self.assertEqual(load_config(path)['model'],'legacy')
