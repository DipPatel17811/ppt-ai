"""Hero slide template: full-bleed image with an overlay and headline."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import HeroSlide, ImageSpec
from templates.base import BaseTemplate


class HeroTemplate(BaseTemplate):
    kind = "hero"
    full_bleed = True

    def render(self, b: SlideBuilder, c: HeroSlide) -> None:
        t = b.theme
        area = b.content_rect()

        if c.image:
            b.image(self._full_rect(b), c.image, key="hero_image")
            b.rect(self._full_rect(b), fill=t.spec.foreground, alpha=0.58, key="hero_overlay")
        else:
            b.background(t.spec.primary)
            b.rect(Rect(0, b.height - 40, b.width, 40), fill=t.spec.foreground, alpha=0.25)

        text_color = "#ffffff"
        muted = "#d5dceb"
        y = area.y + 90
        if c.kicker:
            b.text(Rect(area.x, y, area.width, 18), c.kicker.upper(), role="kicker",
                   size=t.type_size("kicker"), color=t.spec.accent,
                   bold=True, letter_spacing=2.0, key="kicker")
            y += 26
        b.text(Rect(area.x, y, area.width, 110), c.title, role="display",
               size=t.type_size("display"), color=text_color, bold=True,
               auto_fit=True, key="title")
        y += 118
        if c.subtitle:
            b.text(Rect(area.x, y, area.width, 44), c.subtitle, role="body",
                   size=t.type_size("h4"), color=muted, line_spacing=1.3,
                   auto_fit=True, key="subtitle")
            y += 56
        if c.tags:
            x = area.x
            for i, tag in enumerate(c.tags[:5]):
                w = 24 + len(tag) * 7.5
                b.chip(Rect(x, y, w, 26), tag, fill=t.spec.accent,
                       color=t.readable_on(t.spec.accent), key=f"tag_{i}")
                x += w + space(1)
            y += 40
        if c.cta:
            w = 36 + len(c.cta) * 7.5
            b.chip(Rect(area.x, y, w, 32), c.cta, fill=t.spec.secondary,
                   color="#ffffff", bold=True, size=12.0, key="cta")
        b.notes(c.notes)

    @staticmethod
    def _full_rect(b: SlideBuilder) -> Rect:
        return Rect(0, 0, b.width, b.height)
