"""Text measurement and auto-fitting helpers.

Templates never guess whether text will fit: this module provides a
deterministic estimate of rendered text size using Pillow's FreeType engine,
with graceful fallback to a conservative character-width heuristic when a
requested font is not installed.  This powers both the auto-shrink behaviour
of the renderer and the post-render text-fit validation.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from config import FONT_SEARCH_ROOTS, FALLBACK_FONT

# Pillow is an optional dependency for measurement; without it we degrade to
# a width heuristic.  We import lazily so the compiler still works without it.
try:  # pragma: no cover - environment dependent
    from PIL import ImageFont
except Exception:  # pragma: no cover
    ImageFont = None  # type: ignore[assignment]


def _candidates(family: str, bold: bool) -> List[Tuple[str, Path]]:
    names = [family]
    if family.lower() in ("segou ui", "segoe ui", "helvetica", "arial", "dejavu sans"):
        names.append(FALLBACK_FONT)
    result: List[Tuple[str, Path]] = []
    for root in FONT_SEARCH_ROOTS:
        if not root.exists():
            continue
        for name in names:
            stems = [
                name.replace(" ", ""),
                name,
                "segoeui",
                "arial",
                "dejavusans",
            ]
            for stem in dict.fromkeys(stems):
                for ext in (".ttf", ".ttc"):
                    p = root / f"{stem}{ext}"
                    if p.exists():
                        result.append((name, p))
                        break
    return result


@lru_cache(maxsize=256)
def font_file(family: str, bold: bool = False) -> Optional[Path]:
    """Resolve a font family to a filesystem path, or None."""
    if ImageFont is None:
        return None
    for name, path in _candidates(family, bold):
        if bold and "bold" in path.stem.lower():
            return path
        return path
    return None


def _font(family: str, size: float, bold: bool = False) -> Optional[object]:
    """Load a Pillow font, or None when Pillow / font is unavailable."""
    if ImageFont is None:
        return None
    path = font_file(family, bold)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size=int(max(1, round(size))))
        except Exception:
            return None
    try:
        return ImageFont.load_default(size=int(max(1, round(size))))
    except TypeError:  # older Pillow has no size argument
        return ImageFont.load_default()


def measure(text: str, family: str, size: float, bold: bool = False) -> Tuple[float, float]:
    """Estimate ``(width, height)`` of ``text`` in points at the given size."""
    font = _font(family, size, bold)
    if font is not None and hasattr(font, "getlength"):
        return (float(font.getlength(text)), float(font.size))
    # Heuristic fallback: average glyph width ~= 0.55em.
    width = sum(2.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 1.0 for ch in text)
    return (width * size * 0.55, size * 1.2)


def wrap(text: str, family: str, size: float, max_width: float, bold: bool = False) -> List[str]:
    """Greedy word-wrap ``text`` to ``max_width`` points; returns lines."""
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if measure(candidate, family, size, bold)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if measure(current, family, size, bold)[0] > max_width:
                # A single word is wider than the box; hard-break it.
                lines.append(current)
                current = ""
    if current:
        lines.append(current)
    return lines


def block_height(text: str, family: str, size: float, max_width: float,
                 line_spacing: float = 1.2, bold: bool = False) -> float:
    """Estimated height in points of a wrapped text block."""
    lines = wrap(text, family, size, max_width, bold=bold)
    return len(lines) * size * line_spacing


def fits(text: str, family: str, size: float, box_w: float, box_h: float,
         line_spacing: float = 1.2, bold: bool = False) -> bool:
    """Return True when the wrapped block fits inside the given box."""
    return block_height(text, family, size, box_w, line_spacing, bold) <= box_h


def fit_font_size(text: str, family: str, box_w: float, box_h: float,
                  start: float, min_size: float, line_spacing: float = 1.15,
                  bold: bool = False) -> float:
    """Largest font size <= ``start`` such that ``text`` fits ``box``."""
    lo, hi = min_size, start
    if fits(text, family, hi, box_w, box_h, line_spacing, bold):
        return hi
    best = min_size
    while lo <= hi:
        mid = (lo + hi) / 2.0
        if fits(text, family, mid, box_w, box_h, line_spacing, bold):
            best, lo = mid, mid + 0.5
        else:
            hi = mid - 0.5
    return round(best, 1)
