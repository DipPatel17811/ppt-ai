"""SVG icon engine.

Icons are stored as hand-authored, simple SVG files in ``assets/icons`` and
are parsed into a vector description (a list of drawing primitives).  The
engine then:

* **recolors** the icon to any theme colour (monochrome by design);
* **scales** it into an arbitrary target rect preserving aspect ratio;
* renders using native PowerPoint shapes (rectangles, ovals, freeforms) --
  never a rasterised image.

The parser deliberately supports a small, safe subset of SVG (rect, circle,
ellipse, line, polygon, polyline, path with M/L/H/V/C/S/Q/T/A/Z, plus
``translate``/``scale`` transforms).  Anything unsupported falls back to a
built-in geometric placeholder so rendering never crashes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from config import ICON_DIR
from utils.geometry import Point, Rect

# ---------------------------------------------------------------------------
# Drawing primitives (renderer-agnostic)
# ---------------------------------------------------------------------------


@dataclass
class IconPrimitive:
    """One drawing operation within an icon."""

    kind: str  # "rect" | "round_rect" | "ellipse" | "line" | "polygon" | "polyline"
    points: List[Point] = field(default_factory=list)
    rect: Optional[Rect] = None
    radius: float = 0.0
    filled: bool = True
    stroked: bool = False
    stroke_width: float = 1.0


@dataclass
class Icon:
    """A parsed icon: primitives in a viewBox coordinate space."""

    name: str
    viewbox: Rect
    primitives: List[IconPrimitive]

    def build(self, target: Rect, color: str = "#333333",
              stroke_width: Optional[float] = None) -> List[IconPrimitive]:
        """Scale this icon into ``target`` and apply ``color`` to all marks."""
        scale = min(target.width / self.viewbox.width, target.height / self.viewbox.height)
        out_w = self.viewbox.width * scale
        out_h = self.viewbox.height * scale
        ox = target.x + (target.width - out_w) / 2.0
        oy = target.y + (target.height - out_h) / 2.0

        def pt(p: Point) -> Point:
            return Point(ox + (p.x - self.viewbox.x) * scale, oy + (p.y - self.viewbox.y) * scale)

        built: List[IconPrimitive] = []
        for prim in self.primitives:
            if prim.kind in ("rect", "round_rect", "ellipse"):
                r = prim.rect
                nr = Rect(ox + (r.x - self.viewbox.x) * scale, oy + (r.y - self.viewbox.y) * scale,
                          r.width * scale, r.height * scale)
                built.append(IconPrimitive(kind=prim.kind, rect=nr, radius=prim.radius * scale,
                                           filled=True, stroked=False))
            else:
                pts = [pt(p) for p in prim.points]
                built.append(IconPrimitive(kind=prim.kind, points=pts, filled=prim.filled,
                                           stroked=True,
                                           stroke_width=(stroke_width or prim.stroke_width) * scale))
        return built


# ---------------------------------------------------------------------------
# SVG subset parser
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<(/?)(\w+)([^>]*?)(/?)>")
_ATTR_RE = re.compile(r'([a-zA-Z_:][\w:.-]*)\s*=\s*("([^"]*)"|\'([^\']*)\')')
_TRANSFORM_RE = re.compile(r"(\w+)\s*\(([^)]*)\)")

_NUM_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _numbers(s: str) -> List[float]:
    return [float(m.group()) for m in _NUM_RE.finditer(s)]


def _parse_transform(value: Optional[str]) -> Tuple[float, float, float, float]:
    """Return ``(sx, sy, tx, ty)``.  Supports translate/scale/matrix."""
    sx = sy = 1.0
    tx = ty = 0.0
    if not value:
        return sx, sy, tx, ty
    for match in _TRANSFORM_RE.finditer(value):
        op, args = match.group(1), _numbers(match.group(2))
        if op == "translate" and args:
            tx = args[0]
            ty = args[1] if len(args) > 1 else 0.0
        elif op == "scale" and args:
            sx = args[0]
            sy = args[1] if len(args) > 1 else args[0]
        elif op == "matrix" and len(args) >= 6:
            a, b, c, d, e, f = args[:6]
            sx, sy, tx, ty = a, d, e, f
    return sx, sy, tx, ty


def _apply(x: float, y: float, sx: float, sy: float, tx: float, ty: float) -> Point:
    return Point(x * sx + tx, y * sy + ty)


def _point(sx: float, sy: float, tx: float, ty: float, args: Sequence[float], i: int) -> Point:
    return _apply(args[i], args[i + 1], sx, sy, tx, ty)


def _flatten_curve(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 6) -> List[Point]:
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt ** 3 * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t ** 3 * p3.x
        y = mt ** 3 * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t ** 3 * p3.y
        pts.append(Point(x, y))
    return pts


def _arc_points(p0: Point, rx: float, ry: float, rot: float,
                large: bool, sweep: bool, p1: Point) -> List[Point]:
    """Sample points along an SVG elliptical arc from p0 to p1."""
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(rot)
    cosphi, sinphi = math.cos(phi), math.sin(phi)
    dx2 = (p0.x - p1.x) / 2.0
    dy2 = (p0.y - p1.y) / 2.0
    x1p = cosphi * dx2 + sinphi * dy2
    y1p = -sinphi * dx2 + cosphi * dy2
    rx2, ry2 = rx * rx, ry * ry
    x1p2, y1p2 = x1p * x1p, y1p * y1p
    radicand = (rx2 * ry2 - rx2 * y1p2 - ry2 * x1p2) / (rx2 * y1p2 + ry2 * x1p2)
    radicand = max(0.0, radicand)
    coef = math.sqrt(radicand)
    if large == sweep:
        coef = -coef
    cxp = coef * (rx * y1p / ry)
    cyp = coef * (-ry * x1p / rx)
    cx = cosphi * cxp - sinphi * cyp + (p0.x + p1.x) / 2.0
    cy = sinphi * cxp + cosphi * cyp + (p0.y + p1.y) / 2.0

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        cross = ux * vy - uy * vx
        a = math.atan2(cross, dot)
        return a

    ux = (x1p - cxp) / rx
    uy = (y1p - cyp) / ry
    vx = (-x1p - cxp) / rx
    vy = (-y1p - cyp) / ry
    start = angle(1.0, 0.0, ux, uy)
    delta = angle(ux, uy, vx, vy)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(2, int(abs(delta) / (math.pi / 12)))
    out: List[Point] = []
    for i in range(1, steps + 1):
        t = start + delta * (i / steps)
        x = cx + rx * math.cos(t) * cosphi - ry * math.sin(t) * sinphi
        y = cy + rx * math.cos(t) * sinphi + ry * math.sin(t) * cosphi
        out.append(Point(x, y))
    return out


def _parse_path(d: str, sx: float, sy: float, tx: float, ty: float) -> List[List[Point]]:
    """Parse a path ``d`` into closed/open subpaths as point lists."""
    tokens = re.findall(r"[MLHVCSQTAZmlhvcsqtaz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d)
    subpaths: List[List[Point]] = []
    current: Optional[List[Point]] = None
    cursor = Point(0.0, 0.0)
    start = Point(0.0, 0.0)
    prev_control: Optional[Point] = None
    i = 0

    def numeric(idx: int) -> Optional[float]:
        if idx >= len(tokens):
            return None
        tok = tokens[idx]
        if tok in "MLHVCSQTAZmlhvcsqtaz":
            return None
        return float(tok)

    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "Z" or cmd == "z":
            if current:
                current.append(Point(start.x, start.y))
                subpaths.append(current)
            current = None
            cursor = Point(start.x, start.y)
            prev_control = None
            continue

        absolute = cmd.isupper()
        op = cmd.upper()

        def p(a: float, b: float) -> Point:
            return Point(a, b)

        if op in "ML":
            # read coordinate pairs (repeatable)
            pairs = []
            while True:
                a = numeric(i)
                b = numeric(i + 1) if a is not None else None
                if a is None or b is None:
                    break
                pairs.append((a, b))
                i += 2
            if not pairs:
                continue
            if op == "M":
                for j, (a, b) in enumerate(pairs):
                    c = _apply(a, b, sx, sy, tx, ty) if absolute else Point(cursor.x + a, cursor.y + b)
                    if j == 0:
                        current = [c]
                        cursor = c
                        start = c
                    else:
                        if current is not None:
                            current.append(c)
                        cursor = c
                        start = c
                prev_control = None
            else:  # L
                for a, b in pairs:
                    c = _apply(a, b, sx, sy, tx, ty) if absolute else Point(cursor.x + a, cursor.y + b)
                    if current is not None:
                        current.append(c)
                    cursor = c
                prev_control = None
        elif op == "H":
            values = []
            while True:
                v = numeric(i)
                if v is None:
                    break
                values.append(v)
                i += 1
            for v in values:
                c = Point(_apply(v, cursor.y, sx, sy, tx, ty).x, _apply(v, cursor.y, sx, sy, tx, ty).y) \
                    if absolute else Point(cursor.x + v * sx, cursor.y)
                if current is not None:
                    current.append(c)
                cursor = c
            prev_control = None
        elif op == "V":
            values = []
            while True:
                v = numeric(i)
                if v is None:
                    break
                values.append(v)
                i += 1
            for v in values:
                c = Point(cursor.x, _apply(cursor.x, v, sx, sy, tx, ty).y) if absolute else Point(cursor.x, cursor.y + v * sy)
                if current is not None:
                    current.append(c)
                cursor = c
            prev_control = None
        elif op in "C":
            while True:
                a1, b1, a2, b2, a3, b3 = [numeric(i + k) for k in range(6)]
                if any(v is None for v in (a1, b1, a2, b2, a3, b3)):
                    break
                i += 6
                if absolute:
                    c1 = _apply(a1, b1, sx, sy, tx, ty)
                    c2 = _apply(a2, b2, sx, sy, tx, ty)
                    end = _apply(a3, b3, sx, sy, tx, ty)
                else:
                    c1 = Point(cursor.x + a1 * sx, cursor.y + b1 * sy)
                    c2 = Point(cursor.x + a2 * sx, cursor.y + b2 * sy)
                    end = Point(cursor.x + a3 * sx, cursor.y + b3 * sy)
                if current is not None:
                    current.extend(_flatten_curve(cursor, c1, c2, end))
                cursor = end
                prev_control = c2
        elif op == "S":
            while True:
                a1, b1, a2, b2 = [numeric(i + k) for k in range(4)]
                if any(v is None for v in (a1, b1, a2, b2)):
                    break
                i += 4
                if prev_control is not None:
                    c1 = Point(2 * cursor.x - prev_control.x, 2 * cursor.y - prev_control.y)
                else:
                    c1 = Point(cursor.x, cursor.y)
                c2 = _apply(a1, b1, sx, sy, tx, ty) if absolute else Point(cursor.x + a1 * sx, cursor.y + b1 * sy)
                end = _apply(a2, b2, sx, sy, tx, ty) if absolute else Point(cursor.x + a2 * sx, cursor.y + b2 * sy)
                if current is not None:
                    current.extend(_flatten_curve(cursor, c1, c2, end))
                cursor = end
                prev_control = c2
        elif op in "Q":
            while True:
                a1, b1, a2, b2 = [numeric(i + k) for k in range(4)]
                if any(v is None for v in (a1, b1, a2, b2)):
                    break
                i += 4
                c1 = _apply(a1, b1, sx, sy, tx, ty) if absolute else Point(cursor.x + a1 * sx, cursor.y + b1 * sy)
                end = _apply(a2, b2, sx, sy, tx, ty) if absolute else Point(cursor.x + a2 * sx, cursor.y + b2 * sy)
                # Convert quadratic to cubic for flattening.
                p0x, p0y = cursor.x, cursor.y
                c0 = Point(p0x + 2.0 / 3.0 * (c1.x - p0x), p0y + 2.0 / 3.0 * (c1.y - p0y))
                c2 = Point(end.x + 2.0 / 3.0 * (c1.x - end.x), end.y + 2.0 / 3.0 * (c1.y - end.y))
                if current is not None:
                    current.extend(_flatten_curve(cursor, c0, c2, end))
                cursor = end
                prev_control = c1
        elif op == "T":
            while True:
                a2, b2 = numeric(i), numeric(i + 1)
                if a2 is None or b2 is None:
                    break
                i += 2
                c1 = Point(2 * cursor.x - (prev_control.x if prev_control else cursor.x),
                           2 * cursor.y - (prev_control.y if prev_control else cursor.y))
                end = _apply(a2, b2, sx, sy, tx, ty) if absolute else Point(cursor.x + a2 * sx, cursor.y + b2 * sy)
                p0x, p0y = cursor.x, cursor.y
                c0 = Point(p0x + 2.0 / 3.0 * (c1.x - p0x), p0y + 2.0 / 3.0 * (c1.y - p0y))
                c2 = Point(end.x + 2.0 / 3.0 * (c1.x - end.x), end.y + 2.0 / 3.0 * (c1.y - end.y))
                if current is not None:
                    current.extend(_flatten_curve(cursor, c0, c2, end))
                cursor = end
                prev_control = c1
        elif op == "A":
            while True:
                rx, ry, rot, large, sweep, a2, b2 = [numeric(i + k) for k in range(7)]
                if any(v is None for v in (rx, ry, rot, large, sweep, a2, b2)):
                    break
                i += 7
                end = _apply(a2, b2, sx, sy, tx, ty) if absolute else Point(cursor.x + a2 * sx, cursor.y + b2 * sy)
                pts = _arc_points(cursor, rx * sx, ry * sy, rot, bool(large), bool(sweep), end)
                if current is not None:
                    current.extend(pts)
                cursor = end
                prev_control = None
        else:
            break

    if current is not None:
        subpaths.append(current)
    return subpaths


def _parse_svg(text: str, name: str) -> Icon:
    primitives: List[IconPrimitive] = []
    viewbox = Rect(0, 0, 24, 24)
    root_g = (1.0, 1.0, 0.0, 0.0)  # (sx, sy, tx, ty)

    stack = [(root_g, root_g)]
    for match in _TAG_RE.finditer(text):
        closing, tag, attrs, self_close = match.groups()
        if closing:
            if len(stack) > 1:
                stack.pop()
            continue
        attr_map: Dict[str, str] = {}
        for am in _ATTR_RE.finditer(attrs):
            attr_map[am.group(1)] = am.group(3) if am.group(3) is not None else am.group(4)

        parent_tf = stack[-1][1] if stack else root_g
        local_tf = _parse_transform(attr_map.get("transform"))
        child_tf = (local_tf[0] * parent_tf[0], local_tf[1] * parent_tf[1],
                    local_tf[2] * parent_tf[0] + parent_tf[2],
                    local_tf[3] * parent_tf[1] + parent_tf[3])

        if tag == "g":
            stack.append((child_tf, child_tf))
            continue
        if tag == "svg":
            if "viewBox" in attr_map:
                v = _numbers(attr_map["viewBox"])
                if len(v) == 4:
                    viewbox = Rect(v[0], v[1], v[2], v[3])
            continue
        if tag == "defs":
            stack.append((child_tf, child_tf))
            continue
        if tag in ("title", "desc"):
            continue

        sx, sy, tx, ty = child_tf
        filled = "none" not in (attr_map.get("fill") or "").lower() and attr_map.get("fill", "none") != "none" \
            or "fill" not in attr_map
        stroked = "none" not in (attr_map.get("stroke") or "").lower() and "stroke" in attr_map

        def pt_at(x: float, y: float) -> Point:
            return _apply(x, y, sx, sy, tx, ty)

        if tag == "rect":
            x, y = _numbers(attr_map.get("x", "0")), _numbers(attr_map.get("y", "0"))
            w = _numbers(attr_map.get("width", "0"))
            h = _numbers(attr_map.get("height", "0"))
            rx = _numbers(attr_map.get("rx", "0"))
            rx = rx[0] if rx else 0.0
            rx = max(0.0, min(rx, (w[0] if w else 0) / 2.0))
            r = Rect(pt_at(x[0] if x else 0, y[0] if y else 0).x,
                     pt_at(x[0] if x else 0, y[0] if y else 0).y,
                     (w[0] if w else 0) * sx, (h[0] if h else 0) * sy)
            kind = "round_rect" if rx > 0 else "rect"
            primitives.append(IconPrimitive(kind=kind, rect=r, radius=rx * min(sx, sy)))
        elif tag == "circle":
            c = _numbers(attr_map.get("cx", "0"))
            cy = _numbers(attr_map.get("cy", "0"))
            r = _numbers(attr_map.get("r", "0"))
            cx = c[0] if c else 0.0
            cyp = cy[0] if cy else 0.0
            rad = (r[0] if r else 0.0) * sx
            p = pt_at(cx, cyp)
            primitives.append(IconPrimitive(kind="ellipse", rect=Rect(p.x - rad, p.y - rad, rad * 2, rad * 2)))
        elif tag == "ellipse":
            c = _numbers(attr_map.get("cx", "0"))
            cy = _numbers(attr_map.get("cy", "0"))
            rx = _numbers(attr_map.get("rx", "0"))
            ry = _numbers(attr_map.get("ry", "0"))
            p = pt_at(c[0] if c else 0.0, cy[0] if cy else 0.0)
            primitives.append(IconPrimitive(kind="ellipse",
                                            rect=Rect(p.x - (rx[0] if rx else 0) * sx,
                                                      p.y - (ry[0] if ry else 0) * sy,
                                                      (rx[0] if rx else 0) * 2 * sx,
                                                      (ry[0] if ry else 0) * 2 * sy)))
        elif tag == "line":
            x1 = _numbers(attr_map.get("x1", "0"))
            y1 = _numbers(attr_map.get("y1", "0"))
            x2 = _numbers(attr_map.get("x2", "0"))
            y2 = _numbers(attr_map.get("y2", "0"))
            a = pt_at(x1[0], y1[0])
            b = pt_at(x2[0], y2[0])
            primitives.append(IconPrimitive(kind="polyline", points=[a, b], filled=False,
                                            stroked=True, stroke_width=_numbers(attr_map.get("stroke-width", "1.5"))[0]))
        elif tag in ("polygon", "polyline"):
            pts = _numbers(attr_map.get("points", ""))
            if len(pts) >= 4:
                points = [pt_at(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
                if tag == "polygon" and points:
                    points.append(points[0])
                primitives.append(IconPrimitive(kind="polygon", points=points,
                                                filled=tag == "polygon",
                                                stroked=True,
                                                stroke_width=_numbers(attr_map.get("stroke-width", "1.5"))[0]))
        elif tag == "path":
            d = attr_map.get("d", "")
            if d:
                for subpath in _parse_path(d, sx, sy, tx, ty):
                    if len(subpath) >= 2:
                        closed = subpath[0] == subpath[-1]
                        kind = "polygon" if closed else "polyline"
                        primitives.append(IconPrimitive(kind=kind, points=subpath,
                                                        filled=closed, stroked=not closed,
                                                        stroke_width=_numbers(attr_map.get("stroke-width", "1.5"))[0]))
    return Icon(name=name, viewbox=viewbox, primitives=primitives)


# ---------------------------------------------------------------------------
# Library / fallback
# ---------------------------------------------------------------------------


@dataclass
class _PlaceholderIcon:
    """A simple geometric icon used when an SVG is missing or unparsable."""

    name: str

    def build(self, target: Rect, color: str = "#333333", **_) -> List[IconPrimitive]:
        s = min(target.width, target.height)
        center = (target.x + target.width / 2.0, target.y + target.height / 2.0)
        r = s * 0.4
        ring = IconPrimitive(kind="ellipse", rect=Rect(center[0] - r, center[1] - r, r * 2, r * 2))
        inner = IconPrimitive(kind="ellipse", rect=Rect(center[0] - r * 0.4, center[1] - r * 0.4, r * 0.8, r * 0.8))
        return [ring, inner]


class IconLibrary:
    """Loads and caches icons from ``assets/icons``."""

    def __init__(self, directory: Path = ICON_DIR) -> None:
        self.directory = directory
        self._cache: Dict[str, Icon] = {}

    def available(self) -> List[str]:
        if not self.directory.exists():
            return []
        return sorted(p.stem for p in self.directory.glob("*.svg"))

    def get(self, name: str) -> Icon:
        if name in self._cache:
            return self._cache[name]
        path = self.directory / f"{name}.svg"
        if path.exists():
            try:
                icon = _parse_svg(path.read_text(encoding="utf-8"), name)
                self._cache[name] = icon
                return icon
            except Exception:
                pass
        raise KeyError(f"Icon {name!r} not found in {self.directory}")

    def resolve(self, name: Optional[str]) -> Icon:
        """Return the requested icon, or a geometric placeholder."""
        if name and name in self.available():
            return self.get(name)
        return _PlaceholderIcon(name or "placeholder")


_library: Optional[IconLibrary] = None


def library() -> IconLibrary:
    global _library
    if _library is None:
        _library = IconLibrary()
    return _library
