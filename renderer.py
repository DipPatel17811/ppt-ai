"""The renderer: turns a validated Presentation AST into an editable .pptx.

This is the deterministic pipeline orchestrator:

    Presentation AST -> theme resolution -> per-slide template render
                      -> footer -> animation -> transition/morph -> save

It performs *no* creative decisions; every step is driven by the AST, the
selected template and the theme.  AI was already finished by the time this
module runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from config import ASPECT_RATIOS, MARGIN_BOTTOM, MARGIN_TOP, MARGIN_X
from morph import ObjectIdBank
from schema import Presentation, TransitionKind
from theme import Theme

from animation import plan_for
from builder import SlideBuilder
from compiler import Compiler
from ppt import animations as ppt_animations
from ppt import morph as ppt_morph
from ppt import transitions as ppt_transitions
from utils.spacing import Padding


class PresentationRenderer:
    """Deterministic AST -> pptx renderer."""

    def __init__(self, compiler: Optional[Compiler] = None,
                 object_ids: Optional[ObjectIdBank] = None) -> None:
        self.compiler = compiler or Compiler()
        self.object_ids = object_ids or ObjectIdBank()

    def render(self, ast: Presentation, out_path: str | Path,
               footer: Optional[str] = None) -> Path:
        from templates import TemplateRegistry  # import after templates registered

        theme = self._resolve_theme(ast)
        self.compiler.create(ast.aspect.value)
        width, height = ASPECT_RATIOS[ast.aspect.value]
        self.compiler.set_core_properties(
            ast.title,
            author=(ast.meta.author if ast.meta else None) or "",
            subject=(ast.meta.subject if ast.meta else None) or "",
        )
        margins = Padding(MARGIN_X, MARGIN_TOP, MARGIN_X, MARGIN_BOTTOM)
        total = len(ast.slides)
        footer_text = footer if footer is not None else (ast.footer or theme.footer_text)

        for index, slide_content in enumerate(ast.slides, start=1):
            pptx_slide = self.compiler.add_slide()
            builder = SlideBuilder(self.compiler, theme, pptx_slide, index, total,
                                   self.object_ids, (width, height), margins)
            template_cls = TemplateRegistry.get(slide_content.type)
            template = template_cls()
            template.render(builder, slide_content)
            if not template.full_bleed:
                builder.footer(footer_text)

            self._apply_animation(builder, pptx_slide, slide_content.animation)
            self._apply_transition(pptx_slide, slide_content.transition)

        out_path = Path(out_path)
        self.compiler.save(out_path)
        return out_path

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _resolve_theme(ast: Presentation) -> Theme:
        if ast.theme_spec is not None:
            return Theme.from_spec(ast.theme_spec)
        return Theme.builtin(ast.theme or "corporate")

    def _apply_animation(self, builder: SlideBuilder, pptx_slide, semantic) -> None:
        plan = plan_for(semantic, builder.registered)
        if not plan.has_effects():
            return
        effects = [
            ppt_animations.Effect(
                spid=builder.registered[e.target],
                effect=e.effect,
                delay_ms=e.delay_ms,
                duration_ms=e.duration_ms,
            )
            for e in plan.effects
        ]
        ppt_animations.apply_animations(self.compiler.slide_element(pptx_slide), effects)

    def _apply_transition(self, pptx_slide, transition) -> None:
        if transition is None or transition.kind == TransitionKind.NONE:
            return
        element = self.compiler.slide_element(pptx_slide)
        if transition.kind == TransitionKind.MORPH:
            ppt_morph.apply_morph_transition(element, duration_ms=transition.duration_ms)
        else:
            ppt_transitions.apply_transition(
                element,
                transition.kind.value,
                transition.duration_ms,
                transition.direction.value if transition.direction else None,
            )
