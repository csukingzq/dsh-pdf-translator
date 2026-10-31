import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pymupdf
from pathlib import Path
from document_pipeline import (page_indices, validate, assemble, block_markdown,
                               page_quality, render_page, record_usage, take_usage, request_page,
                               split_heading_blocks, normalize_notes, adjust_boxes, check_numbered_equations,
                               check_table_language, table_cells, PROMPT,
                               pages_hash, save_final_pages, load_final_pages, thinking_enabled,
                               run_document, drop_running_headers, merge_adjacent_headings,
                               merge_bottom_notes, drop_page_footers, api,
                               untranslated_pages, references_start, process_page)


class StructuredPipelineTests(unittest.TestCase):
    def setUp(self):
        guide = patch('document_pipeline.coordinate_reference', return_value=b'guide')
        guide.start()
        self.addCleanup(guide.stop)

    def block(self, text, page=1, **extra):
        return dict(kind='paragraph',bbox=[0.1,0.1,0.9,0.3],markdown=text,page=page,id=f'p{page}-b1',**extra)

    def test_pages(self):
        self.assertEqual(page_indices('3,1-2,2',5),[0,1,2])
        for bad in ['0','5-2','6','-1','1,,2']:
            with self.assertRaises(ValueError):
                page_indices(bad,5)

    def test_note_correspondence(self):
        data=dict(complete=True,blocks=[self.block('正文[^1]'),self.block('[^1]: 注释')])
        validate(data)
        data['blocks'].pop()
        with self.assertRaises(ValueError):
            validate(data)

    def test_invalid_bbox_and_truncation(self):
        data=dict(complete=True,blocks=[self.block('正文')])
        data['blocks'][0]['bbox']=[0,0,0,1]
        with self.assertRaises(ValueError):
            validate(data)
        with self.assertRaises(ValueError):
            validate(dict(complete=False,blocks=[self.block('正文')]))

    def test_unsafe_math_is_rejected(self):
        with self.assertRaises(ValueError):
            validate(dict(complete=True,blocks=[self.block(r'$\input{secret}$')]))

    def test_fallback_preserves_footnote_binding(self):
        with tempfile.TemporaryDirectory() as folder, patch('document_pipeline.crop'):
            note=self.block('[^2]: 带公式的注释',kind_unused=None)
            note.update(kind='footnote',status='source_image')
            text=block_markdown(note,None,Path(folder))
            self.assertTrue(text.startswith('[^p1-2]: ![]('))
            paragraph=self.block('正文[^2]',status='source_image')
            self.assertIn('[^p1-2]',block_markdown(paragraph,None,Path(folder)))

    def test_code_font_preserves_literal_operators(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pdf'
            with pymupdf.open() as doc:
                page=doc.new_page(width=300,height=300)
                page.insert_text((30,50),'a_b = x*y; result = fun(a_b);',fontname='cour')
                doc.save(path)
            block=self.block(r'a\_b = x\*y; result = fun(a\_b);')
            text=block_markdown(block,path,Path(folder))
            self.assertTrue(text.startswith('~~~~text'))
            self.assertIn('a_b = x*y',text)

    def test_html_code_indentation_is_decoded(self):
        with patch('document_pipeline.source_is_code', return_value=True):
            text = block_markdown(self.block('<pre>if x<br>&nbsp;&nbsp;y=1;</pre>'), Path('source.pdf'), Path('.'))
        self.assertEqual(text, '~~~~text\nif x\n  y=1;\n~~~~')

    def test_cross_page_code_fences_join_on_newline(self):
        pages = [dict(blocks=[self.block('~~~~text\nif x\n  y=1;\n~~~~', continues_next=True)]),
                 dict(blocks=[self.block('~~~~text\nend\n~~~~', 2, continues_previous=True)])]
        self.assertEqual(assemble(pages, None, Path('.')), '~~~~text\nif x\n  y=1;\nend\n~~~~\n')


    def test_continuations_and_page_scoped_notes(self):
        pages=[dict(blocks=[self.block('跨页',continues_next=True)]),
               dict(blocks=[self.block('段落[^1]。',2,continues_previous=True),self.block('[^1]: 注释',2)])]
        text=assemble(pages,None,Path('.'))
        self.assertIn('跨页段落[^p2-1]',text)
        self.assertIn('[^p2-1]: 注释',text)
        pages[1]['blocks'][0]['page']=3
        self.assertIn('跨页\n\n段落',assemble(pages,None,Path('.')))

    def test_footnote_does_not_break_continuation(self):
        note=self.block('[^1]: 注释')
        note['kind']='footnote'
        pages=[dict(blocks=[self.block('跨页[^1]',continues_next=True),note]),
               dict(blocks=[self.block('段落',2,continues_previous=True)])]
        self.assertIn('跨页[^p1-1]段落',assemble(pages,None,Path('.')))

    def two_column_pdf(self, path):
        """A page whose text really sits in two columns, so the grid is detected."""
        words='dense reconstruction from uncalibrated images without camera poses'.split()
        with pymupdf.open() as doc:
            page=doc.new_page(width=612,height=792)
            for column,left in enumerate((50,322)):
                for line in range(20):
                    text=' '.join(words[(line+column*3) % len(words):][:5])
                    page.insert_text((left,70+line*15),text,fontsize=10,fontname='helv')
            doc.save(path)
        return Path(path)

    def test_caption_above_table_is_emitted_once_inside_the_float(self):
        # Journal tables put the caption above the table; it has to travel inside
        # the float, and must not also be emitted as body text.
        caption = self.block('表 1. 结果对比。')
        caption['id'], caption['bbox'] = 'p1-b2', [0.1, 0.10, 0.9, 0.13]
        table = dict(kind='table', bbox=[0.1, 0.14, 0.9, 0.30], markdown='| A | B |\n|---|---|\n| 1 | 2 |',
                     page=1, id='p1-b3')
        body = self.block('正文')
        body['id'], body['bbox'] = 'p1-b4', [0.1, 0.32, 0.9, 0.5]
        text = assemble([dict(blocks=[caption, table, body])], None, Path('.'))
        self.assertEqual(text.count('表 1. 结果对比。'), 1)
        self.assertLess(text.index('<!-- translator-float: table -->'), text.index('表 1. 结果对比。'))
        self.assertLess(text.index('表 1. 结果对比。'), text.index('| A | B |'))

    def test_narrow_table_stays_inside_its_column(self):
        # A table that fits one column used to be promoted to a page-wide float,
        # which left a hole in the column and pushed it away from its text.
        with tempfile.TemporaryDirectory() as folder:
            path = self.two_column_pdf(Path(folder)/'two.pdf')
            narrow = dict(kind='table', bbox=[0.53, 0.2, 0.9, 0.3],
                          markdown='| A | B |\n|---|---|\n| 1 | 2 |', page=1, id='p1-b2')
            wide = dict(kind='table', bbox=[0.08, 0.6, 0.9, 0.7],
                        markdown='| ' + ' | '.join('c%d' % n for n in range(9)) + ' |\n|'
                                 + '---|' * 9 + '\n|' + ' 1 |' * 9, page=1, id='p1-b4')
            page = [self.block('左栏正文'), narrow, self.block('右栏正文'), wide]
            page[0]['bbox'], page[2]['bbox'] = [0.08, 0.1, 0.47, 0.2], [0.53, 0.1, 0.91, 0.2]
            text = assemble([dict(blocks=page)], path, Path(folder))
            self.assertIn('<!-- translator-float: table -->', text)
            self.assertIn('<!-- translator-float: table-span -->', text)
            # The in-column table must not open a spanning float before the column.
            self.assertLess(text.index('<!-- translator-columns: 2 -->'),
                            text.index('<!-- translator-float: table -->'))
            self.assertLess(text.index('<!-- translator-float: table -->'),
                            text.index('<!-- translator-float: table-span -->'))

    def test_three_column_table_leaves_the_column_region(self):
        # multicols cannot contain floats, so a page-wide table has to close the
        # column region, float, and let the pipeline reopen the region.
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder/'three.pdf'
            with pymupdf.open() as doc:
                doc.new_page(width=595, height=842)
                doc.save(path)
            # A forced count is what the user picks in the panel; the detected
            # grid of this blank page has nothing to offer.
            cache = folder/'cache'
            cache.mkdir()
            (cache/'layout.json').write_text('{"columns": 3}', 'utf-8')
            table = dict(kind='table', bbox=[0.07, 0.7, 0.93, 0.8],
                         markdown='| ' + ' | '.join('c%d' % n for n in range(9)) + ' |\n|'
                                  + '---|' * 9 + '\n|' + ' 1 |' * 9, page=1, id='p1-b2')
            body = self.block('正文')
            body['bbox'] = [0.05, 0.1, 0.30, 0.2]   # first column of three
            text = assemble([dict(blocks=[body, table])], path, cache)
            self.assertIn('<!-- translator-columns: 3 -->', text)
            opened = text.index('<!-- translator-columns: 3 -->')
            closed = text.index('<!-- translator-columns-end -->')
            float_at = text.index('<!-- translator-float: table-span -->')
            self.assertTrue(opened < closed < float_at)


        with tempfile.TemporaryDirectory() as folder:
            path=self.two_column_pdf(Path(folder)/'two.pdf')
            title=self.block('通栏标题'); title['bbox']=[0.2,0.05,0.8,0.09]
            left=self.block('左栏正文'); left['bbox']=[0.08,0.2,0.47,0.5]; left['id']='p1-b2'
            right=self.block('右栏正文'); right['bbox']=[0.51,0.2,0.91,0.5]; right['id']='p1-b3'
            text=assemble([dict(blocks=[title,left,right])],path,Path(folder))
            self.assertTrue(text.startswith('通栏标题\n\n<!-- translator-columns: 2 -->'))
            self.assertIn('左栏正文\n\n右栏正文',text)
            self.assertTrue(text.rstrip().endswith('<!-- translator-columns-end -->'))

    def test_single_column_document_has_no_column_markers(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'one.pdf'
            with pymupdf.open() as doc:
                page=doc.new_page(width=612,height=792)
                for line in range(20):
                    page.insert_text((50,70+line*15),'single column body text line',fontsize=10,fontname='helv')
                doc.save(path)
            pages=[dict(blocks=[self.block('正文一'),self.block('正文二')]),
                   dict(blocks=[self.block('正文三')])]
            text=assemble(pages,path,Path(folder))
            self.assertNotIn('translator-columns',text)
            self.assertNotIn('translator-float',text)

    def test_page_quality_and_render_format(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            path=folder/'source.pdf'
            with pymupdf.open() as doc:
                plain=doc.new_page(width=300,height=300)
                plain.insert_text((30,50),'ordinary prose without formulas')
                graphic=doc.new_page(width=300,height=300)
                for y in range(20,220,8):
                    graphic.draw_line((20,y),(280,y))
                doc.save(path)
            with pymupdf.open(path) as doc:
                self.assertEqual(page_quality(doc[0]),'normal')
                self.assertEqual(page_quality(doc[1]),'high')
                self.assertEqual(render_page(doc[0],folder)[1],'image/jpeg')
                self.assertEqual(render_page(doc[1],folder)[1],'image/png')

    def test_usage_is_summed_and_cleared(self):
        take_usage()
        record_usage({'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}, 'page')
        record_usage({'prompt_tokens':20,'completion_tokens':7,'total_tokens':27,
                      'completion_tokens_details':{'reasoning_tokens':3}}, 'formula-review')
        usage = take_usage()
        self.assertEqual(usage['requests'],2)
        self.assertEqual(usage['total_tokens'],42)
        self.assertEqual(usage['reasoning_tokens'],3)
        self.assertEqual(usage['by_kind']['page'],
                         {'requests':1,'prompt_tokens':10,'completion_tokens':5,'total_tokens':15})
        self.assertEqual(usage['by_kind']['formula-review']['requests'],1)
        self.assertEqual(take_usage(),{'requests':0,'by_kind':{}})

    def test_thinking_policy(self):
        self.assertFalse(thinking_enabled('auto',0))
        self.assertFalse(thinking_enabled('auto',1))
        self.assertTrue(thinking_enabled('auto',2))
        self.assertFalse(thinking_enabled('off',2))
        self.assertTrue(thinking_enabled('on',0))

    def page_response(self, blocks, finish='stop', usage=None):
        return {'choices':[{'finish_reason':finish,'message':{'content':json.dumps(
                    {'blocks':blocks, 'complete':True})}}],
                'usage':usage or {'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}


    def test_page_request_can_keep_reasoning(self):
        llm = SimpleNamespace(base_url='https://example.invalid/v1', api_key='k', model='m')
        block = {'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':'译文'}
        with patch('document_pipeline.api.json_request',
                   return_value=self.page_response([block])) as call:
            request_page(llm,b'img','','',thinking=True)
        self.assertNotIn('reasoning_effort',call.call_args.kwargs['payload'])

    def test_endpoint_without_reasoning_switch_still_works(self):
        llm = SimpleNamespace(base_url='https://example.invalid/v1', api_key='k', model='m')
        block = {'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':'译文'}
        error = api.PipelineError('unsupported field', status=400)
        with patch('document_pipeline.api.json_request',
                   side_effect=[error,self.page_response([block])]) as call:
            data = request_page(llm,b'img','','',thinking=False)
        self.assertEqual(call.call_count,2)
        self.assertIn('reasoning_effort',call.call_args_list[0].kwargs['payload'])
        self.assertNotIn('reasoning_effort',call.call_args_list[1].kwargs['payload'])
        self.assertNotIn('max_tokens',call.call_args_list[1].kwargs['payload'])
        self.assertTrue(data['complete'])

    def test_merged_headings_are_split(self):
        data = {'complete':True,'blocks':[{'kind':'heading','bbox':[.1,.1,.9,.2],
                'markdown':'# 第 7 章\n## 常微分方程','continues_previous':False,'continues_next':False}]}
        blocks = split_heading_blocks(data)['blocks']
        self.assertEqual([b['markdown'] for b in blocks],['# 第 7 章','## 常微分方程'])
        self.assertEqual({b['bbox'][0] for b in blocks},{.1})

    def test_dropped_equation_number_is_attached_from_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'source.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page(width=400,height=400)
                page.insert_text((300,200),'(7.1)')
                doc.save(path)
            data = {'complete':True,'blocks':[{'kind':'equation','bbox':[.1,.45,.9,.55],
                    'markdown':'$$x=1$$'}]}
            check_numbered_equations(path,0,data)
            self.assertTrue(data['blocks'][0]['markdown'].endswith(r'\tag{7.1}$$'))
            self.assertEqual(data['tags_added'],['7.1'])
            # An extra tagless display on the same line makes the target ambiguous.
            ambiguous = {'complete':True,'blocks':[
                {'kind':'equation','bbox':[.1,.45,.9,.55],'markdown':'$$x=1$$'},
                {'kind':'equation','bbox':[.1,.45,.9,.55],'markdown':'$$y=2$$'}]}
            with self.assertRaises(ValueError):
                check_numbered_equations(path,0,ambiguous)

    def test_boxes_at_or_past_the_page_edge_are_clamped(self):
        data = {'complete':True,'blocks':[
            {'kind':'equation','bbox':[.15,1.0,.85,1.0],'markdown':'$$x$$'},
            {'kind':'paragraph','bbox':[.1,1.01,.9,1.06],'markdown':'正文'},
            {'kind':'figure','bbox':[.1,1.0,.9,1.0],'markdown':''}]}
        data = adjust_boxes(data)
        self.assertEqual(data['bbox_adjusted'],2)
        for block in data['blocks'][:2]:
            self.assertLess(block['bbox'][1],block['bbox'][3])
        self.assertEqual(data['blocks'][2]['bbox'],[.1,1.0,.9,1.0])
        with self.assertRaises(ValueError):
            validate(data)

    def test_bottom_note_fragments_are_grouped_into_footnote(self):
        page = {'page':1,'blocks':[
            {'kind':'heading','bbox':[.1,.1,.9,.2],'markdown':'# 标题*'},
            {'kind':'paragraph','bbox':[.1,.2,.9,.22],'markdown':'作者 A$^{\\dagger}$，B$^{\\ddagger}$'},
            {'kind':'paragraph','bbox':[.1,.7,.9,.73],'markdown':'* 2023 年收到稿。'},
            {'kind':'paragraph','bbox':[.1,.73,.9,.76],'markdown':'**资助：** 基金。'},
            {'kind':'paragraph','bbox':[.1,.76,.9,.8],'markdown':'$^{\\dagger}$ 单位 A。'},
            {'kind':'paragraph','bbox':[.1,.95,.9,.97],'markdown':'版权所有 ©。'}]}
        merge_bottom_notes(page)
        self.assertEqual([block['kind'] for block in page['blocks']],
                         ['heading','paragraph','footnote','paragraph'])
        self.assertFalse(page['blocks'][0]['markdown'].endswith('*'))
        self.assertIn('[^',page['blocks'][1]['markdown'])
        self.assertIn('2023',page['blocks'][2]['markdown'])
        self.assertIn('资助',page['blocks'][2]['markdown'])
        self.assertIn('单位 A',page['blocks'][2]['markdown'])
        self.assertIn('版权所有',page['blocks'][3]['markdown'])

    def test_copyright_footer_is_dropped_from_body(self):
        pages = [{'page':1,'blocks':[
            {'kind':'paragraph','bbox':[.1,.2,.9,.3],'markdown':'正文'},
            {'kind':'paragraph','bbox':[.1,.95,.9,.97],'markdown':'版权所有 © 由 SIAM 持有。'}]}]
        drop_page_footers(pages)
        self.assertEqual(len(pages[0]['blocks']),1)

    def test_unmarked_bottom_note_becomes_page_note(self):
        page = {'page':2,'blocks':[
            {'kind':'paragraph','bbox':[.1,.7,.9,.8],'markdown':'† 单位 A。'}]}
        merge_bottom_notes(page)
        self.assertTrue(page['blocks'][0]['markdown'].startswith('::: {.translation-note}'))

    def test_symbol_note_is_anchored_to_author_line(self):
        data = {'complete':True,'blocks':[
            {'kind':'paragraph','bbox':[.1,.2,.9,.22],'markdown':'A. Author, B. Author*'},
            {'kind':'footnote','bbox':[.1,.9,.9,.95],'markdown':'[^1]: * Corresponding author.'},
            {'kind':'paragraph','bbox':[.1,.3,.9,.32],'markdown':'*Affiliation*'}]}
        data = normalize_notes(data)
        self.assertEqual(data['blocks'][0]['markdown'],'A. Author, B. Author[^1]')
        self.assertEqual(data['blocks'][1]['kind'],'footnote')
        self.assertEqual(data['blocks'][1]['markdown'],'[^1]: Corresponding author.')
        self.assertNotIn('dangling_notes', data)

    def test_note_without_marker_is_kept_as_body_text(self):
        data = {'complete':True,'blocks':[
            {'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':'正文[^1]'},
            {'kind':'footnote','bbox':[.1,.9,.9,.95],'markdown':'[^1]: 有标记的注释'},
            {'kind':'footnote','bbox':[.1,.95,.9,.97],'markdown':'[^2]: 参考文献'},
            {'kind':'footnote','bbox':[.1,.97,.9,.99],'markdown':'[^3]: '}]}
        blocks = normalize_notes(data)['blocks']
        self.assertEqual(len(blocks),3)
        self.assertEqual(blocks[1]['kind'],'footnote')
        self.assertEqual(blocks[2]['kind'],'paragraph')
        self.assertEqual(blocks[2]['markdown'],'参考文献')
        self.assertEqual(data['dangling_notes'],['2'])
        validate(data)

    def test_final_pages_cache_round_trip_and_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            pages = [{'page':1,'blocks':[self.block('译文')]}]
            fingerprint = pages_hash(pages)
            save_final_pages(cache, fingerprint, pages, {'unresolved':0}, 2, {'tier':'standard'}, 'local')
            loaded = load_final_pages(cache, fingerprint, 'local')
            self.assertEqual(loaded['pages'], pages)
            self.assertEqual(loaded['local_images'], 2)
            self.assertIsNone(load_final_pages(cache, fingerprint, 'ai'))
            self.assertIsNone(load_final_pages(cache, 'other', 'local'))
            (cache/'final-pages.json').write_text('{broken', encoding='utf-8')
            self.assertIsNone(load_final_pages(cache, fingerprint, 'local'))

    def test_running_header_is_dropped_but_real_heading_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'source.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page(width=400, height=600)
                page.insert_text((40,30),'1.2 Machine Arithmetic',fontsize=8)
                page.insert_text((40,100),'body text '*20,fontsize=11)
                doc.save(path)
            pages = [{'page':1,'blocks':[
                {'kind':'heading','bbox':[.1,.02,.6,.06],'markdown':'# 1.2 机器算术'},
                {'kind':'paragraph','bbox':[.1,.1,.9,.3],'markdown':'正文'}]}]
            drop_running_headers(path,pages)
            self.assertEqual([block['kind'] for block in pages[0]['blocks']],['paragraph'])
            plain = [{'page':1,'blocks':[
                {'kind':'heading','bbox':[.1,.02,.6,.06],'markdown':'# 1.2 机器算术'}]}]
            with pymupdf.open() as doc:
                doc.new_page(width=400,height=600).insert_text((40,100),'body text '*20,fontsize=11)
                doc.save(path)
            drop_running_headers(path,plain)
            self.assertEqual(len(plain[0]['blocks']),1)

    def test_split_two_line_heading_is_merged(self):
        page = {'page':2,'blocks':[
            {'kind':'heading','page':2,'bbox':[.1,.5,.9,.56],'markdown':'### 1.2.2 误差传播：'},
            {'kind':'heading','page':2,'bbox':[.1,.5,.9,.56],'markdown':'### 抵消误差'},
            {'kind':'paragraph','page':2,'bbox':[.1,.6,.9,.7],'markdown':'正文'}]}
        merge_adjacent_headings(page)
        self.assertEqual([block['kind'] for block in page['blocks']],['heading','paragraph'])
        self.assertEqual(page['blocks'][0]['markdown'],'### 1.2.2 误差传播：抵消误差')
        separate = {'page':2,'blocks':[
            {'kind':'heading','page':2,'bbox':[.1,.5,.9,.56],'markdown':'### 小节'},
            {'kind':'heading','page':2,'bbox':[.1,.6,.9,.66],'markdown':'### 另一个'}]}
        merge_adjacent_headings(separate)
        self.assertEqual(len(separate['blocks']),2)



    def table_source(self, path, lines, fontname='helv'):
        """A page whose text layer holds one table, for the language check."""
        with pymupdf.open() as doc:
            page = doc.new_page(width=400, height=600)
            for row, text in enumerate(lines):
                page.insert_text((40, 100+row*20), text, fontsize=10, fontname=fontname)
            doc.save(path)
        return Path(path)

    def test_table_keeps_source_text(self):
        # Tables are rebuilt in the source language: an English table must come
        # back English, and the columns are never re-wrapped by a translation.
        with tempfile.TemporaryDirectory() as folder:
            source = self.table_source(Path(folder)/'source.pdf',
                                       ['Subject Mean deviation', 'alpha 12.5 3.1', 'beta 7.25 0.85'])
            data = {'complete':True, 'blocks':[dict(kind='table', bbox=[.05,.15,.95,.25],
                    markdown='| Subject | Mean | deviation |\n|---|---|---|\n| alpha | 12.5 | 3.1 |')]}
            self.assertIsNone(check_table_language(source, 0, data))

    def test_translated_table_is_rejected(self):
        # A translated cell is longer than the original and breaks the layout,
        # so the page is rejected and the model is told to copy the cells.
        with tempfile.TemporaryDirectory() as folder:
            source = self.table_source(Path(folder)/'source.pdf',
                                       ['Subject Mean deviation', 'alpha 12.5 3.1', 'beta 7.25 0.85'])
            data = {'complete':True, 'blocks':[dict(kind='table', bbox=[.05,.15,.95,.25],
                    markdown='| 学科名称 | 平均值 | 偏差值 |\n|---|---|---|\n| 阿尔法系数 | 12.5 | 3.1 |\n| 贝塔系数 | 7.25 | 0.85 |')]}
            with self.assertRaises(ValueError):
                check_table_language(source, 0, data)

    def test_chinese_table_is_not_flagged(self):
        # The rule is "keep the source language", not "force English": a table
        # that really is Chinese in the PDF stays Chinese and passes.
        with tempfile.TemporaryDirectory() as folder:
            source = self.table_source(Path(folder)/'source.pdf',
                                       ['学科名称 平均值 偏差值', '阿尔法系数 12.5 3.1'], fontname='china-s')
            data = {'complete':True, 'blocks':[dict(kind='table', bbox=[.05,.15,.95,.25],
                    markdown='| 学科名称 | 平均值 | 偏差值 |\n|---|---|---|\n| 阿尔法系数 | 12.5 | 3.1 |')]}
            self.assertIsNone(check_table_language(source, 0, data))

    def test_small_table_with_translated_header_is_rejected(self):
        # A two-column table carries three characters of header at most, and the
        # old twelve-character rule let a fully translated one through.
        with tempfile.TemporaryDirectory() as folder:
            source = self.table_source(Path(folder)/'source.pdf',
                                       ['Group Accuracy', 'alpha 0.83', 'beta 0.29'])
            data = {'complete':True, 'blocks':[dict(kind='table', bbox=[.05,.15,.95,.25],
                    markdown='| 组 | 精度 |\n|---|---|\n| alpha | 0.83 |\n| beta | 0.29 |')]}
            with self.assertRaises(ValueError):
                check_table_language(source, 0, data)

    def test_one_chinese_word_in_an_english_table_is_tolerated(self):
        # The budget is measured against the source: one stray label must not send
        # the whole page back through the model.
        with tempfile.TemporaryDirectory() as folder:
            source = self.table_source(Path(folder)/'source.pdf',
                                       ['Subject Mean deviation', 'alpha 12.5 3.1', 'beta 7.25 0.85'])
            data = {'complete':True, 'blocks':[dict(kind='table', bbox=[.05,.15,.95,.25],
                    markdown='| Subject | Mean | deviation |\n|---|---|---|\n| alpha | 12.5 | 3.1 |\n'
                             '| beta（中文） | 7.25 | 0.85 |')]}
            self.assertIsNone(check_table_language(source, 0, data))

    def test_table_cells_read_pipe_and_html_tables(self):
        pipe = '| 方法 | RRA@15 |\n|---|---|\n| a | 1 |'
        self.assertEqual(table_cells(pipe), ['方法', 'RRA@15', 'a', '1'])
        html = '<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>'
        self.assertEqual(table_cells(html), ['A', 'B', '1', '2'])
        # A caption line above the table is a paragraph, never a cell.
        self.assertEqual(table_cells('表 1. 精度\n\n| a | b |'), ['a', 'b'])

    def test_prompt_forbids_translating_tables(self):
        # The instruction is the whole mechanism: a table block must carry the
        # original wording, never a translation.
        self.assertIn('表格只重建结构', PROMPT)
        self.assertIn('表格内容一律保留原文', PROMPT)
        self.assertNotIn('翻译正文、图注、表格', PROMPT)

    def test_ai_first_pass_still_receives_no_extracted_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((72,72),'WRONG extracted formula reference')
                doc.save(source)
            response = {'complete':True,'blocks':[{'kind':'paragraph',
                        'bbox':[.1,.1,.9,.2],'markdown':'译文'}]}
            from document_pipeline import process_page
            with patch('document_pipeline.request_page',return_value=response) as request:
                process_page(source,0,root/'cache',None,'test',1)
            self.assertEqual(request.call_args.args[2:4],('', ''))

    def test_echoed_english_body_page_is_flagged(self):
        # A page the model echoed instead of translating used to pass silently;
        # two English paragraphs prove the page, a short page does not.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page(width=595, height=842)
                page.insert_text((50, 70), 'Introduction body text', fontsize=10, fontname='helv')
                doc.save(source)
            english = ('the network predicts a depth map from the reference image and then refines it '
                       'with a cost volume and several convolutions before the final output is produced '
                       'and the differentiable homography warping encodes the camera geometry directly '
                       'while the metric maps multiple features into one cost volume feature')
            pages = [{'page':1,'blocks':[{'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':english},
                                         {'kind':'paragraph','bbox':[.1,.2,.9,.3],'markdown':english}]}]
            self.assertEqual(untranslated_pages(source, pages), [1])
            pages[0]['blocks'] = [{'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':english}]
            self.assertEqual(untranslated_pages(source, pages), [])

    def test_reference_pages_stay_in_the_source_language(self):
        # The bibliography is English by design: only pages before it may be
        # flagged, and a page whose paragraphs are a numbered list is exempt too.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.pdf'
            with pymupdf.open() as doc:
                doc.new_page(width=595, height=842).insert_text((50, 70), 'Body text', fontsize=10, fontname='helv')
                doc.new_page(width=595, height=842).insert_text((50, 70), 'References', fontsize=10, fontname='helv')
                doc.new_page(width=595, height=842).insert_text((50, 70), '[1] Aanaes H.', fontsize=10, fontname='helv')
                doc.save(source)
            self.assertEqual(references_start(source), 2)
            english = 'Zbontar J and LeCun Y stereo matching by training a convolutional network a b c d e f g h'
            pages = [{'page':2,'blocks':[{'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':english},
                                         {'kind':'paragraph','bbox':[.1,.2,.9,.3],'markdown':english}]},
                     {'page':3,'blocks':[{'kind':'paragraph','bbox':[.1,.1,.9,.9],
                                          'markdown':'\n'.join(f'[{i}] Author A. Title. Journal, 2018.' for i in range(1, 8))}]}]
            self.assertEqual(untranslated_pages(source, pages), [])

    def test_retry_reason_bypasses_the_cached_page(self):
        # The cache would hand back the identical echo, so a retried page must be
        # re-read and the instruction must reach the model as the error argument.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source.pdf'
            with pymupdf.open() as doc:
                doc.new_page(width=595, height=842).insert_text((50, 70), 'Body text', fontsize=10, fontname='helv')
                doc.save(source)
            cache = root/'cache'
            result = {'complete':True,'signature':'test','status':'translated',
                      'blocks':[{'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':'正文'}]}
            path = cache/'pages/0001/result.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(result), 'utf-8')
            response = {'complete':True,'blocks':[{'kind':'paragraph','bbox':[.1,.1,.9,.2],'markdown':'中文正文'}]}
            with patch('document_pipeline.request_page', return_value=response) as request:
                page = process_page(source, 0, cache, None, 'test', 1,
                                    retry_reason='第 1 页正文仍然是原文语言')
            self.assertEqual(request.call_count, 1)
            self.assertIn('第 1 页正文仍然是原文语言', request.call_args.args[4])
            self.assertEqual(page['blocks'][0]['markdown'], '中文正文')


if __name__=='__main__':
    unittest.main()
