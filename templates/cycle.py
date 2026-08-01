"""Cycle slide template: stages on a ring with a center label."""

from __future__ import annotations

import math

from utils.geometry import Point, Rect, polar
from utils.spacing import space

from builder import SlideBuilder
from schema import CycleSlide, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class CycleTemplate(BaseTemplate):
    kind = "cycle"

    def render(self, b: SlideBuilder, c: CycleSlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title)

        n = len(c.stages)
        center_x = area.center_x
        center_y = area.center_y
        node_d = 34.0
        ring_radius = min(area.width, area.height) * 0.30
        text_radius = ring_radius + node_d / 2.0 + 14.0

        # faint ring
        ring = Rect(center_x - ring_radius - node_d / 2.0,
                    center_y - ring_radius - node_d / 2.0,
                    (ring_radius + node_d / 2.0) * 2, (ring_radius + node_d / 2.0) * 2)
        b.oval(ring, fill=None, line=t.border, line_width=1.5, key="ring")

        for i, stage in enumerate(c.stages):
            angle = 360.0 / n * i
            pos = polar(center_x, center_y, ring_radius, angle)
            # connector spoke
            b.line(center_x, center_y, pos.x, pos.y, color=t.border, width=1.5)
            # node
            node = Rect(pos.x - node_d / 2.0, pos.y - node_d / 2.0, node_d, node_d)
            b.oval(node, fill=t.spec.primary, key=f"stage_{i}")
            b.text(node, str(i + 1), role="caption", size=12.0, color="#ffffff",
                   bold=True, align=TextAlign.CENTER, anchor=VerticalAlign.MIDDLE,
                   key=None)
            # label just outside the ring
            tp = polar(center_x, center_y, text_radius, angle)
            self._label(b, tp, stage, angle, i)

        # center label
        center_d = 84.0
        center_rect = Rect(center_x - center_d / 2.0, center_y - center_d / 2.0,
                           center_d, center_d)
        b.oval(center_rect, fill=t.surface, line=t.spec.primary, line_width=2.0,
               key="center")
        label = c.center_label or "Cycle"
        b.text(center_rect, label, role="small", size=12.0,
               color=t.readable_on(t.surface), bold=True, align=TextAlign.CENTER,
               anchor=VerticalAlign.MIDDLE, wrap=True, key="center_label")
        b.notes(c.notes)

    @staticmethod
    def _label(b: SlideBuilder, anchor_pt: Point, text: str, angle: float, i: int) -> None:
        """Place a label anchored just outside the ring, oriented outward."""
        w, h = 120.0, 40.0
        # figure which quadrant the anchor is in to pick box placement
        deg = angle % 360.0
        if 315 <= deg or deg < 45:        # top
            x, y = anchor_pt.x - w / 2.0, anchor_pt.y - h - 10
        elif 45 <= deg < 135:             # right
            x, y = anchor_pt.x + 8, anchor_pt.y - h / 2.0
        elif 135 <= deg < 225:            # bottom
            x, y = anchor_pt.x - w / 2.0, anchor_pt.y + 8
        else:                             # left
            x, y = anchor_pt.x - w - 8, anchor_pt.y - h / 2.0
        rect = Rect(x, y, w, h)
        b.text(rect, text, role="small", size=11.0,
               color=b.theme.heading_color(), bold=True, align=TextAlign.CENTER,
               anchor=VerticalAlign.MIDDLE, wrap=True, key=f"stage_{i}_label")
