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


class JsonRepairTests(unittest.TestCase):
    def test_repair_missing_comma_between_slides(self):
        raw = ('{"title":"Deck","slides":['
               '{"type":"title","title":"A"} '
               '{"type":"title","title":"B"}]}')
        ast = strict_parse(raw)
        self.assertEqual(len(ast.slides), 2)

    def test_repair_missing_comma_between_bullets(self):
        raw = ('{"title":"Deck","slides":[{"type":"bullets","title":"B",'
               '"bullets":["one" "two"]}]}')
        ast = strict_parse(raw)
        bullets = [s for s in ast.slides if s.type == "bullets"][0]
        self.assertEqual([b.text for b in bullets.bullets], ["one", "two"])

    def test_repair_missing_comma_after_number(self):
        raw = '{"title":"Deck","slides":[{"type":"bullets","title":"B",' \
              '"bullets":[{"text":"a","level":0} {"text":"b","level":1}]}]}'
        ast = strict_parse(raw)
        bullets = [s for s in ast.slides if s.type == "bullets"][0]
        self.assertEqual(len(bullets.bullets), 2)

    def test_repair_trailing_comma(self):
        raw = '{"title":"Deck","slides":[{"type":"title","title":"A",}]}'
        ast = strict_parse(raw)
        self.assertEqual(len(ast.slides), 1)

    def test_repair_truncated_deck(self):
        raw = ('{"title":"Deck","slides":['
               '{"type":"title","title":"A"},'
               '{"type":"title","title":"B"}')
        ast = strict_parse(raw)
        self.assertEqual(len(ast.slides), 2)

    def test_repair_truncated_mid_slide(self):
        raw = ('{"title":"Deck","slides":['
               '{"type":"title","title":"A"},'
               '{"type":"title","title":"B"},'
               '{"type":"bullets"')
        ast = strict_parse(raw)
        self.assertEqual(len(ast.slides), 2)

    def test_repair_truncated_inside_unterminated_string(self):
        raw = '{"title":"Deck","slides":[{"type":"title","title":"A"},' \
              '{"type":"title","title":"Unfinished'
        ast = strict_parse(raw)
        self.assertEqual(len(ast.slides), 1)
        self.assertEqual(ast.slides[0].title, "A")

    def test_repair_truncated_before_any_closing_brace(self):
        raw = '{"title":"Deck","slides":[{"type":"title","title":"Unfinished'
        with self.assertRaises(JSONParseError) as ctx:
            strict_parse(raw)
        self.assertIn("slides.0.title", ctx.exception.message)

    def test_repair_extra_data_after_deck(self):
        raw = ('{"title":"Deck","slides":[{"type":"title","title":"A"}]}'
               '{"title":"Junk"}')
        ast = strict_parse(raw)
        self.assertEqual(ast.title, "Deck")
        self.assertEqual(len(ast.slides), 1)

    def test_repair_extra_data_large_echoed_deck(self):
        deck = ('{"title":"Deck","theme":"corporate","slides":['
                '{"type":"title","title":"A","subtitle":"s"},'
                '{"type":"agenda","title":"Agenda","items":["One","Two","Three"]},'
                '{"type":"bullets","title":"B","bullets":[{"text":"one"},{"text":"two"}]},'
                '{"type":"process","title":"P","steps":["a","b","c","d"]}]}')
        raw = deck + deck
        ast = strict_parse(raw)
        self.assertEqual(ast.title, "Deck")
        self.assertEqual(len(ast.slides), 4)

    def test_repair_extra_data_after_deck_with_trailing_prose_brace(self):
        raw = ('{"title":"Deck","slides":[{"type":"title","title":"A"}]}'
               'That wraps up the deck }')
        ast = strict_parse(raw)
        self.assertEqual(ast.title, "Deck")

    def test_repair_single_quotes(self):
        raw = "{'title':'Deck','slides':[{'type':'title','title':'Hello'}]}"
        ast = strict_parse(raw)
        self.assertEqual(ast.title, "Deck")

    def test_repair_preserves_apostrophe_text(self):
        raw = ('{"title":"Deck","slides":[{"type":"bullets","title":"B",'
               '"bullets":[{"text":"It\'s a great plan"}]}]}')
        ast = strict_parse(raw)
        bullets = [s for s in ast.slides if s.type == "bullets"][0]
        self.assertEqual(bullets.bullets[0].text, "It's a great plan")

    def test_repair_failure_preserves_original_error(self):
        with self.assertRaises(JSONParseError) as ctx:
            strict_parse("{ this is not json")
        self.assertIn("Expecting", ctx.exception.message)
        self.assertNotIn("schema", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
