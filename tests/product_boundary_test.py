"""Production setup/build entry points must not depend on the research tree."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductBoundaryTests(unittest.TestCase):
    def test_no_research_paths_in_setup_build_or_ci(self):
        violations = []
        for folder in ('tvsetup', 'scripts', '.github'):
            for path in (ROOT / folder).rglob('*'):
                if not path.is_file() or {'bin', 'obj', '__pycache__'} & set(path.parts):
                    continue
                if path.suffix not in ('.py', '.sh', '.yml', '.yaml', '.json'):
                    continue
                for number, line in enumerate(path.read_text().splitlines(), 1):
                    if re.search(r"\bresearch(?:/|['\"]\s*/)", line):
                        violations.append(f'{path.relative_to(ROOT)}:{number}')
        self.assertEqual(violations, [], 'Production references to research: ' + ', '.join(violations))
