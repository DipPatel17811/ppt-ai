"""Roadmap slide template (phases with status + arrow flow)."""

from __future__ import annotations

from utils.geometry import Rect
from utils.spacing import space

from builder import SlideBuilder
from schema import PhaseStatus, RoadmapSlide
from templates.base import BaseTemplate

_STATUS_COLOR = {
    PhaseStatus.DONE: None,     # filled with success at render time
    PhaseStatus.CURRENT: None,
    PhaseStatus.NEXT: None,
    PhaseStatus.PLANNED: None,
}

_STATUS_LABEL = {
    PhaseStatus.DONE: "Done",
    PhaseStatus.CURRENT: "Now",
    PhaseStatus.NEXT: "Next",
    PhaseStatus.PLANNED: "Planned",
}


class RoadmapTemplate(BaseTemplate):
    kind = "roadmap"

    def render(self, b: SlideBuilder, c: RoadmapSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title, c.intro)
        n = len(c.phases)

        phase_body = Rect(area.x, area.y, area.width, area.height)
        gap = space(2)
        w = (phase_body.width - gap * (n - 1)) / n

        for i, phase in enumerate(c.phases):
            x = phase_body.x + i * (w + gap)
            rect = Rect(x, phase_body.y, w, phase_body.height)
            self._phase(b, rect, phase, i)
            if i < n - 1:
                arrow_x = rect.right + gap / 2.0
                y = phase_body.y + 70
                b.line(arrow_x - 4, y, arrow_x + 4, y, color=t.border, width=1.5,
                       arrow=True)
        b.notes(c.notes)

    def _phase(self, b: SlideBuilder, rect: Rect, phase, index: int) -> None:
        t = b.theme
        status = phase.status or PhaseStatus.PLANNED
        color = {
            PhaseStatus.DONE: t.spec.success,
            PhaseStatus.CURRENT: t.spec.accent,
            PhaseStatus.NEXT: t.spec.secondary,
            PhaseStatus.PLANNED: t.spec.muted,
        }[status]

        b.rect(rect, fill=t.surface, line=t.border, line_width=1.0,
               radius=t.radius, key=f"phase_{index}")

        # header band: status chip + period
        chip_rect = Rect(rect.x + space(1.5), rect.y + space(1.5), 74, 22)
        b.chip(chip_rect, _STATUS_LABEL[status], fill=color, color="#ffffff",
               size=9.5, bold=True, key=f"phase_{index}_status")

        period = phase.period or ""
        if period:
            b.text(Rect(rect.x + space(1.5), chip_rect.bottom + 6, rect.width - space(3), 16),
                   period, role="caption", size=10.5, color=t.spec.muted,
                   bold=True, key=f"phase_{index}_period")

        name_y = (chip_rect.bottom + 26) if period else (chip_rect.bottom + 12)
        b.text(Rect(rect.x + space(1.5), name_y, rect.width - space(3), 22),
               phase.name, role="h4", size=t.type_size("h4"), color=t.heading_color(),
               bold=True, key=f"phase_{index}_name")

        items_y = name_y + 30
        items_rect = Rect(rect.x + space(2), items_y, rect.width - space(4),
                          rect.bottom - items_y - space(1.5))
        from schema import BulletItem
        bullets = [BulletItem(text=p) for p in phase.items[:4]]
        b.bullets(items_rect, bullets, size=10.5, gap=space(1.5),
                  bullet_color=color, key_prefix=f"phase_{index}_items")
