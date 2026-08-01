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


def _mask_strings(text: str) -> Tuple[str, List[str]]:
    """Replace every JSON string literal with a placeholder token.

    After masking, structural characters (``{`` ``}`` ``[`` ``]``) inside
    string values can no longer confuse the structural repairs.
    """
    tokens: List[str] = []

    def _replace(match: "re.Match") -> str:
        tokens.append(match.group(0))
        return "%s%d%s" % (_MARK, len(tokens) - 1, _MARK)

    return _STRING_RE.sub(_replace, text), tokens


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


def _structural_repair(text: str) -> str:
    masked, tokens = _mask_strings(text)
    return _unmask(_fix_structure(masked), tokens)


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
    """Parse ``text``; on failure, salvage a trailing-truncated prefix."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    masked, tokens = _mask_strings(text)
    cut_points = [match.end() for match in re.finditer(
        r"(%s|[}\]])" % _PH_RE, masked)]
    for pos in reversed(cut_points[-200:]):
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
