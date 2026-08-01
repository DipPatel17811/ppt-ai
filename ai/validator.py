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


def _coerce(data) -> dict:
    """Coerce common LLM quirks before schema validation."""
    if not isinstance(data, dict):
        raise JSONParseError("Top-level JSON must be an object")
    data = dict(data)
    slides = data.get("slides")
    if slides is not None and not isinstance(slides, list):
        raise JSONParseError("'slides' must be a list")

    for slide in data.get("slides", []):
        if not isinstance(slide, dict):
            raise JSONParseError("Every slide must be an object")
        if "type" not in slide or not isinstance(slide["type"], str):
            raise JSONParseError("Every slide must declare a 'type'")
        _coerce_lists(slide)
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
        raise JSONParseError(
            f"Model output was not valid JSON: {exc}", detail=exc.msg, raw=raw
        ) from exc

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
