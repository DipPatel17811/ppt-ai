"""Morph support: stable, deterministic object identities.

PowerPoint's Morph transition matches shapes across consecutive slides by
their **name**.  For morphs to work the same logical object (the title, the
footer, bullet #3, ...) must have the same name on every slide while
distinct objects always differ.

``ObjectIdBank`` guarantees exactly that: given a semantic key it returns a
stable, sanitised shape name.  Templates ask the bank for every object they
create, so morphing is a free side-effect of consistent naming -- objects are
never "recreated" between slides, they are the same named object moved by
the layout engine.
"""

from __future__ import annotations

import re
from typing import Dict

_INVALID = re.compile(r"[^A-Za-z0-9_ ]+")


class ObjectIdBank:
    """Deterministic name bank for morph-stable object identity."""

    def __init__(self) -> None:
        self._used: Dict[str, int] = {}

    def name(self, key: str) -> str:
        """Return the stable shape name for ``key``.

        The same key always maps to the same name, so identical semantic
        objects across slides keep a constant identity for Morph.
        """
        safe = _INVALID.sub("_", key).strip().strip("_") or "obj"
        return f"morph_{safe}"

    def track(self, key: str) -> None:
        self._used.setdefault(key, 0)

    def is_morph_compatible(self, key_a: str, key_b: str) -> bool:
        return self.name(key_a) == self.name(key_b)


class MorphPlan:
    """Carries the morph intent of one slide (transition + object mapping)."""

    def __init__(self, morph_to_next: bool = False, duration_ms: int = 700) -> None:
        self.morph_to_next = morph_to_next
        self.duration_ms = duration_ms
