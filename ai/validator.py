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

from config import (MAX_DASHBOARD_METRICS, MAX_HIERARCHY_NODES, MAX_PHASES,
                    MAX_STEPS, MAX_SWOT_ITEMS, MAX_TIMELINE_ITEMS)
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


def _structural_repair(text: str) -> str:
    masked, tokens = _mask_strings(text)
    masked = _fix_structure(masked)
    masked = _fix_missing_slide_braces(masked, tokens)
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
    """Parse ``text``; on failure, salvage the first value or a truncation."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # "Extra data": the model echoed a second object (or prose containing a
    # closing brace) after a complete first value.  ``raw_decode`` returns
    # exactly the first value no matter how much junk follows it.
    try:
        data, _ = json.JSONDecoder().raw_decode(text)
    except (json.JSONDecodeError, ValueError):
        pass
    else:
        if _is_plausible(data):
            return data

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
        if _is_plausible(data):
            return data
    return None


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
                    "topic"):
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
        stages = copy.get("phases") if isinstance(copy.get("phases"), list) \
            else copy.get("stages")
        if isinstance(stages, list):
            copy["stages"] = _as_strings(stages, "phase")[:MAX_STEPS]
        copy.pop("phases", None)
        return copy

    if stype == "hierarchy":
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
        rows = copy.get("analysis")
        if isinstance(rows, list) and all(isinstance(r, dict) for r in rows):
            quad = {"strengths": [], "weaknesses": [],
                    "opportunities": [], "threats": []}
            for src, dst in (("strength", "strengths"), ("weakness", "weaknesses"),
                             ("opportunity", "opportunities"), ("threat", "threats")):
                for row in rows:
                    value = row.get(src)
                    if isinstance(value, str) and value:
                        quad[dst].append(value)
            for key, values in quad.items():
                copy[key] = {"title": key.capitalize(),
                             "items": values[:MAX_SWOT_ITEMS]}
            copy.pop("analysis", None)
        return copy

    if stype == "comparison":
        comps = copy.get("comparisons")
        if isinstance(comps, list):
            left = right = None
            for item in comps:
                if not isinstance(item, dict):
                    continue
                if "left" in item:
                    left = item["left"]
                if "right" in item:
                    right = item["right"]
            for side, value in (("left", left), ("right", right)):
                if isinstance(value, dict):
                    copy[side] = {
                        "heading": value.get("name") or value.get("heading") or "",
                        "subheading": value.get("subheading"),
                        "points": ([value["description"]]
                                   if isinstance(value.get("description"), str)
                                   and value["description"] else []),
                        "icon": value.get("icon"),
                    }
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
        shaped = _normalize_slide(slide)
        if shaped is not None:
            _coerce_lists(shaped)
            normalized.append(shaped)
    data["slides"] = normalized
    return data


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
