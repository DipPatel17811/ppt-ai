"""SWOT slide template: 2x2 matrix with colour-coded quadrants."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import BulletItem, SwoSlide, SwoQuadrant, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class SwoTemplate(BaseTemplate):
    kind = "swot"

    def render(self, b: SlideBuilder, c: SwoSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title, c.context)

        gap = space(2)
        matrix = Rect(area.x, area.y, area.width, area.height)
        cell_w = (matrix.width - gap) / 2.0
        cell_h = (matrix.height - gap) / 2.0

        quads = [
            (Rect(matrix.x, matrix.y, cell_w, cell_h), c.strengths, t.spec.success, "S"),
            (Rect(matrix.x + cell_w + gap, matrix.y, cell_w, cell_h), c.weaknesses, t.spec.danger, "W"),
            (Rect(matrix.x, matrix.y + cell_h + gap, cell_w, cell_h), c.opportunities, t.spec.primary, "O"),
            (Rect(matrix.x + cell_w + gap, matrix.y + cell_h + gap, cell_w, cell_h), c.threats, t.spec.warning, "T"),
        ]
        for rect, quadrant, color, code in quads:
            self._quadrant(b, rect, quadrant, color, code)
        b.notes(c.notes)

    def _quadrant(self, b: SlideBuilder, rect: Rect, q: SwoQuadrant, color: str, code: str) -> None:
        t = b.theme
        b.rect(rect, fill=t.alpha_on(color, 0.06) if t.is_dark else t.tint(color, 0.92),
               line=t.border, line_width=1.0, radius=t.radius, key=f"quad_{code}")

        pad = space(1.5)
        gap = space(1)
        badge = Rect(rect.x + pad, rect.y + pad, 30, 30)
        b.oval(badge, fill=color, key=f"quad_{code}_badge")
        b.text(badge, code, role="caption", size=13.0, color="#ffffff", bold=True,
               align=TextAlign.CENTER, anchor=VerticalAlign.MIDDLE, key=None)

        title_rect = Rect(badge.right + gap, rect.y + pad, rect.right - badge.right - gap - pad, 30)
        b.text(title_rect, q.title, role="h3", size=t.type_size("h3"),
               color=color if t.is_dark else t.shade(color, 0.35), bold=True,
               anchor=VerticalAlign.MIDDLE, key=f"quad_{code}_title")

        items = [BulletItem(text=p) for p in q.items[:6]]
        list_rect = Rect(rect.x + space(2.5), badge.bottom + gap,
                         rect.width - space(5), rect.bottom - badge.bottom - gap - pad)
        b.bullets(list_rect, items, size=t.type_size("small") - 1, gap=space(1),
                  bullet_color=color, key_prefix=f"quad_{code}_items")
