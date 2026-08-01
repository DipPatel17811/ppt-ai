"""Geometry primitives for the deterministic layout engine.

Everything in the layout pipeline is expressed in abstract point-space
``Rect`` objects.  The PowerPoint compiler is the *only* place that converts
these to OOXML EMU coordinates, so templates never see raw units.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Union

Number = Union[int, float]


@dataclass(frozen=True)
class Point:
    """An immutable 2D point."""

    x: float
    y: float


@dataclass(frozen=True)
class Size:
    """An immutable 2D size."""

    width: float
    height: float

    @classmethod
    def square(cls, side: float) -> "Size":
        return cls(side, side)


@dataclass(frozen=True)
class Rect:
    """An immutable axis-aligned rectangle given as origin + size."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError(f"Rect width/height must be >= 0, got {self!r}")

    # -- factories -------------------------------------------------------
    @classmethod
    def from_ltrb(cls, left: float, top: float, right: float, bottom: float) -> "Rect":
        return cls(left, top, right - left, bottom - top)

    # -- edges -----------------------------------------------------------
    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def center(self) -> Point:
        return Point(self.center_x, self.center_y)

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else float("inf")

    @property
    def area(self) -> float:
        return self.width * self.height

    # -- transformations -------------------------------------------------
    def translate(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def inset(self, dx: float, dy: float) -> "Rect":
        """Shrink from all four edges by ``dx`` horizontally / ``dy`` vertically."""
        return Rect(self.x + dx, self.y + dy, self.width - 2 * dx, self.height - 2 * dy)

    def inset_to(self, left: float, top: float, right: float, bottom: float) -> "Rect":
        return Rect(
            self.x + left,
            self.y + top,
            self.width - left - right,
            self.height - top - bottom,
        )

    def with_size(self, width: float, height: float) -> "Rect":
        return Rect(self.x, self.y, width, height)

    def with_center(self, center_x: float, center_y: float) -> "Rect":
        return Rect(center_x - self.width / 2.0, center_y - self.height / 2.0, self.width, self.height)

    def centered(self, size: Size) -> "Rect":
        """Return a rect of ``size`` centered inside this rect."""
        return self.with_center(self.center_x, self.center_y).with_size(size.width, size.height)

    def intersected(self, other: "Rect") -> Optional["Rect"]:
        left, top = max(self.left, other.left), max(self.top, other.top)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return Rect.from_ltrb(left, top, right, bottom)

    # -- predicates ------------------------------------------------------
    def overlaps(self, other: "Rect", epsilon: float = 0.25) -> bool:
        return not (
            self.right <= other.left + epsilon
            or other.right <= self.left + epsilon
            or self.bottom <= other.top + epsilon
            or other.bottom <= self.top + epsilon
        )

    def contains_point(self, px: float, py: float) -> bool:
        return self.left <= px <= self.right and self.top <= py <= self.bottom

    def contains(self, other: "Rect", epsilon: float = 0.25) -> bool:
        return (
            other.left >= self.left - epsilon
            and other.right <= self.right + epsilon
            and other.top >= self.top - epsilon
            and other.bottom <= self.bottom + epsilon
        )

    def scaled(self, sx: float, sy: float) -> "Rect":
        return Rect(self.x * sx, self.y * sy, self.width * sx, self.height * sy)


def center(outer: Rect, inner: Size) -> Rect:
    """Return a rect of ``inner`` size centered inside ``outer``."""
    return Rect(
        outer.x + (outer.width - inner.width) / 2.0,
        outer.y + (outer.height - inner.height) / 2.0,
        inner.width,
        inner.height,
    )


def polar(center_x: float, center_y: float, radius: float, angle_deg: float) -> Point:
    """Point on a circle.  0 degrees == 12 o'clock, clockwise positive."""
    theta = math.radians(angle_deg - 90.0)
    return Point(center_x + radius * math.cos(theta), center_y + radius * math.sin(theta))


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def ensure_within(box: Rect, item: Rect) -> Rect:
    """Translate ``item`` minimally so it is fully contained in ``box``."""
    dx = 0.0
    dy = 0.0
    if item.left < box.left:
        dx = box.left - item.left
    elif item.right > box.right:
        dx = box.right - item.right
    if item.top < box.top:
        dy = box.top - item.top
    elif item.bottom > box.bottom:
        dy = box.bottom - item.bottom
    return item.translate(dx, dy)
