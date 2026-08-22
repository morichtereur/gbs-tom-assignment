"""Typefaces, embedded as data URIs.

Same three families as the rest of the portfolio, and embedded for the same
reason: the page is opened in contexts where a strict policy blocks every
external host, and a blocked font link does not fail loudly — it falls back to a
system stack and the page quietly loses the identity it was designed with.

Latin subsets, only the weights used. All OFL-licensed; see
assets/fonts/LICENSE.md.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from tom.config import ROOT

FONT_DIR = ROOT / "assets" / "fonts"

FACES = [
    ("Archivo", 400, "archivo-400.woff2"),
    ("Archivo", 600, "archivo-600.woff2"),
    ("Archivo", 700, "archivo-700.woff2"),
    ("Source Serif 4", 400, "source-serif-400.woff2"),
    ("IBM Plex Mono", 400, "plex-mono-400.woff2"),
    ("IBM Plex Mono", 500, "plex-mono-500.woff2"),
]


@lru_cache(maxsize=1)
def face_css() -> str:
    rules = []
    for family, weight, filename in FACES:
        path = FONT_DIR / filename
        if not path.exists():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode()
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:normal;"
            f"font-weight:{weight};font-display:swap;"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2');}}"
        )
    return "".join(rules)
