"""Product code must never read source inputs from the research tree."""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from tvsetup import planner

ROOT = Path(__file__).resolve().parents[1]
TREES = ('tvsetup', 'scripts', '.github', 'agent', 'telemetry', 'tools', 'native',
         'native-hub', 'launchers', 'setup')
TYPES = ('.py', '.sh', '.yml', '.yaml', '.json', '.cs', '.csproj', '.cjs', '.js', '.c', '.h')
RESEARCH = re.compile(r'''(?<![\w-])research/|\.\./research(?=['"])|['"]research['"]''')
EVIDENCE = {'telemetry/byte-identity.json', 'telemetry/agent-byte-identity.json',
            'telemetry/product-byte-identity.json'}


def violations(root):
    files = [p for tree in TREES for p in (root/tree).rglob('*')]
    files += [p for p in root.iterdir() if p.is_file() and not p.name.startswith('.') and (p.suffix in ('.py', '.sh', '.js', '.cjs') or not p.suffix)]
    result = []
    for path in files:
        relative = path.relative_to(root)
        if not path.is_file() or {'bin', 'obj', '__pycache__', 'node_modules'} & set(relative.parts):
            continue
        if path.suffix and path.suffix not in TYPES:
            continue
        try:
            text = path.read_text()
        except UnicodeError:
            continue
        # These are compiler debug-name labels, not source lookup paths. Strip
        # only the mapping value, so a second reference on that line still fails.
        text = re.sub(r'<PathMap>[^<]*</PathMap>', '', text)
        text = re.sub(r'(-ffile-prefix-map=\S+=)/src/research/[^\s]+', r'\1CANONICAL', text)
        for number, line in enumerate(text.splitlines(), 1):
            # Historical before/after labels in the three recorded comparisons
            # do not open files. Other keys and all other JSON remain scanned.
            if relative.as_posix() in EVIDENCE:
                line = re.sub(r'"(?:before|after)":\s*"[^"]*"', '', line)
            if RESEARCH.search(line):
                result.append(f'{relative}:{number}')
    return result


def revision_research_files():
    files = planner.source_files()
    files += [p for kind in ('boot', 'service', 'helper', 'saver') for p in planner.component_files(kind)]
    return [p for p in files if p.relative_to(planner.REPO).parts[0] == 'research']


class ProductBoundaryTests(unittest.TestCase):
    def test_no_research_paths_in_any_product_tree(self):
        self.assertEqual(violations(ROOT), [])

    def test_revision_input_sets_never_include_research(self):
        self.assertEqual(revision_research_files(), [])

    def test_mutated_paths_and_segments_are_detected(self):
        mutations = ["REPO/'research'/name", "REPO.joinpath('research', name)",
                     "Path(REPO, 'research', name)", "os.path.join(root, 'research', name)",
                     "require('../research/module')", 'sh research/build.sh',
                     "Path('prefix/../research')"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for tree in TREES:
                (root/tree).mkdir()
                for extension in TYPES + ('',):
                    path = root/tree/('entry'+extension)
                    for mutation in mutations:
                        with self.subTest(tree=tree, extension=extension, mutation=mutation):
                            path.write_text(mutation)
                            self.assertEqual(violations(root), [f'{tree}/entry{extension}:1'])
                    path.unlink()
            for extension in ('.py', '.sh', '.js', '.cjs', ''):
                path = root/('entry'+extension)
                path.write_text("Path('research')")
                self.assertEqual(violations(root), [f'entry{extension}:1'])
                path.unlink()

    def test_revision_set_mutations_are_detected(self):
        bad = ROOT/'research/accidental.c'
        with patch.object(planner, 'source_files', return_value=[bad]):
            self.assertIn(bad, revision_research_files())
        with patch.object(planner, 'component_files', return_value=[bad]):
            self.assertIn(bad, revision_research_files())
