"""Agenda / table-of-contents template."""

from __future__ import annotations

from layout import equal_rows
from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import AgendaSlide, VerticalAlign
from templates.base import BaseTemplate


class AgendaTemplate(BaseTemplate):
    kind = "agenda"

    def render(self, b: SlideBuilder, c: AgendaSlide) -> None:
        t = b.theme
        area = b.header(c.kicker or "Agenda", c.title)

        items = c.items[:8]
        rows = equal_rows(area, len(items), space(1.5))
        num_w = 56
        for i, (row, item) in enumerate(zip(rows, items)):
            b.text(Rect(row.x, row.y + 2, num_w, row.height), f"{i + 1:02d}",
                   role="h2", size=t.type_size("h3"), color=t.spec.primary,
                   bold=True, key=f"num_{i}")
            b.line(row.x + num_w + space(1), row.y + 4,
                   row.x + num_w + space(1), row.bottom - 4,
                   color=t.border, width=1.0)
            b.text(Rect(row.x + num_w + space(2), row.y, row.width - num_w - space(2), row.height),
                   item, role="h4", size=t.type_size("h4"), color=t.heading_color(),
                   bold=False, anchor=VerticalAlign.MIDDLE,
                   key=f"item_{i}")
        b.notes(c.notes)
