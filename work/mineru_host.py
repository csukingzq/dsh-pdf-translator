"""Local-only MinerU worker. No translator configuration or API key is passed here."""
import contextlib
import json
import sys
from pathlib import Path

VERSION = '4.2.3'
RENDERER_VERSION = '0.6.26'


def recognize(source, target):
    from importlib.metadata import version
    if version('mineru') != VERSION or version('docvortex') != RENDERER_VERSION:
        raise RuntimeError('MinerU 版本不匹配，请重新准备环境。')
    for package, expected in {'reportlab':'5.1.0', 'ziamath':'0.13', 'ziafont':'0.11', 'fonttools':'4.68.0'}.items():
        if version(package) != expected:
            raise RuntimeError(f'MinerU 的 {package} 版本不匹配，请重新准备环境。')
    from mineru.parser import parse
    from mineru.render import PdfLayout, render_pdf
    from mineru_math import text_formula_glyphs
    # Basic performs local OCR, formula and table recognition. It does not use
    # the VLM service configured by a user's separate MinerU installation.
    result = parse(str(source), tier='basic', ocr_mode='ocr', image_analysis=False)
    with text_formula_glyphs():
        pdf = render_pdf(result.middle_json, layout=PdfLayout.ORIGINAL)
    Path(target).write_bytes(pdf)


if __name__ == '__main__':
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        recognize(request['source'], request['target'])
