"""Offline syntax and repository-root checks; parses source without importing it."""
import ast
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROOT_NAMES = {'repo', 'root', 'REPO', 'ROOT'}
# Entry points that drive devices; they must parse even though no test imports them.
DEVICE_ENTRY_POINTS = ('tools/qn90a/root-check.py', 'tools/qn90a/home-integration.py',
                       'tools/qn90a/home-route.py', 'tools/qn90a/cast.py',
                       'tools/qn90a/screensaver.py', 'tools/qn90a/cleanup.py',
                       'tools/qn90a/trim.py', 'tools/s90d/restore.py', 'tools/s90d/splash.py',
                       'native-hub/cards/cards.py')


def python_sources():
    try:
        listed = subprocess.run(['git', 'ls-files', '-z', '--', '*.py'], cwd=ROOT, check=True,
                                capture_output=True).stdout.decode().split('\0')
        return sorted(ROOT / name for name in listed if name)
    except (OSError, subprocess.CalledProcessError):
        return sorted(p for p in ROOT.rglob('*.py') if 'node_modules' not in p.parts)


def file_parents(node):
    """Return N for Path(__file__)[.resolve()].parents[N], otherwise None."""
    if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
            and node.value.attr == 'parents' and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, int)):
        return None
    base = node.value.value
    if (isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute)
            and base.func.attr == 'resolve' and not base.args):
        base = base.func.value
    if (isinstance(base, ast.Call) and isinstance(base.func, ast.Name) and base.func.id == 'Path'
            and len(base.args) == 1 and isinstance(base.args[0], ast.Name)
            and base.args[0].id == '__file__'):
        return node.slice.value
    return None


class RepositoryPaths(unittest.TestCase):
    def setUp(self):
        self.sources = python_sources()

    def test_every_tracked_python_file_parses(self):
        names = {p.relative_to(ROOT).as_posix() for p in self.sources}
        self.assertTrue(set(DEVICE_ENTRY_POINTS) <= names, set(DEVICE_ENTRY_POINTS) - names)
        errors = []
        for path in self.sources:
            try:
                ast.parse(path.read_bytes(), filename=str(path))
            except SyntaxError as error:
                errors.append(f'{path.relative_to(ROOT)}:{error.lineno}: {error.msg}')
        self.assertEqual(errors, [])

    def test_repository_root_names_resolve_to_this_checkout(self):
        checked, wrong = 0, []
        for path in self.sources:
            try:
                tree = ast.parse(path.read_bytes(), filename=str(path))
            except SyntaxError:
                continue  # reported by the parse test
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                if not any(isinstance(t, ast.Name) and t.id in ROOT_NAMES for t in node.targets):
                    continue
                depth = file_parents(node.value)
                if depth is None:
                    continue
                checked += 1
                parents = path.resolve().parents
                if depth >= len(parents) or parents[depth] != ROOT:
                    wrong.append(f'{path.relative_to(ROOT)}:{node.lineno}: parents[{depth}]')
        self.assertEqual(wrong, [])
        self.assertGreaterEqual(checked, 10)


if __name__ == '__main__':
    unittest.main()
