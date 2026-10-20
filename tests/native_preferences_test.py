import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('native_preferences', Path(__file__).parents[1] / 'research/archive/native-hub/import-chromium-state.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativePreferenceTests(unittest.TestCase):
    def key(self, name):
        return module.PREFIX + ('minimal-hub.' + name + '.v1').encode()

    def test_latest_tombstone_prevents_obsolete_table_resurrection(self):
        k = self.key('clock')
        self.assertEqual({}, module.extract_preferences([(k, b'\1' + b'24h', 2, True), (k, b'', 4, False), (k, b'\1' + b'12h', 1, True)]))

    def test_allowlist_origin_and_both_string_encodings(self):
        rows = [(self.key('layout'), b'\1compact', 1, True),
                (self.key('selection'), b'\0' + 'app.id'.encode('utf-16-le'), 2, True),
                (self.key('monitoring-token'), b'\1private', 3, True),
                (module.PREFIX + b'\xffunrelated', b'\1private', 3, True),
                (b'_https://unrelated\0\1minimal-hub.clock.v1', bytes([1]) + b'24h', 4, True)]
        self.assertEqual({'minimal-hub.layout.v1': 'compact', 'minimal-hub.selection.v1': 'app.id'}, module.extract_preferences(rows))

    def test_conflicting_sequences_and_invalid_encoding_fail_closed(self):
        k = self.key('clock')
        for rows in [[(k, bytes([1]) + b'12h', 1, True), (k, bytes([1]) + b'24h', 1, True)],
                     [(k, b'\2invalid', 2, True)], [(k, b'\0x', 3, True)]]:
            with self.assertRaises((ValueError, UnicodeError)):
                module.extract_preferences(rows)


if __name__ == '__main__':
    unittest.main()
