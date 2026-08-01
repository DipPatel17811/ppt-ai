"""Conclusion slide template: key takeaways + CTA."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import ConclusionSlide, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class ConclusionTemplate(BaseTemplate):
    kind = "conclusion"

    def render(self, b: SlideBuilder, c: ConclusionSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title)

        cta_w = 0
        if c.cta:
            cta_w = 36 + len(c.cta) * 7.5
            b.chip(Rect(area.right - cta_w, area.y, cta_w, 30),
                   c.cta, fill=t.spec.accent, color=t.readable_on(t.spec.accent),
                   bold=True, size=12.0, key="cta")

        quote_h = 46 if c.quote else 0
        rows_area = Rect(area.x, area.y, area.width, area.height - quote_h)
        takeaways = c.takeaways[:6]
        rows = _rows(rows_area, len(takeaways), space(1.5))

        for i, (takeaway, row) in enumerate(zip(takeaways, rows)):
            num_w = 40
            b.rect(Rect(row.x, row.y + 2, 34, 34), fill=t.spec.primary, radius=8,
                   key=f"takeaway_{i}")
            b.text(Rect(row.x, row.y + 2, 34, 34), str(i + 1), role="caption",
                   size=14.0, color="#ffffff", bold=True, align=TextAlign.CENTER,
                   anchor=VerticalAlign.MIDDLE, key=None)
            text_w = row.width - num_w
            if c.cta and i == 0:
                text_w = row.width - num_w - cta_w - space(1)
            b.text(Rect(row.x + num_w, row.y, text_w, row.height),
                   takeaway, role="h4", size=t.type_size("h4"), color=t.heading_color(),
                   bold=False, anchor=VerticalAlign.MIDDLE, wrap=True,
                   key=f"takeaway_{i}_text")

        if c.quote:
            b.text(Rect(area.x, area.bottom - 40, area.width, 36), "“" + c.quote + "”",
                   role="body", size=t.type_size("h4"), color=t.spec.muted,
                   italic=True, align=TextAlign.LEFT, wrap=True, key="quote")
        b.notes(c.notes)


def _rows(area: Rect, n: int, gap: float):
    rows = []
    total_gap = gap * (n - 1)
    h = (area.height - total_gap) / n
    for i in range(n):
        rows.append(Rect(area.x, area.y + i * (h + gap), area.width, h))
    return rows
