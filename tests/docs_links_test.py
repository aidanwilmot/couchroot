"""Offline doc-checker regressions; fixtures never depend on the checkout index."""
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location('check_docs', Path(__file__).resolve().parents[1]/'scripts/check-docs.py')
docs = importlib.util.module_from_spec(spec); spec.loader.exec_module(docs)


class DocsLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
    def write(self, name, text):
        path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    def check(self):
        return docs.check(self.root, {p.relative_to(self.root) for p in self.root.rglob('*') if p.is_file()})
    def test_repository_links_and_index(self):
        # web-and-offline already runs this discovery suite; do not edit the
        # workflow currently owned by the pending platform PR.
        subprocess.run([sys.executable, str(docs.ROOT/"scripts/check-docs.py")], check=True, cwd=docs.ROOT)
    def test_relative_links_reference_links_images_and_html_anchors(self):
        self.write('README.md', '# Start\n[doc](docs/a.md#hello--world)\n![art](image%20one.svg)\n[ref][guide]\n[guide]: docs/a.md#hello--world-1\n<a href="page.html#spot">page</a>\n')
        self.write('docs/README.md', '[a](a.md)\n')
        self.write('docs/a.md', '# Hello — world\n# Hello — world\n[back](../README.md#start)\n')
        self.write('page.html', '<h2 id="spot">Here</h2><a href="README.md#start">back</a>')
        self.write('image one.svg', '<svg/>')
        self.assertEqual(self.check(), [])
        self.write('page.html', '<a href="README.md#absent">broken</a><img src="missing.png">')
        errors = '\n'.join(self.check()); self.assertIn('missing anchor', errors); self.assertIn('missing target', errors)
    def test_missing_files_and_unindexed_docs_fail_independently(self):
        self.write('README.md', '[lost](missing.md)\n')
        self.write('docs/README.md', '# Index\n')
        self.write('docs/new.md', '# New\n')
        errors = '\n'.join(self.check()); self.assertIn('missing target', errors); self.assertIn('unindexed document: docs/new.md', errors)
    def test_code_comments_external_urls_and_site_routes_are_not_repo_links(self):
        self.write('README.md', '# Guide\n```md\n[example](not-real.md)\n```\n<!-- [old](removed.md) -->\n`[uep][bash] across\nlines`\n[remote](https://example.invalid/no.md#x) [route](/app)\n')
        self.assertEqual(self.check(), [])
    def test_setext_duplicates_explicit_anchors_and_balanced_paths(self):
        self.write('README.md', 'Title\n=====\n# Title\n<a id="explicit"></a>\n[one](#title) [two](#title-1) [three](#explicit) [file](a(b).md#child)\n')
        self.write('a(b).md', '# Child\n')
        self.assertEqual(self.check(), [])
    def test_source_line_anchors_must_exist(self):
        self.write('README.md', '[source](tool.py#L1-L2)')
        self.write('tool.py', 'a = 1\nb = 2\n')
        self.assertEqual(self.check(), [])
        self.write('README.md', '[source](tool.py#L99)')
        self.assertIn('invalid file anchor', self.check()[0])
    def test_unrecognized_generated_asset_is_not_ignored(self):
        self.write('index.html', '<script src="missing.js"></script>')
        self.assertIn('missing target', self.check()[0])
    def test_index_requires_actual_link_not_plain_text_mention(self):
        self.write('docs/README.md', '`guide.md` is not a link.\n')
        self.write('docs/guide.md', '# Guide')
        self.assertIn('unindexed document', self.check()[0])


if __name__ == '__main__': unittest.main()
