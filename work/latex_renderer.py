"""Pandoc AST -> editable XeLaTeX project -> Tectonic PDF.

Document HTML is converted structurally; document-supplied raw TeX is disabled.
Only math regions become TeX, with file/engine primitives rejected.
"""
import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import progress

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path(os.environ.get('DSH_PDF_RUNTIME_DIR') or (ROOT/'runtime'))
# Overfull boxes up to a few points are cosmetic. Blocking the whole PDF for
# them costs one AI repair plus a full rebuild per box; only real overflow does.
SEVERE_OVERFULL_PT = 20

class LatexCompileError(RuntimeError):
    """A failed TeX run, optionally attributable to one active math region."""
    def __init__(self, message, math_error=None):
        super().__init__(message)
        self.math_error = math_error


class LatexLayoutError(LatexCompileError):
    """A successful compile whose blocking layout check failed."""


def layout_error_context(project, engine_log):
    """Locate math only inside a reported overflowing paragraph or glyph error."""
    regions = json.loads((project/'math-regions.json').read_text('utf-8'))
    lines = (project/'main.tex').read_text('utf-8').splitlines()
    for match in re.finditer(r'Overfull \\hbox \(([0-9.]+)pt too wide\).*?at lines (\d+)--(\d+)', engine_log):
        if float(match[1]) <= 2:
            continue
        source = '\n'.join(lines[int(match[2])-1:int(match[3])])
        ids = set(re.findall(r'TRANSLATOR-MATH-BEGIN:(\d+)', source))
        candidates = sorted((regions[int(i)] for i in ids), key=lambda r: len(r['latex']), reverse=True)
        # Avoid repairing unrelated short symbols in the same paragraph.
        if candidates and (len(candidates) == 1 or len(candidates[0]['latex']) > sum(len(r['latex']) for r in candidates[1:])):
            return {**candidates[0], 'kind': 'layout', 'error': match[0]}
        if candidates:
            return {'kind': 'paragraph', 'anchors': [r['latex'] for r in candidates],
                    'error': match[0], 'tex_context': source}
    for match in re.finditer(r'^Missing character:.*$', engine_log, re.M):
        events = re.findall(r'^TRANSLATOR-MATH-(BEGIN|END):(\d+)\s*$', engine_log[:match.start()], re.M)
        if events and events[-1][0] == 'BEGIN':
            return {**regions[int(events[-1][1])], 'kind': 'layout', 'error': match[0]}
    return None

HEADER = r"""
\usepackage{xeCJK}
% 本机有 Windows 字体时保持原样；Overleaf 等缺少这些字体的环境自动退回
% TeX Live 自带字体（Fandol、TeX Gyre Termes），因此同一个 main.tex 到处可编译。
\IfFontExistsTF{Times New Roman}{\setmainfont{Times New Roman}}{%
  \setmainfont[Extension=.otf,UprightFont=*-regular,BoldFont=*-bold,ItalicFont=*-italic,BoldItalicFont=*-bolditalic]{texgyretermes}}
\IfFontExistsTF{SimSun}{%
  \setCJKmainfont[AutoFakeBold=2]{SimSun}%
  \setCJKsansfont{Microsoft YaHei}%
  \setCJKmonofont{SimSun}%
}{%
  \setCJKmainfont[AutoFakeBold=2,ItalicFont=FandolSong-Regular.otf,BoldItalicFont=FandolSong-Regular.otf]{FandolSong-Regular.otf}%
  \setCJKsansfont[AutoFakeBold=2,ItalicFont=FandolHei-Regular.otf,BoldItalicFont=FandolHei-Regular.otf]{FandolHei-Regular.otf}%
  \setCJKmonofont{FandolSong-Regular.otf}%
}
\usepackage{amsmath,amssymb,mathtools}
% bm redefines boldsymbol using legacy mathchar primitives, incompatible
% with Unicode math. Select Unicode bold italic vector/Greek glyphs directly.
\setmathfont{XITSMath-Regular.otf}
\renewcommand{\boldsymbol}[1]{\symbfit{#1}}
\providecommand{\bm}[1]{\boldsymbol{#1}}
\usepackage{newunicodechar}
\newunicodechar{☐}{\ensuremath{\square}}
\newunicodechar{★}{\ensuremath{\bigstar}}
% 正文里常出现的勾选/方框/箭头字符不在 Times New Roman 里，逐字改成
% 符号字体回退，避免 XeTeX 直接报缺字。编译后仍缺的字由 heal_glyphs 追加。
\IfFontExistsTF{Segoe UI Symbol}{%
  \newfontfamily\symbolfont{Segoe UI Symbol}%
}{%
  \IfFontExistsTF{DejaVu Sans}{%
    \newfontfamily\symbolfont{DejaVu Sans}%
  }{%
    \newfontfamily\symbolfont{FreeSerif}%
  }%
}
\IfFontExistsTF{Microsoft YaHei}{%
  \newCJKfontfamily\cjkfallback{Microsoft YaHei}%
}{%
  \newCJKfontfamily\cjkfallback{FandolSong-Regular.otf}%
}
\newcommand{\symbolchar}[1]{{\symbolfont #1}}
\newcommand{\cjkchar}[1]{{\cjkfallback #1}}
\newunicodechar{✓}{\symbolchar{✓}}
\newunicodechar{✔}{\symbolchar{✔}}
\newunicodechar{✗}{\symbolchar{✗}}
\newunicodechar{✘}{\symbolchar{✘}}
\newunicodechar{✕}{\symbolchar{✕}}
\newunicodechar{☑}{\symbolchar{☑}}
\newunicodechar{☒}{\symbolchar{☒}}
\newunicodechar{◆}{\symbolchar{◆}}
\newunicodechar{◇}{\symbolchar{◇}}
\newunicodechar{▪}{\symbolchar{▪}}
\newunicodechar{▫}{\symbolchar{▫}}
\newunicodechar{▲}{\symbolchar{▲}}
\newunicodechar{▼}{\symbolchar{▼}}
\newunicodechar{⟨}{\ensuremath{\langle}}
\newunicodechar{⟩}{\ensuremath{\rangle}}
\usepackage{graphicx,adjustbox,multicol}
\usepackage{fancyhdr}
\usepackage{needspace}
\usepackage{indentfirst}
\usepackage{titlesec}
\titleformat{\section}{\Large\sffamily\bfseries}{}{0pt}{}
\titleformat{\subsection}{\large\sffamily\bfseries}{}{0pt}{}
\titleformat{\subsubsection}{\normalsize\sffamily\bfseries}{}{0pt}{}
\setlength{\parindent}{2em}
\setlength{\parskip}{0.35em}
\linespread{1.22}
\setlength{\emergencystretch}{3em}
\pagestyle{fancy}
\fancyhf{}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0pt}
\setlength{\headheight}{14pt}
\widowpenalty=10000
\clubpenalty=10000
\setcounter{secnumdepth}{-1}
% 双栏论文的宽图表可能比栏高，默认比例限制会让它们无法落页、一路漂到文末。
\setcounter{topnumber}{3}
\setcounter{dbltopnumber}{3}
\renewcommand{\topfraction}{0.95}
\renewcommand{\dbltopfraction}{0.95}
\renewcommand{\textfraction}{0.05}
\renewcommand{\floatpagefraction}{0.75}
\newsavebox{\displaybox}
\newlength{\formulawidth}
% 公式比栏宽时不再整体缩小（会看不清），改为按关系符断行、保持原字号。
% 带 array/aligned 的多行公式不能断行，仍用 \DisplayMathFit 等比缩放。
\newcommand{\DisplayMath}[2]{%
  \par\addvspace{0.65\baselineskip}%
  \sbox{\displaybox}{$\displaystyle #1$}%
  \setlength{\formulawidth}{\dimexpr\linewidth-4em\relax}%
  \ifdim\wd\displaybox>\dimexpr 1.12\formulawidth\relax
    \typeout{LATEX-TRANSLATOR: broken wide display}%
    \begingroup
      \leftskip=0pt plus 1fil \rightskip=0pt plus 1fil \parfillskip=0pt\relax
      \noindent$\displaystyle #1$\par
    \endgroup
    \ifx\relax#2\relax\else
      \begingroup\parfillskip=0pt\relax
        \noindent\hfill\makebox[4em][r]{#2}\par
      \endgroup
    \fi
  \else
    \noindent\makebox[\linewidth]{%
      \ifdim\wd\displaybox>\formulawidth
        \typeout{LATEX-TRANSLATOR: scaled wide display}%
        \makebox[\formulawidth]{\adjustbox{max width=\formulawidth}{\usebox{\displaybox}}}%
        \makebox[4em][r]{#2}%
      \else
        \ifx\relax#2\relax
          \usebox{\displaybox}%
        \else
          \makebox[\formulawidth]{\usebox{\displaybox}}\makebox[4em][r]{#2}%
        \fi
      \fi}%
  \fi
  \par\addvspace{0.65\baselineskip}}
\newcommand{\DisplayMathFit}[2]{%
  \par\addvspace{0.65\baselineskip}%
  \sbox{\displaybox}{$\displaystyle #1$}%
  \setlength{\formulawidth}{\dimexpr\linewidth-4em\relax}%
  \ifdim\wd\displaybox>\formulawidth
    \typeout{LATEX-TRANSLATOR: scaled wide display}%
  \fi
  \noindent\makebox[\linewidth]{%
    \ifx\relax#2\relax
      \adjustbox{max width=\formulawidth}{\usebox{\displaybox}}%
    \else
      \makebox[\formulawidth]{\adjustbox{max width=\formulawidth}{\usebox{\displaybox}}}%
      \makebox[4em][r]{#2}%
    \fi}%
  \par\addvspace{0.65\baselineskip}}
"""


def binaries():
    roots = [RUNTIME]
    legacy = ROOT/'runtime'
    if legacy != RUNTIME:
        roots.append(legacy)
    pandoc = tectonic = None
    for runtime in roots:
        if pandoc is None:
            pandoc = next((runtime/'pandoc').glob('*/pandoc.exe'), None)
            if pandoc is None:
                pandoc = next((runtime/'pandoc').glob('*/pandoc'), None)
        if tectonic is None:
            candidate = runtime/'tectonic'/'tectonic.exe'
            if not candidate.is_file():
                candidate = runtime/'tectonic'/'tectonic'
            if candidate.is_file():
                tectonic = candidate
        if pandoc is not None and tectonic is not None:
            break
    if pandoc is None or tectonic is None:
        raise RuntimeError(f'缺少 LaTeX 运行时（{RUNTIME}），请运行 scripts/setup.ps1。')
    return str(pandoc), str(tectonic)


def run(command, text=None, cwd=None):
    result = subprocess.run(command, input=text, cwd=cwd, capture_output=True,
                            encoding='utf-8', errors='replace', timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:] or result.stdout[-5000:])
    return result.stdout


def safe_math(value):
    value = html.unescape(value)
    forbidden = r'\\(?:input|include\w*|open\w*|read\w*|write\w*|close\w*|special|usepackage|documentclass|RequirePackage|catcode|csname|endcsname|def|edef|gdef|xdef|let|futurelet|newcommand|renewcommand|providecommand|newenvironment|renewenvironment|directlua|lua\w*|ExplSyntaxOn|scantokens|every\w*|loop|repeat|shipout|pdf\w*|immediate|global|font|end|begin)\b'
    # begin/end are allowed only for mathematical environments.
    checked = re.sub(r'\\(?:begin|end)\s*\{(?:aligned|alignedat|gathered|split|array|[pbBvV]?matrix|cases|smallmatrix)\}', '', value)
    if '^^' in checked or re.search(forbidden, checked):
        raise ValueError('公式含不支持的 TeX 指令；已保留原文，请检查生成目录。')
    # A divided-difference bracket at the start of a matrix row must not be
    # parsed as the optional row-height argument of \\. Keep real [2pt] gaps.
    value = re.sub(r'\\\\(\s*)(?=\[[^\]\n]*,)', lambda m: '\\\\{}' + m[1], value)
    value = value.replace(r'\begin{split}', r'\begin{aligned}').replace(r'\end{split}', r'\end{aligned}')
    # A wholly empty left column is not an alignment. Nested cases in that
    # column trigger an amsmath/Unicode-math error on the shipped TeX runtime.
    # Convert only this structural case; never edit symbols or inner case rows.
    match = re.fullmatch(r'\s*\\begin\{aligned\}(.*?)\\end\{aligned\}\s*', value, re.S)
    if match:
        rows = math_rows(match[1])
        if rows and all(row.lstrip().startswith('&') and len(math_cells(row)) == 2 for row in rows):
            value = r'\begin{gathered}' + r' \\ '.join(row.lstrip()[1:] for row in rows) + r'\end{gathered}'
    return value


def split_math(value, separator):
    """Split only at the current environment/group depth (not inside cases)."""
    parts, start, depth, braces, index = [], 0, 0, 0, 0
    while index < len(value):
        env = re.match(r'\\(begin|end)\s*\{[^{}]+\}', value[index:])
        if env:
            depth += 1 if env[1] == 'begin' else -1
            index += len(env[0]); continue
        if depth == 0 and braces == 0 and value.startswith(separator, index):
            parts.append(value[start:index]); index += len(separator); start = index; continue
        if value[index] == '\\':
            index += 2; continue
        if value[index] == '{': braces += 1
        if value[index] == '}': braces -= 1
        index += 1
    parts.append(value[start:])
    return parts


def math_rows(value):
    return [part for part in split_math(value, r'\\') if part.strip()]


def math_cells(value):
    return split_math(value, '&')


def remove_tags(value):
    """Balanced-brace tags; regex alone loses nested tags such as 3_{a}."""
    parts, tags, cursor = [], [], 0
    for match in re.finditer(r'\\tag(\*)?\s*\{', value):
        if match.start() < cursor:
            continue
        index, depth = match.end(), 1
        while index < len(value) and depth:
            if value[index] == '\\': index += 2; continue
            if value[index] == '{': depth += 1
            elif value[index] == '}': depth -= 1
            index += 1
        if depth:
            raise ValueError('公式编号括号不完整。')
        parts.append(value[cursor:match.start()])
        label = value[match.end():index-1]
        tags.append(label if match[1] else '('+label+')')
        cursor = index
    parts.append(value[cursor:])
    return ''.join(parts), tags


# Bodies that carry their own line structure cannot be broken at a relation, so
# they are scaled to the measure instead of being re-flowed.
FIT_BODY = re.compile(r'\\(?:begin\{(?:array|aligned|alignedat|gathered|split|[pbBvV]?matrix|cases|smallmatrix)\}|substack)')


def display_command(body):
    return r'\DisplayMathFit' if FIT_BODY.search(body) else r'\DisplayMath'


def display_math(value):
    outer = re.fullmatch(r'\s*\\begin\{(aligned|gathered)\}(.*?)\\end\{\1\}\s*', value, re.S)
    if outer and r'\tag' in outer[2]:
        lines = []
        for row in math_rows(outer[2]):
            body, tags = remove_tags(row)
            if len(tags)>1:
                raise ValueError('同一公式行包含多个编号，请检查译文。')
            # Each row retains its own alignment; labels occupy their own column.
            body = r'\begin{aligned}'+body+r'\end{aligned}' if len(math_cells(body))>1 else body
            label = tags[0] if tags else ''
            lines.append(r'\displaystyle '+body+r' & \displaystyle '+label)
        return r'\DisplayMathFit{\begin{array}{r@{\quad}l}'+r' \\ '.join(lines)+r'\end{array}}{}'
    body, tags = remove_tags(value)
    if len(tags)>1:
        raise ValueError('无法定位多个公式编号的所属行，请检查译文。')
    label = tags[0] if tags else ''
    if label and not re.fullmatch(r'[\w.()\- ]+', label):
        label = r'\ensuremath{'+label+'}'
    return display_command(body)+'{'+body+'}{'+label+'}'


def prepare_html(text, pandoc, tables=None):
    """Keep tables and repaired notes instead of dropping raw HTML in LaTeX."""
    from bs4 import BeautifulSoup
    def convert(match):
        fragment = match.group()
        if fragment.lower().startswith('<table') and tables is not None:
            marker = 'LATEXTABLE' + str(len(tables)).zfill(6)
            tables[marker] = json.loads(run([pandoc, '-f', 'html+tex_math_dollars', '-t', 'json'], fragment))['blocks'][0]
            return '\n\n' + marker + '\n\n'
        soup = BeautifulSoup(fragment, 'html.parser')
        note = soup.select_one('.docvortex-page-footnote, .repaired-footnote')
        if note:
            # Presentation wrappers from both MinerU and the repair pass must
            # not hide the numbered paragraph inside another AST Div/Span.
            fragment = note.decode_contents()
        converted = run([pandoc, '-f', 'html+tex_math_dollars', '-t', 'markdown-raw_html-raw_tex', '--wrap=none'], fragment)
        if note:
            return '\n\n::: {.translation-note}\n' + converted + '\n:::\n\n'
        return '\n\n' + converted + '\n\n'
    pattern = r'<table\b[\s\S]*?</table\s*>|<div\b[\s\S]*?</div\s*>|<small\b[\s\S]*?</small\s*>'
    return re.sub(pattern, convert, text, flags=re.I)


def inline_footnote_math(text):
    """LaTeX footnotes cannot hold display math: it leaks out as body text at a
    page break. Keep the formula but set it inline inside footnote definitions."""
    def convert(match):
        return match.group(0).replace('$$', '$')
    return re.sub(r'(?ms)^\[\^[^\]]+\]:.*?(?=^\[\^|\Z)', convert, text)


def break_long_urls(tex):
    """Give TeX break points in bare URLs so bibliography lines don't overflow."""
    def convert(match):
        url = match.group(0)
        prefix = tex[max(0, match.start()-6):match.start()]
        if prefix.endswith(('\\url{', '\\href{')):
            return url
        head, separator, tail = url.partition('://')
        if not separator:
            return url
        tail = re.sub(r'([/.\-_?&=])(?=[^\s])', r'\1\\allowbreak{}', tail)
        return head + separator + tail
    return re.sub(r'https?://[^\s{}]+', convert, tex)


def _group(tex, index):
    """Index just past the balanced group starting at `index`, which holds '{'."""
    depth = 0
    while index < len(tex):
        char = tex[index]
        if char == '\\':
            index += 2
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return index+1
        index += 1
    raise ValueError('LaTeX 分组不完整。')


def _tabular_spec(tex, index):
    """Read the optional [..] and required {..} column spec of a table."""
    while index < len(tex) and tex[index] in ' \t\n':
        index += 1
    if index < len(tex) and tex[index] == '[':
        index = tex.index(']', index)+1
        while index < len(tex) and tex[index] in ' \t\n':
            index += 1
    if index >= len(tex) or tex[index] != '{':
        raise ValueError('无法识别表格列定义。')
    end = _group(tex, index)
    return index+1, end-1, end


# A table taller than this cannot break across pages once it is a tabular, so
# it is also scaled down to stay on one page.
TALL_TABLE_ROWS = 25
# Fixed-width columns measured against the text block wrap one word per line
# once the table sits in a single column. Typeset those wider, then scale down.
NARROW_TABLE_SCALE = 1.6
NARROW_TABLE_COLUMNS = 4


def in_float(tex, position):
    """True when the offset sits inside one of the full-width float regions."""
    opened = max(tex.rfind(r'\begin{figure*}', 0, position), tex.rfind(r'\begin{table*}', 0, position))
    closed = max(tex.rfind(r'\end{figure*}', 0, position), tex.rfind(r'\end{table*}', 0, position))
    return opened > closed


def spec_columns(spec):
    """Column count of a tabular preamble, skipping filler and font arguments."""
    count, index = 0, 0
    while index < len(spec):
        char = spec[index]
        if char in '>@!<':
            index += 1
            while index < len(spec) and spec[index] in ' \t':
                index += 1
            if index < len(spec) and spec[index] == '{':
                index = _group(spec, index)
            continue
        if char in 'lcrpmbX':
            count += 1
        index += 1
    return count


LONGTABLE_HOOK = re.compile(r'\\(?:endfirsthead|endhead|endfoot|endlastfoot)\b')


def split_longtable(body):
    """Split pandoc's longtable body into head, rows and the closing footer.

    pandoc writes `head \\endhead  \\bottomrule \\endlastfoot  rows`, i.e. the
    repeated footer is emitted *before* the rows. Keeping it there put a double
    rule under the header and dropped the table's closing rule.
    """
    pieces = LONGTABLE_HOOK.split(body)
    if len(pieces) == 1:
        return '', pieces[0], ''
    return pieces[0], pieces[-1], ''.join(pieces[1:-1])


def fit_tables(tex):
    """Rewrite pandoc's longtable into a scalable tabular.

    longtable cannot be used inside multicols at all, and its natural width
    overflows the text block when the source table has many columns. A tabular
    inside adjustbox is scaled to whatever width is available: the column width
    inside multicols, the text width outside.

    Returns the source and the line ranges of the rewritten tables; an overfull
    box inside one of them is scaled away by adjustbox, so it is not a defect.
    """
    out, pos, fitted, ranges, line = [], 0, 0, [], 0
    while True:
        start = tex.find(r'\begin{longtable}', pos)
        if start < 0:
            break
        try:
            spec_start, spec_end, body_start = _tabular_spec(tex, start+len(r'\begin{longtable}'))
        except ValueError:
            out.append(tex[pos:start+len(r'\begin{longtable}')])
            pos = start+len(r'\begin{longtable}')
            continue
        end = tex.find(r'\end{longtable}', body_start)
        if end < 0:
            break
        spec = tex[spec_start:spec_end]
        body = tex[body_start:end]
        caption = ''
        match = re.search(r'\\caption(\*?)\s*\{', body)
        if match:
            close = _group(body, match.end()-1)
            caption = body[match.start():close]
            body = body[:match.start()]+body[close:]
        # Page-break hooks of longtable have no meaning inside a tabular, and its
        # footer block (the repeated rule, placed before the rows) has to become
        # the closing rule of the single-piece table instead.
        head, body, foot = split_longtable(body)
        height = r',max totalheight=0.9\textheight' if body.count(r'\\') > TALL_TABLE_ROWS else ''
        # Inside a single column proportional fixed-width columns are crushed
        # into one word per line; a wider measure scaled back down keeps them.
        narrow = ('p{' in spec and not in_float(tex, start)
                  and spec_columns(spec) >= NARROW_TABLE_COLUMNS)
        out.append(tex[pos:start])
        out.append(r'\par\noindent'+(caption+r'\par\noindent' if caption else ''))
        line = ''.join(out).count('\n')+1
        out.append(r'\begin{adjustbox}{max width=\linewidth'+height+'}'+'\n')
        if narrow:
            out.append(r'\begin{minipage}{'+str(NARROW_TABLE_SCALE)+r'\linewidth}'+'\n')
        out.append(r'\begin{tabular}{'+spec+'}'+'\n')
        out.append('\n'.join(part.strip() for part in (head, body, foot) if part.strip())+'\n')
        out.append(r'\end{tabular}'+'\n')
        if narrow:
            out.append(r'\end{minipage}'+'\n')
        out.append(r'\end{adjustbox}')
        ranges.append([line, ''.join(out).count('\n')+1])
        fitted += 1
        pos = end+len(r'\end{longtable}')
    out.append(tex[pos:])
    return ''.join(out), fitted, ranges


def mark_regions(blocks):
    """Swap the layout markers for TeX sentinels that survive the LaTeX writer.

    Regions are never converted on their own: pandoc decides which packages the
    preamble needs from the whole document, so a table inside a region must stay
    visible to it. The sentinels become real environments after conversion.
    """
    out, columns, floated = [], 1, None
    for block in blocks:
        mark = column_mark(block['c'][1]) if block.get('t') == 'RawBlock' and block['c'][0] == 'html' else None
        if not mark:
            out.append(block)
            continue
        kind, value = mark
        if kind == 'columns':
            columns = value
            command = r'\typeout{TRANSLATOR-COLUMNS-BEGIN:'+str(value)+'}'
        elif kind == 'float':
            floated = value
            command = r'\typeout{TRANSLATOR-FLOAT-BEGIN:'+value+'}'
        elif value:
            command = r'\typeout{TRANSLATOR-FLOAT-END:'+str(floated)+'}'
        else:
            command = r'\typeout{TRANSLATOR-COLUMNS-END}'
        out.append({'t': 'RawBlock', 'c': ['latex', command]})
    return out, columns


REGION_TEX = (
    (re.compile(r'\\typeout\{TRANSLATOR-COLUMNS-BEGIN:(\d+)\}'),
     lambda match: '\n'+r'\begin{multicols*}{'+match[1]+'}'+'\n'),
    (re.compile(r'\\typeout\{TRANSLATOR-COLUMNS-END\}'),
     lambda match: '\n'+r'\end{multicols*}'+'\n'),
    (re.compile(r'\\typeout\{TRANSLATOR-FLOAT-BEGIN:(figure|table)\}'),
     lambda match: '\n'+r'\begin{'+match[1]+r'}[!t]\centering'+'\n'),
    (re.compile(r'\\typeout\{TRANSLATOR-FLOAT-END:(figure|table)\}'),
     lambda match: '\n'+r'\end{'+match[1]+'}'+'\n'),
)

# In `twocolumn` mode the body already flows in columns, so only the wide
# elements need an environment, and they become full-width floats.
TWO_COLUMN_TEX = (
    (re.compile(r'\s*\\typeout\{TRANSLATOR-COLUMNS-(?:BEGIN:\d+|END)\}'), lambda match: ''),
    (re.compile(r'\\typeout\{TRANSLATOR-FLOAT-BEGIN:(figure|table)\}'),
     lambda match: '\n'+r'\begin{'+match[1]+r'*}[!t]\centering'+'\n'),
    (re.compile(r'\\typeout\{TRANSLATOR-FLOAT-END:(figure|table)\}'),
     lambda match: '\n'+r'\end{'+match[1]+r'*}'+'\n'),
)


REFERENCE_HEADING = re.compile(
    r'\\(?:sub)?section\*?\{[^{}]*(?:参考文献|引用文献|References|Bibliography)[^{}]*\}')


def shrink_references(tex):
    """Set the bibliography in a smaller size, as the source paper does.

    Only a heading in the last half of the *body* counts as the reference list,
    so material after it (an appendix) is not shrunk by accident.
    """
    start = tex.find(r'\begin{document}')
    end = tex.find(r'\end{document}')
    if start < 0 or end < 0:
        return tex
    matches = [match for match in REFERENCE_HEADING.finditer(tex, start, end)]
    if not matches:
        return tex
    heading = matches[-1]
    if heading.start() < start + (end-start)*0.45:
        return tex
    return tex[:heading.end()] + r'\small' + tex[heading.end():]


def apply_regions(tex, columns=1):
    """Turn the sentinels into the real layout.

    Two columns use the class option: the body then flows continuously, so a
    wide figure or table can float to the top of a page and the text keeps
    filling the page it left. Three or more columns use multicols regions,
    because the class option only supports two.
    """
    if columns == 2:
        anchor = tex.index(r'\begin{document}')+len(r'\begin{document}')
        first = tex.find(r'\typeout{TRANSLATOR-COLUMNS-BEGIN')
        if first > anchor and tex[anchor:first].strip():
            # The title block belongs to the full width above both columns.
            tex = (tex[:anchor]+'\n'+r'\twocolumn[{' + tex[anchor:first] + '}]'+'\n'+tex[first:])
        for pattern, replace in TWO_COLUMN_TEX:
            tex = pattern.sub(replace, tex)
        return tex
    for pattern, replace in REGION_TEX:
        tex = pattern.sub(replace, tex)
    return tex


COLUMN_MARK = re.compile(r'^<!--\s*translator-columns:\s*(\d+)\s*-->$', re.I)
COLUMN_END = re.compile(r'^<!--\s*translator-columns-end\s*-->$', re.I)
FLOAT_MARK = re.compile(r'^<!--\s*translator-float:\s*(figure|table)\s*-->$', re.I)
FLOAT_END = re.compile(r'^<!--\s*translator-float-end\s*-->$', re.I)


def column_mark(raw):
    """Recognise the invisible layout markers written by assemble()."""
    text = raw.strip()
    opened = COLUMN_MARK.match(text)
    if opened:
        return ('columns', int(opened[1]))
    floated = FLOAT_MARK.match(text)
    if floated:
        return ('float', floated[1].lower())
    if FLOAT_END.match(text):
        return ('end', 'float')
    return ('end', None) if COLUMN_END.match(text) else None


def validate_layout(layout):
    limits = {'figureMaxWidth':(.3,1), 'figureMaxHeight':(.15,.65), 'fontSize':(9,14), 'columns':(0,3)}
    if not isinstance(layout,dict) or set(layout)-set(limits):
        raise ValueError('无效排版参数。')
    for key,value in layout.items():
        low,high = limits[key]
        if type(value) not in (int,float) or not low <= value <= high or (key in {'fontSize','columns'} and int(value)!=value):
            raise ValueError('排版参数超出允许范围：'+key)
    return layout


def build_project(text, source_dir, project):
    pandoc, _ = binaries()
    layout_path = Path(source_dir)/'layout.json'
    layout = validate_layout(json.loads(layout_path.read_text('utf-8'))) if layout_path.exists() else {}
    project.mkdir(parents=True, exist_ok=True)
    assets = project/'images'
    assets.mkdir(exist_ok=True)
    tables = {}
    prepared = prepare_html(text, pandoc, tables)
    prepared = inline_footnote_math(prepared)
    ast = json.loads(run([pandoc, '-f', 'markdown-raw_tex+tex_math_single_backslash', '-t', 'json'], prepared))
    heading_levels = [b['c'][0] for b in ast['blocks'] if b.get('t') == 'Header']
    heading_shift = min(heading_levels, default=1) - 1
    # MinerU can emit a display as a one-formula paragraph followed by its number.
    merged = []
    for block in ast['blocks']:
        if block.get('t') == 'Para' and len(block['c']) == 1:
            item = block['c'][0]
            if item.get('t') == 'Str' and re.fullmatch(r'\(\d+(?:\.\d+)*[a-z]?\)', item['c']) and merged:
                previous = merged[-1]
                if previous.get('t') == 'Para' and len(previous['c']) == 1 and previous['c'][0].get('t') == 'Math':
                    previous['c'][0]['c'][1] += r'\tag{' + item['c'][1:-1] + '}'
                    continue
            if item.get('t') == 'Math':
                item['c'][0] = {'t': 'DisplayMath'}
        merged.append(block)
    ast['blocks'] = merged
    # Keep an extracted figure with its immediately following caption.
    for index, block in enumerate(merged[:-1]):
        if block.get('t')=='Para' and len(block['c'])==1 and block['c'][0].get('t')=='Image':
            following = merged[index+1]
            if following.get('t')=='Para':
                caption = ''.join(x.get('c','') if x.get('t')=='Str' else ' ' for x in following['c'])
                if re.match(r'\s*(?:图\s*\d|Figure\s+\d|Fig\.\s*\d)',caption):
                    block['c'][0]['c'][0][2].append(['keep-with-caption','true'])
    grouped = []
    index = 0
    while index < len(merged):
        block = merged[index]
        if (block.get('t')=='Para' and len(block['c'])==1 and block['c'][0].get('t')=='Image'
                and ['keep-with-caption','true'] in block['c'][0]['c'][0][2] and index+1<len(merged)):
            grouped.append({'t':'TranslatorFigure','c':[block,merged[index+1]]})
            index += 2
        else:
            grouped.append(block)
            index += 1
    ast['blocks'] = grouped
    counts = {'inline_math': 0, 'display_math': 0, 'images': 0, 'notes': 0, 'unresolved_note_fragments': []}
    math_regions = []

    def visit(node):
        if isinstance(node, list):
            return [visit(x) for x in node]
        if not isinstance(node, dict):
            return node
        kind = node.get('t')
        content = node.get('c')
        if kind == 'TranslatorFigure':
            blocks = [visit(item) for item in content]
            body = run([pandoc,'-f','json','-t','latex'],json.dumps({**ast,'blocks':blocks}))
            return {'t':'RawBlock','c':['latex',r'\par\noindent\begin{minipage}{\linewidth}'+'\n'+body+'\n'+r'\end{minipage}\par']}
        if kind == 'Div' and 'figure-row' in content[0][1]:
            # assemble() 把同一行左右并排的图包成 .figure-row；这里渲染成左右 minipage。
            figures = []
            current = None
            for block in content[1]:
                if block.get('t') == 'Para' and len(block['c']) == 1 and block['c'][0].get('t') == 'Image':
                    image = block['c'][0]
                    visit(image)
                    current = {'image': image['c'][2][0], 'caption': ''}
                    figures.append(current)
                elif block.get('t') == 'Para' and current is not None:
                    caption = run([pandoc,'-f','json','-t','latex'],
                                  json.dumps({**ast,'blocks':[visit(block)]})).strip()
                    current['caption'] = caption
            if not figures:
                return {'t':'RawBlock','c':['latex','']}
            width = f'{0.96 / len(figures):.3f}\\linewidth'
            cells = []
            for figure in figures:
                cells.append(r'\begin{minipage}[t]{' + width + r'}\centering' + '\n'
                             + r'\adjustbox{max width=\linewidth,max height=' + str(layout.get('figureMaxHeight',.45)) + r'\textheight}{\includegraphics{'
                             + figure['image'] + r'}}\par' + '\n' + figure['caption'] + '\n' + r'\end{minipage}')
            return {'t':'RawBlock','c':['latex',r'\par\noindent' + r'\hfill'.join(cells) + r'\par']}
        if kind == 'Header':
            content[0] -= heading_shift
        if kind == 'Para' and len(content) == 1 and content[0].get('t') == 'Image':
            keep_caption = ['keep-with-caption','true'] in content[0]['c'][0][2]
            picture = visit(content[0])
            target = picture['c'][2][0]
            bounds = f"max width={layout.get('figureMaxWidth',.85)}\\linewidth,max height={layout.get('figureMaxHeight',.25)}\\textheight"
            return {'t': 'RawBlock', 'c': ['latex', r'\begin{center}\adjustbox{' + bounds + r'}{\includegraphics{' + target + r'}}\end{center}' + (r'\nopagebreak[4]' if keep_caption else '')]}
        if kind == 'Para' and len(content) == 1 and content[0].get('t') == 'Str' and content[0]['c'] in tables:
            return visit(tables[content[0]['c']])
        if kind == 'Math':
            value = safe_math(content[1])
            region_id = len(math_regions)
            math_regions.append({'id': region_id, 'latex': content[1], 'engine_latex': value})
            start = r'\typeout{TRANSLATOR-MATH-BEGIN:' + str(region_id) + '}'
            end = r'\typeout{TRANSLATOR-MATH-END:' + str(region_id) + '}'
            if content[0]['t'] == 'DisplayMath':
                counts['display_math'] += 1
                return {'t': 'RawInline', 'c': ['latex', start + display_math(value) + end]}
            counts['inline_math'] += 1
            # Retain source footnote markers for the later binding pass.
            if re.fullmatch(r'\^(?:\{\d+\}|\d+)', value.strip()):
                return {'t': 'Math', 'c': [content[0], value]}
            return {'t': 'RawInline', 'c': ['latex', start + r'\(' + value + r'\)' + end]}
        if kind == 'Image':
            target = content[2][0]
            match = re.fullmatch(r'data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=\s]+)', target)
            if match:
                data = base64.b64decode(match[2])
                ext = 'jpg' if match[1] == 'jpeg' else match[1]
            else:
                path = (Path(source_dir)/target).resolve()
                if not path.is_relative_to(Path(source_dir).resolve()) or not path.is_file():
                    raise ValueError('图片必须是缓存目录内的本地文件或内嵌 PNG/JPEG。')
                data, ext = path.read_bytes(), path.suffix.lstrip('.')
                if ext.lower() not in ('png', 'jpg', 'jpeg', 'pdf'):
                    raise ValueError('不支持的图片格式：' + ext)
            name = hashlib.sha256(data).hexdigest()[:16] + '.' + ext
            (assets/name).write_bytes(data)
            content[2][0] = 'images/' + name
            counts['images'] += 1
        if kind == 'Div' and 'translation-note' in content[0][1]:
            counts['notes'] += 1
            # OCR carries the source footnote marker as an inline math atom.
            # Use native insertions so complete numbered notes sit at the page
            # bottom under one shared footnote rule, rather than quote blocks.
            note_number = None
            prose = 0
            blocks = content[1]
            def unwrap_spans(inlines):
                result = []
                for inline in inlines:
                    if inline.get('t') == 'Span':
                        result.extend(unwrap_spans(inline['c'][1]))
                    else:
                        result.append(inline)
                return result
            for block in blocks:
                if block.get('t') in ('Para', 'Plain'):
                    block['c'] = unwrap_spans(block['c'])
            if blocks and blocks[0].get('t') in ('Para', 'Plain') and blocks[0]['c']:
                first = blocks[0]['c'][0]
                marker = re.fullmatch(r'\^\s*\{(\d+)\}', first['c'][1].strip()) if first.get('t') == 'Math' else None
                prose = sum(len(x.get('c', '')) for x in blocks[0]['c'] if x.get('t') == 'Str')
                if marker and prose >= 15:
                    note_number = marker[1]
                    blocks[0]['c'] = blocks[0]['c'][1:]
            blocks = visit(content[1])
            body = run([pandoc, '-f', 'json', '-t', 'latex'], json.dumps({**ast, 'blocks': blocks}))
            if note_number is not None:
                return {'t': 'RawBlock', 'c': ['latex', r'\footnotetext[' + note_number + ']{' + body.strip() + '}']}
            # Unnumbered or incomplete material is retained for review.
            if prose < 15:
                counts['unresolved_note_fragments'].append(body.strip())
            return {'t': 'RawBlock', 'c': ['latex', r'\begin{quote}\footnotesize\noindent\rule{0.3\linewidth}{0.3pt}\par ' + body + r'\end{quote}']}
        if kind in ('RawInline', 'RawBlock'):
            if content[0]=='html':
                if re.fullmatch(r'<br\s*/?>',content[1],re.I):
                    return {'t':'LineBreak'}
                if column_mark(content[1]):
                    return node
            raise ValueError('存在未转换的 HTML 内容，停止以免遗漏。')
        return {k: visit(v) for k, v in node.items()}

    ast['blocks'] = visit(ast['blocks'])
    # Bind a uniquely identified source marker to its note. LaTeX then keeps
    # the note on the marker's page even when translated paragraphs reflow.
    notes = {}
    for block in ast['blocks']:
        if block.get('t') == 'RawBlock':
            match = re.fullmatch(r'\\footnotetext\[(\d+)\]\{([\s\S]*)\}', block['c'][1])
            if match:
                notes.setdefault(match[1], []).append((block, match[2]))
    references = {}
    heading_references = {}
    def find_references(node, heading=None):
        if isinstance(node, list):
            for item in node:
                find_references(item, heading)
        elif isinstance(node, dict):
            if node.get('t') == 'Header':
                heading = node
            if node.get('t') == 'Math':
                match = re.fullmatch(r'\^(?:\{(\d+)\}|(\d+))', node['c'][1].strip())
                if match:
                    references.setdefault(match[1] or match[2], []).append(node)
                    if heading is not None:
                        heading_references[id(node)] = heading
            else:
                for value in node.values():
                    find_references(value, heading)
    find_references(ast['blocks'])
    moved = []
    after_heading = {}
    for number, entries in notes.items():
        if len(entries) == 1 and len(references.get(number, [])) == 1:
            block, body = entries[0]
            reference = references[number][0]
            heading = heading_references.get(id(reference))
            reference.clear()
            if heading is not None:
                reference.update({'t': 'RawInline', 'c': ['latex', r'\protect\footnotemark[' + number + ']']})
                after_heading.setdefault(id(heading), []).append(block)
            else:
                reference.update({'t': 'RawInline', 'c': ['latex', r'\footnote[' + number + ']{' + body + '}']})
            moved.append(block)
    ast['blocks'] = [block for block in ast['blocks'] if block not in moved]
    ast['blocks'] = [item for block in ast['blocks'] for item in [block, *after_heading.get(id(block), [])]]
    counts['anchored_notes'] = len(moved)
    # Layout markers survive the passes above; they become multicols regions and
    # floats only after the single LaTeX conversion, so footnote binding still
    # sees one flat block stream and pandoc still sees every table.
    ast['blocks'], counts['columns'] = mark_regions(ast['blocks'])
    (project/'document.json').write_text(json.dumps(ast, ensure_ascii=False), encoding='utf-8')
    (project/'math-regions.json').write_text(json.dumps(math_regions, ensure_ascii=False, indent=2), encoding='utf-8')
    size = layout.get('fontSize',11)
    font_override = ('\n'+r'\AtBeginDocument{\fontsize{'+str(size)+'pt}{'+str(round(size*1.2,1))+r'pt}\selectfont}') if 'fontSize' in layout else ''
    (project/'layout.tex').write_text(HEADER+font_override, encoding='utf-8')
    tex = run([pandoc, '-f', 'json', '-t', 'latex', '-s', '--pdf-engine=xelatex',
               '-V', f"fontsize={layout.get('fontSize',11)}pt",
               '-V', 'geometry:margin=24mm', '-V', 'papersize=a4',
               '-V', 'colorlinks=true', '-V', 'linkcolor=black']
              + (['-V', 'classoption=twocolumn'] if counts['columns'] == 2 else [])
              + ['--include-in-header=layout.tex'], json.dumps(ast), cwd=project)
    tex = break_long_urls(tex)
    tex = apply_regions(tex, counts['columns'])
    tex = shrink_references(tex)
    tex, counts['fitted_tables'], counts['table_lines'] = fit_tables(tex)
    (project/'main.tex').write_text(tex, encoding='utf-8')
    (project/'README.txt').write_text(
        '使用 XeLaTeX 编译 main.tex（两遍），或 tectonic --untrusted main.tex。\n'
        '优先使用 Windows 的宋体（SimSun）和微软雅黑（Microsoft YaHei）；缺少时自动退回 Fandol 字体。\n'
        '可直接在 Overleaf 选择 XeLaTeX 编译，但需连同 images 目录一起上传。\n',
        encoding='utf-8')
    return counts


MISSING_GLYPH = re.compile(r'Missing character: There is no .*? \(U\+([0-9A-Fa-f]{4,6})\)')
CJK_RANGES = ((0x3000, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
              (0x20000, 0x2FA1F), (0xFF00, 0xFFEF))


OVERFULL = re.compile(r'Overfull \\[hv]box \(([0-9.]+)pt([^\n]*)')
OVERFULL_LINES = re.compile(r'at lines (\d+)--(\d+)')


def split_overfull(engine_log, table_lines=()):
    """Separate real overflow from boxes that adjustbox already scales down."""
    outside, inside = [], []
    for match in OVERFULL.finditer(engine_log):
        size = float(match[1])
        where = OVERFULL_LINES.search(match[2])
        first = int(where[1]) if where else 0
        if first and any(start-1 <= first <= end+1 for start, end in table_lines):
            inside.append(size)
        else:
            outside.append(size)
    return outside, inside


def missing_glyphs(log):
    """Characters the main font cannot render, in first-seen order."""
    seen = []
    for code in MISSING_GLYPH.findall(log):
        char = chr(int(code, 16))
        if char not in seen:
            seen.append(char)
    return seen


def heal_glyphs(project, chars):
    """Route unrepresentable characters through the fallback fonts and rebuild.

    One missing glyph used to abort the whole translation. Re-adding the
    character with a font that has it costs a compile, never a model call.
    """
    tex_path = project/'main.tex'
    tex = tex_path.read_text('utf-8')
    marker = r'\begin{document}'
    if marker not in tex:
        return False
    lines = []
    for char in chars:
        command = 'cjkchar' if any(low <= ord(char) <= high for low, high in CJK_RANGES) else 'symbolchar'
        lines.append('\\newunicodechar{'+char+'}{\\'+command+'{'+char+'}}')
    tex_path.write_text(tex.replace(marker, '\n'.join(lines)+'\n'+marker, 1), encoding='utf-8')
    return True


def compile_pdf(project, tectonic):
    """One TeX run; returns (returncode, console log)."""
    result = subprocess.run([tectonic, '--untrusted', '--keep-logs', 'main.tex'],
                            cwd=project, capture_output=True, encoding='utf-8', errors='replace', timeout=600)
    log = result.stdout + '\n' + result.stderr
    (project/'compile.log').write_text(log, encoding='utf-8')
    return result.returncode, log


def render_latex(text, cache, output):
    output = Path(output)
    project = output.with_suffix('')
    with progress.spinner('生成 LaTeX 项目'):
        counts = build_project(text, cache, project)
    _, tectonic = binaries()
    healed = []
    with progress.spinner('编译 PDF（tectonic）'):
        code, log = compile_pdf(project, tectonic)
        for _ in range(2):
            engine_log = (project/'main.log').read_text('utf-8', errors='replace') if (project/'main.log').exists() else ''
            pending = [char for char in missing_glyphs(engine_log) if char not in healed]
            if not pending or not heal_glyphs(project, pending):
                break
            healed.extend(pending)
            code, log = compile_pdf(project, tectonic)
    if code or not (project/'main.pdf').exists():
        engine_log = (project/'main.log').read_text('utf-8', errors='replace') if (project/'main.log').exists() else ''
        events = re.findall(r'^TRANSLATOR-MATH-(BEGIN|END):(\d+)\s*$', engine_log, re.M)
        context = None
        if events and events[-1][0] == 'BEGIN':
            regions = json.loads((project/'math-regions.json').read_text('utf-8'))
            context = dict(regions[int(events[-1][1])])
            errors = re.findall(r'^! .*(?:\n(?!\n)[^\n]*){0,4}', engine_log, re.M)
            context['error'] = '\n'.join(errors[-2:]) or log[-1200:]
        summary = context['error'] if context else '\n'.join(re.findall(r'^error:.*', log, re.M)[:4])
        raise LatexCompileError('LaTeX 编译失败：\n' + (summary or log[-1500:]) + '\n源文件和日志：' + str(project), context)
    engine_log = (project/'main.log').read_text('utf-8', errors='replace')
    counts['scaled_displays'] = engine_log.count('LATEX-TRANSLATOR: scaled wide display')
    counts['warnings'] = [line for line in log.splitlines() if 'warning:' in line.lower()]
    table_lines = counts.pop('table_lines', [])
    counts['overfull_boxes_pt'], counts['scaled_table_boxes'] = split_overfull(engine_log, table_lines)
    counts['missing_characters'] = [line for line in engine_log.splitlines() if 'Missing character:' in line]
    counts['healed_glyphs'] = healed
    severe = [n for n in counts['overfull_boxes_pt'] if n > SEVERE_OVERFULL_PT]
    context = layout_error_context(project, engine_log) if severe else None
    if severe and context:
        (project/'render-report.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding='utf-8')
        raise LatexLayoutError('LaTeX 排版检查发现内容严重越界，未更新最终 PDF。请检查：' + str(project/'render-report.json'), context)
    if counts['missing_characters']:
        # A glyph the fallback fonts do not carry either is a cosmetic defect on
        # one character; it must not discard an otherwise complete translation.
        counts['unresolved_glyphs'] = missing_glyphs(engine_log)
    if severe:
        # No block can be blamed (e.g. a long DOI in the bibliography): keep the
        # compiled PDF and report it instead of failing the whole document.
        counts['overfull_accepted'] = severe
    (project/'render-report.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding='utf-8')
    if counts['unresolved_note_fragments']:
        print(f"脚注结构需复核：保留了 {len(counts['unresolved_note_fragments'])} 个无法确认归属的短片段，详见 {project/'render-report.json'}", flush=True)
    if counts.get('unresolved_glyphs'):
        print(f"字形警告：{' '.join(counts['unresolved_glyphs'])} 在可用字体中缺失，已保留 PDF；详见 render-report.json", flush=True)
    if severe:
        print(f"排版警告：{len(severe)} 处越界无法定位到具体内容块（{', '.join(f'{n:g}pt' for n in severe)}），已保留 PDF；详见 render-report.json", flush=True)
    try:
        shutil.copyfile(project/'main.pdf', output)
    except PermissionError as exc:
        raise PermissionError('输出 PDF 被占用：' + str(output)) from exc
    return text
