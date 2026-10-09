"""Semantic rendering contracts; no inferred grading or changes to authored source."""
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs


class Tree(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.nodes, self.stack = [], []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'parent': self.stack[-1] if self.stack else None}
        self.nodes.append(node)
        if tag not in {'input', 'br', 'hr', 'img', 'meta', 'link'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1]['tag'] == tag:
            self.stack.pop()

    def tagged(self, tag):
        return [n for n in self.nodes if n['tag'] == tag]


class SemanticRenderingTests(unittest.TestCase):
    def test_document_shell_separates_metadata_and_keeps_content_order(self):
        state = {'schema_version': 1, 'session_id': 'shell-fixture', 'type': 'tutor-session',
                 'title': 'Lesson', 'source_markdown': '# Lesson\n\n## Concept\n\nUnchanged prose.',
                 'metadata': {'created': '2026-10-09', 'subtitle': '<script>Context</script>'},
                 'lifecycle': 'active', 'questions': [], 'events': [], 'open_questions': []}
        markup = hs.render_html(state)
        tree = Tree(markup)
        self.assertEqual(len(tree.tagged('h1')), 1)
        header = tree.tagged('header')[0]
        self.assertEqual(header['attrs']['class'], 'ros-session-header')
        self.assertIn('ros-session-meta', markup)
        self.assertIn('Active · 2026-10-09', markup)
        self.assertNotIn('<script>Context</script>', markup)
        self.assertIn('&lt;script&gt;Context&lt;/script&gt;', markup)
        self.assertLess(markup.index('</header>'), markup.index('Unchanged prose.'))
        self.assertEqual(state['source_markdown'], '# Lesson\n\n## Concept\n\nUnchanged prose.')

    def test_lists_are_semantic_and_nested_inside_parent_item(self):
        markup = hs.markdown_html('- Parent\n  - Child\n    1. Grandchild\n- Second\n\n3. Third\n4. Fourth')
        tree = Tree(markup)
        self.assertEqual(len(tree.tagged('ul')), 2)
        self.assertEqual(len(tree.tagged('ol')), 2)
        self.assertEqual(len(tree.tagged('li')), 6)
        self.assertEqual(tree.tagged('ul')[1]['parent']['tag'], 'li')
        self.assertEqual(tree.tagged('ol')[0]['parent']['tag'], 'li')
        self.assertEqual(tree.tagged('ol')[1]['attrs']['start'], '3')
        self.assertNotIn('ros-list-item', markup)
        self.assertFalse(tree.stack)

    def test_indented_paragraph_and_post_list_prose_remain_separate(self):
        markup = hs.markdown_html('1. First\n   continued\n2. Second\nOutside the list.\n\nNext paragraph.')
        self.assertIn('First continued', markup)
        self.assertIn('</ol>\n<p>Outside the list.</p>', markup)
        self.assertIn('<p>Next paragraph.</p>', markup)

    def test_callout_groups_title_body_list_and_formula(self):
        markup = hs.markdown_html('> [!info] How this session works\n> Body *emphasis*.\n>\n> - One\n> - Two\n\n> [!formula] Matrix\n> $$\n> \\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}\n> $$')
        tree = Tree(markup)
        self.assertEqual(len(tree.tagged('aside')), 2)
        self.assertIn('ros-callout-info', markup)
        self.assertIn('ros-callout-header">How this session works', markup)
        self.assertNotIn('[!info]', markup)
        self.assertNotIn('<blockquote', markup)
        self.assertIn('<em>emphasis</em>', markup)
        self.assertIn('\\begin{pmatrix}1&amp;0\\\\0&amp;1\\end{pmatrix}', markup)
        self.assertFalse(tree.stack)

    def test_disclosures_and_plain_quotations_are_distinct(self):
        markup = hs.markdown_html('> [!hint]- Think first\n> Hint.\n\n> [!example]+ Worked example\n> Explanation.\n\n> A real quotation.\n> Continued quotation.')
        tree = Tree(markup)
        self.assertEqual(len(tree.tagged('details')), 2)
        self.assertNotIn('open', tree.tagged('details')[0]['attrs'])
        self.assertIn('open', tree.tagged('details')[1]['attrs'])
        self.assertEqual(len(tree.tagged('blockquote')), 1)
        self.assertIn('A real quotation. Continued quotation.', markup)

    def test_single_page_title_and_duplicate_heading_anchors(self):
        markup = hs.markdown_html('# Lesson\n\n## Definition\n\n## Definition\n\n# Appendix', page_title='Lesson')
        tree = Tree(markup)
        self.assertEqual(len(tree.tagged('h1')), 0)
        self.assertEqual(len(tree.tagged('h2')), 3)
        ids = [n['attrs']['id'] for n in tree.nodes if 'id' in n['attrs']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('section-' + hs._hash(b'Lesson')[:12], ids)

    def test_frontmatter_does_not_become_document_content(self):
        markup = hs.markdown_html('---\ntype: tutor-session\nsecret_label: metadata-only\n---\n# Lesson\n\nContent')
        self.assertNotIn('metadata-only', markup)
        self.assertNotIn('type:', markup)

    def test_soft_and_explicit_hard_line_breaks(self):
        markup = hs.markdown_html('Wrapped\nprose.\n\nExplicit  \nbreak.')
        self.assertIn('<p>Wrapped prose.</p>', markup)
        self.assertIn('<p>Explicit<br>break.</p>', markup)
        self.assertIn('<p>Explicit<br>break.</p>', hs.markdown_html('Explicit\\\nbreak.'))

    def test_code_inside_emphasis_and_literal_math_are_preserved(self):
        markup = hs.markdown_html('**Use `x`** and _intuition_ with $a**b**$.\n\n```python\nprint("<x>")\n```')
        self.assertIn('<strong>Use <code>x</code></strong>', markup)
        self.assertIn('<em>intuition</em>', markup)
        self.assertIn('data-tex="a**b**"', markup)
        self.assertIn('data-language="python"', markup)
        self.assertIn('print(&quot;&lt;x&gt;&quot;)', markup)

    def test_tasks_are_recorded_disabled_checks_without_events(self):
        markup = hs.markdown_html('- [x] Completed\n- [ ] Pending')
        checks = Tree(markup).tagged('input')
        self.assertEqual(len(checks), 2)
        self.assertTrue(all('disabled' in n['attrs'] for n in checks))
        self.assertIn('checked', checks[0]['attrs'])
        self.assertNotIn('checked', checks[1]['attrs'])

    def test_raw_html_remains_escaped_and_unterminated_fences_survive(self):
        markup = hs.markdown_html('<script>attack()</script>\n\n```\nlegacy')
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)
        self.assertIn('data-ros="legacy"', markup)
        self.assertIn('legacy', markup)


if __name__ == '__main__':
    unittest.main()
