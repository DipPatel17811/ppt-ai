"""The 8pt spacing system shared across every template.

All gutters, gaps and paddings in the compiler are multiples of an 8pt base
unit, which is what gives consulting-style decks their consistent rhythm.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import BASE_SPACING, SPACE, space
from utils.geometry import Rect

# Public re-exports for ergonomic use throughout templates.
BASE = BASE_SPACING
XS, SM, MD, LG, XL, XXL, XXXL = (SPACE[k] for k in ("xs", "sm", "md", "lg", "xl", "xxl", "xxxl"))


@dataclass(frozen=True)
class Padding:
    """Uniform or asymmetric padding in points."""

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def all(cls, value: float) -> "Padding":
        return cls(value, value, value, value)

    @classmethod
    def symmetric(cls, horizontal: float = 0.0, vertical: float = 0.0) -> "Padding":
        return cls(horizontal, vertical, horizontal, vertical)

    @classmethod
    def box(cls, top: float, horizontal: float, bottom: float) -> "Padding":
        return cls(horizontal, top, horizontal, bottom)

    def apply(self, rect: Rect) -> Rect:
        """Return the rect inset by this padding."""
        return rect.inset_to(self.left, self.top, self.right, self.bottom)

    def horizontal(self) -> float:
        return self.left + self.right

    def vertical(self) -> float:
        return self.top + self.bottom
