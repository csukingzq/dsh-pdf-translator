import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
import document_pipeline as pipeline
from cache_ops import clear_cache, cache_list
from latex_renderer import render_latex, display_math, safe_math

FIXTURES = Path(__file__).resolve().parent.parent/'tests/fixtures'


class PanelPipelineTests(unittest.TestCase):
    def test_distinct_author_notes_survive_postprocessing(self):
        page={'page':1,'complete':True,'blocks':[
            {'kind':'paragraph','bbox':[.1,.1,.8,.2],'markdown':'作者甲[^1] 和作者乙[^2]'},
            {'kind':'footnote','bbox':[.1,.8,.8,.85],'markdown':'[^1]: 第一位作者的资助。'},
            {'kind':'footnote','bbox':[.1,.86,.8,.9],'markdown':'[^2]: 第二位作者的资助。'}]}
        before=copy.deepcopy(page)
        pipeline.validate(page);pipeline.merge_bottom_notes(page);pipeline.validate(page)
        self.assertEqual(page['blocks'],before['blocks'])

    def test_manual_cache_delete_preserves_legacy_markdown_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);identity='0123456789abcdef';cache=root/'work/document-cache'/identity/'model'
            (cache/'crops').mkdir(parents=True);(cache/'crops/image.png').write_bytes(b'image')
            (cache/'translated.md').write_text('![](crops/image.png)','utf-8')
            (cache/'request.json').write_text(json.dumps({'source':'sample.pdf'}),'utf-8')
            outputs=root/'outputs';outputs.mkdir();(outputs/'original.pdf').write_bytes(b'original')
            report=outputs/'original.report.json';report.write_text(json.dumps({'cache':str(cache)}),'utf-8')
            self.assertGreater(cache_list(root)[0]['bytes'],0)
            clear_cache(root,identity)
            self.assertFalse(cache.exists());self.assertEqual((outputs/'original.pdf').read_bytes(),b'original')
            markdown=Path(json.loads(report.read_text('utf-8'))['markdown'])
            self.assertEqual((markdown.parent/'crops/image.png').read_bytes(),b'image')
            with self.assertRaises(ValueError):clear_cache(root,'../outputs')

    def test_new_export_is_independent_and_progress_counts_cached_pages(self):
        cfg={'model':'test','base_url':'https://example.invalid','api_key':'unused'}
        data={'complete':True,'blocks':[{'kind':'figure','bbox':[.1,.2,.8,.7],'markdown':'x：时间'}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline,'request_page',return_value=data):
            root=Path(folder);events=[]
            first=pipeline.run_document(FIXTURES/'vision-sample.pdf','all',cfg,data_dir=root,output_dir=root/'自选目录',on_progress=events.append)
            second=pipeline.run_document(FIXTURES/'vision-sample.pdf','all',cfg,data_dir=root,output_dir=root/'自选目录',on_progress=events.append)
            self.assertNotEqual(first.parent,second.parent)
            self.assertEqual(events[-1]['completed'],1);self.assertEqual(events[-1]['cached'],1)
            report=json.loads(second.with_suffix('.report.json').read_text('utf-8'))
            identity=Path(report['cache']).parent.name;clear_cache(root,identity)
            markdown=Path(report['markdown']);self.assertTrue(markdown.exists())
            self.assertTrue((markdown.parent/'crops/p1-b1.png').exists())
            with pymupdf.open(second) as doc:
                self.assertGreater(len(doc),0)
            # A clean rebuild consumes only exported Markdown/images after deletion.
            render_latex(markdown.read_text('utf-8'),markdown.parent,root/'recompiled.pdf')
            with pymupdf.open(root/'recompiled.pdf') as doc:
                self.assertGreater(len(doc),0)

    def test_exact_session_formula_and_nested_row_tags_compile(self):
        text=(FIXTURES/'session-p10-equation.md').read_text('utf-8')
        rows=r'\begin{aligned}a&=b\tag{3_{a}}\\c&=d\tag{3b}\end{aligned}'
        self.assertIn('gathered',safe_math(text[2:-2]))
        converted=display_math(rows);self.assertIn('(3_{a})',converted);self.assertIn('(3b)',converted)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'formula.pdf'
            render_latex(text+'\n\n$$'+rows+'$$',root,out)
            with pymupdf.open(out) as doc:
                self.assertGreater(len(doc),0)
            report=json.loads((out.with_suffix('')/'render-report.json').read_text('utf-8'))
            self.assertFalse(report['missing_characters'])

    def test_offline_upgrade_uses_old_pages_and_discards_obsolete_renderer_fallback(self):
        source=FIXTURES/'vision-sample.pdf'
        cfg={'model':'test','base_url':'https://example.invalid','api_key':'unused'}
        identity=hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline,'request_page') as request, patch.object(pipeline,'render_latex'):
            root=Path(folder);cache=root/'work/document-cache'/identity/'old-signature'
            page={'complete':True,'page':1,'signature':'old','status':'translated','blocks':[
                {'id':'p1-b1','page':1,'kind':'paragraph','bbox':[.1,.2,.8,.3],'markdown':'完整译文。','status':'translated'}]}
            pipeline.save(cache/'pages/0001/result.json',page)
            pipeline.save(cache/'request.json',{'model':'test','image_quality':'safe','signature':'old','source':str(source)})
            fallback=copy.deepcopy(page);fallback['blocks'][0]['status']='source_image'
            pipeline.save(cache/'final-pages.json',{'input_hash':pipeline.pages_hash([page]),'pages':[fallback],'mode':'ai'})
            out=pipeline.run_document(source,'all',cfg,data_dir=root,render_only=True)
            request.assert_not_called()
            report=json.loads(out.with_suffix('.report.json').read_text('utf-8'))
            self.assertEqual(report['source_image_units'],[])
            canonical=Path(report['canonical_document']);accepted=json.loads(canonical.read_text('utf-8'))
            accepted['pages'][0]['blocks'][0]['markdown']='手动接受的修订。'
            pipeline.save(canonical,accepted)
            revised=pipeline.run_document(source,'all',cfg,data_dir=root,render_only=True)
            new_report=json.loads(revised.with_suffix('.report.json').read_text('utf-8'))
            self.assertIn('手动接受的修订',Path(new_report['markdown']).read_text('utf-8'))


if __name__=='__main__':unittest.main()
