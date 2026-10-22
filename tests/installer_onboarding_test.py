"""New front-door flows exercise only mocked TV responses and temporary files."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tvsetup import installer, onboarding, survey
from tvsetup.config import profile


def identity():
    p = profile('s90d')
    return {'modelName': p['model'], 'model': p['platform'],
            'id': 'uuid:00000000-0000-4000-8000-000000000001',
            'developerMode': '1', 'developerIP': '192.0.2.30'}


class InstallerOnboardingTests(unittest.TestCase):
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = installer.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_survey_report_and_skeleton_use_one_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'report'
            with patch.object(survey, 'read_identity', return_value=identity()) as read:
                code, out, err = self.invoke('survey', '192.0.2.20', '--json', '--report', str(destination), '--profile-skeleton')
            self.assertEqual(code, 0, err)
            read.assert_called_once_with('192.0.2.20')
            self.assertTrue(json.loads(out)['report_written'])
            self.assertEqual(set(p.name for p in destination.iterdir()), {'device-report.json', 'device-report.md', 'profile-skeleton.json'})
            combined = out + err + ''.join(p.read_text() for p in destination.iterdir())
            self.assertNotIn(identity()['id'], combined)
            self.assertNotIn('192.0.2.', combined)

    def test_skeleton_requires_report_before_contact(self):
        with patch.object(survey, 'read_identity') as read, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                installer.main(['survey', '192.0.2.20', '--profile-skeleton'])
        self.assertEqual(error.exception.code, 2)
        read.assert_not_called()

    def test_tv_doctor_is_site_free_and_uses_exit_two_for_missing_checks(self):
        for failed in (False, True):
            with patch.object(onboarding, 'read_identity', return_value=identity()), patch.object(onboarding, '_routed_address', return_value='192.0.2.31' if failed else '192.0.2.30'), patch.object(onboarding.socket, 'create_connection'), patch('tvsetup.site.load_site') as site, patch('tvsetup.toolkit.load') as toolkit:
                code, out, err = self.invoke('doctor', '--tv', '192.0.2.20', '--json')
            self.assertEqual(code, 2 if failed else 0, err)
            self.assertEqual(json.loads(out)['ok'], not failed)
            self.assertIn('192.0.2.31' if failed else '192.0.2.30', out)
            self.assertNotIn('192.0.2.20', out + err)
            self.assertNotIn(identity()['id'], out + err)
            if failed:
                self.assertNotIn(identity()['developerIP'], out + err)
            site.assert_not_called()
            toolkit.assert_not_called()
        for args in (['doctor'], ['doctor', '--device', 's90d'], ['doctor', '--tv', '192.0.2.20', '--launcher', 'web']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                installer.main(args)
            self.assertEqual(error.exception.code, 2)

    def test_tv_doctor_text_and_json_show_computer_address_when_mismatch_or_unknown(self):
        for missing in (False, True):
            for json_output in (False, True):
                with self.subTest(missing_developer_ip=missing, json=json_output):
                    data = identity()
                    if missing:
                        data.pop('developerIP')
                    with patch.object(onboarding, 'read_identity', return_value=data), patch.object(onboarding, '_routed_address', return_value='198.51.100.24'), patch.object(onboarding.socket, 'create_connection'):
                        args = ['doctor', '--tv', '192.0.2.20'] + (['--json'] if json_output else [])
                        code, out, err = self.invoke(*args)
                    self.assertEqual(code, 2, err)
                    self.assertIn("Set Developer Mode's host IP to 198.51.100.24 (this computer)", out)
                    self.assertNotIn(identity()['developerIP'], out + err)
                    self.assertNotIn(identity()['id'], out + err)
                    self.assertNotIn('192.0.2.20', out + err)

    def test_unknown_tv_survey_keeps_all_report_files_with_optional_skeleton(self):
        data = {**identity(), 'modelName': 'QN65S90CAFXZA', 'model': '23_PTM_QD_T09'}
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'report'
            with patch.object(survey, 'read_identity', return_value=data) as read:
                code, out, err = self.invoke('survey', '192.0.2.20', '--json', '--report', str(destination), '--profile-skeleton')
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)['verdict'], 'unknown')
            self.assertTrue(json.loads(out)['report_written'])
            read.assert_called_once_with('192.0.2.20')
            self.assertEqual({p.name for p in destination.iterdir()}, {'device-report.json', 'device-report.md', 'profile-skeleton.json'})
            skeleton = json.loads((destination / 'profile-skeleton.json').read_text())
            self.assertIsNone(skeleton['_diff_against'])
            self.assertEqual(skeleton['diff'], [])
            combined = out + err + ''.join(p.read_text() for p in destination.iterdir())
            self.assertNotIn(identity()['id'], combined)
            self.assertNotRegex(combined, r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')

    def test_init_stores_identity_privately_but_not_in_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'private/site.json'
            with patch.object(onboarding, 'DEFAULT_SITE', destination), patch.object(onboarding, 'read_identity', return_value=identity()):
                code, out, err = self.invoke('init', '192.0.2.20', '--json')
                self.assertEqual(code, 0, err)
                self.assertTrue(json.loads(out)['written'])
                self.assertNotIn(identity()['id'], out + err)
                self.assertNotIn('192.0.2.', out + err)
                self.assertEqual(json.loads(destination.read_text())['devices']['s90d']['device_id'], identity()['id'])
                original = destination.read_bytes()
                code, out, err = self.invoke('init', '192.0.2.20', '--json')
                self.assertEqual(code, 1)
                self.assertEqual(destination.read_bytes(), original)
                self.assertNotIn(identity()['id'], out + err)

    def test_trust_outputs_only_explicit_certificate_fingerprints(self):
        with patch.object(onboarding, '_certificate_der', side_effect=[b'author', b'distributor']), patch.object(onboarding, 'read_identity') as read:
            code, out, err = self.invoke('trust', '--device', 's90d', '--signing-profile', 'OwnerTV', '--author-cert', 'author.pem', '--distributor-cert', 'distributor.pem')
        self.assertEqual(code, 0, err)
        self.assertEqual(set(json.loads(out)['s90d']), {'signing_profile', 'author_cert_sha256', 'distributor_cert_sha256'})
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
