import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
import review_pipeline as review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'sample.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50,50),'Original paragraph')
            pdf.save(self.source)
        self.folder = self.root/'outputs'/'task'
        self.folder.mkdir(parents=True)
        self.output = self.folder/'translated.pdf'
        self.output.write_bytes(self.source.read_bytes())
        self.cache = self.root/'work'/'document-cache'/'abc'/'model'
        self.cache.mkdir(parents=True)
        self.page = {'page':1,'complete':True,'blocks':[{'page':1,'id':'p1-b1','kind':'paragraph','bbox':[0,0,1,1],'markdown':'原始译文','status':'translated'}]}
        doc = {'version':1,'pages':[self.page]}
        for target in [self.folder/'document.json',self.cache/'rendering.json',self.cache/'document.json',self.cache/'final-pages.json']:
            review.save(target,doc)
        (self.folder/'translated.md').write_text('原始译文',encoding='utf-8')
        self.result = {'output':str(self.output),'document':str(self.folder/'document.json'),
                       'report':str(self.folder/'translated.report.json'),'markdown':str(self.folder/'translated.md'),
                       'canonical_document':str(self.cache/'rendering.json')}
        review.save(Path(self.result['report']),{'status':'complete','issues':[],'source_pages':1})
        self.request = {'operation':'review','dataDir':str(self.root),'pdf':str(self.source),
                        'identity':review.digest(self.source)[:16],'result':self.result,'round':1,'remaining':[]}

    def invoke(self,action,**kwargs):
        return review.execute({**self.request,'action':action,**kwargs})

    def render(self,text,cache,output):
        output.write_bytes(self.source.read_bytes())
        project = output.with_suffix('')
        project.mkdir()
        (project/'main.tex').write_text(text,encoding='utf-8')
        review.save(project/'render-report.json',{})

    def test_staged_success_updates_all_formats_and_retains_backup(self):
        version = self.invoke('inspect')['version']
        revised = copy.deepcopy(self.page)
        revised['blocks'][0]['markdown'] = '修订译文'
        with patch.object(review,'render_latex',self.render):
            result = self.invoke('apply',expectedVersion=version,pages=[revised])
        self.assertNotEqual(result['version'],version)
        for target in [self.result['document'],self.result['canonical_document'],self.cache/'document.json',self.cache/'final-pages.json']:
            self.assertEqual(review.read(target)['pages'][0],revised)
        self.assertIn('修订译文',Path(self.result['markdown']).read_text('utf-8'))
        self.assertIn('修订译文',(self.output.with_suffix('')/'main.tex').read_text('utf-8'))
        journal=review.read(result['backup'])
        row=next(r for r in journal['files'] if Path(r['target']).resolve()==Path(self.result['document']).resolve())
        self.assertEqual(review.read(Path(result['backup']).parent/row['backup'])['pages'][0],self.page)
        self.assertEqual(review.read(self.result['report'])['ai_review']['rounds'],1)

    def test_failed_compile_never_publishes(self):
        before={p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        with patch.object(review,'render_latex',side_effect=RuntimeError('compile failed')):
            with self.assertRaisesRegex(RuntimeError,'compile failed'):
                self.invoke('apply',pages=[self.page])
        self.assertEqual(before,{p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()})

    def test_partial_publication_rolls_back_and_crash_recovery(self):
        transaction=self.root/'work'/'review-transactions'/'test'
        transaction.mkdir(parents=True)
        staged=transaction/'new';staged.write_text('new')
        old=self.root/'old';old.write_text('old')
        other=self.root/'other';other.write_text('other')
        real=review.atomic_copy
        def fail_second(source,target):
            if Path(source)==staged and Path(target)==other:
                raise OSError('locked')
            real(source,target)
        with patch.object(review,'atomic_copy',side_effect=fail_second):
            with self.assertRaisesRegex(OSError,'locked'):
                review.publish(transaction,[(staged,old),(staged,other)])
        self.assertEqual(old.read_text(),'old')
        self.assertEqual(other.read_text(),'other')
        journal=review.read(transaction/'journal.json');journal['status']='publishing'
        review.save(transaction/'journal.json',journal);old.write_text('partial after crash')
        review.recover(self.root)
        self.assertEqual(old.read_text(),'old')

    def test_preview_version_scope_and_hostile_block_id(self):
        result=self.invoke('preview',page=1,target='source')
        self.assertTrue(result['image']);self.assertEqual(result['pageCount'],1)
        with self.assertRaisesRegex(ValueError,'不属于'):
            self.invoke('preview',page=2,target='source')
        with self.assertRaisesRegex(ValueError,'改变'):
            self.invoke('inspect',expectedVersion='stale')
        bad=copy.deepcopy(self.page);bad['blocks'][0]['id']='../../escape'
        with self.assertRaisesRegex(ValueError,'ID'):
            self.invoke('apply',pages=[bad])
        bad=copy.deepcopy(self.page);bad['page']=2
        with self.assertRaisesRegex(ValueError,'不属于'):
            self.invoke('apply',pages=[bad])

    def test_finish_reports_remaining_without_claiming_success(self):
        result=self.invoke('finish',summary='保留最近可用版本',remaining=['表格待确认'])
        self.assertEqual(result['result']['status'],'needs_review')
        self.assertEqual(review.read(self.result['report'])['ai_review']['remaining'],['表格待确认'])

    def test_real_compiler_accepts_revision(self):
        revised=copy.deepcopy(self.page);revised['blocks'][0]['markdown']='修订后的中文段落，含公式 $a+b=c$。'
        result=self.invoke('apply',pages=[revised],layout={'fontSize':12,'figureMaxHeight':.45})
        with pymupdf.open(self.output) as pdf:
            self.assertGreater(len(pdf),0)
            self.assertIn('修订',pdf[0].get_text())
        self.assertTrue((self.output.with_suffix('')/'main.tex').exists())
        self.assertIn(r'\fontsize{12pt}',(self.output.with_suffix('')/'layout.tex').read_text('utf-8'))
        self.assertEqual(result['result']['status'],'complete')

    def test_layout_only_revision_is_versioned_and_reusable(self):
        version=self.invoke('inspect')['version']
        with patch.object(review,'render_latex',self.render):
            result=self.invoke('apply',layout={'figureMaxHeight':.45,'figureMaxWidth':.95})
        self.assertNotEqual(result['version'],version)
        self.assertEqual(review.read(self.result['document'])['pages'],[self.page])
        for target in [self.folder/'layout.json',self.cache/'layout.json']:
            self.assertEqual(review.read(target),{'figureMaxHeight':.45,'figureMaxWidth':.95})
        self.assertEqual(review.read(self.result['canonical_document'])['layout']['figureMaxHeight'],.45)
        with self.assertRaisesRegex(ValueError,'排版参数'):
            self.invoke('apply',layout={'figureMaxHeight':9})


if __name__=='__main__':
    unittest.main()
