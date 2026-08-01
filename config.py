"""Central configuration and constants for the presentation compiler.

Every tunable default for the compiler pipeline lives here so that the
behaviour of the whole tool is deterministic and can be overridden from a
single, well-documented location.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------
# Filesystem layout
# --------------------------------------------------------------------------
ROOT: Path = Path(__file__).resolve().parent
ASSETS: Path = ROOT / "assets"
ICON_DIR: Path = ASSETS / "icons"
FONT_DIR: Path = ASSETS / "fonts"
THEME_DIR: Path = ASSETS / "themes"
TEMP_DIR: Path = ROOT / "ppt_ai_tmp"

# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------
PT_PER_INCH: float = 72.0
EMU_PER_PT: int = 12700  # OOXML English Metric Units per point

# --------------------------------------------------------------------------
# Slide geometry (in points). 16:9 is the default consulting aspect.
# --------------------------------------------------------------------------
ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "16:9": (960, 540),
    "16:10": (960, 600),
    "4:3": (720, 540),
}
DEFAULT_ASPECT: str = "16:9"

# Safe content margins (in points), leaving room for a header + footer.
MARGIN_X: float = 56.0
MARGIN_TOP: float = 48.0
MARGIN_BOTTOM: float = 40.0
FOOTER_HEIGHT: float = 28.0

# --------------------------------------------------------------------------
# 8pt spacing system
# --------------------------------------------------------------------------
BASE_SPACING: float = 8.0
SPACE: Dict[str, float] = {
    "xs": 8.0,
    "sm": 16.0,
    "md": 24.0,
    "lg": 32.0,
    "xl": 40.0,
    "xxl": 64.0,
    "xxxl": 96.0,
}


def space(multiple: float) -> float:
    """Return ``multiple`` of the base 8pt spacing unit."""
    return multiple * BASE_SPACING


# --------------------------------------------------------------------------
# Typography scale (in points)
# --------------------------------------------------------------------------
TYPE_SCALE: Dict[str, float] = {
    "display": 42.0,
    "h1": 30.0,
    "h2": 24.0,
    "h3": 20.0,
    "h4": 16.0,
    "body": 14.0,
    "small": 12.0,
    "caption": 10.0,
    "kicker": 12.0,
}

# --------------------------------------------------------------------------
# Content limits enforced by the validators
# --------------------------------------------------------------------------
MAX_BULLETS_PER_LIST: int = 7
MAX_STEPS: int = 8
MAX_TIMELINE_ITEMS: int = 8
MAX_PHASES: int = 5
MAX_SWOT_ITEMS: int = 6
MAX_HIERARCHY_NODES: int = 14
MAX_COMPARISON_POINTS: int = 6
MAX_DASHBOARD_METRICS: int = 6
MIN_FONT_SIZE: float = 9.0
MAX_CHART_CATEGORIES: int = 12
MAX_PIE_SLICES: int = 8
MAX_CHART_SERIES: int = 8

# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
DEFAULT_THEME: str = "corporate"
DEFAULT_FONT: str = "Segoe UI"
FALLBACK_FONT: str = "Arial"
DEFAULT_OUTPUT: str = "presentation.pptx"
DEFAULT_FOOTER: str = "Confidential"

# --------------------------------------------------------------------------
# LLM / AI defaults (used by the ``ai`` package)
# --------------------------------------------------------------------------
LLM_MODELS: Dict[str, str] = {
    "qwen": "Qwen/Qwen2.5-1.5B-Instruct",
    "llama": "meta-llama/Llama-3.2-1B-Instruct",
    "gemma": "google/gemma-2-2b-it",
}
LLM_DEFAULT_MODEL: str = LLM_MODELS["qwen"]
LLM_MAX_NEW_TOKENS: int = 3000
LLM_TEMPERATURE: float = 0.4
LLM_TIMEOUT_ATTEMPTS: int = 3

# --------------------------------------------------------------------------
# Fonts searched by utils.fonts (Windows, then macOS, then Linux)
# --------------------------------------------------------------------------
FONT_SEARCH_ROOTS: List[Path] = [
    Path("C:/Windows/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/usr/share/fonts"),
]

# Known good sans-serif fonts for the Windows environment.
FONT_FALLBACKS: List[str] = [
    "Segoe UI",
    "Arial",
    "Helvetica",
    "DejaVu Sans",
]
