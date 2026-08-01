"""Slide transition writer (fade / push / wipe / none)."""

from __future__ import annotations

from typing import Optional

from lxml import etree

from ppt.xml_writer import find_children, insert_in_slide_order, new_element

_DIR_MAP = {
    "left": "l",
    "right": "r",
    "up": "u",
    "down": "d",
}

_TRANSITION_TAGS = {"transition", "extLst"}


def _remove_existing(slide_element) -> None:
    for el in find_children(slide_element, "p", "transition"):
        slide_element.remove(el)


def apply_transition(slide_element, kind: str, duration_ms: int = 600,
                     direction: Optional[str] = None) -> None:
    """Attach a transition to a slide element (the transition happens when
    *entering* this slide)."""
    if not kind or kind == "none":
        return
    _remove_existing(slide_element)

    transition = new_element("p", "transition", {"spd": "slow" if duration_ms > 800 else "mid"})
    transition.set("{http://schemas.microsoft.com/office/powerpoint/2010/main}dur", str(duration_ms))

    if kind == "fade":
        new_element("p", "fade")
        transition.append(new_element("p", "fade"))
    elif kind in ("push", "wipe"):
        transition.append(new_element("p", kind, {"dir": _DIR_MAP.get(direction or "left", "l")}))
    else:  # fall back to fade
        transition.append(new_element("p", "fade"))

    insert_in_slide_order(slide_element, transition)
