import copy
import json
import tempfile
import unittest
from pathlib import Path
import pymupdf
from figure_geometry import resolve_figure_crop
from document_pipeline import assemble


class FigureGeometryTests(unittest.TestCase):
    def test_cut_frame_and_labels_recovered_without_caption_or_body(self):
        with pymupdf.open() as pdf:
            p=pdf.new_page(width=400,height=600)
            p.draw_rect((120,100,250,155))
            p.insert_text((180,97),'f',fontsize=9)
            p.insert_text((270,130),'(v > n)',fontsize=9)
            p.insert_text((100,185),'Fig. 1.2 A caption, not part of the image',fontsize=9)
            p.insert_text((40,210),'A sufficiently long body paragraph outside the figure must remain outside.',fontsize=10)
            r=resolve_figure_crop(p,[.25,110/600,.78,180/600])
            self.assertFalse(r['diagnostics'])
            self.assertLess(r['bbox'][1]*600,88)
            self.assertGreater(r['bbox'][2]*400,290)
            self.assertLess(r['bbox'][3]*600,175)

    def test_axis_arrow_outside_seed_and_its_label_are_preserved(self):
        with pymupdf.open() as pdf:
            p=pdf.new_page(width=400,height=600)
            p.draw_line((200,190),(200,285))
            p.draw_polyline([(197,197),(200,190),(203,197)])
            p.draw_line((155,245),(260,245))
            p.insert_text((207,186),'x2',fontsize=9)
            r=resolve_figure_crop(p,[.35,.35,.7,.49])
            self.assertFalse(r['diagnostics'])
            self.assertLess(r['bbox'][1]*600,180)

    def test_bitmap_rules_are_graphics_not_ignored_images(self):
        with pymupdf.open() as pdf:
            p=pdf.new_page(width=400,height=600)
            pixel=pymupdf.Pixmap(pymupdf.csGRAY,pymupdf.IRect(0,0,1,1),False)
            pixel.clear_with(0)
            data=pixel.tobytes('png')
            for rect in ((100,100,300,101),(100,101,101,125),(299,101,300,125),(100,125,300,126)):
                p.insert_image(rect,stream=data,keep_proportion=False)
            r=resolve_figure_crop(p,[.24,105/600,.76,140/600])
            self.assertFalse(r['diagnostics'])
            self.assertLess(r['bbox'][1]*600,100)
            self.assertGreater(r['bbox'][3]*600,126)

    def test_full_page_scan_requires_review_not_false_verification(self):
        with pymupdf.open() as pdf:
            p=pdf.new_page(width=400,height=600)
            pix=pymupdf.Pixmap(pymupdf.csGRAY,pymupdf.IRect(0,0,400,600),False)
            pix.clear_with(255)
            p.insert_image(p.rect,stream=pix.tobytes('png'))
            box=[.2,.2,.6,.4];r=resolve_figure_crop(p,box)
            self.assertEqual(r['bbox'],box)
            self.assertEqual(r['diagnostics'],['figure_object_exceeds_search_region'])

    def test_rotated_page_geometry_matches_render_coordinates(self):
        with pymupdf.open() as pdf:
            p=pdf.new_page(width=400,height=600)
            p.draw_rect((100,100,250,160))
            p.set_rotation(90)
            r=resolve_figure_crop(p,[.74,.26,.83,.63])
            self.assertFalse(r['diagnostics'])
            target=pymupdf.Rect(100,100,250,160)*p.rotation_matrix
            box=r['bbox'];actual=pymupdf.Rect(box[0]*600,box[1]*400,box[2]*600,box[3]*400)
            self.assertTrue(actual.contains(target))

    def test_assembly_is_repeatable_and_keeps_recognition_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache=Path(temporary);source=cache/'source.pdf'
            with pymupdf.open() as pdf:
                p=pdf.new_page(width=400,height=600);p.draw_rect((100,100,250,160));pdf.save(source)
            pages=[dict(page=1,blocks=[dict(id='p1-b1',page=1,kind='figure',bbox=[.24,.18,.65,.28],markdown='label',status='translated')])]
            before=copy.deepcopy(pages)
            first=assemble(pages,source,cache)
            image=(cache/'crops/p1-b1.png').read_bytes()
            self.assertEqual(assemble(pages,source,cache),first)
            self.assertEqual((cache/'crops/p1-b1.png').read_bytes(),image)
            self.assertEqual(pages,before)
            self.assertFalse(json.loads((cache/'crop-report.json').read_text())['figures']['p1-b1']['diagnostics'])


if __name__=='__main__':unittest.main()
