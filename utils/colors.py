"""Colour helpers shared by the theme engine, templates and charts.

All colours are internally stored as ``"#RRGGBB"`` strings; this module
provides pure functions to mix, tint, shade and compare colours so that the
theme engine can derive its full palette deterministically from a small set
of base colours.
"""

from __future__ import annotations

import re
from typing import Tuple

_HEX_RE = re.compile(r"^#(?:([0-9a-fA-F]{3})|([0-9a-fA-F]{6}))$")


def normalize(hex_color: str) -> str:
    """Validate and normalise a colour to ``#RRGGBB`` lowercase form."""
    hex_color = hex_color.strip()
    if hex_color.lower().startswith("0x"):
        hex_color = "#" + hex_color[2:]
    m = _HEX_RE.match(hex_color)
    if not m:
        raise ValueError(f"Invalid hex colour: {hex_color!r}")
    digits = (m.group(1) or m.group(2)).lower()
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits


def to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = normalize(hex_color)
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (r, g, b)


def to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(a: str, b: str, t: float) -> str:
    """Linear blend from ``a`` to ``b`` (``t`` in [0, 1])."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = to_rgb(a)
    rb, gb, bb = to_rgb(b)
    return to_hex(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def tint(hex_color: str, factor: float) -> str:
    """Blend ``hex_color`` towards white by ``factor`` in [0, 1]."""
    return mix(hex_color, "#ffffff", factor)


def shade(hex_color: str, factor: float) -> str:
    """Blend ``hex_color`` towards black by ``factor`` in [0, 1]."""
    return mix(hex_color, "#000000", factor)


def luminance(hex_color: str) -> float:
    """Relative luminance in [0, 1] per WCAG 2.0."""
    r, g, b = (c / 255.0 for c in to_rgb(hex_color))
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def is_light(hex_color: str, threshold: float = 0.6) -> bool:
    """Return True if the colour reads as light on screen."""
    return luminance(hex_color) > threshold


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours."""
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def readable_text_on(background: str, dark_text: str = "#1a1a1a", light_text: str = "#ffffff") -> str:
    """Pick the most readable foreground for a given background."""
    return dark_text if is_light(background) else light_text


def text_color_for(background: str) -> str:
    """Convenience alias: black text on light backgrounds, white on dark."""
    return readable_text_on(background)
