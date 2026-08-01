"""Schema tests: discriminated union, field defaults, content limits."""

import unittest

from pydantic import ValidationError

from schema import (
    AgendaSlide,
    BulletsSlide,
    BulletItem,
    ChartKind,
    ChartSpec,
    Presentation,
    ProcessSlide,
    RoadmapPhase,
    TitleSlide,
)


class DiscriminatedUnionTests(unittest.TestCase):
    def test_title_roundtrip(self):
        ast = Presentation(title="T", slides=[{"type": "title", "title": "Hello"}])
        self.assertEqual(ast.slides[0].type, "title")
        self.assertIsInstance(ast.slides[0], TitleSlide)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValidationError):
            Presentation(title="T", slides=[{"type": "nope", "title": "x"}])

    def test_all_types_in_union(self):
        raw = [
            {"type": "title", "title": "a"},
            {"type": "hero", "title": "b"},
            {"type": "agenda", "title": "c", "items": ["one", "two"]},
            {"type": "bullets", "title": "d", "bullets": [{"text": "x"}]},
            {"type": "comparison", "title": "e",
             "left": {"heading": "L"}, "right": {"heading": "R"}},
            {"type": "timeline", "title": "f",
             "items": [{"title": "Now"}, {"title": "Next"}]},
            {"type": "process", "title": "g", "steps": ["A", "B", "C"]},
            {"type": "roadmap", "title": "h",
             "phases": [{"name": "P1"}]},
            {"type": "cycle", "title": "i", "stages": ["S1", "S2", "S3"]},
            {"type": "hierarchy", "title": "j",
             "root": {"name": "R", "children": [{"name": "C"}]}},
            {"type": "dashboard", "title": "k",
             "metrics": [{"label": "M", "value": "V"}]},
            {"type": "swot", "title": "l",
             "strengths": {"title": "S", "items": ["a"]},
             "weaknesses": {"title": "W", "items": ["b"]},
             "opportunities": {"title": "O", "items": []},
             "threats": {"title": "T", "items": []}},
            {"type": "conclusion", "title": "m", "takeaways": ["t1"]},
        ]
        ast = Presentation(title="All", slides=raw)
        self.assertEqual(len(ast.slides), 13)


class AgendaTests(unittest.TestCase):
    def test_items_are_strings(self):
        ast = Presentation(title="T", slides=[{"type": "agenda", "title": "a",
                                               "items": ["one", "two"]}])
        self.assertEqual(ast.slides[0].items, ["one", "two"])


class LimitTests(unittest.TestCase):
    def test_too_many_bullets_rejected(self):
        with self.assertRaises(ValidationError):
            BulletsSlide(title="t", bullets=[BulletItem(text="b")] * 8)

    def test_bullet_char_limit_reported_by_validator(self):
        from validator import validate_presentation

        ast = Presentation(title="T", slides=[{"type": "bullets", "title": "b",
                                               "bullets": [{"text": "x" * 200}]}])
        report = validate_presentation(ast)
        self.assertFalse(report.ok)

    def test_too_many_steps_rejected(self):
        with self.assertRaises(ValidationError):
            ProcessSlide(title="t", steps=[f"s{i}" for i in range(9)])

    def test_roadmap_status_enum(self):
        RoadmapPhase(name="P", status="current")
        with self.assertRaises(ValidationError):
            RoadmapPhase(name="P", status="bogus")

    def test_chart_series_length_mismatch(self):
        with self.assertRaises(ValidationError):
            ChartSpec(kind=ChartKind.BAR, categories=["A", "B", "C"],
                      series=[{"name": "s", "values": [1, 2]}])


if __name__ == "__main__":
    unittest.main()
