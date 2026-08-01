"""The theme engine.

A ``Theme`` wraps a validated :class:`schema.ThemeSpec` and provides all of
the derived values the renderer needs: the full colour ladder (base, tints,
shades, text-on-colour), the typography scale, spacing helpers and the chart
palette.  Themes are pure data -- they never draw anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from config import DEFAULT_THEME, THEME_DIR, TYPE_SCALE
from schema import ThemeMode, ThemeSpec
from utils import colors

# ---------------------------------------------------------------------------
# Built-in presets.  These are also exported as JSON to ``assets/themes`` so
# they can be inspected and copied by users.
# ---------------------------------------------------------------------------

PRESET_THEMES: Dict[str, dict] = {
    "corporate": {
        "name": "corporate",
        "mode": "light",
        "background": "#ffffff",
        "foreground": "#16233b",
        "muted": "#5a6b83",
        "primary": "#0f4c81",
        "secondary": "#1f8a8f",
        "accent": "#f2a03d",
        "success": "#2e9e5b",
        "warning": "#d97b29",
        "danger": "#c0392b",
        "heading_font": "Segoe UI",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#0f4c81", "#1f8a8f", "#f2a03d", "#c0392b", "#6b5b95", "#3a6ea5", "#5a6b83"],
    },
    "slate": {
        "name": "slate",
        "mode": "light",
        "background": "#fbfbfc",
        "foreground": "#1e2630",
        "muted": "#6a7686",
        "primary": "#2f3a4f",
        "secondary": "#4a7fb5",
        "accent": "#d98e32",
        "success": "#3d8b6d",
        "warning": "#c9872e",
        "danger": "#b0403a",
        "heading_font": "Segoe UI",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#2f3a4f", "#4a7fb5", "#d98e32", "#b0403a", "#3d8b6d", "#8b6f47"],
    },
    "crimson": {
        "name": "crimson",
        "mode": "light",
        "background": "#ffffff",
        "foreground": "#241a1a",
        "muted": "#6d5a5a",
        "primary": "#8c1d2f",
        "secondary": "#2a4d6b",
        "accent": "#e0a32e",
        "success": "#2e7d57",
        "warning": "#c97f2e",
        "danger": "#a83232",
        "heading_font": "Georgia",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#8c1d2f", "#2a4d6b", "#e0a32e", "#2e7d57", "#7a4a8f", "#b4553d"],
    },
    "forest": {
        "name": "forest",
        "mode": "light",
        "background": "#fcfdf9",
        "foreground": "#1c2620",
        "muted": "#5c6b62",
        "primary": "#1f5f46",
        "secondary": "#3f7a8c",
        "accent": "#d9a93b",
        "success": "#2e7d3b",
        "warning": "#c9872e",
        "danger": "#b0403a",
        "heading_font": "Segoe UI",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#1f5f46", "#3f7a8c", "#d9a93b", "#b0403a", "#7a8c3f", "#5c6b62"],
    },
    "royal": {
        "name": "royal",
        "mode": "dark",
        "background": "#101623",
        "foreground": "#f2f5fa",
        "muted": "#9aa7bd",
        "primary": "#3b6fd4",
        "secondary": "#3fb6b0",
        "accent": "#f2b441",
        "success": "#48c78e",
        "warning": "#f0933f",
        "danger": "#e05656",
        "heading_font": "Segoe UI",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#3b6fd4", "#3fb6b0", "#f2b441", "#e05656", "#9c6bd4", "#4f8fd4"],
    },
    "midnight": {
        "name": "midnight",
        "mode": "dark",
        "background": "#0b0e14",
        "foreground": "#eef1f6",
        "muted": "#8b95a5",
        "primary": "#4c8bff",
        "secondary": "#38c0b8",
        "accent": "#ffc24b",
        "success": "#4fd18b",
        "warning": "#ff9d45",
        "danger": "#ff5c5c",
        "heading_font": "Segoe UI",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#4c8bff", "#38c0b8", "#ffc24b", "#ff5c5c", "#a97bff", "#5cd6d6"],
    },
    "mono": {
        "name": "mono",
        "mode": "light",
        "background": "#ffffff",
        "foreground": "#111111",
        "muted": "#6b6b6b",
        "primary": "#111111",
        "secondary": "#444444",
        "accent": "#888888",
        "success": "#2e7d3b",
        "warning": "#8a6d1f",
        "danger": "#9c2f2f",
        "heading_font": "Segoe UI",
        "body_font": "Segoe UI",
        "mono_font": "Consolas",
        "chart_palette": ["#111111", "#444444", "#888888", "#bbbbbb", "#6b6b6b", "#333333"],
    },
}


def _spec_from_dict(data: dict) -> ThemeSpec:
    allowed = ThemeSpec.model_fields.keys()
    return ThemeSpec(**{k: v for k, v in data.items() if k in allowed})


class Theme:
    """Runtime wrapper around :class:`ThemeSpec` with derived values."""

    def __init__(self, spec: ThemeSpec) -> None:
        self.spec = spec

    # -- construction ----------------------------------------------------
    @classmethod
    def builtin(cls, name: str) -> "Theme":
        name = (name or DEFAULT_THEME).lower()
        if name in PRESET_THEMES:
            return cls(_spec_from_dict(PRESET_THEMES[name]))
        path = THEME_DIR / f"{name}.json"
        if path.exists():
            return cls(_spec_from_dict(json.loads(path.read_text(encoding="utf-8"))))
        raise KeyError(
            f"Unknown theme {name!r}. Available: {sorted(PRESET_THEMES)} "
            f"plus JSON files in {THEME_DIR}."
        )

    @classmethod
    def from_spec(cls, spec: ThemeSpec) -> "Theme":
        return cls(spec)

    @classmethod
    def list_builtin(cls) -> List[str]:
        files = sorted(p.stem for p in THEME_DIR.glob("*.json")) if THEME_DIR.exists() else []
        return sorted(set(list(PRESET_THEMES) + files))

    # -- colour ladder ---------------------------------------------------
    def tint(self, hex_color: str, factor: float) -> str:
        return colors.tint(hex_color, factor)

    def shade(self, hex_color: str, factor: float) -> str:
        return colors.shade(hex_color, factor)

    def readable_on(self, background: str) -> str:
        return colors.text_color_for(background)

    def alpha_on(self, base: str, factor: float) -> str:
        """Colour suitable for a subtle wash/overlay (mixed toward background)."""
        return colors.mix(base, self.spec.background, 1.0 - factor)

    # -- semantic aliases ------------------------------------------------
    @property
    def is_dark(self) -> bool:
        return self.spec.mode == ThemeMode.DARK

    @property
    def surface(self) -> str:
        """Card surface: slightly off the slide background."""
        if self.is_dark:
            return colors.mix(self.spec.background, "#ffffff", 0.06)
        return colors.mix(self.spec.background, "#000000", 0.035)

    @property
    def border(self) -> str:
        if self.is_dark:
            return colors.mix(self.spec.background, "#ffffff", 0.16)
        return colors.mix(self.spec.background, "#000000", 0.12)

    def heading_color(self, emphasis: bool = False) -> str:
        return self.spec.primary if emphasis else self.spec.foreground

    # -- typography ------------------------------------------------------
    @property
    def heading_font(self) -> str:
        return self.spec.heading_font

    @property
    def body_font(self) -> str:
        return self.spec.body_font

    @property
    def mono_font(self) -> str:
        return self.spec.mono_font

    def type_size(self, role: str) -> float:
        return TYPE_SCALE.get(role, 14.0)

    # -- spacing ---------------------------------------------------------
    def space(self, multiple: float) -> float:
        return multiple * self.spec.base_spacing

    @property
    def radius(self) -> float:
        return self.spec.corner_radius

    # -- charts ----------------------------------------------------------
    def chart_color(self, index: int) -> str:
        palette = self.spec.chart_palette or ["#0f4c81"]
        return palette[index % len(palette)]

    # -- footer ----------------------------------------------------------
    @property
    def footer_text(self) -> str:
        return self.spec.footer_text
