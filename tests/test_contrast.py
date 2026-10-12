"""WCAG 2.1 contrast of the dashboard's colour tokens, read from frontend/index.html, in both themes.

Text tokens need 4.5:1 on the card (--bg) and page (--soft) backgrounds (AA, normal text).
Chart, zone, sport, sleep and status colours need 3:1 on the card (AA non-text / large text).
Gridlines (--line) are decorative and exempt.
"""

import re
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text()
TEXT = ("text", "muted", "faint", "accent")
GRAPHIC = (
    "good",
    "warn",
    "bad",
    "blue",
    "purple",
    "c1",
    "c2",
    "c3",
    "c4",
    "c5",
    "ink",
    "z1",
    "z2",
    "z3",
    "z4",
    "z5",
    "deep",
    "rem",
    "light",
    "awake",
    "run",
    "walk",
    "gym",
    "hike",
    "stretch",
    "other",
)


def _tokens(selector: str) -> dict[str, str]:
    block = re.search(re.escape(selector) + r"\{([^}]*)\}", HTML).group(1)
    return dict(re.findall(r"--([\w-]+):(#[0-9a-fA-F]{3,6})", block))


LIGHT = _tokens(":root")
DARK = {**LIGHT, **_tokens(":root[data-theme=dark]")}


def _lum(hex_: str) -> float:
    h = hex_.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    rgb = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_dark_overrides_match_system_dark():
    assert _tokens(":root[data-theme=dark]") == _tokens(":root:not([data-theme=light])")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_tokens_aa(theme):
    t = LIGHT if theme == "light" else DARK
    bad = {
        k: round(min(ratio(t[k], t["bg"]), ratio(t[k], t["soft"])), 2)
        for k in TEXT
        if min(ratio(t[k], t["bg"]), ratio(t[k], t["soft"])) < 4.5
    }
    assert not bad, f"{theme} text below 4.5:1: {bad}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_graphic_tokens_aa(theme):
    t = LIGHT if theme == "light" else DARK
    bad = {
        k: round(ratio(t[k], t["bg"]), 2)
        for k in GRAPHIC
        if k in t and ratio(t[k], t["bg"]) < 3.0
    }
    assert not bad, f"{theme} graphics below 3:1: {bad}"
