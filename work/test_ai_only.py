import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import document_pipeline as pipeline
import pymupdf
from cli import exclusive


class AiOnlyTests(unittest.TestCase):
    def test_first_request_carries_original_and_coordinate_guide_in_one_call(self):
        cfg = SimpleNamespace(base_url='https://example.invalid/v1', api_key='test-key', model='vision')
        result = {'complete':True,'blocks':[{'kind':'figure','bbox':[.1,.1,.9,.9],'markdown':'距离'}]}
        response = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
        with patch.object(pipeline, 'coordinate_reference', return_value=b'guide'), patch.object(pipeline, 'chat_json', return_value=response) as call:
            pipeline.request_page(cfg, b'original', '', '')
        self.assertEqual(call.call_count, 1)
        content = call.call_args.args[1]['messages'][1]['content']
        images = [c['image_url']['url'] for c in content if c['type']=='image_url']
        self.assertEqual(len(images), 2)
        self.assertTrue(images[0].endswith('b3JpZ2luYWw='))
        self.assertTrue(images[1].endswith('Z3VpZGU='))

    def test_coordinate_guide_preserves_source_dimensions(self):
        with pymupdf.open() as doc:
            page = doc.new_page(width=300,height=400)
            page.insert_text((40,100),'Chart')
            image = page.get_pixmap().tobytes('png')
        guide = pymupdf.Pixmap(pipeline.coordinate_reference(image))
        self.assertEqual((guide.width,guide.height),(300,400))


    def test_ai_figure_box_is_used_exactly_and_labels_are_preserved(self):
        block = {'id':'p1-b1', 'page':1, 'kind':'figure', 'bbox':[.13,.22,.87,.71],
                 'markdown':'Time：时间；Distance：距离。'}
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, 'crop') as crop:
            text = pipeline.block_markdown(block, Path('source.pdf'), Path(folder))
            self.assertEqual(crop.call_args.args[2], block['bbox'])
            self.assertIn('Time：时间', text)

    def test_missing_completeness_is_rejected(self):
        cfg = SimpleNamespace(base_url='https://example.invalid/v1', api_key='test-key', model='vision')
        response = {'choices':[{'finish_reason':'stop', 'message':{'content':json.dumps({'blocks':[
            {'kind':'table','bbox':[0,0,1,1],'markdown':'|A|\n|---|\n|1|'}]})}}]}
        with patch.object(pipeline, 'coordinate_reference', return_value=b'guide'), patch.object(pipeline, 'chat_json', return_value=response):
            with self.assertRaisesRegex(ValueError, '未完整'):
                pipeline.request_page(cfg, b'image', '', '')

    def test_output_directory_lock_blocks_overlapping_runs_and_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with exclusive(path):
                with self.assertRaisesRegex(RuntimeError, '已有'):
                    with exclusive(path):
                        pass
            with exclusive(path):
                pass

    def test_pdf_subset_cache_can_render_without_any_model_requests(self):
        source = Path(__file__).resolve().parent.parent/'tests/fixtures/vision-sample.pdf'
        cfg = {'base_url':'https://example.invalid/v1','api_key':'test-key','model':'vision'}
        data = {'complete':True, 'blocks':[
            {'kind':'table', 'bbox':[.1,.5,.9,.8], 'markdown':'| 时间 | 距离 |\n|---|---|\n|0|1|'}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, 'request_page', return_value=data) as request, patch.object(pipeline, 'render_latex'):
            result = pipeline.run_document(source, '1', cfg, workers=1, data_dir=folder)
            self.assertEqual(request.call_count, 1)
            request.reset_mock()
            pipeline.run_document(source, 'all', cfg, workers=1, data_dir=folder, render_only=True)
            request.assert_not_called()
            report = json.loads(result.with_suffix('.report.json').read_text('utf-8'))
            self.assertIsNone(report['ocr'])
            self.assertEqual(report['formula_review']['mode'], 'ai')


if __name__ == '__main__':
    unittest.main()
