# License and attribution

The integrated release starting at 1.1.0 is distributed under GNU AGPL version 3
(see LICENSE). Copyright (c) 2026 csukingzq and contributors. Earlier DSH PDF
Translator code was distributed under MIT; its notice is preserved in LICENSE-MIT.
That earlier grant is not revoked.

Complete corresponding source, tests and build scripts:
https://github.com/csukingzq/dsh-pdf-translator
Use the Git tag matching the package version. lib/client.js is built from
src/client.jsx using scripts/build-client.mjs.

## Translation components

- **Zotero PDF2zh**, guaguastandup and contributors:
  https://github.com/guaguastandup/zotero-pdf2zh (AGPL-3.0).
  This plugin follows its PDFMathTranslate / BabelDOC integration approach.
  It is a separate DSH plugin, not an official Zotero plugin build or endorsement.
- **PDFMathTranslate-next / pdf2zh-next 2.10.2**, upstream contributors:
  https://github.com/PDFMathTranslate/PDFMathTranslate-next (AGPL-3.0).
  Installed separately. work/engine_host.py adapts its configuration/API.
- **BabelDOC 0.7.1**, funstory-ai and contributors:
  https://github.com/funstory-ai/BabelDOC (AGPL-3.0).
  work/mathfonts.py retains its default formula font pattern, adding local font
  handling. Other compatibility modules adjust temporary input PDFs, model
  layout results and invalid translation responses at runtime. Installed
  upstream sources are not overwritten.
- **PyMuPDF**, Artifex and contributors: https://github.com/pymupdf/PyMuPDF
  (AGPL-3.0, with separate commercial licensing available upstream).
- **pypdf**: https://github.com/py-pdf/pypdf (BSD-3-Clause).

## OCR rendering and optional structure extraction

- **Pandoc 3.12.1**: https://github.com/jgm/pandoc (GPL-2.0-or-later).
- **Tectonic 0.17.0**: https://github.com/tectonic-typesetting/tectonic (MIT;
  dependencies and TeX resources retain their own notices).
- **Beautiful Soup** (MIT), **tqdm** (MPL-2.0 / MIT for the relevant portions).
- Optional structure worker: **PaddleOCR / PaddlePaddle** (Apache-2.0) and
  BabelDOC; see requirements-structure.txt for its separate environment.

These components, model weights and LaTeX resources are downloaded separately;
their licenses apply. The release archive does not bundle their binaries or
weights. Node dependency licenses remain with their respective packages.

Redistributors must preserve applicable notices and provide corresponding
source under the applicable licenses. Modified network deployments must also
observe AGPL source-offer requirements. The software license does not cover
users' input papers, translations, credentials or private caches.
