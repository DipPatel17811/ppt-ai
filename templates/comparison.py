"""Comparison slide template (two columns + bottom line)."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import BulletItem, ComparisonSlide, VerticalAlign
from templates.base import BaseTemplate


class ComparisonTemplate(BaseTemplate):
    kind = "comparison"

    def render(self, b: SlideBuilder, c: ComparisonSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title)
        y = area.y
        if c.context:
            b.text(Rect(area.x, y, area.width, 24), c.context, role="body",
                   size=t.type_size("small"), color=t.spec.muted, key="context")
            y += 30

        content_bottom = area.bottom
        if c.bottom_line:
            content_bottom = area.bottom - 46

        body = Rect(area.x, y, area.width, content_bottom - y)
        left, right = self._columns(body)

        self._column(b, left, c.left, t.spec.primary, key="col_left")
        self._column(b, right, c.right, t.spec.secondary, key="col_right")

        if c.bottom_line:
            bl_y = content_bottom + 6
            b.rect(Rect(body.x, bl_y, body.width, 34), fill=t.surface,
                   line=t.border, line_width=0.75, radius=t.radius, key="bottom_line")
            b.text(Rect(body.x + space(2), bl_y, body.width - space(4), 34),
                   "▍ " + c.bottom_line, role="body", size=t.type_size("small"),
                   color=t.spec.foreground, bold=True, anchor=VerticalAlign.MIDDLE,
                   key=None)
        b.notes(c.notes)

    @staticmethod
    def _columns(body: Rect):
        gap = space(3)
        w = (body.width - gap) / 2.0
        return (Rect(body.x, body.y, w, body.height), Rect(body.x + w + gap, body.y, w, body.height))

    def _column(self, b: SlideBuilder, rect: Rect, col, accent: str, key: str):
        t = b.theme
        header_h = 64
        b.rect(Rect(rect.x, rect.y, rect.width, header_h), fill=accent, radius=t.radius, key=key)
        if col.icon:
            b.icon(Rect(rect.x + space(2), rect.y + space(1.5), 28, 28),
                   col.icon, color="#ffffff")
        b.text(Rect(rect.x + space(4.5) if col.icon else rect.x + space(2), rect.y, rect.width - space(4),
                    header_h), col.heading, role="h3", size=t.type_size("h3"),
               color="#ffffff", bold=True, anchor=VerticalAlign.MIDDLE, wrap=True, key=None)
        if col.subheading:
            b.text(Rect(rect.x + space(2), rect.y + header_h, rect.width - space(4), 20),
                   col.subheading, role="caption", size=t.type_size("caption"),
                   color=t.spec.muted, key=None)
        items = [BulletItem(text=p) for p in col.points[:6]]
        list_rect = Rect(rect.x + space(1.5), rect.y + header_h + 26,
                         rect.width - space(3), rect.height - header_h - 26)
        b.bullets(list_rect, items, size=t.type_size("small"), gap=space(1.5),
                  bullet_color=accent, key_prefix=f"{key}_bullets")
        return rect
