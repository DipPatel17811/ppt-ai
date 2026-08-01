"""The deterministic layout engine.

Templates never hard-code coordinates.  Instead they describe structure --
rows, columns, grids, stacks -- and this module resolves that structure into
concrete, non-overlapping :class:`Rect` objects.

Three ideas are central:

1. **Partitioning** - a parent rect is divided among children along an axis;
   the space is split exactly so nothing overlaps and nothing is lost.
2. **Alignment** - children can be stretched, centered or packed along the
   cross axis.
3. **Constraint solving** - ``FitBox`` solves simple proportional-fit
   problems (respecting minimum sizes) so objects can auto-size.

All units are points.  The compiler converts to EMU at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Union

from config import BASE_SPACING, space
from utils.geometry import Point, Rect, Size, clamp

Axis = str  # "x" or "y"

Align = str  # "start" | "center" | "end" | "stretch"


# ---------------------------------------------------------------------------
# Partition helpers
# ---------------------------------------------------------------------------


def _partition_along(rect: Rect, weights: Sequence[float], gap: float) -> List[Rect]:
    """Split ``rect`` into ``len(weights)`` slices along the x-axis."""
    total_gap = gap * (len(weights) - 1)
    total = sum(weights)
    usable = rect.width - total_gap
    slices: List[Rect] = []
    cursor = rect.x
    for w in weights:
        width = usable * (w / total) if total else usable / len(weights)
        slices.append(Rect(cursor, rect.y, width, rect.height))
        cursor += width + gap
    return slices


def _partition_down(rect: Rect, weights: Sequence[float], gap: float) -> List[Rect]:
    """Split ``rect`` into ``len(weights)`` slices along the y-axis."""
    total_gap = gap * (len(weights) - 1)
    total = sum(weights)
    usable = rect.height - total_gap
    slices: List[Rect] = []
    cursor = rect.y
    for w in weights:
        height = usable * (w / total) if total else usable / len(weights)
        slices.append(Rect(rect.x, cursor, rect.width, height))
        cursor += height + gap
    return slices


def _align_in(box: Rect, inner: Rect, align: Align, axis: Axis) -> Rect:
    if align == "stretch" or align == "fill":
        return inner
    if axis == "x":
        if align == "center":
            return inner.translate((box.width - inner.width) / 2.0 - (inner.x - box.x), 0)
        if align == "end":
            return inner.translate((box.width - inner.width) - (inner.x - box.x), 0)
        return inner
    else:
        if align == "center":
            return inner.translate(0, (box.height - inner.height) / 2.0 - (inner.y - box.y))
        if align == "end":
            return inner.translate(0, (box.height - inner.height) - (inner.y - box.y))
        return inner


def equal_columns(parent: Rect, count: int, gap: float) -> List[Rect]:
    """Return ``count`` equal-width, full-height column rects."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return _partition_along(parent, [1.0] * count, gap)


def equal_rows(parent: Rect, count: int, gap: float) -> List[Rect]:
    """Return ``count`` equal-height, full-width row rects."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return _partition_down(parent, [1.0] * count, gap)


def weighted_columns(parent: Rect, weights: Sequence[float], gap: float) -> List[Rect]:
    return _partition_along(parent, list(weights), gap)


def weighted_rows(parent: Rect, weights: Sequence[float], gap: float) -> List[Rect]:
    return _partition_down(parent, list(weights), gap)


def grid(parent: Rect, rows: int, cols: int, gap_x: float, gap_y: float) -> List[List[Rect]]:
    """Return a ``rows x cols`` grid of cell rects, row-major."""
    row_rects = equal_rows(parent, rows, gap_y)
    return [equal_columns(r, cols, gap_x) for r in row_rects]


def row_grid(parent: Rect, items: int, gap_x: float, gap_y: float, cols: Optional[int] = None) -> List[List[Rect]]:
    """Auto grid: at most ``cols`` columns, filling rows as needed."""
    cols = cols or max(1, items)
    rows = (items + cols - 1) // cols
    cells = grid(parent, rows, cols, gap_x, gap_y)
    return [row for row in cells for _ in [0]]


def hstack(parent: Rect, sizes: Sequence[float], gap: float, align: Align = "stretch") -> List[Rect]:
    """Horizontal stack of rects with explicit widths, aligned vertically."""
    rects = _partition_along(parent, list(sizes), gap)
    if align != "stretch":
        for i, r in enumerate(rects):
            rects[i] = _align_in(r, r, align, "y")
    return rects


def vstack(parent: Rect, sizes: Sequence[float], gap: float, align: Align = "stretch") -> List[Rect]:
    """Vertical stack of rects with explicit heights, aligned horizontally."""
    rects = _partition_down(parent, list(sizes), gap)
    if align != "stretch":
        for i, r in enumerate(rects):
            rects[i] = _align_in(r, r, align, "x")
    return rects


def scatter(parent: Rect, count: int, gap: float) -> List[Rect]:
    """Equally spaced items along the main axis, centered as a group."""
    if count < 1:
        return []
    if count == 1:
        return [parent]
    return _partition_along(parent, [1.0] * count, gap)


# ---------------------------------------------------------------------------
# Declarative layout objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """Split the parent horizontally into children (columns)."""

    weights: Optional[List[float]] = None
    gap: float = field(default_factory=lambda: space(1))
    n: Optional[int] = None

    def rects(self, parent: Rect) -> List[Rect]:
        if self.weights:
            return weighted_columns(parent, self.weights, self.gap)
        return equal_columns(parent, self.n or 1, self.gap)


@dataclass(frozen=True)
class Column:
    """Split the parent vertically into children (rows/bands)."""

    weights: Optional[List[float]] = None
    gap: float = field(default_factory=lambda: space(1))
    n: Optional[int] = None

    def rects(self, parent: Rect) -> List[Rect]:
        if self.weights:
            return weighted_rows(parent, self.weights, self.gap)
        return equal_rows(parent, self.n or 1, self.gap)


@dataclass(frozen=True)
class Grid:
    """Split the parent into a ``rows`` x ``cols`` grid."""

    rows: int
    cols: int
    gap_x: float = field(default_factory=lambda: space(1))
    gap_y: float = field(default_factory=lambda: space(1))

    def rects(self, parent: Rect) -> List[Rect]:
        return [cell for row in grid(parent, self.rows, self.cols, self.gap_x, self.gap_y) for cell in row]


@dataclass(frozen=True)
class Stack:
    """Lay children in sequence with equal spacing (main axis)."""

    axis: Axis = "x"
    count: int = 1
    gap: float = field(default_factory=lambda: space(1))

    def rects(self, parent: Rect) -> List[Rect]:
        if self.axis == "y":
            return equal_rows(parent, self.count, self.gap)
        return equal_columns(parent, self.count, self.gap)


# ---------------------------------------------------------------------------
# Constraint solving (simple proportional fit)
# ---------------------------------------------------------------------------


@dataclass
class FitBox:
    """A child with a proportional weight and an optional minimum size."""

    weight: float = 1.0
    min_size: float = 0.0
    content_size: Optional[float] = None  # preferred size used when space allows


def solve_axis(total: float, gap: float, boxes: Sequence[FitBox]) -> List[float]:
    """Distribute ``total`` points among ``boxes`` respecting minimums.

    The algorithm is a simple iterative "assign then reclaim" proportional
    solve: space is distributed by weight; any box below its minimum reclaims
    the shortfall from the remaining boxes.
    """
    n = len(boxes)
    gaps = gap * (n - 1) if n > 1 else 0.0
    usable = max(0.0, total - gaps)
    weights = [max(0.0, b.weight) for b in boxes]
    wsum = sum(weights) or 1.0

    sizes = [usable * w / wsum for w in weights]

    # Honour minimums, iteratively reclaiming space from the rest.
    while True:
        mins_ok = True
        deficit = 0.0
        for i, b in enumerate(boxes):
            if sizes[i] < b.min_size:
                deficit += b.min_size - sizes[i]
                sizes[i] = b.min_size
        if deficit <= 0.001:
            break
        shrinkable = [i for i, b in enumerate(boxes) if sizes[i] > b.min_size]
        if not shrinkable:
            break
        over = sum(sizes[i] - b.min_size for i in shrinkable)
        if over <= 0.001:
            break
        for i in shrinkable:
            excess = sizes[i] - b.min_size
            if excess > 0:
                sizes[i] = max(b.min_size, sizes[i] - deficit * (excess / over))
    return sizes


def solve_row(parent: Rect, boxes: Sequence[FitBox], gap: float,
              align: Align = "stretch") -> List[Rect]:
    """Solve a proportional horizontal row inside ``parent``."""
    widths = solve_axis(parent.width, gap, boxes)
    rects: List[Rect] = []
    cursor = parent.x
    for i, w in enumerate(widths):
        r = Rect(cursor, parent.y, w, parent.height)
        if align != "stretch":
            r = _align_in(parent, r, align, "y")
        rects.append(r)
        cursor += w + gap
    return rects


def solve_column(parent: Rect, boxes: Sequence[FitBox], gap: float,
                 align: Align = "stretch") -> List[Rect]:
    """Solve a proportional vertical column inside ``parent``."""
    heights = solve_axis(parent.height, gap, boxes)
    rects: List[Rect] = []
    cursor = parent.y
    for i, h in enumerate(heights):
        r = Rect(parent.x, cursor, parent.width, h)
        if align != "stretch":
            r = _align_in(parent, r, align, "x")
        rects.append(r)
        cursor += h + gap
    return rects
