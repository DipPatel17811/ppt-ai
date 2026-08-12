"""Dashboard slide template: KPI cards + chart + optional commentary."""

from __future__ import annotations

from math import ceil

from layout import grid
from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import DashboardSlide, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class DashboardTemplate(BaseTemplate):
    kind = "dashboard"

    def render(self, b: SlideBuilder, c: DashboardSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title, c.subtitle)

        metrics = c.metrics[:6]
        if not metrics:
            b.notes(c.notes)
            return
        cols = 3 if len(metrics) >= 3 else max(1, len(metrics))
        rows = ceil(len(metrics) / cols)
        card_gap = space(2)
        cards_area = Rect(area.x, area.y, area.width, rows * 86 + (rows - 1) * card_gap)
        cells = grid(cards_area, rows, cols, card_gap, card_gap)

        for i, (metric, cell) in enumerate(zip(metrics, [c for row in cells for c in row])):
            self._metric_card(b, cell, metric, i)

        body_y = cards_area.bottom + space(2)
        body_h = area.bottom - body_y
        has_bullets = bool(c.bullets)
        if c.chart:
            chart_rect = Rect(area.x, body_y, area.width * (0.62 if has_bullets else 1.0), body_h)
            b.chart(chart_rect, c.chart, key="chart")
        if has_bullets:
            bullets_rect = Rect(area.x + area.width * 0.66, body_y, area.width * 0.34, body_h)
            b.bullets(bullets_rect, c.bullets, size=11.0, gap=space(1.5),
                      key_prefix="dash_bullets")
        b.notes(c.notes)

    def _metric_card(self, b: SlideBuilder, rect: Rect, metric, index: int) -> None:
        t = b.theme
        b.rect(rect, fill=t.surface, line=t.border, line_width=1.0,
               radius=t.radius, key=f"metric_{index}")

        pad = space(1.5)
        label_rect = Rect(rect.x + pad, rect.y + pad, rect.width - pad * 2, 18)
        b.text(label_rect, metric.label.upper(), role="caption", size=9.5,
               color=t.spec.muted, bold=True, letter_spacing=0.5,
               align=TextAlign.LEFT, key=f"metric_{index}_label")

        value_rect = Rect(rect.x + pad, rect.y + pad + 22, rect.width - pad * 2, 30)
        b.text(value_rect, metric.value, role="h2", size=t.type_size("h2"),
               color=t.heading_color(), bold=True, align=TextAlign.LEFT,
               anchor=VerticalAlign.MIDDLE, key=f"metric_{index}_value")

        if metric.delta:
            up = metric.delta_good
            arrow = "▲" if up else "▼"
            dcolor = t.spec.success if up else t.spec.danger
            delta_rect = Rect(rect.x + pad, rect.bottom - 24, rect.width - pad * 2, 18)
            b.text(delta_rect, f"{arrow} {metric.delta}", role="caption", size=10.0,
                   color=dcolor, bold=True, key=f"metric_{index}_delta")
