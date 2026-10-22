"""Pin the unchanged shell guards to their pre-onboarding source at 62dcced."""

import ast
import hashlib
import unittest

from tvsetup.common import REPO


class GuardRegressionTests(unittest.TestCase):
    def test_ast_located_guard_definitions_are_byte_identical_to_original(self):
        expected = {
            "identity_guard": "315d3a00939c251436ec3cf945cbde0ece57d472ca78e331a5280725f8e9f266",
            "managed_guard": "723a205b0f7542c871b239f82f4ddad254fa9dfb10f10db8786177cd4bc7baf8",
            "hash_guard": "1a49535a936f86b11017aa1fbd3f3314f0290845acb43c1a67028b6d6c6da161",
        }
        source = (REPO / "tvsetup/transport.py").read_text()
        found = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name in expected:
                self.assertNotIn(node.name, found)
                definition = ast.get_source_segment(source, node)
                found[node.name] = hashlib.sha256(definition.encode()).hexdigest()
        self.assertEqual(found, expected)


if __name__ == "__main__":
    unittest.main()
