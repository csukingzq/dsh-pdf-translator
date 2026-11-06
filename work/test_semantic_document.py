import copy
import tempfile
import unittest
from pathlib import Path
from semantic_document import bind_notes, units_for, batches_for, translate_document
from document_structure import resolve_document_structure
from document_pipeline import assemble


def block(identifier, text, kind='paragraph', page=1, **extra):
    return dict(id=identifier, page=page, kind=kind, markdown=text, source_text=text,
                bbox=[.1,.7,.9,.9] if kind=='footnote' else [.1,.2,.9,.6],
                role_candidate='footnote' if kind=='footnote' else 'body', **extra)


def document(*blocks):
    pages = {}
    for b in blocks:
        pages.setdefault(b['page'], dict(page=b['page'], blocks=[], recognition_schema=2,
                                        complete=True, semantic_document=True))['blocks'].append(b)
    return list(pages.values())


class SemanticTests(unittest.TestCase):
    def test_author_star_and_unmarked_publication_note(self):
        pages=document(block('authors','Lei Bi a, Ping Yang a,*, George W. Kattawar b, Michael I. Mishchenko c'),
                       block('correspondence','[^1]: 通讯地址：University','footnote'),
                       block('publication','[^2]: 版权与 DOI','footnote'))
        pages[0]['blocks'][1]['source_text']='*Correspondence to: University'
        pages[0]['blocks'][2]['source_text']='0022-4073/$ © 2012 Elsevier. http://dx.doi.org/example'
        notes, diagnostics=bind_notes(pages)
        self.assertFalse(diagnostics)
        self.assertEqual(notes[0]['anchors'],['authors'])
        self.assertEqual(notes[0]['marker'],'*')
        self.assertEqual(pages[0]['blocks'][2]['note_type'],'publication')
        self.assertNotIn('publication]',pages[0]['blocks'][0]['markdown'])
        self.assertIn('a,[^note-correspondence], George',pages[0]['blocks'][0]['markdown'])

    def test_superscript_and_math_legacy_notes_are_restored(self):
        raw = document(block('p1-b1', '正文¹ 和 Hilbert$^2$'),
                       block('p1-b2', '注释一', role='footnote'),
                       block('p1-b3', '[^2]: 注释二', 'footnote'))
        raw[0]['blocks'][1].update(source_text='1Rounding errors', role_candidate='footnote')
        original = copy.deepcopy(raw)
        result = resolve_document_structure(raw, {})
        self.assertEqual(raw, original)
        self.assertEqual(len(result['notes']), 2)
        self.assertTrue(all(n['anchors']==['p1-b1'] for n in result['notes']))
        self.assertEqual(result['pages'][0]['blocks'][1]['kind'], 'footnote')
        again = resolve_document_structure(result['pages'], {})
        self.assertEqual(result['pages'], again['pages'])

    def test_page_local_number_reset_and_unlinked_preservation(self):
        pages = document(block('p1-b1','正文¹'), block('p1-b2','[^1]: 一','footnote'),
                         block('p2-b1','正文¹',page=2),block('p2-b2','[^1]: 二','footnote',2),
                         block('p2-b3','[^9]: 无锚点','footnote',2))
        result = resolve_document_structure(pages,{})
        self.assertEqual(result['notes'][0]['anchors'],['p1-b1'])
        self.assertEqual(result['notes'][1]['anchors'],['p2-b1'])
        self.assertEqual(result['notes'][2]['anchors'],[])
        with tempfile.TemporaryDirectory() as folder:
            before = copy.deepcopy(result['pages'])
            text = assemble(result['pages'],None,Path(folder))
            self.assertIn('未关联脚注', text)
            self.assertIn('无锚点',text)
            self.assertIn('[^note-p1-b2]',text)
            self.assertIn('[^note-p2-b2]',text)
            self.assertEqual(result['pages'],before)

    def test_explicit_cross_page_note_override(self):
        pages = document(block('p1-b1','正文'), block('p2-b1','[^1]: 注','footnote',2,
                         note_override={'anchors':['p1-b1']}))
        result=resolve_document_structure(pages,{})
        self.assertEqual(result['notes'][0]['anchors'],['p1-b1'])
        self.assertIn('[^note-p2-b1]',result['pages'][0]['blocks'][0]['markdown'])

    def test_translation_batch_crosses_pages_and_protects_math(self):
        pages=resolve_document_structure(document(block('p1-b1','Start $x_1$'),
                    block('p2-b1','continued.',page=2)),{})['pages']
        calls=[]
        def request(payload,error):
            calls.append(payload)
            return {'units':[dict(id=u['id'],text='译文 '+u['text']) for u in payload['units']]}
        with tempfile.TemporaryDirectory() as folder:
            result=translate_document(pages,[],folder,{'model':'test'},request)
            self.assertEqual(len(calls),1)
            self.assertEqual(len(calls[0]['units']),2)
            self.assertNotIn('$x_1$',calls[0]['units'][0]['text'])
            self.assertIn('$x_1$',result['pages'][0]['blocks'][0]['markdown'])
            translate_document(pages,[],folder,{'model':'test'},lambda *a:self.fail('cache miss'))

    def test_invalid_translation_retries_then_preserves_source(self):
        pages=resolve_document_structure(document(block('p1-b1','Source $x$')), {})['pages']
        calls=[]
        def request(payload,error):
            calls.append(error)
            return {'units':[dict(id=payload['units'][0]['id'],text='missing formula')]}
        with tempfile.TemporaryDirectory() as folder:
            result=translate_document(pages,[],folder,{},request)
        self.assertEqual(len(calls),3)
        self.assertEqual(result['pages'][0]['blocks'][0]['markdown'],'Source $x$')
        self.assertEqual(result['diagnostics'][0]['reason'],'translation_failed')

    def test_author_names_are_not_failed_translation(self):
        from semantic_document import is_author_list
        self.assertTrue(is_author_list('Lei Bi a, Ping Yang a,*, George W. Kattawar b, Michael I. Mishchenko c'))
        self.assertTrue(is_author_list('Lei Bi a, Ping Yang a,*'))
        self.assertFalse(is_author_list('The first result, the second result, and the final result are discussed.'))

    def test_failed_unit_does_not_discard_valid_neighbor(self):
        pages = resolve_document_structure(document(block('a','Source $x$'),
                    block('b','Other $y$')), {})['pages']
        calls = []
        def request(payload, error):
            calls.append(error)
            return {'units':[dict(id=u['id'], text=('译文 '+u['text']) if u['id'].startswith('a:') else 'broken')
                             for u in payload['units']]}
        with tempfile.TemporaryDirectory() as folder:
            result = translate_document(pages, [], folder, {}, request)
        self.assertEqual(len(calls), 3)
        self.assertIn('译文', result['pages'][0]['blocks'][0]['markdown'])
        self.assertEqual([d['block'] for d in result['diagnostics']], ['b'])

    def test_duplicate_marker_is_not_guessed(self):
        pages=document(block('p1-b1','正文¹'),block('p1-b2','[^1]: 一','footnote'),
                       block('p1-b3','[^1]: 二','footnote'))
        notes, diagnostics=bind_notes(pages)
        self.assertEqual(len(diagnostics),2)
        self.assertTrue(all(not n['anchors'] for n in notes))

    def test_repeated_reference_and_header_export(self):
        from latex_renderer import build_project
        pages=document(block('p1-b1','# 1 标题','heading'),block('p1-b2','正文¹，再次¹'),
                       block('p1-b3','[^1]: 注释','footnote'))
        pages[0]['blocks'][0]['role_candidate']='heading'
        result=resolve_document_structure(pages,{})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            build_project(assemble(result['pages'],None,root),root,root/'project')
            tex=(root/'project/main.tex').read_text('utf-8')
        self.assertNotIn('DSHNOTELABEL',tex)
        self.assertIn(r'\label{dsh-note-',tex)
        self.assertIn(r'\textsuperscript{\ref{dsh-note-',tex)
        self.assertIn(r'\markboth{',tex)
        self.assertEqual(tex.count(r'\footnote{'),1)

    def test_cross_page_continuation_keeps_source_ids(self):
        pages=document(block('p1-b1','正文¹'),block('p1-b2','[^1]: 前半','footnote',continues_next=True),
                       block('p2-b1','后半','footnote',2,continues_previous=True))
        result=resolve_document_structure(pages,{})
        self.assertEqual(len(result['notes']),1)
        self.assertEqual(result['pages'][0]['blocks'][1]['source_ids'],['p1-b2','p2-b1'])
        self.assertTrue(result['pages'][1]['blocks'][0]['excluded'])
        self.assertIn('后半',result['pages'][0]['blocks'][1]['markdown'])

    def test_three_page_note_continuation(self):
        pages=document(block('p1-b1','正文¹'),block('p1-b2','[^1]: 前','footnote',continues_next=True),
            block('p2-b1','中','footnote',2,continues_previous=True,continues_next=True),
            block('p3-b1','后','footnote',3,continues_previous=True))
        result=resolve_document_structure(pages,{})
        self.assertEqual(len(result['notes']),1)
        self.assertEqual(result['pages'][0]['blocks'][1]['source_ids'],['p1-b2','p2-b1','p3-b1'])
        with tempfile.TemporaryDirectory() as folder:
            translated=translate_document(result['pages'],[],folder,{},lambda payload,error:{'units':payload['units']})
        again=resolve_document_structure(translated['pages'],{})
        text=again['pages'][0]['blocks'][1]['markdown']
        self.assertEqual(text.count('中'),1)
        self.assertEqual(text.count('后'),1)

    def test_scan_wide_header_and_identical_body_title(self):
        a=block('p1-b1','§2. Orthogonality');a.update(bbox=[.05,.04,.95,.07],role_candidate='running_header')
        b=block('p1-b2','§2. Orthogonality','heading');b.update(bbox=[.06,.6,.5,.64],role_candidate='heading')
        index={'pages':{'1':{'regions':[dict(source_text=a['source_text'],bbox=[.06,.05,.24,.07],role='running_header')]}}}
        result=resolve_document_structure(document(a,b),index)
        self.assertTrue(result['pages'][0]['blocks'][0]['excluded'])
        self.assertFalse(result['pages'][0]['blocks'][1]['excluded'])

    def test_partial_selection_inherits_full_document_chapter(self):
        tree=[dict(id='c',title='Chapter I',page=1,level=1,parent_id=None),
              dict(id='s',title='Section 2',page=4,level=2,parent_id='c')]
        units=units_for(document(block('p8-b1','Paragraph',page=8)),tree)
        self.assertEqual(units[0]['chapter'],['Chapter I','Section 2'])

    def test_plain_number_requires_native_superscript_evidence(self):
        pages=document(block('p1-b1','Hilbert2 matrix'),block('p1-b2','[^2]: Note','footnote'))
        without=resolve_document_structure(pages,{})
        self.assertFalse(without['notes'][0]['anchors'])
        evidence={'pages':{'1':{'lines':[dict(source_text='Hilbert2 matrix',bbox=[.1,.2,.9,.6],
            superscripts=[dict(text='2',bbox=[.3,.3,.31,.32])])]}}}
        with_evidence=resolve_document_structure(pages,evidence)
        self.assertEqual(with_evidence['notes'][0]['anchors'],['p1-b1'])

    def test_long_small_print_note_does_not_define_body_font(self):
        header=block('p3-b1','Running Section',page=3)
        header.update(bbox=[.1,.03,.9,.07],role_candidate='running_header')
        note=block('p3-b3','A long note','footnote',3)
        index={'pages':{str(n):{'lines':[
            dict(source_text='Running Section',bbox=[.1,.04,.4,.06],font_size=8),
            dict(source_text='Normal body paragraph',bbox=[.1,.3,.9,.4],font_size=10),
            dict(source_text='note '*300,bbox=[.1,.75,.9,.8],font_size=8)]} for n in (1,2,3)}}
        result=resolve_document_structure(document(header,block('p3-b2','Normal body paragraph',page=3),note),index)
        self.assertTrue(result['pages'][0]['blocks'][0]['excluded'])
        self.assertFalse(result['pages'][0]['blocks'][1]['excluded'])

    def test_publication_footer_does_not_reject_translated_body(self):
        footer=block('p1-b2','© Example Academic Publisher International, DOI 10.123/example')
        footer['role_candidate']='running_footer'
        pages=resolve_document_structure(document(block('p1-b1','An ordinary paragraph with enough English letters to require translation.'),footer),{})['pages']
        def request(payload,error):
            return {'units':[dict(id=u['id'],text='正文译文' if u['id'].startswith('p1-b1:') else u['text']) for u in payload['units']]}
        with tempfile.TemporaryDirectory() as folder:
            result=translate_document(pages,[],folder,{},request)
        self.assertEqual(result['diagnostics'],[])
        self.assertEqual(result['pages'][0]['blocks'][0]['markdown'],'正文译文')


if __name__ == '__main__':
    unittest.main()
