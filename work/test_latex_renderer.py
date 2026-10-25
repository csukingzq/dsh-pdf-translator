import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import latex_renderer
from latex_renderer import build_project, safe_math, render_latex, break_long_urls


class LatexRendererTests(unittest.TestCase):
    def test_bare_urls_get_break_points_but_url_commands_do_not(self):
        broken = break_long_urls('see https://doi.org/10.1016/j.apnum.2023.12.005 now')
        self.assertIn('https://doi', broken)
        self.assertIn('10.\\allowbreak{}1016', broken)
        self.assertTrue(broken.endswith(' now'))
        self.assertEqual(break_long_urls(r'\url{https://doi.org/10.1016/j.apnum.2023.12.005}'),
                         r'\url{https://doi.org/10.1016/j.apnum.2023.12.005}')

    def test_figure_keeps_following_caption(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)
            (project/'figure.png').write_bytes(b'fixture')
            build_project('![](figure.png)\n\n图 6.1 图题\n\n正文',project,project)
            self.assertIn(r'\end{center}\nopagebreak[4]',(project/'main.tex').read_text('utf-8'))

    def test_html_break_in_markdown_table_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)
            build_project('| A | B |\n|---|---|\n| 第一行<br>第二行 | $x$ |',project,project)
            tex=(project/'main.tex').read_text('utf-8')
            self.assertIn('第一行',tex)
            self.assertIn('第二行',tex)
            self.assertNotIn('<br>',tex)

    def test_local_html_table_and_code_block_compile(self):
        text = ('# 标题\n\n<table><tr><td>n</td><td>$a_{1}$</td></tr></table>\n\n'
                '$$x=1\\tag{1.1}$$\n\n~~~~text\nprint(1)\n~~~~\n')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'table.pdf'
            render_latex(text, Path(folder), output)
            self.assertTrue(output.is_file())

    def test_matrix_row_divided_difference_is_not_row_spacing(self):
        source = r'\begin{array}{cc}[x_1,x_1]p&0\\ [x_1,x_2]p&1\\[2pt]0&1\end{array}'
        fixed = safe_math(source)
        self.assertIn(r'\\{} [x_1,x_2]', fixed)
        self.assertIn(r'\\[2pt]', fixed)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'matrix.pdf'
            render_latex('$$'+source+'$$', Path(folder), output)
            self.assertTrue(output.is_file())
    def test_adjacent_complete_notes_use_native_footnotes(self):
        text = '\n\n'.join('<small><span class="docvortex-page-footnote">$^{'+str(n)+'}$ 这里是一条完整的中文脚注，含有公式 $x+n$，应当保留在页底。</span></small>' for n in [3,4])
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            build_project(text, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertEqual(tex.count(r'\footnotetext[3]'), 1)
            self.assertEqual(tex.count(r'\footnotetext[4]'), 1)
            self.assertNotIn(r'\begin{quote}', tex)
            self.assertNotIn(r'\(^{3}\)', tex)

    def test_unique_note_marker_moves_note_to_anchor(self):
        text = '正文中的引用$^4$。\n\n<small><span class="docvortex-page-footnote">$^{4}$ 这是一条足够完整的中文脚注，应跟随正文中的引用位置排版。</span></small>'
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            counts = build_project(text, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertEqual(counts['anchored_notes'], 1)
            self.assertIn(r'正文中的引用\footnote[4]{', tex)
            self.assertNotIn(r'\footnotetext[4]', tex)

    def test_repaired_note_wrapper_does_not_hide_marker(self):
        text = '<div class="repaired-footnote"><p>$^{6}$ 这是经过清理后的完整中文脚注，编号仍应当被识别并保留。</p></div>'
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            counts = build_project(text, project, project)
            self.assertEqual(counts['unresolved_note_fragments'], [])
            self.assertIn(r'\footnotetext[6]', (project/'main.tex').read_text('utf-8'))

    def test_unicode_bold_math_compiles(self):
        # Regression: bm + unicode-math used to abort on boldsymbol{y}.
        source = r'''中文向量 $\boldsymbol{y}$，希腊字母 $\boldsymbol{\alpha}$。

$$\boldsymbol{y}^{\mathrm{T}}=[y^1,y^2,y^d],\quad\bm{f}(x,\boldsymbol{y})\tag{5.16}$$

$$\boldsymbol{\sum_{i=1}^n y_i + \alpha}=\mathbf{A}\boldsymbol{y}$$
'''
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'bold.pdf'
            render_latex(source, Path(folder), output)
            report = json.loads((output.with_suffix('')/'render-report.json').read_text('utf-8'))
            self.assertTrue(output.is_file())
            self.assertEqual(report['missing_characters'], [])
            self.assertEqual(report['overfull_boxes_pt'], [])
            log = (output.with_suffix('')/'main.log').read_text('utf-8')
            self.assertNotIn('Extended mathchar used as mathchar', log)
            self.assertNotIn('Extended mathchar', log)

    def test_generated_preamble_falls_back_to_portable_fonts(self):
        # Overleaf has neither SimSun nor Times New Roman; the same main.tex must
        # still compile there by falling back to TeX Live fonts.
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            build_project('中文测试 $x$', project, project)
            layout = (project/'layout.tex').read_text('utf-8')
            tex = (project/'main.tex').read_text('utf-8')
            self.assertIn(r'\IfFontExistsTF{SimSun}', layout)
            self.assertIn('FandolSong-Regular.otf', layout)
            self.assertIn('FandolHei-Regular.otf', layout)
            self.assertIn(r'\IfFontExistsTF{Times New Roman}', layout)
            self.assertIn('texgyretermes', layout)
            self.assertNotIn(r'\setmainfont[]{Times New Roman}', tex)
            self.assertIn(r'\IfFontExistsTF{SimSun}', tex)

    def test_portable_fonts_compile_without_windows_fonts(self):
        # Simulate Overleaf: report every Windows font as missing and compile
        # with the TeX Live fallback fonts only, including emphasis and bold.
        header = (latex_renderer.HEADER
                  .replace(r'\IfFontExistsTF{SimSun}', r'\IfFontExistsTF{NoSuchWindowsFont}')
                  .replace(r'\IfFontExistsTF{Times New Roman}', r'\IfFontExistsTF{NoSuchWindowsFont}'))
        self.assertNotEqual(header, latex_renderer.HEADER)
        with tempfile.TemporaryDirectory() as folder, patch.object(latex_renderer, 'HEADER', header):
            output = Path(folder)/'portable.pdf'
            latex_renderer.render_latex('中文测试 *强调中文* **粗体中文** English $a^2+b^2=c^2$。', Path(folder), output)
            self.assertTrue(output.is_file())
            log = (output.with_suffix('')/'main.log').read_text('utf-8', errors='replace')
            self.assertNotIn('undefined', log)
            self.assertNotIn('Missing character', log)

    def test_math_file_commands_rejected(self):
        for value in [r'\input{config.json}', r'\csname input\endcsname', r'^^5cinput{x}', r'\write18{cmd}']:
            with self.assertRaises(ValueError):
                safe_math(value)
        self.assertEqual(safe_math(r'\begin{array}{c}a\\b\end{array}'), r'\begin{array}{c}a\\b\end{array}')

    def test_chinese_math_table_and_note_survive(self):
        source = r'''## 中文标题

正文 $x_1$ 与百分数 50%。

$$\sum_{i=0}^n x_i\tag{2.49}$$

<table><tr><td rowspan="2">$x$</td><td>A</td></tr><tr><td>B</td></tr></table>

<small><span class="docvortex-page-footnote">脚注 $y$。</span></small>
'''
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            counts = build_project(source, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertIn('中文标题', tex)
            self.assertIn(r'\DisplayMath{\sum_{i=0}^n x_i}{(2.49)}', tex)
            self.assertIn('脚注', tex)
            self.assertIn(r'\multirow{2}', tex)
            self.assertEqual(counts['display_math'], 1)
            self.assertEqual(counts['inline_math'], 3)
            self.assertEqual(counts['notes'], 1)

    def test_remote_or_outside_images_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for target in ['https://example.com/image.png', '../config.json']:
                with self.assertRaises(ValueError):
                    build_project('![](' + target + ')', Path(folder), Path(folder))

    def test_detached_equation_number_is_reattached(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            counts = build_project('$a+b=c$\n\n(2.7)\n\n后文。', project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertIn(r'\DisplayMath{a+b=c}{(2.7)}', tex)
            self.assertEqual(tex.count('(2.7)'), 1)
            self.assertEqual(counts['display_math'], 1)

    def test_two_columns_use_the_class_option_and_full_width_floats(self):
        # Two columns stay one continuous flow, so a wide element floats to the
        # top of a page and the text keeps filling the page it left.
        source = ('<!-- translator-columns: 2 -->\n\n左栏正文。\n\n'
                  '<!-- translator-float: figure -->\n\n![](figure.png)\n\n图 1 题注\n\n'
                  '<!-- translator-float-end -->\n\n<!-- translator-columns-end -->\n')
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project/'figure.png').write_bytes(b'fixture')
            counts = build_project(source, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertEqual(counts['columns'], 2)
            self.assertRegex(tex, r'\\documentclass\[[^\]]*twocolumn')
            self.assertIn(r'\begin{figure*}[!t]', tex)
            self.assertNotIn(r'\begin{multicols*', tex)

    def test_three_columns_use_multicols_regions(self):
        source = ('<!-- translator-columns: 3 -->\n\n三段正文。\n\n'
                  '<!-- translator-columns-end -->\n')
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            counts = build_project(source, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertEqual(counts['columns'], 3)
            self.assertIn(r'\begin{multicols*}{3}', tex)
            self.assertNotIn('twocolumn', tex.split(r'\begin{document}')[0].split('documentclass')[1][:80])

    def test_wide_table_is_scaled_instead_of_overflowing(self):
        header = ' | '.join('列'+str(index) for index in range(8))
        rule = ' | '.join(['---']*8)
        row = ' | '.join(['147.1 px']*8)
        source = '| ' + header + ' |\n| ' + rule + ' |\n| ' + row + ' |\n'
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'wide.pdf'
            render_latex(source, Path(folder), output)
            self.assertTrue(output.is_file())
            project = output.with_suffix('')
            tex = (project/'main.tex').read_text('utf-8')
            self.assertIn(r'\begin{adjustbox}{max width=\linewidth}', tex)
            self.assertNotIn(r'\begin{longtable}', tex)
            report = json.loads((project/'render-report.json').read_text('utf-8'))
            self.assertEqual(report['overfull_boxes_pt'], [])
            self.assertEqual(report['fitted_tables'], 1)

    def test_dingbats_render_through_the_fallback_font(self):
        # These glyphs are absent from Times New Roman; a missing character used
        # to abort the whole translation.
        source = '正确性 ✓，错误 ✗，方框 ☐，勾选框 ☑，箭头 →，编号 ①。\n'
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'glyph.pdf'
            render_latex(source, Path(folder), output)
            self.assertTrue(output.is_file())
            report = json.loads((output.with_suffix('')/'render-report.json').read_text('utf-8'))
            self.assertEqual(report['missing_characters'], [])
            self.assertEqual(report.get('unresolved_glyphs'), None)

    def test_reference_list_is_set_smaller(self):
        # The source paper sets the bibliography smaller; a translated run that
        # keeps body size turns 3 pages of references into 8.
        body = '正文段落。'*600
        source = (body+'\n\n## 参考文献\n\n' + '\n\n'.join('[%d] Author. Title. In CVPR, 2020.' % n
                                                          for n in range(1, 30)) + '\n')
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            build_project(source, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            heading = tex.index(r'\section{参考文献}') if r'\section{参考文献}' in tex else tex.index('参考文献}')
            self.assertIn(r'\small', tex[heading:heading+120])

    def test_heading_in_the_first_half_is_not_treated_as_references(self):
        source = '## 参考文献\n\n[1] Author. Title.\n\n' + '正文段落。'*600 + '\n'
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            build_project(source, project, project)
            tex = (project/'main.tex').read_text('utf-8')
            body = tex.split(r'\begin{document}', 1)[1]
            self.assertNotIn(r'\section{参考文献}\small', body)


if __name__ == '__main__':
    unittest.main()
