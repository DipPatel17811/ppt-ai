"""Title slide template."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import TextAlign, TitleSlide
from templates.base import BaseTemplate


class TitleTemplate(BaseTemplate):
    kind = "title"
    full_bleed = True

    def render(self, b: SlideBuilder, c: TitleSlide) -> None:
        t = b.theme
        area = b.content_rect()
        b.background(t.spec.background)
        b.rect(Rect(0, 0, 12, b.height), fill=t.spec.primary, key="accent_band")

        y = area.y + 88
        if c.kicker:
            b.text(Rect(area.x, y, area.width, 18), c.kicker.upper(), role="kicker",
                   size=t.type_size("kicker"), color=t.spec.primary,
                   bold=True, letter_spacing=2.0, key="kicker")
            y += 26
        b.text(Rect(area.x, y, area.width, 92), c.title, role="display",
               size=t.type_size("display"), color=t.heading_color(), bold=True,
               align=TextAlign.LEFT,
               auto_fit=True, key="title")
        y += 100
        if c.subtitle:
            b.text(Rect(area.x, y, area.width, 24), c.subtitle, role="body",
                   size=t.type_size("h4"), color=t.spec.muted, key="subtitle")
            y += 34
        b.line(area.x, y, area.x + 120, y, color=t.spec.primary, width=3.0, key="rule")

        if c.tags:
            chips_y = y + space(3)
            x = area.x
            for i, tag in enumerate(c.tags[:5]):
                w = 24 + len(tag) * 7.5
                b.chip(Rect(x, chips_y, w, 24), tag,
                       fill=t.surface, color=t.spec.primary, bold=False, key=f"tag_{i}")
                x += w + space(1)

        bottom = area.bottom - space(2)
        left = area.x
        parts = []
        if c.presenter:
            parts.append(c.presenter)
        if c.date:
            parts.append(c.date)
        if parts:
            b.text(Rect(left, bottom, area.width, 16), "   ·   ".join(parts),
                   role="small", size=t.type_size("small"), color=t.spec.muted,
                   key="presenter")
        b.notes(c.notes)
