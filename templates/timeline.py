"""Timeline slide template (horizontal, or vertical for many items)."""

from __future__ import annotations

from math import ceil

from utils.geometry import Point, Rect, center
from utils.spacing import space

from builder import SlideBuilder
from schema import TimelineItem, TimelineSlide, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class TimelineTemplate(BaseTemplate):
    kind = "timeline"

    def render(self, b: SlideBuilder, c: TimelineSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title, c.kicker and None)
        items = c.items[:8]
        if len(items) <= 6:
            self._horizontal(b, area, items)
        else:
            self._vertical(b, area, items)
        b.notes(c.notes)

    def _horizontal(self, b: SlideBuilder, area: Rect, items: list) -> None:
        t = b.theme
        n = len(items)
        line_y = area.y + area.height * 0.42
        step = area.width / n
        node_r = 7.0

        b.line(area.x, line_y, area.right, line_y, color=t.border, width=2.0, key="line")

        for i, item in enumerate(items):
            cx = area.x + step * (i + 0.5)
            # node
            b.oval(Rect(cx - node_r, line_y - node_r, node_r * 2, node_r * 2),
                   fill=t.spec.primary, key=f"item_{i}_node")
            # connector tick
            b.line(cx, line_y, cx, line_y + 14, color=t.spec.primary, width=2.0)
            # label (above line)
            label = item.label or ""
            if label:
                b.text(Rect(cx - step * 0.4, line_y - 34, step * 0.8, 18), label,
                       role="caption", size=t.type_size("small"), color=t.spec.primary,
                       bold=True, align=TextAlign.CENTER, key=f"item_{i}_label")
            # title + detail (below line)
            b.text(Rect(cx - step * 0.45, line_y + 20, step * 0.9, 24), item.title,
                   role="small", size=t.type_size("small"), color=t.heading_color(),
                   bold=True, align=TextAlign.CENTER, wrap=True, key=f"item_{i}")
            if item.detail:
                b.text(Rect(cx - step * 0.45, line_y + 44, step * 0.9, 20), item.detail,
                       role="caption", size=t.type_size("caption"), color=t.spec.muted,
                       align=TextAlign.CENTER, wrap=True, key=f"item_{i}_detail")

    def _vertical(self, b: SlideBuilder, area: Rect, items: list) -> None:
        t = b.theme
        line_x = area.x + 18
        gap = space(2)
        n = len(items)
        rows = _split_rows(area, n, gap)
        b.line(line_x, rows[0].y, line_x, rows[-1].y, color=t.border, width=2.0, key="line")

        for i, (item, row) in enumerate(zip(items, rows)):
            b.oval(Rect(line_x - 6, row.y + row.height / 2.0 - 6, 12, 12),
                   fill=t.spec.primary, key=f"item_{i}_node")
            body = Rect(line_x + 22, row.y, area.right - line_x - 22, row.height)
            label = item.label or f"Phase {i + 1}"
            b.text(Rect(body.x, row.y, body.width, 18), label, role="caption",
                   size=t.type_size("small"), color=t.spec.primary, bold=True, key=f"item_{i}_label")
            b.text(Rect(body.x, row.y + 20, body.width, row.height - 20), item.title,
                   role="body", size=t.type_size("body"), color=t.heading_color(),
                   bold=True, wrap=True, key=f"item_{i}")
            if item.detail:
                b.text(Rect(body.x, row.y + 20, body.width, row.height - 20),
                       item.detail, role="small", size=t.type_size("small"),
                       color=t.spec.muted, wrap=True, key=None)


def _split_rows(area: Rect, n: int, gap: float):
    rows = []
    total_gap = gap * (n - 1)
    h = (area.height - total_gap) / n
    for i in range(n):
        rows.append(Rect(area.x, area.y + i * (h + gap), area.width, h))
    return rows
