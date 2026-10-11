import unittest
import xml.etree.ElementTree as ET

from scripts.prepare_qn90a_d2tv_trial import (
    APP_NS, APP_ID, BASE_VERSION, METADATA_KEY, METADATA_VALUE, PACKAGE,
    WIDGET_NS, parse_config, snapshot_payload, transform_config,
)
from tvsetup.common import Refused


CONFIG = b'''<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://www.w3.org/ns/widgets" xmlns:tizen="http://tizen.org/ns/widgets" id="https://local.invalid/minimal-tv-hub" version="0.4.11" viewmodes="maximized">
  <tizen:application id="MiniHub001.Hub" package="MiniHub001" required_version="6.0"/>
  <content src="index.html"/>
  <name>Minimal Hub</name>
  <icon src="icon.png"/>
  <tizen:metadata key="http://samsung.com/tv/metadata/use.network" value="false"/>
</widget>
'''


class D2TVPackageTrialTests(unittest.TestCase):
    def test_trial_changes_only_version_and_adds_exact_d2tv_entry(self):
        before = ET.fromstring(CONFIG)
        output = transform_config(CONFIG, '0.4.12', True)
        after, entries = parse_config(output)
        self.assertEqual(after.get('version'), '0.4.12')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].get('key'), METADATA_KEY)
        self.assertEqual(entries[0].get('value'), METADATA_VALUE)
        self.assertEqual(len(before.findall(f'{{{APP_NS}}}metadata')), 1)
        self.assertEqual(len(after.findall(f'{{{APP_NS}}}metadata')), 2)
        self.assertIn(b'<tizen:metadata key="http://samsung.com/tv/metadata/D2TV" value="ISPBound"/>', output)
        self.assertEqual(output.count(b'version="0.4.12"'), 1)
        self.assertEqual(output.count(b'version="0.4.11"'), 0)

    def test_inverse_has_forward_version_and_no_d2tv_metadata(self):
        output = transform_config(CONFIG, '0.4.13', False)
        root, entries = parse_config(output)
        self.assertEqual(root.get('version'), '0.4.13')
        self.assertEqual(entries, [])
        self.assertIn(b'key="http://samsung.com/tv/metadata/use.network" value="false"', output)
        self.assertNotIn(METADATA_KEY.encode(), output)

    def test_rejects_unexpected_base_metadata_or_identity(self):
        already_bound = CONFIG.replace(b'</widget>', b'<tizen:metadata key="'+METADATA_KEY.encode()+b'" value="ISPBound"/></widget>')
        with self.assertRaisesRegex(Refused, 'already contains D2TV'):
            transform_config(already_bound, '0.4.12', True)
        wrong_app = CONFIG.replace(b'package="MiniHub001"', b'package="Other"')
        with self.assertRaisesRegex(Refused, 'identity'):
            transform_config(wrong_app, '0.4.12', True)
        with self.assertRaises(Refused):
            transform_config(CONFIG, '0.4.12.1', True)

    def test_snapshot_requires_exact_qn90a_installed_package_and_config_hash(self):
        digest = 'a'*64
        snapshot = {
            'device': 'qn90a',
            'packages': [[PACKAGE, APP_ID, 'wgt', BASE_VERSION, 'true', 'false', 'false', 'false']],
            'files': {
                '/opt/usr/apps/MiniHub001/res/wgt/config.xml': digest,
                '/opt/usr/apps/MiniHub001/res/wgt/index.html': digest,
                '/opt/usr/apps/MiniHub001/res/wgt/hub.js': digest,
                '/opt/usr/apps/Other/res/wgt/config.xml': 'b'*64,
            },
        }
        result = snapshot_payload(snapshot)
        self.assertEqual(set(result), {'config.xml', 'index.html', 'hub.js'})
        snapshot['device'] = 's90d'
        with self.assertRaisesRegex(Refused, 'pinned QN90A'):
            snapshot_payload(snapshot)


if __name__ == '__main__':
    unittest.main()
