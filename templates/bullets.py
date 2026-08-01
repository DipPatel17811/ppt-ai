"""Bullets slide template (icon bullets + optional right panel)."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import BulletsSlide
from templates.base import BaseTemplate


class BulletsTemplate(BaseTemplate):
    kind = "bullets"

    def render(self, b: SlideBuilder, c: BulletsSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title)
        y = area.y
        if c.intro:
            b.text(Rect(area.x, y, area.width, 26), c.intro, role="body",
                   size=t.type_size("body"), color=t.spec.muted, key="intro")
            y += 34

        has_panel = bool(c.image or c.chart)
        bullets_rect = Rect(area.x, y, area.width, area.bottom - y)
        panel_rect = None
        if has_panel:
            left_w = area.width * 0.55 if c.chart else area.width * 0.58
            bullets_rect = Rect(area.x, y, left_w, area.bottom - y)
            panel_rect = Rect(area.x + left_w + space(3), y,
                              area.width - left_w - space(3), area.bottom - y)

        b.bullets(bullets_rect, c.bullets, key_prefix="bullets",
                  bullet_color=t.spec.primary)

        if panel_rect is not None:
            if c.chart:
                b.chart(panel_rect, c.chart, key="chart")
            elif c.image:
                b.image(panel_rect, c.image, key="image")
        b.notes(c.notes)
