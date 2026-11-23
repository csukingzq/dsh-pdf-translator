"""Local-only MinerU worker. No translator configuration or API key is passed here."""
import contextlib
import json
import sys
from pathlib import Path

VERSION = '4.2.3'
RENDERER_VERSION = '0.6.26'
TIER = 'standard'


def recognize(source, target):
    from importlib.metadata import version
    if version('mineru') != VERSION or version('docvortex') != RENDERER_VERSION:
        raise RuntimeError('MinerU 版本不匹配，请重新准备环境。')
    for package, expected in {'reportlab':'5.1.0', 'ziamath':'0.13', 'ziafont':'0.11', 'fonttools':'4.68.0'}.items():
        if version(package) != expected:
            raise RuntimeError(f'MinerU 的 {package} 版本不匹配，请重新准备环境。')
    from mineru.parser import parse
    from mineru.config import VlmConfig
    from mineru.render import PdfLayout, render_pdf
    from mineru_math import text_formula_glyphs
    # Explicit local configuration must override any unrelated remote VLM
    # endpoint in a user's MinerU configuration. Bound concurrency for desktop.
    result = parse(str(source), tier=TIER, ocr_mode='ocr', image_analysis=False,
                   vlm_config=VlmConfig(engine='llama-cpp', server_url='', max_concurrency=2))
    with text_formula_glyphs():
        pdf = render_pdf(result.middle_json, layout=PdfLayout.ORIGINAL)
    Path(target).write_bytes(pdf)


if __name__ == '__main__':
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        recognize(request['source'], request['target'])
