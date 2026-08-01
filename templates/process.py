"""Process slide template: perfect circles with automatic connectors.

The step count is unlimited up to the validator limit (8).  Steps are placed
on one row when they fit; otherwise the layout wraps into two rows (snake
order) while keeping every circle *perfect* (equal diameter) and the
connectors automatically sized to bridge the exact gaps -- never overlapping.
"""

from __future__ import annotations

from math import ceil

from utils.geometry import Point, Rect, center, polar
from utils.spacing import space

from builder import SlideBuilder
from schema import ProcessSlide, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class ProcessTemplate(BaseTemplate):
    kind = "process"

    def render(self, b: SlideBuilder, c: ProcessSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title, c.subtitle)

        n = len(c.steps)
        if n <= 4:
            self._single_row(b, area, c.steps)
        else:
            self._two_rows(b, area, c.steps)
        b.notes(c.notes)

    # -- layout ----------------------------------------------------------
    @staticmethod
    def _row_slots(area: Rect, count: int, gap: float, label_h: float):
        """Equal-width slots across ``area`` leaving room for labels."""
        body = area.with_size(area.width, area.height - label_h)
        w = (body.width - gap * (count - 1)) / count
        return body, w

    def _single_row(self, b: SlideBuilder, area: Rect, steps: list) -> None:
        t = b.theme
        gap = space(2)
        label_h = 56.0
        body, w = self._row_slots(area, len(steps), gap, label_h)
        d = min(w * 0.72, body.height * 0.9)
        cx_list = [body.x + (w - d) / 2.0 + i * (w + gap) for i in range(len(steps))]
        cy = body.y + (body.height - d) / 2.0 + d / 2.0
        centers = [Point(x + d / 2.0, cy) for x in cx_list]
        self._draw_connectors(b, centers, t.spec.primary)
        for i, (step, cx) in enumerate(zip(steps, cx_list)):
            circle = Rect(cx, cy - d / 2.0, d, d)
            self._draw_step(b, circle, i, step, len(steps))

    def _two_rows(self, b: SlideBuilder, area: Rect, steps: list) -> None:
        t = b.theme
        n = len(steps)
        first = ceil(n / 2.0)
        gap = space(3)
        label_h = 44.0
        row_body = Rect(area.x, area.y, area.width, (area.height - gap) / 2.0)
        row2_y = row_body.bottom + gap
        row2 = Rect(area.x, row2_y, area.width, row_body.height)

        centers: list[Point] = []
        for ri, (row, count, rev) in enumerate([(row_body, first, False), (row2, n - first, True)]):
            if count == 0:
                continue
            body, w = self._row_slots(row, count, space(2), label_h)
            d = min(w * 0.8, body.height * 0.95)
            cy = body.y + (body.height - d) / 2.0 + d / 2.0
            xs = [body.x + (w - d) / 2.0 + i * (w + space(2)) for i in range(count)]
            if rev:
                xs = xs[::-1]
            for i, x in enumerate(xs):
                centers.append(Point(x + d / 2.0, cy))
                circle = Rect(x, cy - d / 2.0, d, d)
                idx = ri * first + i
                self._draw_step(b, circle, idx, steps[idx], n)
        self._draw_connectors(b, centers, t.spec.primary)

    # -- drawing ---------------------------------------------------------
    def _draw_step(self, b: SlideBuilder, circle: Rect, index: int, label: str, total: int) -> None:
        t = b.theme
        b.oval(circle, fill=t.surface, line=t.spec.primary, line_width=2.0,
               key=f"step_{index}")
        # number badge on the circle's top-right corner
        num_rect = Rect(circle.x + circle.width * 0.55, circle.y - circle.width * 0.05,
                        circle.width * 0.5, circle.width * 0.5)
        b.oval(num_rect, fill=t.spec.primary, key=f"step_{index}_badge")
        b.text(num_rect, str(index + 1), role="caption", size=12.0, color="#ffffff",
               bold=True, align=TextAlign.CENTER, anchor=VerticalAlign.MIDDLE, key=None)
        # step label beneath the circle
        b.text(Rect(circle.x - 20, circle.bottom + 6, circle.width + 40, 44),
               label, role="small", size=12.0, color=t.heading_color(),
               bold=True, align=TextAlign.CENTER, wrap=True, key=f"step_{index}_label")

    def _draw_connectors(self, b: SlideBuilder, centers: list, color: str) -> None:
        for a, c in zip(centers, centers[1:]):
            b.line(a.x, a.y, c.x, c.y, color=color, width=2.0, arrow=True,
                   key="connector")
