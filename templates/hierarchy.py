"""Hierarchy / org-chart slide template.

Builds a layered tree from :class:`HierarchyNode`.  Each level is laid out
on its own row; every level is horizontally centered so connectors between
levels never overlap nodes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from utils.geometry import Rect, center
from utils.spacing import space

from builder import SlideBuilder
from schema import HierarchyNode, HierarchySlide, TextAlign, VerticalAlign
from templates.base import BaseTemplate


class HierarchyTemplate(BaseTemplate):
    kind = "hierarchy"

    def render(self, b: SlideBuilder, c: HierarchySlide) -> None:
        t = b.theme
        area = b.header(c.kicker, c.title)

        levels: List[List[HierarchyNode]] = []
        self._collect_levels(c.root, levels, 0)
        depth = len(levels)

        row_h = min(64.0, (area.height - space(2) * (depth - 1)) / max(1, depth))
        rows = [Rect(area.x, area.y + i * (row_h + space(2)), area.width, row_h)
                for i in range(depth)]

        positions: Dict[int, List[Rect]] = {}
        for li, (nodes, row) in enumerate(zip(levels, rows)):
            gap = space(2)
            w = (row.width - gap * (len(nodes) - 1)) / len(nodes)
            node_w = min(w, 180.0)
            total = node_w * len(nodes) + gap * (len(nodes) - 1)
            start_x = row.x + (row.width - total) / 2.0
            rects = [Rect(start_x + i * (node_w + gap), row.y, node_w, row.height)
                     for i in range(len(nodes))]
            positions[li] = rects
            for i, node in enumerate(nodes):
                self._node(b, rects[i], node, li == 0)

        self._connectors(b, levels, positions)
        b.notes(c.notes)

    @staticmethod
    def _collect_levels(node: HierarchyNode, levels: List[List[HierarchyNode]], depth: int) -> None:
        while len(levels) <= depth:
            levels.append([])
        levels[depth].append(node)
        for child in node.children:
            HierarchyTemplate._collect_levels(child, levels, depth + 1)

    def _node(self, b: SlideBuilder, rect: Rect, node: HierarchyNode, is_root: bool) -> None:
        t = b.theme
        fill = t.spec.primary if is_root else t.surface
        text_color = "#ffffff" if is_root else t.heading_color()
        b.rect(rect, fill=fill, line=None if is_root else t.border,
               line_width=1.0, radius=t.radius, key=f"node_{node.name}")
        b.text(rect, node.name, role="small", size=11.5 if is_root else 11.0,
               color=text_color, bold=True, align=TextAlign.CENTER,
               anchor=VerticalAlign.MIDDLE, wrap=True, key=f"node_{node.name}_name")
        if node.role and rect.height > 40:
            role_rect = Rect(rect.x, rect.y + rect.height * 0.52, rect.width, rect.height * 0.4)
            b.text(role_rect, node.role, role="caption", size=9.0,
                   color=t.spec.muted if not is_root else "#e6ecf5",
                   align=TextAlign.CENTER, anchor=VerticalAlign.TOP, key=None)

    def _connectors(self, b: SlideBuilder, levels: List[List[HierarchyNode]],
                    positions: Dict[int, List[Rect]]) -> None:
        t = b.theme
        for li in range(len(levels) - 1):
            for ni, node in enumerate(levels[li]):
                rect = positions[li][ni]
                children = node.children
                if not children:
                    continue
                child_rects = [positions[li + 1][i] for i in range(len(levels[li + 1]))
                               if levels[li + 1][i] in children]
                if not child_rects:
                    continue
                start = (rect.center_x, rect.bottom)
                mid_y = rect.bottom + space(1)
                for cr in child_rects:
                    pts = [
                        start,
                        (start[0], mid_y),
                        (cr.center_x, mid_y),
                        (cr.center_x, cr.top),
                    ]
                    b.polyline(pts, color=t.border, width=1.0)
