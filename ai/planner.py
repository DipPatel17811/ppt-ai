"""Planner: the entry point for turning a brief into a Presentation AST.

Two strategies are provided:

* ``ai`` - a HuggingFace model emits a strict-JSON AST (validated & repaired
  against the schema);
* ``deterministic`` - a rule-based planner produces a professional,
  topic-aware executive deck offline (used for tests, demos and when
  torch/transformers are not installed).

``Planner`` is a facade that selects between them.
"""

from __future__ import annotations

from typing import List, Optional

from config import LLM_DEFAULT_MODEL
from schema import (
    AgendaSlide,
    BulletItem,
    BulletsSlide,
    ComparisonColumn,
    ComparisonSlide,
    ConclusionSlide,
    DashboardSlide,
    MetricCard,
    Presentation,
    ProcessSlide,
    RoadmapPhase,
    RoadmapSlide,
    SemanticAnimation,
    TimelineItem,
    TimelineSlide,
    TitleSlide,
    TransitionDirection,
    TransitionKind,
    TransitionSpec,
)


class DeterministicPlanner:
    """Rule-based offline planner producing a clean executive deck."""

    def build(self, topic: str, sections: Optional[List[str]] = None,
              tone: str = "professional") -> Presentation:
        sections = sections or ["title", "agenda", "overview", "process",
                                "roadmap", "dashboard", "comparison", "conclusion"]
        slides = []
        for section in sections:
            builder = getattr(self, f"_section_{section}", None)
            if builder is None:
                continue
            slides.append(builder(topic))
        return Presentation(
            title=topic,
            theme="corporate",
            slides=slides,
            meta={"title": topic},
        )

    # -- sections --------------------------------------------------------
    def _section_title(self, topic: str) -> TitleSlide:
        return TitleSlide(
            type="title",
            kicker="Executive Briefing",
            title=topic,
            subtitle=f"Strategic overview · 2026 outlook for {topic.lower()}",
            presenter="Strategy Office",
            date="2026",
            tags=["Strategy", "Growth", "Execution"],
            animation=SemanticAnimation.EXECUTIVE_REVEAL,
        )

    def _section_agenda(self, topic: str) -> AgendaSlide:
        return AgendaSlide(
            type="agenda",
            kicker="Agenda",
            title="What we will cover",
            items=[
                "Market context and why now",
                "Strategic priorities",
                "Operating model and process",
                "Execution roadmap",
                "Key metrics and decision points",
            ],
            animation=SemanticAnimation.EXECUTIVE_REVEAL,
        )

    def _section_overview(self, topic: str) -> BulletsSlide:
        return BulletsSlide(
            type="bullets",
            kicker="Context",
            title="Why {topic} is a priority".format(topic=topic),
            intro="The environment is shifting faster than the market can absorb.",
            bullets=[
                BulletItem(text="Customer expectations are rising across every channel", icon="trend"),
                BulletItem(text="New entrants are compressing margins and cycle times", icon="users"),
                BulletItem(text="Technology costs are falling while capability gaps widen", icon="gear"),
                BulletItem(text="We have the assets and the mandate to move now", icon="check"),
            ],
            animation=SemanticAnimation.EXECUTIVE_REVEAL,
        )

    def _section_process(self, topic: str) -> ProcessSlide:
        return ProcessSlide(
            type="process",
            kicker="Approach",
            title="How we will execute",
            subtitle="A disciplined, stage-gated operating rhythm",
            steps=["Discover", "Design", "Build", "Launch", "Scale", "Optimize"],
            animation=SemanticAnimation.PROCESS_BUILD,
        )

    def _section_roadmap(self, topic: str) -> RoadmapSlide:
        return RoadmapSlide(
            type="roadmap",
            kicker="Roadmap",
            title="The next twelve months",
            intro="Staged delivery with clear decision gates between phases.",
            phases=[
                RoadmapPhase(name="Foundation", period="Q1", status="done",
                             items=["Baseline assessment", "Target operating model"]),
                RoadmapPhase(name="Build", period="Q2", status="current",
                             items=["Pilot capabilities", "Data foundation"]),
                RoadmapPhase(name="Scale", period="Q3", status="next",
                             items=["Rollout by segment", "Change enablement"]),
                RoadmapPhase(name="Embed", period="Q4", status="planned",
                             items=["Continuous improvement", "Benefits capture"]),
            ],
            animation=SemanticAnimation.TIMELINE,
        )

    def _section_dashboard(self, topic: str) -> DashboardSlide:
        return DashboardSlide(
            type="dashboard",
            kicker="Scorecard",
            title="Leading indicators",
            subtitle="How we will know we are winning",
            metrics=[
                MetricCard(label="Momentum", value="Strong", delta="+18%", delta_good=True, icon="trend"),
                MetricCard(label="Adoption", value="On track", delta="+9%", delta_good=True, icon="users"),
                MetricCard(label="Cost to serve", value="Improving", delta="-6%", delta_good=True, icon="gear"),
                MetricCard(label="Risk", value="Contained", delta="Stable", delta_good=True, icon="shield"),
            ],
            bullets=[
                BulletItem(text="Review scorecard monthly at exec committee"),
                BulletItem(text="Escalate any red flag within 48 hours"),
                BulletItem(text="Owner assigned for each metric"),
            ],
            animation=SemanticAnimation.DASHBOARD_FOCUS,
        )

    def _section_comparison(self, topic: str) -> ComparisonSlide:
        return ComparisonSlide(
            type="comparison",
            kicker="Options",
            title="Choosing the path forward",
            context="Two realistic paths were assessed against strategic fit, cost and risk.",
            left=ComparisonColumn(
                heading="Incremental",
                subheading="Low ambition, low risk",
                icon="shield",
                points=[
                    "Minimal disruption to operations",
                    "Slow but steady capability gain",
                    "Harder to attract talent",
                    "Risk of being outplayed by competitors",
                ],
            ),
            right=ComparisonColumn(
                heading="Transformational",
                subheading="High ambition, managed risk",
                icon="rocket",
                points=[
                    "Clear strategic differentiation",
                    "Faster learning and compounding gains",
                    "Stronger talent pull",
                    "Requires disciplined execution",
                ],
            ),
            bottom_line="Recommended: a phased transformational path.",
            animation=SemanticAnimation.COMPARE,
        )

    def _section_timeline(self, topic: str) -> TimelineSlide:
        return TimelineSlide(
            type="timeline",
            kicker="Milestones",
            title="Critical milestones",
            items=[
                TimelineItem(label="M1", title="Program launch", detail="Steering committee established"),
                TimelineItem(label="M2", title="Pilot live", detail="First customer cohort onboarded"),
                TimelineItem(label="M3", title="Full rollout", detail="All segments active"),
                TimelineItem(label="M4", title="Benefits review", detail="Hard savings validated"),
            ],
            animation=SemanticAnimation.TIMELINE,
        )

    def _section_conclusion(self, topic: str) -> ConclusionSlide:
        return ConclusionSlide(
            type="conclusion",
            kicker="Next steps",
            title="The decision in front of us",
            takeaways=[
                "The window for action is now — waiting costs more than acting",
                "A phased, measurable plan de-risks the transformation",
                "We have the assets, mandate and leadership to win",
                "We ask for approval to mobilise the program",
            ],
            cta="Approve the plan",
            quote="Bold is a decision, not a description.",
            animation=SemanticAnimation.EXECUTIVE_REVEAL,
        )


class Planner:
    """Facade that picks the planning strategy."""

    def __init__(self, mode: str = "auto",
                 generator=None,
                 model_name: Optional[str] = None) -> None:
        self.mode = mode
        self.generator = generator
        self.model_name = model_name

    def plan(self, topic: str, sections: Optional[List[str]] = None,
             tone: str = "professional") -> Presentation:
        mode = self.mode
        if mode == "ai":
            gen = self._ensure_generator()
            return gen.generate_ast(topic, sections, tone)
        if mode == "deterministic":
            return DeterministicPlanner().build(topic, sections, tone)
        # auto
        if self._ai_available():
            gen = self._ensure_generator()
            try:
                return gen.generate_ast(topic, sections, tone)
            except Exception:
                pass
        return DeterministicPlanner().build(topic, sections, tone)

    def _ensure_generator(self):
        if self.generator is not None:
            return self.generator
        from ai.json_generator import JSONGenerator
        self.generator = JSONGenerator(model_name=self.model_name or LLM_DEFAULT_MODEL)
        return self.generator

    @staticmethod
    def _ai_available() -> bool:
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            return True
        except Exception:
            return False


# Convenience API
def plan(topic: str, mode: str = "auto", **kwargs) -> Presentation:
    return Planner(mode=mode).plan(topic, **kwargs)
