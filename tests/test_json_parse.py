"""Strict JSON parsing / coercion tests (ai.validator)."""

import unittest

from ai.validator import JSONParseError, strict_parse, try_parse


SAMPLE = {
    "title": "Deck",
    "theme": "royal",
    "slides": [
        {"type": "title", "title": "Hello", "tags": ["a", "b"]},
        {"type": "agenda", "title": "Agenda", "items": ["One", "Two"]},
        {"type": "bullets", "title": "Bullets",
         "bullets": ["plain string bullet", {"text": "dict bullet", "icon": "check"}]},
        {"type": "timeline", "title": "Timeline",
         "items": ["Now", {"title": "Q1", "detail": "x"}]},
        {"type": "process", "title": "Process", "steps": ["A", "B", "C"]},
        {"type": "conclusion", "title": "Close", "takeaways": ["t"]},
    ],
}


class StrictParseTests(unittest.TestCase):
    def test_plain_json(self):
        ast = strict_parse(__import__("json").dumps(SAMPLE))
        self.assertEqual(len(ast.slides), 6)
        self.assertEqual(ast.theme, "royal")

    def test_fenced_json(self):
        raw = "Here is the deck:\n```json\n%s\n```\nEnjoy!" % __import__("json").dumps(SAMPLE)
        ast = strict_parse(raw)
        self.assertEqual(ast.title, "Deck")

    def test_bullets_string_coerced(self):
        ast = strict_parse(__import__("json").dumps(SAMPLE))
        bullets = [s for s in ast.slides if s.type == "bullets"][0]
        self.assertEqual(bullets.bullets[0].text, "plain string bullet")
        self.assertEqual(bullets.bullets[1].icon, "check")

    def test_agenda_items_stay_strings(self):
        ast = strict_parse(__import__("json").dumps(SAMPLE))
        agenda = [s for s in ast.slides if s.type == "agenda"][0]
        self.assertEqual(agenda.items, ["One", "Two"])

    def test_timeline_strings_coerced(self):
        ast = strict_parse(__import__("json").dumps(SAMPLE))
        tl = [s for s in ast.slides if s.type == "timeline"][0]
        self.assertEqual(tl.items[0].title, "Now")
        self.assertEqual(tl.items[1].detail, "x")

    def test_invalid_json_raises(self):
        with self.assertRaises(JSONParseError):
            strict_parse("{ this is not json")

    def test_schema_error_reports_location(self):
        bad = dict(SAMPLE)
        bad["slides"] = [{"type": "title", "title": "x"},
                         {"type": "agenda", "title": "a", "items": [{"oops": 1}]}]
        with self.assertRaises(JSONParseError) as ctx:
            strict_parse(__import__("json").dumps(bad))
        self.assertIn("slides.1.agenda.items.0", str(ctx.exception.message))

    def test_try_parse_returns_errors(self):
        ast, errors = try_parse("not json at all")
        self.assertIsNone(ast)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
