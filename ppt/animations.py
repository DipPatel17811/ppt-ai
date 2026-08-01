"""Entrance-animation writer.

Builds the ``p:timing`` tree that makes PowerPoint animate individual shapes
when a slide appears.  Effects are described semantically (fade, fly, zoom,
...) and this module turns them into the raw timing XML with correct shape
``spid`` references and deterministic timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from lxml import etree

from ppt.xml_writer import insert_in_slide_order, new_element

# presetID / presetSubtype / animEffect filter per entrance effect.
EFFECT_TABLE: dict = {
    "appear": (1, 0, "appear"),
    "fade": (10, 0, "fade"),
    "fly_up": (33, 8, "fly"),
    "fly_left": (33, 1, "fly"),
    "fly_right": (33, 3, "fly"),
    "zoom": (56, 0, "zoom"),
    "wipe": (19, 1, "wipe"),
}


@dataclass
class Effect:
    """One animated shape."""

    spid: int
    effect: str = "fade"
    delay_ms: int = 0
    duration_ms: int = 500


def _build_effect_block(effect: Effect, id_counter: List[int]) -> etree._Element:
    preset, subtype, filter_ = EFFECT_TABLE.get(effect.effect, EFFECT_TABLE["fade"])
    id0 = id_counter[0]
    id_counter[0] += 4

    par = new_element("p", "par")
    cTn = new_element("p", "cTn", {"id": str(id0), "fill": "hold"})
    stCond = new_element("p", "stCondLst")
    stCond.append(new_element("p", "cond", {"delay": str(effect.delay_ms)}))
    cTn.append(stCond)

    child = new_element("p", "childTnLst")
    inner_par = new_element("p", "par")
    effect_cTn = new_element(
        "p",
        "cTn",
        {
            "id": str(id0 + 1),
            "presetID": str(preset),
            "presetClass": "entr",
            "presetSubtype": str(subtype),
            "fill": "hold",
            "nodeType": "clickEffect",
        },
    )
    e_stCond = new_element("p", "stCondLst")
    e_stCond.append(new_element("p", "cond", {"delay": "0"}))
    effect_cTn.append(e_stCond)

    e_child = new_element("p", "childTnLst")

    # 1) make visible
    vis_set = new_element("p", "set")
    bhr = new_element("p", "cBhvr")
    vis_cTn = new_element("p", "cTn", {"id": str(id0 + 2), "dur": "1", "fill": "hold"})
    vc = new_element("p", "stCondLst")
    vc.append(new_element("p", "cond", {"delay": "0"}))
    vis_cTn.append(vc)
    tgt = new_element("p", "tgtEl")
    tgt.append(new_element("p", "spTgt", {"spid": str(effect.spid)}))
    attrs = new_element("p", "attrNameLst")
    attrs.append(new_element("p", "attrName", {"val": "style.visibility"}))
    bhr.append(vis_cTn)
    bhr.append(tgt)
    bhr.append(attrs)
    vis_set.append(bhr)
    vis_to = new_element("p", "to")
    vis_to.append(new_element("p", "strVal", {"val": "visible"}))
    vis_set.append(vis_to)

    # 2) animate the effect
    anim = new_element("p", "animEffect", {"transition": "in", "filter": filter_})
    abhr = new_element("p", "cBhvr")
    anim_cTn = new_element("p", "cTn", {"id": str(id0 + 3), "dur": str(effect.duration_ms)})
    atgt = new_element("p", "tgtEl")
    atgt.append(new_element("p", "spTgt", {"spid": str(effect.spid)}))
    abhr.append(anim_cTn)
    abhr.append(atgt)
    anim.append(abhr)

    e_child.append(vis_set)
    e_child.append(anim)
    effect_cTn.append(e_child)
    inner_par.append(effect_cTn)
    child.append(inner_par)
    cTn.append(child)
    par.append(cTn)
    return par


def apply_animations(slide_element, effects: List[Effect]) -> None:
    """Attach a timing tree to ``slide_element`` for the given effects.

    Effects are ordered and staggered automatically by their ``delay_ms``.
    """
    if not effects:
        return
    for el in list(slide_element):
        if etree.QName(el).localname == "timing":
            slide_element.remove(el)

    effects = sorted(effects, key=lambda e: (e.delay_ms, e.spid))

    timing = new_element("p", "timing")
    tnLst = new_element("p", "tnLst")
    root_par = new_element("p", "par")
    root_cTn = new_element("p", "cTn", {"id": "1", "dur": "indefinite", "restart": "never", "nodeType": "tmRoot"})
    root_child = new_element("p", "childTnLst")
    seq = new_element("p", "seq", {"concurrent": "1", "nextAc": "seek"})
    seq_cTn = new_element("p", "cTn", {"id": "2", "dur": "indefinite", "nodeType": "mainSeq"})
    seq_child = new_element("p", "childTnLst")

    counter = [10]
    for eff in effects:
        seq_child.append(_build_effect_block(eff, counter))

    seq_cTn.append(seq_child)
    seq.append(seq_cTn)

    prev = new_element("p", "prevCondLst")
    prev.append(new_element("p", "cond", {"evt": "onPrev", "delay": "0"}))
    prev_tgt = new_element("p", "tgtEl")
    prev_tgt.append(new_element("p", "sldTgt"))
    prev[-1].append(prev_tgt)

    next_ = new_element("p", "nextCondLst")
    next_.append(new_element("p", "cond", {"evt": "onNext", "delay": "0"}))
    next_tgt = new_element("p", "tgtEl")
    next_tgt.append(new_element("p", "sldTgt"))
    next_[-1].append(next_tgt)

    seq.append(prev)
    seq.append(next_)

    root_child.append(seq)
    root_cTn.append(root_child)
    root_par.append(root_cTn)
    tnLst.append(root_par)
    timing.append(tnLst)

    insert_in_slide_order(slide_element, timing)
