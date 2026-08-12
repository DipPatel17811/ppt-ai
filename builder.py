"""The ``SlideBuilder``: a high-level, themed drawing façade.

Templates never talk to ``python-pptx`` directly.  Instead they receive a
``SlideBuilder`` which:

* owns the current slide, the active :class:`Theme`, the compiler and the
  morph object-id bank;
* exposes semantic helpers (``header``, ``footer``, ``chip``, ``icon``,
  ``bullets``, ``chart``, ``image``, ...) that all resolve to *theme-aware*
  drawing calls;
* records every drawn shape under a semantic key so the renderer can attach
  stable morph names and semantic animations automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from config import MIN_FONT_SIZE, TYPE_SCALE
from schema import BulletItem, ChartSpec, ImageSpec, TextAlign, VerticalAlign
from theme import Theme
from utils import fonts as font_utils
from utils.geometry import Rect
from utils.spacing import Padding, space

from compiler import Compiler, ParaSpec, RunSpec
from icons import IconPrimitive, library as icon_library
from morph import ObjectIdBank


@dataclass
class Block:
    """A single paragraph for :meth:`SlideBuilder.text_block`."""

    text: str
    role: str = "body"
    size: Optional[float] = None
    color: Optional[str] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    align: TextAlign = TextAlign.LEFT
    space_after: float = 0.0
    space_before: float = 0.0
    line_spacing: Optional[float] = None
    letter_spacing: Optional[float] = None


class SlideBuilder:
    """Theme-aware drawing API handed to every template renderer."""

    def __init__(self, compiler: Compiler, theme: Theme, slide, page_number: int,
                 total_pages: int, object_ids: ObjectIdBank, size: Tuple[float, float],
                 margins: Padding) -> None:
        self.compiler = compiler
        self.theme = theme
        self.slide = slide
        self.page_number = page_number
        self.total_pages = total_pages
        self.object_ids = object_ids
        self.width, self.height = size
        self.margins = margins
        self.registered: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    @property
    def size_rect(self) -> Rect:
        return Rect(0, 0, self.width, self.height)

    def content_rect(self) -> Rect:
        return self.margins.apply(self.size_rect)

    # ------------------------------------------------------------------
    # Low-level primitives (all register morph-stable names + animation)
    # ------------------------------------------------------------------
    def _keyed(self, key: Optional[str], shape) -> object:
        if key is not None:
            shape.name = self.object_ids.name(key)
            try:
                self.registered[key] = shape.shape_id
            except Exception:
                pass
        return shape

    def rect(self, rect: Rect, *, fill: Optional[str] = None,
             line: Optional[str] = None, line_width: float = 0.75,
             radius: Optional[float] = None, alpha: float = 1.0,
             key: Optional[str] = None):
        return self._keyed(key, self.compiler.add_rect(self.slide, rect, fill, line,
                                                       line_width, radius, alpha))

    def oval(self, rect: Rect, *, fill: Optional[str] = None,
             line: Optional[str] = None, line_width: float = 0.75,
             alpha: float = 1.0, key: Optional[str] = None):
        return self._keyed(key, self.compiler.add_oval(self.slide, rect, fill, line,
                                                       line_width, alpha))

    def line(self, x1: float, y1: float, x2: float, y2: float, *,
             color: str, width: float = 1.5, dash: bool = False,
             arrow: bool = False, key: Optional[str] = None):
        return self._keyed(key, self.compiler.add_line(self.slide, x1, y1, x2, y2,
                                                       color, width, dash, arrow))

    def polygon(self, points: Sequence[Tuple[float, float]], *, fill: Optional[str] = None,
                line: Optional[str] = None, line_width: float = 1.0,
                key: Optional[str] = None):
        return self._keyed(key, self.compiler.add_freeform(self.slide, points, closed=True,
                                                           fill=fill, line=line,
                                                           line_width=line_width))

    def polyline(self, points: Sequence[Tuple[float, float]], *, color: str,
                 width: float = 1.5, key: Optional[str] = None):
        return self._keyed(key, self.compiler.add_freeform(self.slide, points, closed=False,
                                                           fill=None, line=color,
                                                           line_width=width))

    def text(self, rect: Rect, text: str, *, role: str = "body",
             size: Optional[float] = None, color: Optional[str] = None,
             bold: Optional[bool] = None, italic: Optional[bool] = None,
             font: Optional[str] = None, align: TextAlign = TextAlign.LEFT,
             anchor: VerticalAlign = VerticalAlign.TOP, wrap: bool = True,
             auto_fit: bool = False, line_spacing: Optional[float] = None,
             letter_spacing: Optional[float] = None, key: Optional[str] = None):
        size = size or TYPE_SCALE.get(role, 14.0)
        family = font or self.theme.body_font
        if auto_fit:
            size = font_utils.fit_font_size(text, family, max(1.0, rect.width - 8),
                                            max(1.0, rect.height - 8), size, MIN_FONT_SIZE)
        para = ParaSpec(
            runs=[RunSpec(text=text, font=family, size=size, color=color,
                          bold=bold, italic=italic, letter_spacing=letter_spacing)],
            align=align, line_spacing=line_spacing,
        )
        return self._keyed(key, self.compiler.add_textbox(self.slide, rect, [para], anchor=anchor, wrap=wrap))

    def text_block(self, rect: Rect, blocks: Sequence[Block], *,
                   anchor: VerticalAlign = VerticalAlign.TOP,
                   wrap: bool = True, auto_fit: bool = False,
                   key: Optional[str] = None):
        paras: List[ParaSpec] = []
        for b in blocks:
            size = b.size or TYPE_SCALE.get(b.role, 14.0)
            family = self.theme.heading_font if b.role in ("display", "h1", "h2", "h3", "h4", "kicker") else self.theme.body_font
            color = b.color or self.theme.spec.foreground
            paras.append(ParaSpec(
                runs=[RunSpec(text=b.text, font=family, size=size, color=color,
                              bold=b.bold, italic=b.italic, letter_spacing=b.letter_spacing)],
                align=b.align, space_after=b.space_after, space_before=b.space_before,
                line_spacing=b.line_spacing,
            ))
        if auto_fit:
            total = sum(len(p.runs[0].text) for p in paras)
            size = paras[0].runs[0].size or 14.0
            joined = "\n".join(p.runs[0].text for p in paras)
            size = font_utils.fit_font_size(joined, self.theme.body_font,
                                            max(1.0, rect.width - 8), max(1.0, rect.height - 8),
                                            size, MIN_FONT_SIZE)
            for p in paras:
                p.runs[0].size = size
        return self._keyed(key, self.compiler.add_textbox(self.slide, rect, paras, anchor=anchor, wrap=wrap))

    def bullets(self, rect: Rect, items: Sequence[BulletItem], *,
                size: Optional[float] = None, color: Optional[str] = None,
                bullet_color: Optional[str] = None, gap: float = space(1.5),
                icon_size: float = 14.0, key_prefix: Optional[str] = None,
                marker: str = "▪") -> List[object]:
        size = size or TYPE_SCALE["body"]
        paras: List[ParaSpec] = []
        shapes: List[object] = []
        line_h = size * 1.2
        for i, item in enumerate(items):
            style = item.style
            run_color = (style.color if style and style.color else None) or color or self.theme.spec.foreground
            paras.append(ParaSpec(
                runs=[RunSpec(text=item.text, font=self.theme.body_font, size=size,
                              color=run_color,
                              bold=(style.bold if style else None) or item.highlight,
                              italic=(style.italic if style else None))],
                align=TextAlign.LEFT,
                space_after=gap if i < len(items) - 1 else 0.0,
                line_spacing=1.2,
                bullet=not item.icon,
                bullet_char=marker,
                bullet_color=bullet_color or self.theme.spec.primary,
                bullet_size_pct=80.0,
            ))
            if item.icon:
                icon_rect = Rect(rect.x, rect.y + i * (line_h + gap), icon_size, icon_size)
                self.icon(icon_rect, item.icon, color=bullet_color or self.theme.spec.primary,
                          key=self._item_key(key_prefix, i, "icon"))
        if paras:
            shapes.append(self._keyed(key_prefix, self.compiler.add_textbox(
                self.slide, rect, paras, anchor=VerticalAlign.TOP, wrap=True)))
        return shapes

    def _item_key(self, prefix: Optional[str], index: int, suffix: str = "") -> str:
        base = f"{prefix}_{index}" if prefix else f"item_{index}"
        return f"{base}_{suffix}" if suffix else base

    def chip(self, rect: Rect, text: str, *, fill: Optional[str] = None,
             color: Optional[str] = None, bold: bool = True,
             size: Optional[float] = None, key: Optional[str] = None):
        fill = fill or self.theme.spec.primary
        color = color or self.theme.readable_on(fill)
        self.rect(rect, fill=fill, radius=min(rect.height / 2.0, self.theme.radius), key=key)
        return self.text(rect, text, role="caption", size=size or 11.0, color=color,
                         bold=bold, align=TextAlign.CENTER, anchor=VerticalAlign.MIDDLE,
                         wrap=False, key=None)

    def icon(self, rect: Rect, name: str, color: Optional[str] = None,
             stroke_width: Optional[float] = None, key: Optional[str] = None):
        color = color or self.theme.spec.primary
        icon = icon_library().resolve(name)
        primitives = icon.build(rect, color=color, stroke_width=stroke_width)
        for k, prim in enumerate(primitives):
            s = self._draw_primitive(prim)
            try:
                s.name = f"_icon_{k}"
            except Exception:
                pass
        if key is not None:
            # placeholder shape so the icon participates in morph/animation
            ph = self.rect(rect, fill=None, line=None, key=key)
            ph._placeholder = True  # type: ignore[attr-defined]
            return ph
        return None

    def _draw_primitive(self, prim: IconPrimitive) -> object:
        c = self.compiler
        if prim.kind == "ellipse":
            return c.add_oval(self.slide, prim.rect, fill=None if not prim.filled else "#000000", alpha=1.0)
        elif prim.kind in ("rect", "round_rect"):
            radius = prim.radius if prim.kind == "round_rect" else None
            return c.add_rect(self.slide, prim.rect, fill="#000000", radius=radius, alpha=1.0)
        elif prim.kind in ("polygon", "polyline"):
            pts = [(p.x, p.y) for p in prim.points]
            return c.add_freeform(self.slide, pts, closed=prim.kind == "polygon",
                                  fill="#000000" if prim.filled else None, line="#000000",
                                  line_width=max(0.5, prim.stroke_width or 1.0))
        elif prim.kind == "line":
            a, b = prim.points[0], prim.points[1]
            return c.add_line(self.slide, a.x, a.y, b.x, b.y, color="#000000", width=prim.stroke_width)
        return None

    def image(self, rect: Rect, spec: ImageSpec, key: Optional[str] = None):
        shape = self.compiler.add_picture(self.slide, rect, spec)
        if shape is None:
            return None
        return self._keyed(key, shape)

    def chart(self, rect: Rect, spec: ChartSpec, key: Optional[str] = None):
        chart = self.compiler.add_chart(self.slide, rect, spec)
        if key is not None:
            try:
                self.registered[key] = chart._chartSpace  # charts have no spid; use the graphic frame
            except Exception:
                pass
        return chart

    def group(self, rect: Rect, key: Optional[str] = None):
        group = self.compiler.add_group(self.slide, rect, rect.x, rect.y)
        return self._keyed(key, group)

    def register_key(self, key: str, spid: int) -> None:
        self.registered[key] = spid

    # ------------------------------------------------------------------
    # Composite helpers
    # ------------------------------------------------------------------
    def background(self, fill: Optional[str] = None, key: Optional[str] = None):
        return self.rect(self.size_rect, fill=fill or self.theme.spec.background, key=key)

    def header(self, kicker: Optional[str], title: str, subtitle: Optional[str] = None,
               *, content_top: Optional[float] = None) -> Rect:
        t = self.theme
        area = self.content_rect()
        y = area.y
        if kicker:
            self.text(Rect(area.x, y, area.width, 16), kicker.upper(), role="kicker",
                      size=t.type_size("kicker"), color=t.spec.primary,
                      bold=True, letter_spacing=1.5, align=TextAlign.LEFT,
                      anchor=VerticalAlign.TOP, key="kicker")
            y += 20
        self.text(Rect(area.x, y, area.width, 42), title, role="h1",
                  size=t.type_size("h1"), color=t.heading_color(),
                  bold=True, anchor=VerticalAlign.TOP, key="title")
        y += 46
        if subtitle:
            self.text(Rect(area.x, y, area.width, 18), subtitle, role="body",
                      size=t.type_size("small"), color=t.spec.muted,
                      anchor=VerticalAlign.TOP, key="subtitle")
            y += 24
        rule_y = y
        self.line(area.x, rule_y, area.right, rule_y, color=t.border, width=1.0, key="rule")
        top = content_top or (rule_y + space(2))
        return Rect(area.x, top, area.width, area.bottom - top)

    def group_builder(self, rect: Rect, key: Optional[str] = None) -> "SlideBuilder":
        """Create a group and return a sub-builder working in local coords."""
        group = self.compiler.add_group(self.slide, rect, rect.x, rect.y)
        self._keyed(key, group)
        sub = SlideBuilder(self.compiler, self.theme, group, self.page_number,
                           self.total_pages, self.object_ids,
                           (rect.width, rect.height), Padding.all(0))
        return sub

    def footer(self, footer_text: Optional[str] = None) -> None:
        t = self.theme
        y = self.height - 22
        self.line(self.margins.left, y, self.width - self.margins.left, y,
                  color=t.border, width=1.0)
        self.text(Rect(self.margins.left, y + 4, 400, 14), footer_text or t.footer_text,
                  role="caption", size=t.type_size("caption"), color=t.spec.muted,
                  align=TextAlign.LEFT, key="footer")
        self.text(Rect(self.width - self.margins.left - 80, y + 4, 80, 14),
                  f"{self.page_number} / {self.total_pages}", role="caption",
                  size=t.type_size("caption"), color=t.spec.muted,
                  align=TextAlign.RIGHT, key="pagenum")

    def notes(self, text: Optional[str]) -> None:
        self.compiler.set_notes(self.slide, text)
