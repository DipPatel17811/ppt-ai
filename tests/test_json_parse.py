"""Strict JSON parsing / coercion tests (ai.validator)."""

import os
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

    def test_repair_missing_comma_before_literal_keyword(self):
        raw = ('{"title":"Deck","slides":[{"type":"bullets","title":"X",'
               '"bullets":[{"text":"a","highlight":true "level":1}]}]}')
        ast = strict_parse(raw)
        bullets = [s for s in ast.slides if s.type == "bullets"][0]
        self.assertEqual(bullets.bullets[0].text, "a")
        self.assertTrue(bullets.bullets[0].highlight)
        self.assertEqual(bullets.bullets[0].level, 1)

    def test_repair_missing_comma_after_literal_keyword(self):
        raw = ('{"title":"Deck","slides":[{"type":"bullets","title":"X",'
               '"bullets":[{"text":"a","icon":"star","highlight":false "level":2}]}]}')
        ast = strict_parse(raw)
        bullets = [s for s in ast.slides if s.type == "bullets"][0]
        self.assertFalse(bullets.bullets[0].highlight)
        self.assertEqual(bullets.bullets[0].level, 2)

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

    def test_repair_missing_slide_open_brace_after_agenda(self):
        # Qwen drops the ``{`` of every slide after the agenda: ``]},"type":...``
        raw = ('{"title":"Deck","slides":['
               '{"type":"agenda","title":"Agenda","items":["One"]},'
               '"type":"timeline","title":"T","items":["Now"]},'
               '"type":"bullets","title":"B","bullets":["x"]}]}')
        ast = strict_parse(raw)
        self.assertEqual([s.type for s in ast.slides],
                         ["agenda", "timeline", "bullets"])

    def test_coerce_comparison_comparisons_columns(self):
        raw = ('{"title":"Deck","slides":[{"type":"comparison","title":"C",'
               '"comparisons":[{"left":{"name":"Old","description":"Slow and costly"}},'
               '{"right":{"name":"New","description":"Fast and cheap"}}]}]}')
        ast = strict_parse(raw)
        comp = [s for s in ast.slides if s.type == "comparison"][0]
        self.assertEqual(comp.left.heading, "Old")
        self.assertEqual(comp.left.points, ["Slow and costly"])
        self.assertEqual(comp.right.heading, "New")
        self.assertEqual(comp.right.points, ["Fast and cheap"])

    def test_coerce_timeline_events_to_items(self):
        raw = ('{"title":"Deck","slides":[{"type":"timeline","title":"T",'
               '"events":[{"date":"2023-01-01","event":"Kick off"},'
               '{"date":"2023-06-01","event":"Ship it","description":"GA"}]}]}')
        ast = strict_parse(raw)
        tl = [s for s in ast.slides if s.type == "timeline"][0]
        self.assertEqual(tl.items[0].label, "2023-01-01")
        self.assertEqual(tl.items[0].title, "Kick off")
        self.assertEqual(tl.items[1].detail, "GA")

    def test_coerce_agenda_topic_items(self):
        raw = ('{"title":"Deck","slides":[{"type":"agenda","title":"Agenda",'
               '"items":[{"topic":"Intro","duration":"30"},'
               '{"topic":"Roadmap","duration":"45"}]}]}')
        ast = strict_parse(raw)
        agenda = [s for s in ast.slides if s.type == "agenda"][0]
        self.assertEqual(agenda.items, ["Intro", "Roadmap"])

    def test_repair_echoed_deck_truncated_first_value(self):
        # The model echoes the whole deck but the first deck is cut off
        # (missing its closing ``}``) because generation hit the token cap.
        deck = ('{"title":"Deck","slides":['
                '{"type":"agenda","title":"Agenda","items":["One","Two"]},'
                '{"type":"bullets","title":"B","bullets":["x"]}]')
        ast = strict_parse(deck + "\n" + deck + "}")
        self.assertEqual(ast.title, "Deck")
        self.assertEqual(len(ast.slides), 2)


class QwenRealOutputTests(unittest.TestCase):
    """The exact Colab output that used to fail must repair end-to-end."""

    FIXTURE = os.path.join(os.path.dirname(__file__), "data", "failed_output.txt")

    @classmethod
    def setUpClass(cls):
        with open(cls.FIXTURE, encoding="utf-8") as fh:
            cls.ast = strict_parse(fh.read())

    def test_parses_full_real_output(self):
        self.assertEqual(len(self.ast.slides), 10)
        self.assertEqual(self.ast.title, "Digital Transformation")

    def test_agenda_bullet_items_coerced(self):
        agenda = [s for s in self.ast.slides if s.type == "agenda"][0]
        self.assertTrue(all(isinstance(i, str) for i in agenda.items))
        self.assertTrue(any("Introduction" in i for i in agenda.items))

    def test_timeline_date_events_coerced(self):
        tl = [s for s in self.ast.slides if s.type == "timeline"][0]
        self.assertEqual(tl.items[0].label, "2023-01-01")
        self.assertEqual(tl.items[0].title, "Discovery Phase")

    def test_roadmap_phases_truncated(self):
        rm = [s for s in self.ast.slides if s.type == "roadmap"][0]
        self.assertLessEqual(len(rm.phases), 5)
        self.assertEqual(rm.phases[0].name, "Phase 1: Discovery")
        self.assertEqual(rm.phases[0].items, ["Task A", "Task B", "Task C"])

    def test_cycle_phases_renamed_to_stages(self):
        cy = [s for s in self.ast.slides if s.type == "cycle"][0]
        self.assertEqual(len(cy.stages), 6)

    def test_hierarchy_levels_become_root_children(self):
        hi = [s for s in self.ast.slides if s.type == "hierarchy"][0]
        self.assertEqual(hi.root.name, "Hierarchy of Needs")
        self.assertEqual(hi.root.children[0].name, "Leadership Buy-In")
        self.assertEqual(hi.root.children[0].role, "Level 1")

    def test_dashboard_metrics_coerced(self):
        db = [s for s in self.ast.slides if s.type == "dashboard"][0]
        self.assertEqual(db.metrics[0].label, "Revenue Growth Rate")
        self.assertEqual(db.metrics[0].value, "+7%")

    def test_swot_analysis_rows_split_into_quadrants(self):
        sw = [s for s in self.ast.slides if s.type == "swot"][0]
        self.assertIn("Strong brand reputation", sw.strengths.items)
        self.assertIn("Competition from emerging players", sw.threats.items)

    def test_conclusion_takeaway_text_and_cta(self):
        co = [s for s in self.ast.slides if s.type == "conclusion"][0]
        self.assertTrue(all(isinstance(t, str) for t in co.takeaways))
        self.assertTrue(co.cta.startswith("Stay informed"))


class QwenRound3OutputTests(unittest.TestCase):
    """Second Colab deck: merged dashboard+swot slide, missing slide braces,
    an unclosed comparison element and sibling hero/agenda objects."""

    FIXTURE = os.path.join(os.path.dirname(__file__), "data", "failed_output2.txt")

    @classmethod
    def setUpClass(cls):
        with open(cls.FIXTURE, encoding="utf-8") as fh:
            cls.ast = strict_parse(fh.read())

    def test_parses_full_real_output(self):
        self.assertEqual(len(self.ast.slides), 11)
        self.assertEqual(self.ast.title, "Digital Transformation")

    def test_merged_dashboard_and_swot_split(self):
        types = [s.type for s in self.ast.slides]
        self.assertIn("dashboard", types)
        self.assertIn("swot", types)
        self.assertLess(types.index("dashboard"), types.index("swot"))

    def test_dashboard_metrics_coerced(self):
        db = [s for s in self.ast.slides if s.type == "dashboard"][0]
        self.assertEqual(db.metrics[0].label, "Customer Satisfaction Score")
        self.assertEqual(db.metrics[0].value, "90")

    def test_swot_rows_keyed_by_wrong_quadrant(self):
        sw = [s for s in self.ast.slides if s.type == "swot"][0]
        self.assertIn("Lack of internal expertise in digital technologies",
                      sw.weaknesses.items)
        self.assertIn("Competition from established players", sw.threats.items)
        self.assertIn("Expanding global reach through digital platforms",
                      sw.opportunities.items)

    def test_cycle_cycles_become_stages(self):
        cy = [s for s in self.ast.slides if s.type == "cycle"][0]
        self.assertEqual(cy.stages, ["Analyze current state", "Identify pain points",
                                     "Set clear vision and priorities"])

    def test_hierarchy_levels_become_children(self):
        hi = [s for s in self.ast.slides if s.type == "hierarchy"][0]
        self.assertEqual(hi.root.name, "Leadership Hierarchy")
        self.assertEqual(hi.root.children[0].name, "CEO")
        self.assertEqual(hi.root.children[0].role, "Chief Executive Officer")

    def test_agenda_topic_items_coerced(self):
        agenda = [s for s in self.ast.slides if s.type == "agenda"][0]
        self.assertEqual(len(agenda.items), 5)
        self.assertIn("Introduction to Digital Transformation", agenda.items)

    def test_roadmap_phases_coerced(self):
        rm = [s for s in self.ast.slides if s.type == "roadmap"][0]
        self.assertEqual([p.name for p in rm.phases],
                         ["Discovery", "Design", "Build", "Launch"])

    def test_timeline_date_events_coerced(self):
        tl = [s for s in self.ast.slides if s.type == "timeline"][0]
        self.assertEqual(tl.items[0].label, "2023-01-01")
        self.assertEqual(tl.items[0].title,
                         "Initiate digital transformation initiative")

    def test_conclusion_takeaway_text_and_cta(self):
        co = [s for s in self.ast.slides if s.type == "conclusion"][0]
        self.assertEqual(len(co.takeaways), 4)
        self.assertEqual(co.cta, "Ready to take action?")


if __name__ == "__main__":
    unittest.main()
