"""Offline discovery: fake responses only, no TV/SDB/toolkit access."""
import contextlib
import io
import json
import unittest
from unittest.mock import Mock, MagicMock, patch
from urllib.error import URLError

from tvsetup import cli, installer, survey, ui_deploy
from tvsetup.common import Refused
from tvsetup.config import profile


def identity(device='s90d'):
    p = profile(device)
    return {'modelName': p['model'], 'model': p['platform'], 'developerMode': '1',
            'developerIP': '192.0.2.24', 'id': 'synthetic-private-identity',
            'duid': '-'.join(('synthetic', 'private', 'duid')), 'name': 'synthetic-private-name',
            'network': {'mac': 'synthetic-private-mac'}, 'token': 'synthetic-private-token'}


class SurveyTests(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = installer.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_all_verdicts_and_no_support_inference(self):
        for device in ('qn90a', 's90d'):
            data = identity(device)
            exact = survey.describe(data)
            self.assertEqual(exact['verdict'], 'exact_model')
            self.assertEqual(exact['nearest_profile'], device)
            self.assertFalse(exact['firmware_verified'])
            self.assertFalse(exact['installation_authorized'])
            data['modelName'] = 'QN55S90CAFXZA'
            data['model'] = '_'.join(data['model'].split('_')[:2]) + '_DIFFERENT'
            family = survey.describe(data)
            self.assertEqual(family['verdict'], 'same_platform_family')
            self.assertEqual(family['nearest_profile'], device)
            data['model'] = '23_PTM_QD_T09'
            self.assertEqual(survey.describe(data)['verdict'], 'unknown')
        for value in ('24', '24_PTM', '24_PT', '24_PTMX_QD_T09', 'PTM_QD_T09'):
            self.assertEqual(survey.describe({**identity(), 'modelName': 'QN55S90CAFXZA', 'model': value})['verdict'], 'unknown')

    def test_redaction_in_human_and_json_output(self):
        data = identity()
        for flag in ([], ['--json']):
            with patch.object(survey, 'read_identity', return_value=data), patch('tvsetup.toolkit.load') as toolkit, patch('tvsetup.site.load_site') as site:
                code, out, err = self.invoke(['survey', 'tv.example.invalid', *flag])
            self.assertEqual(code, 0)
            for secret in ('192.0.2.24', 'tv.example.invalid', 'synthetic-private-identity', 'synthetic-private-duid', 'synthetic-private-name', 'synthetic-private-mac', 'synthetic-private-token'):
                self.assertNotIn(secret, out + err)
            toolkit.assert_not_called()
            site.assert_not_called()
        # Even malformed display fields cannot leak an identifier.
        for key in ('modelName', 'model'):
            for private in ('uuid:00000000-0000-4000-8000-000000000001', '192.0.2.25', 'synthetic-private-token', '<script>'):
                self.assertNotIn(private, json.dumps(survey.describe({**data, key: private})))
        data['id'] = data['modelName']
        self.assertNotEqual(survey.describe(data)['verdict'], 'exact_model')

    def test_developer_fields_reuse_toolkit_semantics_without_host_output(self):
        for mode, expected in ((1, 'enabled'), ('1', 'enabled'), (0, 'disabled'), (None, 'unknown'), (True, 'unknown')):
            result = survey.describe({**identity(), 'developerMode': mode})
            self.assertEqual(result['developer_mode']['mode'], expected)
            self.assertEqual(result['developer_mode']['host'], 'configured (redacted)')
        self.assertEqual(survey.describe({})['developer_mode'], {'mode': 'unknown', 'host': 'unknown'})

    def test_http_is_single_bounded_get_without_proxy_or_redirect(self):
        response = Mock()
        response.read.return_value = json.dumps({'device': identity()}).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch.object(survey, 'build_opener', return_value=opener) as build:
            self.assertEqual(survey.read_identity('192.0.2.20'), identity())
        opener.open.assert_called_once_with('http://192.0.2.20:8001/api/v2/', timeout=5)
        response.read.assert_called_once_with(65537)
        self.assertEqual(build.call_args.args[0].proxies, {})
        with self.assertRaisesRegex(Refused, 'redirected'):
            build.call_args.args[1].redirect_request(None)

    def test_bad_responses_and_network_errors_are_redacted(self):
        for raw in (b'x' * 65537, b'[]', b'{}', b'{"device":[]}', b'not-json', b'\xff'):
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.read.return_value = raw
            with patch.object(survey, 'build_opener', return_value=opener), self.assertRaises(Refused):
                survey.read_identity('tv.example.invalid')
        with patch.object(survey, 'build_opener') as opener:
            opener.return_value.open.side_effect = URLError('private destination and token')
            code, out, err = self.invoke(['survey', 'tv.example.invalid', '--json'])
        self.assertEqual(code, 1)
        self.assertNotIn('private destination', out + err)
        self.assertIn('unavailable', json.loads(out)['error'])
        for host in ('http://tv.example.invalid', 'user@tv.example.invalid', 'tv.example.invalid:80', 'tv.example.invalid/path', 'tv\n.invalid', '224.0.0.1'):
            with patch.object(survey, 'build_opener') as opener, self.assertRaises(Refused):
                survey.read_identity(host)
            opener.assert_not_called()

    def test_all_front_door_argparse_device_choices_stay_exact(self):
        for module in (cli, installer, ui_deploy):
            parser = module.parser()
            subcommands = next(action for action in parser._actions if hasattr(action, 'choices') and isinstance(action.choices, dict))
            for command in subcommands.choices.values():
                device = next((action for action in command._actions if action.dest == 'device'), None)
                if device:
                    self.assertEqual(tuple(device.choices), ('qn90a', 's90d'))

    def test_unsupported_survey_succeeds_but_installer_device_set_is_unchanged(self):
        with patch.object(survey, 'read_identity', return_value={'modelName': 'QN77S89CBFXZA', 'model': '23_PTM_QD_T09'}):
            code, out, _ = self.invoke(['survey', '192.0.2.20', '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['verdict'], 'unknown')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            installer.main(['plan', '--device', 's89c', '--launcher', 'web'])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
