"""End-to-end render smoke tests: render a deck and validate the .pptx."""

import os
import tempfile
import unittest

from ai.planner import DeterministicPlanner
from renderer import PresentationRenderer
from schema import (
    AgendaSlide,
    BulletsSlide,
    BulletItem,
    ComparisonSlide,
    ComparisonColumn,
    ConclusionSlide,
    CycleSlide,
    DashboardSlide,
    HeroSlide,
    HierarchySlide,
    HierarchyNode,
    MetricCard,
    Presentation,
    ProcessSlide,
    RoadmapPhase,
    RoadmapSlide,
    SwoQuadrant,
    SwoSlide,
    TimelineItem,
    TimelineSlide,
    TitleSlide,
)
from validator import LayoutValidator, validate_presentation


def _full_deck() -> Presentation:
    return Presentation(title="All Templates", theme="royal", slides=[
        TitleSlide(title="Title", subtitle="sub", tags=["a"]),
        HeroSlide(title="Hero", subtitle="sub"),
        AgendaSlide(title="Agenda", items=["One", "Two", "Three"]),
        BulletsSlide(title="Bullets", intro="Intro line.",
                     bullets=[BulletItem(text="A"), BulletItem(text="B"), BulletItem(text="C")]),
        ProcessSlide(title="Process", subtitle="sub",
                     steps=["Discover", "Design", "Build", "Launch", "Optimize"]),
        RoadmapSlide(title="Roadmap", intro="Intro.",
                     phases=[RoadmapPhase(name="P1", status="done", period="Q1", items=["a", "b"]),
                             RoadmapPhase(name="P2", status="current", period="Q2", items=["c"]),
                             RoadmapPhase(name="P3", status="planned", period="Q3", items=["d"])]),
        CycleSlide(title="Cycle", stages=["Assess", "Plan", "Do", "Review"], center_label="core"),
        HierarchySlide(title="Hierarchy",
                       root=HierarchyNode(name="Root", children=[
                           HierarchyNode(name="A", children=[HierarchyNode(name="A1")]),
                           HierarchyNode(name="B")])),
        DashboardSlide(title="Dashboard", subtitle="sub",
                       metrics=[MetricCard(label="M1", value="V1", delta="+1%"),
                                MetricCard(label="M2", value="V2", delta="-1%")],
                       bullets=[BulletItem(text="note")]),
        SwoSlide(title="SWOT", context="ctx",
                 strengths=SwoQuadrant(title="S", items=["a", "b"]),
                 weaknesses=SwoQuadrant(title="W", items=["c"]),
                 opportunities=SwoQuadrant(title="O", items=["d"]),
                 threats=SwoQuadrant(title="T", items=["e"])),
        ComparisonSlide(title="Compare", context="ctx",
                        left=ComparisonColumn(heading="L", subheading="ls", points=["p1", "p2"]),
                        right=ComparisonColumn(heading="R", subheading="rs", points=["p3", "p4"]),
                        bottom_line="Bottom line here."),
        TimelineSlide(title="Timeline",
                      items=[TimelineItem(title="Now", detail="d1"),
                             TimelineItem(title="Q1", detail="d2"),
                             TimelineItem(title="Q2", detail="d3"),
                             TimelineItem(title="Q3", detail="d4")]),
        ConclusionSlide(title="Close", takeaways=["Takeaway one.", "Takeaway two.", "Takeaway three."],
                        quote="A closing quote.", cta="Approve"),
    ])


class RenderSmokeTests(unittest.TestCase):
    def test_all_13_templates_render_and_validate(self):
        ast = _full_deck()
        self.assertTrue(validate_presentation(ast).ok)

        out = os.path.join(tempfile.mkdtemp(), "all.pptx")
        PresentationRenderer().render(ast, out)
        self.assertTrue(os.path.exists(out))

        report = LayoutValidator().validate(out)
        self.assertTrue(report.ok, "\n".join(report.issues))

    def test_deterministic_planner_deck(self):
        ast = DeterministicPlanner().build("Digital Transformation")
        self.assertGreaterEqual(len(ast.slides), 6)
        self.assertTrue(validate_presentation(ast).ok)

        out = os.path.join(tempfile.mkdtemp(), "smoke.pptx")
        PresentationRenderer().render(ast, out)
        report = LayoutValidator().validate(out)
        self.assertTrue(report.ok, "\n".join(report.issues))


if __name__ == "__main__":
    unittest.main()
