import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import pymupdf
from document_structure import (build_source_index, resolve_document_structure, resolve_cached,
                                numbered_level, page_segments, validate_analysis)
from document_pipeline import assemble


def block(text, box=None, role='body', kind='paragraph'):
    return dict(kind=kind, source_text=text, markdown=text, role_candidate=role,
                bbox=box or [.1,.3,.9,.34], status='translated')


def page(number, *blocks):
    return dict(page=number, complete=True, recognition_schema=2,
                blocks=[dict(b, id=f'p{number}-b{i}', page=number) for i,b in enumerate(blocks,1)])


def node(name, title, number, level, parent=None):
    return dict(id=name,title=title,page=number,level=level,parent_id=parent)


def index(nodes=None, pages=None):
    return dict(nodes=nodes or [], pages=pages or {}, diagnostics=[], key='fixture')


class StructureTests(unittest.TestCase):
    def resolve(self, pages, evidence=None, overrides=None):
        return resolve_document_structure(pages, evidence or index(), overrides)

    def test_recorded_model_regions_from_book(self):
        path=Path(__file__).resolve().parent.parent/'tests/fixtures/book-structure-regression.json'
        fixture=json.loads(path.read_text('utf-8'))
        result=self.resolve(fixture['pages'],fixture['index'])
        self.assertFalse(result['diagnostics'])
        visible=[b for p in result['pages'] for b in p['blocks'] if not b['excluded']]
        self.assertEqual([b['heading_level'] for b in visible],[1,2,2])
        self.assertEqual([b['role'] for b in result['pages'][1]['blocks'][:2]],['running_header','page_number'])
        self.assertEqual(result['pages'],self.resolve(result['pages'],fixture['index'])['pages'])

    def test_book_page_24_identical_header_and_section_title(self):
        header=block('§2. Orthogonality',[.03,.04,.45,.06],'running_header')
        title=block('§2. Orthogonality',[.04,.65,.8,.69],'heading','heading')
        raw=[page(24,header,block('Exercise 11 remains body'),title,block('2.1. Definition',kind='heading'))]
        evidence=index([node('chapter','Chapter I. Hilbert Spaces',18,1),
                        node('section','§2. Orthogonality',24,2,'chapter')],
                       {'24':dict(regions=[dict(header,role='running_header')])})
        result=self.resolve(raw,evidence);blocks=result['pages'][0]['blocks']
        self.assertTrue(blocks[0]['excluded'])
        self.assertEqual(blocks[2]['heading_level'],2)
        self.assertEqual(blocks[2]['parent_id'],'chapter')
        self.assertEqual(blocks[3]['role'],'body_label')
        self.assertFalse(blocks[3]['excluded'])
        self.assertEqual(result['diagnostics'],[])
        self.assertNotIn('excluded',raw[0]['blocks'][0])

    def test_two_line_chapter_and_section_on_same_page(self):
        raw=[page(18,block('CHAPTER I',[.04,.09,.5,.11],'heading','heading'),
                  block('Hilbert Spaces',[.04,.12,.7,.15],'heading','heading'),
                  block('§1. Elementary Properties and Examples',[.04,.6,.9,.64]),
                  block('1.1. Definition',kind='heading'))]
        evidence=index([node('c','Chapter I. Hilbert Spaces',18,1),
                        node('s','§1. Elementary Properties and Examples',18,2,'c')])
        result=self.resolve(raw,evidence);blocks=result['pages'][0]['blocks']
        self.assertEqual(blocks[0].get('heading_level'),1)
        self.assertEqual(blocks[1].get('merged_into'),blocks[0]['id'])
        self.assertEqual(blocks[2]['heading_level'],2)
        self.assertEqual(blocks[3]['role'],'body_label')

    def test_body_labels_before_after_number_and_outline_exception(self):
        labels=['7.14. 命题','1.1. Definition','定理 3.2','Proposition 4.1','3.2 节']
        raw=[page(1,*[block(x,kind='heading') for x in labels],block('3.1.2 例题',kind='heading'))]
        blocks=self.resolve(raw,index([node('example','3.1.2 例题',1,3)]))['pages'][0]['blocks']
        self.assertEqual([b['role'] for b in blocks[:-1]],['body_label']*len(labels))
        self.assertEqual(blocks[-1]['heading_level'],3)

    def test_repeat_margins_parity_and_numeric_sequence(self):
        raw=[page(n,block('Author' if n%2 else 'Book title',[.1,.02,.5,.05],'running_header'),
                  block(str(n),[.8,.94,.85,.96],'page_number'),block('Actual body')) for n in range(1,7)]
        for p in self.resolve(raw)['pages']:
            self.assertEqual([b['excluded'] for b in p['blocks']],[True,True,False])

    def test_mixed_block_short_body_and_footnote_never_removed(self):
        raw=[page(n,block('Header plus a full body paragraph',[.1,.02,.9,.3],'running_header'),
                  block('12',[.1,.9,.2,.93]),
                  block('[^1]: copyright is discussed here',[.1,.91,.9,.97],'footnote','footnote')) for n in range(1,4)]
        result=self.resolve(raw)
        self.assertTrue(all(not b.get('excluded') for p in result['pages'] for b in p['blocks']))
        self.assertTrue(any(d['reason']=='uncertain_margin_or_mixed_block' for d in result['diagnostics']))

    def test_bookmark_page_alone_never_promotes_unrelated_text(self):
        result=self.resolve([page(1,block('A different paragraph'))],index([node('c','Introduction',1,1)]))
        self.assertEqual(result['pages'][0]['blocks'][0]['role'],'body')

    def test_partial_selection_repeated_section_name_keeps_parent(self):
        evidence=index([node('c1','Chapter I',1,1),node('s1','§1. Examples',1,2,'c1'),
                        node('c2','Chapter II',20,1),node('s2','§1. Examples',20,2,'c2')])
        b=self.resolve([page(20,block('§1. Examples'))],evidence)['pages'][0]['blocks'][0]
        self.assertEqual(b['parent_id'],'c2');self.assertEqual(b['heading_level'],2)

    def test_contents_entries_not_recreated_as_body_headings(self):
        result=self.resolve([page(14,block('Chapter I. Hilbert Spaces',kind='heading'))],
                            index([node('c','Chapter I. Hilbert Spaces',18,1)],{'14':{'is_contents':True}}))
        self.assertEqual(result['pages'][0]['blocks'][0]['role'],'toc_entry')

    def test_pure_assembly_resolution_idempotence_and_override(self):
        raw=[page(1,block('Some heading',role='heading',kind='heading'))]
        overrides={'p1-b1':{'role':'heading','heading_level':3,'parent_id':'external'}}
        first=self.resolve(raw,overrides=overrides)
        self.assertEqual(first['pages'],self.resolve(first['pages'],overrides=overrides)['pages'])
        before=copy.deepcopy(first['pages']);text=assemble(first['pages'],None,Path('.'))
        self.assertEqual(first['pages'],before);self.assertIn('### Some heading',text)
        restored=self.resolve(first['pages'],overrides={'p1-b1':{'role':'body'}})
        self.assertEqual(restored['pages'][0]['blocks'][0]['role'],'body');self.assertFalse(restored['diagnostics'])

    def test_legacy_diagnostic_and_structure_cache_invalidation(self):
        raw=[page(1,block('Body'))];raw[0].pop('recognition_schema')
        with tempfile.TemporaryDirectory() as folder:
            a=resolve_cached(raw,index(),folder)
            b=resolve_cached(raw,index(),folder,{'p1-b1':{'role':'heading','heading_level':2}})
            self.assertNotEqual(a['cache_key'],b['cache_key'])
            self.assertTrue(any(d['reason']=='legacy_recognition' for d in a['diagnostics']))
            self.assertEqual(a,resolve_cached(raw,index(),folder))

    def test_page_mapping_resets_gaps_and_roman_frontmatter(self):
        segments=page_segments([(9,'vii'),(13,'xi'),(18,'1'),(24,'7'),(30,'12'),(31,'13')])
        self.assertEqual([(s['style'],s['offset']) for s in segments],[('roman',2),('arabic',17),('arabic',18)])

    def test_numbering_roman_section_and_decimal(self):
        self.assertEqual(numbered_level('Chapter IV. Spaces'),1)
        self.assertEqual(numbered_level('§2. Orthogonality'),2)
        self.assertEqual(numbered_level('3.2.1 Integral'),3)
        self.assertIsNone(numbered_level('第3章习题与上机作业'))

    def test_scan_bookmarks_and_offline_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.pdf'
            with pymupdf.open() as d:
                for _ in range(3): d.new_page()
                d.set_toc([[1,'Contents',1],[1,'Chapter I. Spaces',2],[2,'§1. Examples',2]])
                d.save(source)
            def analyze(images):
                return {'pages':[dict(page=n,is_contents=n==1,printed_page=str(n-1) if n>1 else '',
                    regions=[],entries=[dict(title='Chapter I. Spaces',level=1,printed_page='1'),
                                        dict(title='§1. Examples',level=2,printed_page='1')] if n==1 else []) for n,_ in images]}
            reader=Mock(side_effect=analyze)
            evidence=build_source_index(source,[2],folder,{'model':'fake'},reader)
            self.assertTrue(reader.called)
            self.assertEqual(evidence['nodes'][2]['parent_id'],evidence['nodes'][1]['id'])
            self.assertEqual(evidence,build_source_index(source,[2],folder,{'model':'fake'}))
            self.assertEqual(evidence,build_source_index(source,[2],folder,{'model':'fake'},reader))
            self.assertEqual(reader.call_count,1)

    def test_analysis_rejects_missing_and_invented_pages(self):
        with self.assertRaises(ValueError): validate_analysis({'pages':[]},[1])
        with self.assertRaises(ValueError): validate_analysis({'pages':[{'page':2,'is_contents':False}]},[1])

    def test_independent_region_tolerates_jitter_but_not_body_overlap(self):
        header=block('Running title',[.06,.03,.3,.055],'running_header')
        body=block('Running title',[.06,.6,.7,.64],'heading','heading')
        evidence=index([node('s','Running title',1,2)],{'1':{'regions':[
            {'source_text':'Running title','bbox':[.06,.05,.24,.07],'role':'running_header'}]}})
        result=self.resolve([page(1,header,body)],evidence)['pages'][0]['blocks']
        self.assertTrue(result[0]['excluded']);self.assertFalse(result[1]['excluded'])

    def test_native_cross_page_evidence_works_for_single_selected_page(self):
        line=dict(source_text='Running title',bbox=[.1,.03,.4,.05])
        evidence=index(pages={str(n):{'lines':[line]} for n in range(1,5)})
        result=self.resolve([page(2,block('Running title',line['bbox'],kind='heading'),block('Body'))],evidence)
        self.assertTrue(result['pages'][0]['blocks'][0]['excluded'])
        self.assertFalse(result['pages'][0]['blocks'][1]['excluded'])

    def test_contents_parent_number_disambiguates_similar_chapters_and_abbreviations(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.pdf'
            with pymupdf.open() as d:
                for _ in range(4):d.new_page()
                d.set_toc([[1,'Contents',1],[1,'Chapter II. Operators on Hilbert Space',2],
                           [2,'§5. The Components of the Fredholm Operators',2],
                           [1,'Chapter IX. Normal Operators on Hilbert Space',4]])
                d.save(source)
            def analyze(images):
                return {'pages':[dict(page=n,is_contents=n==1,printed_page='',regions=[],entries=[
                    dict(title='CHAPTER II Operators on Hilbert Space',level=1,printed_page='1'),
                    dict(title='§5. The Components of SF',level=2,printed_page='1'),
                    dict(title='CHAPTER IX Normal Operators on Hilbert Space',level=1,printed_page='3')
                    ] if n==1 else []) for n,_ in images]}
            result=build_source_index(source,[2],analyze=analyze)
            self.assertEqual(len(result['nodes']),4)
            self.assertFalse(result['diagnostics'])
            self.assertEqual(result['nodes'][2]['parent_id'],result['nodes'][1]['id'])

    def test_structure_version_invalidates_only_derived_cache(self):
        from unittest.mock import patch
        raw=[page(1,block('Body'))]
        with tempfile.TemporaryDirectory() as folder:
            before=resolve_cached(raw,index(),folder)
            with patch('document_structure.STRUCTURE_VERSION','next-version'):
                after=resolve_cached(raw,index(),folder)
            self.assertNotEqual(before['cache_key'],after['cache_key'])
            self.assertEqual(raw,[page(1,block('Body'))])


if __name__ == '__main__':
    unittest.main()
