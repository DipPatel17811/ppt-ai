"""Semantic animation engine.

Templates describe *what* should happen ("the process steps build in one by
one"), never *how* in OOXML terms.  This module maps semantic animations
(``process_build``, ``executive_reveal``, ...) to an ordered list of
primitive per-shape effects that the ``ppt.animations`` writer then renders
into PowerPoint's timing XML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from schema import SemanticAnimation


@dataclass
class ShapeEffect:
    """A primitive animation for one shape, keyed by its semantic key."""

    target: str
    effect: str = "fade"  # appear | fade | fly_up | fly_left | fly_right | zoom | wipe
    delay_ms: int = 0
    duration_ms: int = 500


@dataclass
class AnimationPlan:
    """Ordered list of primitive effects resolved from a semantic animation."""

    semantic: SemanticAnimation = SemanticAnimation.NONE
    effects: List[ShapeEffect] = field(default_factory=list)

    def has_effects(self) -> bool:
        return bool(self.effects)


def _build(keys: List[str], effect: str, step_ms: int, duration_ms: int = 500) -> List[ShapeEffect]:
    out: List[ShapeEffect] = []
    for i, key in enumerate(keys):
        out.append(ShapeEffect(target=key, effect=effect,
                               delay_ms=i * step_ms, duration_ms=duration_ms))
    return out


#: Default per-semantic-animation choreography.  Keys match the object keys
#: registered by templates via ``SlideBuilder.register``.
DEFAULT_PLANS: Dict[SemanticAnimation, Dict[str, object]] = {
    SemanticAnimation.EXECUTIVE_REVEAL: {
        "order": ["kicker", "title", "subtitle", "content"],
        "effect": "fade",
        "step_ms": 300,
    },
    SemanticAnimation.PROCESS_BUILD: {
        "order": ["title", "step_0", "step_1", "step_2", "step_3", "step_4", "step_5", "step_6", "step_7"],
        "effect": "fly_up",
        "step_ms": 250,
    },
    SemanticAnimation.DASHBOARD_FOCUS: {
        "order": ["title", "metric_0", "metric_1", "metric_2", "metric_3", "metric_4", "metric_5"],
        "effect": "zoom",
        "step_ms": 250,
    },
    SemanticAnimation.COMPARE: {
        "order": ["title", "col_left", "col_right", "bottom_line"],
        "effect": "fly_left",
        "step_ms": 300,
    },
    SemanticAnimation.TIMELINE: {
        "order": ["title", "item_0", "item_1", "item_2", "item_3", "item_4", "item_5", "item_6", "item_7"],
        "effect": "fly_left",
        "step_ms": 250,
    },
}


def plan_for(semantic: Optional[SemanticAnimation], registered: Dict[str, int]) -> AnimationPlan:
    """Resolve a semantic animation into a concrete plan.

    ``registered`` maps semantic keys to their PowerPoint ``spid`` values.
    Effects whose keys were never registered are skipped so we never animate
    a phantom shape.
    """
    semantic = semantic or SemanticAnimation.NONE
    if semantic == SemanticAnimation.NONE:
        return AnimationPlan(semantic=semantic)

    template = DEFAULT_PLANS.get(semantic, DEFAULT_PLANS[SemanticAnimation.EXECUTIVE_REVEAL])
    effects: List[ShapeEffect] = []
    for i, key in enumerate(template["order"]):
        spid = registered.get(key)
        if spid is None:
            continue
        effects.append(ShapeEffect(
            target=key,
            effect=str(template["effect"]),
            delay_ms=i * int(template["step_ms"]),
        ))
    return AnimationPlan(semantic=semantic, effects=effects)
