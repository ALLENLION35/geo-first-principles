"""Regression checks for the standalone HTML renderer (standard library only)."""
import importlib.util
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_report", ROOT / "scripts/render_report.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class RenderReportTests(unittest.TestCase):
    def test_bundled_example_keeps_complete_structure(self):
        output = renderer.render(renderer.example_source())
        self.assertEqual(output.count('<section class="module'), 8)
        self.assertEqual(output.count('class="copy"'), 5)
        self.assertEqual(output.count('class="takeaway'), 18)
        self.assertEqual(output.count('<table'), 9)
        self.assertEqual(output.count('<div class="toc-group">'), 8)
        self.assertEqual(output.count('<figure class="visual visual-cards">'), 3)
        self.assertEqual(output.count('<figure class="visual visual-flow">'), 1)
        self.assertIn('allenlion · 1.1', output)
        self.assertNotIn('{{TITLE', output)

    def test_code_headings_do_not_split_sections(self):
        source = '# Report\n\n## One\n\n```markdown\n## Literal heading\n```\n\n## Two\n\nText'
        output = renderer.render(source)
        self.assertEqual(output.count('<section class="module'), 2)
        self.assertIn('<pre><code>## Literal heading</code></pre>', output)

    def test_malformed_link_preserves_label(self):
        output = renderer.inline('[Source](https://[example)')
        self.assertEqual(output, 'Source')

    def test_unsafe_markup_and_links_are_not_executable(self):
        output = renderer.inline('<script>alert(1)</script> [bad](javascript:alert(1))')
        self.assertNotIn('<script>', output)
        self.assertNotIn('href=', output)
        self.assertIn('&lt;script&gt;', output)

    def test_route_rejects_conflicting_states(self):
        with self.assertRaises(ValueError):
            renderer.diagram('geo-route', '{"active":[1],"conditional":[1]}')

    def test_table_rejects_lost_columns(self):
        with self.assertRaises(ValueError):
            renderer.blocks('| A | B |\n| --- | --- |\n| value |')

    def test_sidebar_children_have_unique_existing_targets(self):
        source = '# Report\n\n## One\n\n### Same\n\nFirst detail.\n\n## Two\n\n### Same\n\nSecond detail.'
        class Anchors(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids, self.children = [], []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if 'id' in attrs:
                    self.ids.append(attrs['id'])
                if 'toc-child' in attrs.get('class', '').split():
                    self.children.append(attrs['href'][1:])
        parsed = Anchors()
        parsed.feed(renderer.render(source))
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        self.assertEqual(len(parsed.children), 2)
        self.assertTrue(all(target in parsed.ids for target in parsed.children))

    def test_visual_cards_keep_labels_values_conditions_and_escape_html(self):
        output = renderer.diagram('geo-cards', '{"title":"Costs","items":[{"label":"Income","value":"36000","text":"<script>bad</script>"}],"note":"Not net profit"}')
        self.assertIn('visual-cards', output)
        self.assertIn('36000', output)
        self.assertIn('Not net profit', output)
        self.assertIn('&lt;script&gt;', output)
        self.assertNotIn('<script>', output)

    def test_visual_flow_keeps_all_stages(self):
        output = renderer.diagram('geo-flow', '{"title":"Steps","items":[{"label":"Ask","text":"One question"},{"label":"Save","text":"Keep sources"}],"note":"Illustration"}')
        self.assertEqual(output.count('class="visual-stage"'), 2)
        self.assertIn('Keep sources', output)

    def test_visual_requires_explicit_item_text(self):
        with self.assertRaises(ValueError):
            renderer.diagram('geo-cards', '{"title":"Costs","items":[{"label":"Income"}]}')


if __name__ == '__main__':
    unittest.main()
