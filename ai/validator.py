"""Strict JSON parsing, coercion and repair for LLM output.

LLMs produce free text; this module turns that text into a valid
:class:`Presentation` AST.  It is deliberately strict: output that cannot be
coerced is rejected with actionable messages rather than silently corrupted.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from pydantic import ValidationError

from config import (MAX_COMPARISON_POINTS, MAX_DASHBOARD_METRICS,
                    MAX_HIERARCHY_NODES, MAX_PHASES, MAX_STEPS, MAX_SWOT_ITEMS,
                    MAX_TIMELINE_ITEMS)
from schema import Presentation
from validator import validate_presentation


class JSONParseError(ValueError):
    """Raised when raw model text cannot be converted to a Presentation."""

    def __init__(self, message: str, detail: str = "", raw: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.raw = raw


def _strip_fences(raw: str) -> str:
    """Remove ```json ... ``` fences and any leading prose."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Fall back: take the first { ... } block if plain prose surrounds it.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


# ---------------------------------------------------------------------------
# Best-effort repair of small-model JSON output.
#
# Small instruct models frequently emit output that is *almost* JSON: missing
# commas, trailing commas, truncated objects, or an extra object after the
# deck.  Repair is intentionally lenient about *structure* only -- the repaired
# text still has to parse as JSON and still has to pass the strict schema
# checks below, so it can never silently corrupt a valid deck.
# ---------------------------------------------------------------------------

_MARK = "\x00"
_PH_RE = r"\x00\d+\x00"
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
_LITERAL_RE = re.compile(r"\b(?:true|false|null)\b")


def _mask_strings(text: str) -> Tuple[str, List[str]]:
    """Replace JSON string literals and bare literals with placeholders.

    After masking, structural characters (``{`` ``}`` ``[`` ``]``) inside
    string values can no longer confuse the structural repairs, and the
    ``true``/``false``/``null`` keywords are treated like any other value so
    missing-comma repair covers them uniformly.
    """
    tokens: List[str] = []

    def _replace(match: "re.Match") -> str:
        tokens.append(match.group(0))
        return "%s%d%s" % (_MARK, len(tokens) - 1, _MARK)

    masked = _STRING_RE.sub(_replace, text)
    return _LITERAL_RE.sub(_replace, masked), tokens


def _unmask(masked: str, tokens: List[str]) -> str:
    for index, token in enumerate(tokens):
        masked = masked.replace("%s%d%s" % (_MARK, index, _MARK), token)
    return masked


def _fix_structure(masked: str) -> str:
    """Insert missing commas / drop trailing commas in masked JSON."""
    for pattern, replacement in (
        # object/array boundaries
        (r"}\s*\{", "}, {"),
        (r"}\s*\[", "}, ["),
        (r"]\s*\{", "], {"),
        (r"]\s*\[", "], ["),
        # closing bracket -> next value / key (a string placeholder)
        (r"}\s*(%s)" % _PH_RE, r"}, \1"),
        (r"]\s*(%s)" % _PH_RE, r"], \1"),
        # value (string placeholder) -> object / array value
        (r"(%s)\s*\{" % _PH_RE, r"\1, {"),
        (r"(%s)\s*\[" % _PH_RE, r"\1, ["),
        # adjacent string values (array elements or key/value pairs)
        (r"(%s)\s*(%s)" % (_PH_RE, _PH_RE), r"\1, \2"),
        # number adjacent to a string / opening bracket
        (r"(\d)\s*(%s)" % _PH_RE, r"\1, \2"),
        (r"(\d)\s*([{\[])", r"\1, \2"),
        # string placeholder adjacent to a number
        (r"(%s)\s*(\d)" % _PH_RE, r"\1, \2"),
        (r"(\d)\s+(\d)", r"\1, \2"),
        # trailing commas before } or ]
        (r",\s*([}\]])", r"\1"),
    ):
        masked = re.sub(pattern, replacement, masked)
    return masked


def _fix_missing_slide_braces(masked: str, tokens: List[str]) -> str:
    """Insert the ``{`` a slide loses when the model drops it after ``]},``.

    Qwen emits ``...items":[...]},\"type\":\"comparison\"...`` instead of
    ``...items\":[...]},{\"type\":\"comparison\"...``, leaving the following
    slide's keys dangling at the array level.  ``]},`` followed by the
    ``\"type\"`` key means a new slide object starts there.
    """
    def _replace(match: "re.Match") -> str:
        index = int(match.group(1)[1:-1])
        if 0 <= index < len(tokens) and tokens[index] == '"type"':
            return "}, {%s:" % match.group(1)
        return match.group(0)

    return re.sub(r"}\s*,\s*(%s):" % _PH_RE, _replace, masked)


def _fix_unclosed_array_items(masked: str) -> str:
    """Insert a ``}`` where the model omitted an array element's closing brace.

    Qwen merges comparison columns as ``[{"left":{...},{"right":{...}}]``:
    the first ``{`` is never closed, leaving a bare ``,{`` inside an open
    object.  In valid JSON a comma inside an object must be followed by a key,
    so ``,[`` or ``,{`` can only mean the previous object was left open.

    When the close we insert is the one the model "moved" to the array's end,
    the array also carries a spurious trailing ``}`` right before ``]``; that
    extra close is dropped so the array parses.
    """
    out: List[str] = []
    stack: List[str] = []
    index = 0
    length = len(masked)
    while index < length:
        char = masked[index]
        if char == _MARK:
            end = masked.find(_MARK, index + 1)
            if end == -1:
                out.append(masked[index:])
                break
            out.append(masked[index:end + 1])
            index = end + 1
            continue
        if char in "{[":
            stack.append(char)
        elif char == "]":
            if stack:
                stack.pop()
        elif char == "}":
            if (not stack or stack[-1] != "{") and re.match(r"\s*([\]}])", masked[index + 1:]):
                # A close that matches no open object, directly before the
                # array's ``]``/``}``, is the spurious ``}`` the model
                # "moved" to the end of an array element -- drop it.
                index += 1
                continue
            if stack:
                stack.pop()
        elif char == ",":
            if stack and stack[-1] == "{" and re.match(r"\s*([{\[])", masked[index + 1:]):
                out.append("},")
                stack.pop()
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _structural_repair(text: str) -> str:
    masked, tokens = _mask_strings(text)
    masked = _fix_structure(masked)
    # Slide ``{``s must exist before the array close-brace fix evaluates the
    # stack: ``]}, \"type\":...`` drops a slide's ``{``, so its matching ``}``
    # would otherwise look like a spurious extra close at the array level.
    masked = _fix_missing_slide_braces(masked, tokens)
    masked = _fix_unclosed_array_items(masked)
    return _unmask(masked, tokens)


def _swap_single_quotes(text: str) -> str:
    """Turn single-quoted JSON (``{'a': 'b'}``) into double-quoted JSON."""

    def _replace(match: "re.Match") -> str:
        inner = match.group(1).replace("\\'", "'").replace('"', '\\"')
        return '"' + inner + '"'

    return re.sub(r"'((?:[^'\\]|\\.)*)'", _replace, text)


def _close_open_structures(masked: str) -> str:
    """Append the closers needed to balance ``{``/``[`` at end-of-input."""
    stack: List[str] = []
    index = 0
    length = len(masked)
    while index < length:
        char = masked[index]
        if char == _MARK:
            end = masked.find(_MARK, index + 1)
            index = length if end == -1 else end + 1
            continue
        if char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack:
                stack.pop()
        index += 1
    return masked + "".join("}" if char == "{" else "]" for char in reversed(stack))


def _drop_dangling_string(masked: str) -> str:
    """Remove an unterminated string literal left at the end of the input."""
    end = masked.rfind('"')
    if end == -1 or end > 0 and masked[end - 1] == "\\":
        return masked
    return masked[:end]


def _is_plausible(data) -> bool:
    """A salvage is only accepted if it still looks like a presentation deck."""
    if not isinstance(data, dict):
        return False
    slides = data.get("slides")
    return isinstance(slides, list) and len(slides) > 0


def _try_parse_with_truncation(text: str) -> Optional[dict]:
    """Parse ``text``; on failure, salvage the best deck in the output."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # The model often emits a (possibly malformed) deck, extra slides as
    # sibling objects, then an echo of the full deck.  Collect every complete
    # top-level value and keep the largest plausible deck rather than blindly
    # taking the first value.
    best: Optional[dict] = None
    index = 0
    length = len(text)
    decoder = json.JSONDecoder()
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        try:
            data, end = decoder.raw_decode(text, index)
        except (json.JSONDecodeError, ValueError) as exc:
            # A malformed top-level value (e.g. the truncated compact deck that
            # precedes the echoed deck) must not abort the scan -- skip past
            # the failure and keep looking for the next complete value.
            if isinstance(exc, json.JSONDecodeError):
                index = max(exc.pos + 1, index + 1)
            else:
                index += 1
            continue
        index = end
        if _is_plausible(data) and (
                best is None or len(data["slides"]) > len(best["slides"])):
            best = data

    masked, tokens = _mask_strings(text)
    cut_points = [match.end() for match in re.finditer(
        r"(%s|[}\]])" % _PH_RE, masked)]
    for pos in reversed(cut_points):
        prefix = _drop_dangling_string(masked[:pos])
        closed = _close_open_structures(prefix)
        try:
            data = json.loads(_unmask(closed, tokens))
        except json.JSONDecodeError:
            continue
        if _is_plausible(data) and (
                best is None or len(data["slides"]) > len(best["slides"])):
            best = data
    return best


def _repair_json(text: str) -> Optional[dict]:
    """Return a reparsed, deck-shaped object or ``None`` if unsalvageable."""
    if not text or not text.strip():
        return None
    candidates = [_structural_repair(text)]
    # Single-quoted JSON: only attempt when there are no double quotes and no
    # apostrophes (which would make a naive quote swap corrupt real text).
    if "'" in text and '"' not in text and not re.search(r"\w'\w", text):
        swapped = _structural_repair(_swap_single_quotes(text))
        if swapped != candidates[0]:
            candidates.append(swapped)
    for candidate in candidates:
        data = _try_parse_with_truncation(candidate)
        if data is not None:
            return data
    return None


def _comparison_sides(title: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split a comparison title like ``"Current State vs Vision"`` into its two sides.

    Returns ``(left, right)`` or ``(None, None)`` when the title has no
    separator so callers can fall back to defaults.
    """
    if isinstance(title, str):
        for sep in (" vs ", " vs. ", "|", " — ", " - ", "-"):
            if sep in title:
                parts = [part.strip() for part in title.split(sep)
                         if part.strip()]
                if len(parts) >= 2:
                    return parts[0], parts[1]
    return None, None


def _normalize_slide(slide: dict) -> Optional[dict]:
    """Map the slide shapes the Qwen 1.5B model emits onto the strict schema.

    Slides with no renderable content (e.g. an empty comparison chart) are
    dropped (``None``).  Everything else is coerced key-by-key; items that
    match none of the known shapes are left untouched so the schema can still
    report exactly where they fail.
    """
    stype = slide["type"]
    copy = dict(slide)

    def _pick_text(item: dict) -> Optional[str]:
        for key in ("text", "title", "step", "phase", "event", "task",
                    "label", "name", "metric", "date", "description", "bullet",
                    "topic", "action"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _as_strings(items: list, primary: str) -> list:
        out = []
        for item in items:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                value = _pick_text(item)
                out.append(value if value is not None else item)
        return out

    if stype == "hero":
        if isinstance(copy.get("image"), str):
            copy["image"] = {"source": copy["image"]}
        return copy

    if stype == "agenda":
        if isinstance(copy.get("items"), list):
            copy["items"] = _as_strings(copy["items"], "text")
        elif isinstance(copy.get("agendas"), list):
            copy["items"] = _as_strings(copy["agendas"], "topic")
        copy.pop("agendas", None)
        return copy

    if stype == "timeline" and (isinstance(copy.get("items"), list)
                                or isinstance(copy.get("events"), list)):
        items = []
        for item in copy.get("items") or copy.get("events", []):
            if isinstance(item, str):
                items.append({"title": item})
            elif isinstance(item, dict):
                items.append({
                    "label": item.get("date") or item.get("label"),
                    "title": (item.get("event") or item.get("title")
                              or item.get("text") or ""),
                    "detail": item.get("description") or item.get("detail"),
                })
        copy["items"] = items[:MAX_TIMELINE_ITEMS]
        copy.pop("events", None)
        return copy

    if stype == "process":
        if isinstance(copy.get("steps"), list):
            copy["steps"] = _as_strings(copy["steps"], "step")[:MAX_STEPS]
        return copy

    if stype == "roadmap":
        if isinstance(copy.get("phases"), list):
            phases = []
            for phase in copy["phases"]:
                if isinstance(phase, str):
                    phases.append({"name": phase, "items": []})
                elif isinstance(phase, dict):
                    phases.append({
                        "name": phase.get("phase") or phase.get("name") or "",
                        "period": phase.get("period"),
                        "items": _as_strings(phase.get("tasks", []), "task")[:4],
                    })
            copy["phases"] = phases[:MAX_PHASES]
        return copy

    if stype == "cycle":
        if isinstance(copy.get("cycles"), list):
            stages = []
            for entry in copy["cycles"]:
                if isinstance(entry, dict):
                    steps = entry.get("steps", entry.get("stages", []))
                    if isinstance(steps, list):
                        stages.extend(_as_strings(steps, "step"))
            copy["stages"] = stages[:MAX_STEPS]
            copy.pop("cycles", None)
            return copy
        stages = copy.get("phases") if isinstance(copy.get("phases"), list) \
            else copy.get("stages")
        if isinstance(stages, list):
            copy["stages"] = _as_strings(stages, "phase")[:MAX_STEPS]
        copy.pop("phases", None)
        return copy

    if stype == "hierarchy":
        if (not isinstance(copy.get("root"), dict)
                and isinstance(copy.get("hierarchies"), list)):
            children = []
            for entry in copy["hierarchies"]:
                if isinstance(entry, dict):
                    children.append({
                        "name": entry.get("level") or entry.get("name")
                                or entry.get("role") or "",
                        "role": entry.get("role") or entry.get("level"),
                    })
                elif isinstance(entry, str):
                    children.append({"name": entry})
            copy["root"] = {"name": copy.get("title") or "Organization",
                            "children": children[:MAX_HIERARCHY_NODES]}
            copy.pop("hierarchies", None)
            return copy
        if not isinstance(copy.get("root"), dict) and isinstance(copy.get("levels"), list):
            children = []
            for level in copy["levels"]:
                if isinstance(level, dict):
                    children.append({
                        "name": (level.get("title") or level.get("name")
                                 or level.get("level") or ""),
                        "role": level.get("level") or level.get("role"),
                    })
                elif isinstance(level, str):
                    children.append({"name": level})
            copy["root"] = {"name": copy.get("title") or "Organization",
                            "children": children[:MAX_HIERARCHY_NODES]}
        copy.pop("levels", None)
        return copy

    if stype == "dashboard":
        if isinstance(copy.get("dashboards"), list):
            metrics = []
            for entry in copy["dashboards"]:
                if isinstance(entry, str):
                    metrics.append({"label": entry, "value": ""})
                elif isinstance(entry, dict):
                    data = entry.get("data")
                    value = ""
                    if isinstance(data, list):
                        last = data[-1] if data else None
                        if isinstance(last, list) and len(last) >= 2:
                            value = str(last[-1])
                        elif isinstance(last, (int, float)):
                            value = str(last)
                    subtitles = entry.get("subtitles")
                    if not value and isinstance(subtitles, list) and subtitles:
                        value = str(subtitles[0])
                    metrics.append({
                        "label": entry.get("metric") or entry.get("label") or "",
                        "value": value,
                        "note": (str(subtitles[0]) if isinstance(subtitles, list)
                                 and subtitles else None),
                        "icon": entry.get("icon"),
                    })
            copy["metrics"] = metrics[:MAX_DASHBOARD_METRICS]
            copy.pop("dashboards", None)
            return copy
        if isinstance(copy.get("metrics"), list):
            metrics = []
            for metric in copy["metrics"]:
                if isinstance(metric, str):
                    metrics.append({"label": metric, "value": ""})
                elif isinstance(metric, dict):
                    metrics.append({
                        "label": metric.get("metric") or metric.get("label") or "",
                        "value": metric.get("value") or metric.get("current") or "",
                        "delta": metric.get("delta"),
                        "icon": metric.get("icon"),
                    })
            copy["metrics"] = metrics[:MAX_DASHBOARD_METRICS]
        return copy

    if stype == "swot":
        quad = {"strengths": [], "weaknesses": [],
                "opportunities": [], "threats": []}
        src_map = (("strength", "strengths"), ("weakness", "weaknesses"),
                   ("opportunity", "opportunities"), ("threat", "threats"),
                   ("option", "weaknesses"))
        moved = False

        def _collect(key: str, value) -> None:
            nonlocal moved
            if isinstance(value, str) and value:
                quad[key].append(value)
                moved = True

        rows = copy.get("analysis")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    for src, dst in src_map:
                        _collect(dst, row.get(src))
        for qkey in quad:
            value = copy.get(qkey)
            if isinstance(value, list) and value and any(
                    isinstance(item, dict) for item in value):
                for item in value:
                    if isinstance(item, str):
                        quad[qkey].append(item)
                    elif isinstance(item, dict):
                        for src, dst in src_map:
                            _collect(dst, item.get(src))
                moved = True
        if moved:
            for key, values in quad.items():
                copy[key] = {"title": key.capitalize(),
                             "items": values[:MAX_SWOT_ITEMS]}
            copy.pop("analysis", None)
        return copy

    if stype == "comparison":
        comps = copy.get("comparisons")
        if isinstance(comps, list):
            paired = any(isinstance(item, dict)
                         and ("left" in item or "right" in item)
                         for item in comps)
            if paired:
                # Each item carries ``left``/``right`` side dicts.  Aggregate
                # every row so no data is dropped: side values become the
                # column points (metric/value rows become ``"Label: value"``
                # points), and column headings come from the vs-style title or
                # the side's own name/heading.
                left_pts, right_pts = [], []
                row_labeled = False
                left_name = right_name = None
                for item in comps:
                    if not isinstance(item, dict):
                        continue
                    if isinstance(item.get("title"), str):
                        row_labeled = True
                    for side, pts in (("left", left_pts), ("right", right_pts)):
                        value = item.get(side)
                        if not isinstance(value, dict):
                            continue
                        if side == "left" and left_name is None:
                            left_name = (value.get("name")
                                         or value.get("heading"))
                        if side == "right" and right_name is None:
                            right_name = (value.get("name")
                                          or value.get("heading"))
                        label = (item.get("title")
                                 or value.get("name")
                                 or value.get("heading")
                                 or value.get("metric"))
                        num = value.get("value")
                        desc = value.get("description") or value.get("text")
                        if isinstance(num, str) and num:
                            pts.append(f"{label}: {num}"
                                       if isinstance(label, str) and label
                                       else num)
                        elif isinstance(desc, str) and desc:
                            pts.append(desc)
                left_side, right_side = _comparison_sides(copy.get("title"))
                if row_labeled:
                    left_head = left_side or left_name or "Current"
                    right_head = right_side or right_name or "Future"
                else:
                    left_head = left_name or left_side or "Current"
                    right_head = right_name or right_side or "Future"
                copy["left"] = {"heading": left_head, "subheading": None,
                                "points": left_pts[:MAX_COMPARISON_POINTS]}
                copy["right"] = {"heading": right_head, "subheading": None,
                                 "points": right_pts[:MAX_COMPARISON_POINTS]}
            else:
                # Flat rows without ``left``/``right``.  Two shapes:
                # ``{"heading": ..., "current": ..., "future": ...}`` rows
                # (column one holds the "current" values, column two the
                # "future" values), or plain ``{"name": ..., "description":
                # ...}`` rows paired into the two columns.
                rows = [item for item in comps if isinstance(item, dict)]
                if any("current" in row or "future" in row for row in rows):
                    left, right = _comparison_sides(copy.get("title"))
                    copy["left"] = {
                        "heading": left or "Current",
                        "subheading": None,
                        "points": [row["current"] for row in rows
                                   if isinstance(row.get("current"), str)
                                   and row["current"]][:MAX_COMPARISON_POINTS],
                    }
                    copy["right"] = {
                        "heading": right or "Future",
                        "subheading": None,
                        "points": [row["future"] for row in rows
                                   if isinstance(row.get("future"), str)
                                   and row["future"]][:MAX_COMPARISON_POINTS],
                    }
                else:
                    def _column(col_rows: list, fallback_heading: str) -> dict:
                        heading = ""
                        points = []
                        for row in col_rows:
                            name = row.get("name") or row.get("heading")
                            if not heading and isinstance(name, str) and name:
                                heading = name
                            desc = row.get("description") or row.get("text")
                            if isinstance(desc, str) and desc:
                                points.append(desc)
                        return {"heading": heading or fallback_heading,
                                "subheading": None,
                                "points": points[:MAX_COMPARISON_POINTS]}

                    copy["left"] = _column(rows[0::2], "Current")
                    copy["right"] = _column(rows[1::2], "Vision")
            copy.pop("comparisons", None)
            return copy
        if not copy.get("left") and not copy.get("right"):
            chart = copy.get("chart")
            if isinstance(chart, dict) and not chart.get("categories"):
                return None
        return copy

    if stype == "conclusion":
        cta = copy.get("cta")
        if isinstance(copy.get("takeaways"), list):
            takeaways = []
            for take in copy["takeaways"]:
                if isinstance(take, str):
                    takeaways.append(take)
                elif isinstance(take, dict):
                    value = _pick_text(take)
                    takeaways.append(value if value is not None else take)
                    if not cta and isinstance(take.get("action"), str) and take.get("action"):
                        cta = take["action"]
            copy["takeaways"] = takeaways[:6]
        if cta:
            copy["cta"] = cta
        return copy

    return copy


def _coerce(data) -> dict:
    """Coerce common LLM quirks before schema validation."""
    if not isinstance(data, dict):
        raise JSONParseError("Top-level JSON must be an object")
    data = dict(data)
    slides = data.get("slides")
    if slides is not None and not isinstance(slides, list):
        raise JSONParseError("'slides' must be a list")

    normalized = []
    for slide in data.get("slides", []):
        if not isinstance(slide, dict):
            raise JSONParseError("Every slide must be an object")
        if "type" not in slide or not isinstance(slide["type"], str):
            raise JSONParseError("Every slide must declare a 'type'")
        for shaped in _split_merged_slides(slide):
            shaped = _normalize_slide(shaped)
            if shaped is not None:
                _coerce_lists(shaped)
                normalized.append(shaped)
    data["slides"] = normalized
    return data


def _split_merged_slides(slide: dict) -> list:
    """Split an object that merges two slides (Qwen merges dashboard + SWOT).

    The model emits ``{"type": "dashboard", "dashboards": [...], "type": "swot",
    "strengths": [...]}`` as a single object; duplicate ``"type"``/``"title"``
    keys make the last one win, so the dashboard half loses its title.  Return
    the two slides it was meant to be.
    """
    stype = slide["type"]
    swot_keys = ("strengths", "weaknesses", "opportunities", "threats", "analysis")
    if stype == "swot" and "dashboards" in slide:
        dashboard = {"type": "dashboard", "title": "Performance Dashboard",
                     "dashboards": slide.pop("dashboards")}
        return [dashboard, slide]
    if stype == "dashboard" and any(slide.get(key) for key in swot_keys):
        swot = {"type": "swot", "title": "SWOT Analysis"}
        for key in swot_keys:
            if key in slide:
                swot[key] = slide[key]
                slide.pop(key, None)
        return [slide, swot]
    return [slide]


def _coerce_lists(slide: dict) -> None:
    """Normalise single strings into lists where the schema expects lists."""
    list_fields = ("bullets", "steps", "items", "tags", "points",
                   "takeaways", "stages", "metrics", "phases", "categories")
    for key in list_fields:
        if key in slide and isinstance(slide[key], str):
            slide[key] = [slide[key]]
    # SWOT quadrants: allow a plain list of strings
    for qkey in ("strengths", "weaknesses", "opportunities", "threats"):
        if qkey in slide and isinstance(slide[qkey], list) and \
                slide[qkey] and isinstance(slide[qkey][0], str):
            slide[qkey] = {"title": qkey.capitalize(), "items": slide[qkey]}
    # bullets may be plain strings -> BulletItem
    if "bullets" in slide:
        slide["bullets"] = [
            b if isinstance(b, dict) else {"text": b}
            for b in slide["bullets"]
        ]
    # comparison columns: allow {heading, points} dicts
    for col in ("left", "right"):
        if col in slide and isinstance(slide[col], str):
            slide[col] = {"heading": slide[col], "points": []}
    # timeline items: allow strings (only for timeline slides - agenda
    # keeps plain strings)
    if slide.get("type") == "timeline" and "items" in slide and isinstance(slide["items"], list):
        slide["items"] = [
            it if isinstance(it, dict) else {"title": it}
            for it in slide["items"]
        ]


def strict_parse(raw: str) -> Presentation:
    """Parse raw model text into a validated :class:`Presentation`.

    Raises :class:`JSONParseError` with a helpful message on failure.
    """
    cleaned = _strip_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        repaired = _repair_json(cleaned)
        if repaired is None:
            raise JSONParseError(
                f"Model output was not valid JSON: {exc}", detail=exc.msg, raw=raw
            ) from exc
        data = repaired

    data = _coerce(data)
    try:
        ast = Presentation.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        raise JSONParseError(
            f"Presentation schema error at {loc}: {first.get('msg')}",
            detail=str(exc), raw=raw,
        ) from exc

    report = validate_presentation(ast)
    if not report.ok:
        raise JSONParseError("Presentation failed content validation: " + str(report), raw=raw)
    return ast


def try_parse(raw: str) -> Tuple[Optional[Presentation], List[str]]:
    """Non-raising variant: returns ``(ast, errors)``."""
    try:
        return strict_parse(raw), []
    except JSONParseError as exc:
        return None, [str(exc)]
