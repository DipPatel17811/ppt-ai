"""PowerPoint *Morph* transition writer.

A Morph transition requires:

1. the ``mc:AlternateContent`` wrapper with a ``p14`` choice containing a
   ``p:transition`` with a ``p14:morph`` child;
2. stable, deterministic shape *names* across consecutive slides so that
   PowerPoint can match objects and interpolate them (handled by the
   ``morph`` module at the root level -- see ``ObjectIdBank``).
"""

from __future__ import annotations

import uuid

from lxml import etree

from ppt.xml_writer import find_children, insert_in_slide_order, new_element


def apply_morph_transition(slide_element, duration_ms: int = 700,
                           discrete: bool = False) -> None:
    """Attach a Morph transition to the slide being *entered*."""
    for el in find_children(slide_element, "p", "transition"):
        slide_element.remove(el)

    alternate = new_element("mc", "AlternateContent")

    choice = new_element("mc", "Choice", {"Requires": "p14"})
    transition = new_element("p", "transition", {"spd": "slow"})
    p14_uri = "http://schemas.microsoft.com/office/powerpoint/2010/main"
    transition.set(f"{{{p14_uri}}}dur", str(duration_ms))
    morph = new_element("p14", "morph", {"id": str(uuid.uuid4())})
    if discrete:
        morph.set(f"{{{p14_uri}}}discrete", "1")
    transition.append(morph)
    choice.append(transition)

    fallback = new_element("mc", "Fallback")
    fallback.append(new_element("p", "transition", {"spd": "slow"}))

    alternate.append(choice)
    alternate.append(fallback)

    insert_in_slide_order(slide_element, alternate)
