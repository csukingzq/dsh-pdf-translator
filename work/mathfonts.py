"""Detect PDFs whose math is typeset with MathType / Advance fonts.

BabelDOC decides whether a text run is a formula by font name. Its default
broad pattern misses the MathType ``AdvMacMth*`` / ``AdvP4C4E*`` / ``AdvEls-*``
/ ``AdvPi*`` families, so those glyph runs are sent to the language model as
prose. Their broken ToUnicode mappings then turn math into garbage (radical
rules even become literal ``ffi`` runs) and the translated PDF shows ``f``/``ffi``
noise. Adding the detected families to the formula pattern keeps them out of
translation, so the original math glyphs survive.

Everything here is plain data so it stays testable without pdf2zh-next.
"""
import base64
import re

# Copied from BabelDOC 0.7.1 (the version pinned by pdf2zh-next 2.10.x).
# Setting ``formular_font_pattern`` replaces this broad pattern inside the
# engine, so the defaults must travel together with our additions.
DEFAULT_BROAD_PATTERN = (
    r'(CM[^RB]'
    r'|(MS|XY|MT|BL|RM|EU|LA|RS)[A-Z]'
    r'|LINE'
    r'|LCIRCLE'
    r'|TeX-'
    r'|rsfs'
    r'|txsy'
    r'|wasy'
    r'|stmary'
    r'|.*Mono'
    r'|.*Code'
    r'|.*Sym'
    r'|.*Math'
    r'|AdvP4C4E74'
    r'|AdvPSSym'
    r'|AdvP4C4E59'
    r')'
)

# Fonts that MathType and Advanced Grafx emit for math symbols / extensions.
# Body text uses the separate ``AdvOT*`` (Times) families and must not match.
SUSPECT = re.compile(
    r'^(AdvMacMth.*|AdvP4C4E.*|AdvEls-.*|AdvPi.*|AdvPSSym.*|MathType.*|MTExtra.*)$'
)

# Characters a broken math-font ToUnicode mapping produces in extracted text.
SUSPICIOUS_CHARS = '\uFB03\u00BC\u00D0\u00F0\u00DE\u00FE'


def base_name(font_name):
    """Return the family name the engine matches on (``subset+Name`` -> ``Name``)."""
    name = str(font_name or '').strip()
    if not name:
        return ''
    if name.startswith('BASE64:'):
        try:
            name = base64.b64decode(name[7:]).decode('latin-1')
        except Exception:
            return ''
    parts = [part.strip() for part in name.split('+') if part.strip()]
    return parts[-1] if parts else ''


def detect(font_names):
    """Base names of suspicious math fonts, order preserved and deduplicated."""
    hits = []
    for name in font_names or ():
        base = base_name(name)
        if base and SUSPECT.match(base) and base not in hits:
            hits.append(base)
    return hits


def formula_font_pattern(font_names):
    """Formula pattern that keeps BabelDOC defaults and adds detected families.

    Returns ``None`` when nothing suspicious is found, so ordinary documents
    keep the engine's stock behaviour.
    """
    families = detect(font_names)
    if not families:
        return None
    additions = '|'.join(re.escape(name) for name in families)
    return DEFAULT_BROAD_PATTERN[:-1] + '|' + additions + ')'


def suspicious_chars(text):
    """Count chars that usually mean a math font has no usable ToUnicode."""
    value = str(text or '')
    return sum(value.count(char) for char in SUSPICIOUS_CHARS)


def diagnostics(font_names, char_hits=0):
    families = detect(font_names)
    return {
        'mathFonts': families,
        'formulaProtected': bool(families),
        'suspiciousChars': int(char_hits or 0),
    }
