"""Chart engine.

Charts are never drawn by hand.  This module is responsible for turning
structured data into a validated, colour-assigned :class:`ChartSpec` and for
providing the small amount of normalisation the compiler needs (pie
percentages, palette rotation, axis label defaults).  Actual native-chart
creation lives in ``compiler``; everything here is pure and testable.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from config import MAX_CHART_CATEGORIES, MAX_PIE_SLICES
from schema import ChartKind, ChartSeries, ChartSpec


def assign_colors(spec: ChartSpec, palette: Sequence[str]) -> ChartSpec:
    """Fill in missing series colours deterministically from ``palette``."""
    for i, series in enumerate(spec.series):
        if series.color is None:
            series.color = palette[i % len(palette)]
    return spec


def pie_percentages(spec: ChartSpec) -> List[float]:
    """Return slice percentages for a pie chart, in order."""
    if spec.kind != ChartKind.PIE:
        return [0.0] * len(spec.categories)
    values = spec.series[0].values if spec.series else []
    total = sum(v for v in values if v > 0) or 1.0
    return [v / total * 100.0 for v in values]


def best_category_count(categories: Sequence[str]) -> List[str]:
    """Clamp the number of categories to the engine limit."""
    return list(categories[:MAX_CHART_CATEGORIES])


def normalize_spec(spec: ChartSpec, palette: Sequence[str]) -> ChartSpec:
    """Apply defaults and clamps so the compiler can rely on clean input."""
    spec = assign_colors(spec, palette)
    if spec.kind == ChartKind.PIE:
        spec.categories = spec.categories[:MAX_PIE_SLICES]
    else:
        spec.categories = best_category_count(spec.categories)
    for series in spec.series:
        series.values = series.values[: len(spec.categories)]
    return spec


def infer_bar_kind(spec: ChartSpec) -> str:
    """Return ``"vertical"`` or ``"horizontal"`` for bar charts."""
    if spec.kind != ChartKind.BAR:
        return "vertical"
    return "horizontal" if spec.horizontal else "vertical"


def default_y_label(spec: ChartSpec) -> Optional[str]:
    if spec.kind in (ChartKind.PIE, ChartKind.SCATTER):
        return None
    return spec.y_label or (spec.series[0].name if spec.series and len(spec.series) == 1 else None)
