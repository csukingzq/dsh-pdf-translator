import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import latex_renderer
from latex_renderer import build_project, safe_math, render_latex, break_long_urls
from heading_structure import normalize_headings


class LatexRendererTests(unittest.TestCase):
    def test_heading_numbering_corrects_old_markdown(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            titles = ['# 第3章 积分', '# 3.2 积分', '## 3.2.1 梯形法', '### 3.2 节', '# 3(c) 的图（N=50）']
            pages = [{'blocks': [{'kind':'heading','markdown':title} for title in titles]}]
            normalize_headings(pages)
            build_project('\n\n'.join(b['markdown'] for b in pages[0]['blocks']), project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertIn(r'\subsection{3.2 积分}', tex)
            self.assertIn(r'\subsubsection{3.2.1 梯形法}', tex)
            self.assertIn(r'\textbf{3.2 节}', tex)
            self.assertIn(r'\textbf{3(c)', tex)

    def test_renderer_preserves_canonical_heading_levels(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            build_project('### 3.2 自定义原文层级\n\n## 输出', project, project)
            tex = (project/'main.tex').read_text('utf-8')
            self.assertRegex(tex, r'\\subsubsection\{3\.2\s+自定义原文层级\}')
            self.assertIn(r'\subsection{输出}', tex)

    def test_mathematical_unicode_and_long_content_compile(self):
        source = '数学符号 𝛼 ℝ ∑ → ∎。\n\n公式 $' + 'x+'*180 + '1$\n\n~~~~text\n' + 'long_identifier_'*40 + '\n~~~~\n'
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'long.pdf'
            render_latex(source, Path(folder), output, strict_layout=True)
            report = json.loads((output.with_suffix('')/'render-report.json').read_text('utf-8'))
            self.assertEqual(report['missing_characters'], [])
            self.assertEqual(report['overfull_accepted'], [])
            self.assertGreater(report['scaled_inline_math'], 0)

    def compile_fixture(self, project, engine_log='', returncode=0, write_pdf=True):
        def compile(*args, **kwargs):
            (project/'main.log').write_text(engine_log, encoding='utf-8')
            if write_pdf:
                (project/'main.pdf').write_bytes(b'new pdf')
            return SimpleNamespace(returncode=returncode, stdout='', stderr='error: broken' if returncode else '')
        return compile

    def test_layout_warnings_publish_with_report_and_strict_mode_preserves_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'out.pdf'; project = output.with_suffix(''); project.mkdir()
            (project/'math-regions.json').write_text('[]', encoding='utf-8')
            (project/'main.tex').write_text('text', encoding='utf-8')
            log = 'Missing character: There is no 🦄 (U+1F984) in font test!\nOverfull \\hbox (30.0pt too wide) at lines 1--1\n'
            with patch.object(latex_renderer, 'build_project', return_value={'unresolved_note_fragments': []}), \
                 patch.object(latex_renderer, 'binaries', return_value=('pandoc', 'tectonic')), \
                 patch.object(latex_renderer.subprocess, 'run', side_effect=self.compile_fixture(project, log)):
                render_latex('text', Path(folder), output)
                report = json.loads((project/'render-report.json').read_text('utf-8'))
                self.assertEqual(report['status'], 'needs_review')
                self.assertEqual(report['overfull_accepted'], [30])
                self.assertTrue(report['font_warnings'])
                output.write_bytes(b'previous accepted pdf')
                with self.assertRaises(latex_renderer.LatexLayoutError):
                    render_latex('text', Path(folder), output, strict_layout=True)
                self.assertEqual(output.read_bytes(), b'previous accepted pdf')

    def test_failed_compile_does_not_publish_stale_pdf(self):
        for returncode in [0, 1]:
            with self.subTest(returncode=returncode), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)/'out.pdf'; project = output.with_suffix(''); project.mkdir()
                output.write_bytes(b'accepted pdf')
                (project/'main.pdf').write_bytes(b'stale pdf')
                with patch.object(latex_renderer, 'build_project', return_value={'unresolved_note_fragments': []}), \
                     patch.object(latex_renderer, 'binaries', return_value=('pandoc', 'tectonic')), \
                     patch.object(latex_renderer.subprocess, 'run', side_effect=self.compile_fixture(project, returncode=returncode, write_pdf=False)):
                    with self.assertRaises(latex_renderer.LatexCompileError):
                        render_latex('text', Path(folder), output)
                self.assertEqual(output.read_bytes(), b'accepted pdf')

    def test_layout_context_ignores_small_overflow_before_severe_one(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project/'math-regions.json').write_text(json.dumps([{'id': 0, 'latex': 'wrong'}, {'id': 1, 'latex': 'right'}]), encoding='utf-8')
            (project/'main.tex').write_text('TRANSLATOR-MATH-BEGIN:0\nTRANSLATOR-MATH-BEGIN:1', encoding='utf-8')
            context = latex_renderer.layout_error_context(project, 'Overfull \\hbox (3.0pt too wide) at lines 1--1\nOverfull \\hbox (30.0pt too wide) at lines 2--2')
            self.assertEqual(context['latex'], 'right')

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

    def test_proof_end_and_check_symbols_compile(self):
        # Regression: 正文里的 ∎ 在 Times New Roman 中缺字形，xelatex 报
        # Missing character 后整篇排版判定失败。
        source = '这证明了 (4.8)，从而证明了 (4.7)。∎\n\n已完成 ✓，未完成 ◇。\n'
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'symbols.pdf'
            render_latex(source, Path(folder), output)
            report = json.loads((output.with_suffix('')/'render-report.json').read_text('utf-8'))
            self.assertTrue(output.is_file())
            self.assertEqual(report['missing_characters'], [])

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
        header = latex_renderer.HEADER
        for name in ['SimSun', 'Times New Roman', 'Microsoft YaHei', 'Arial', 'Consolas', 'SimSun-ExtB']:
            header = header.replace(r'\IfFontExistsTF{' + name + '}', r'\IfFontExistsTF{NoSuchWindowsFont}')
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


if __name__ == '__main__':
    unittest.main()
