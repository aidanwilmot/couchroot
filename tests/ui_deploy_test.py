"""UI scope, check failures, shared recovery, and preference preservation."""
import contextlib
import copy
import io
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tvsetup import cli, ui_deploy
from tvsetup.common import Refused, atomic_json, read_json
from tvsetup.config import profile, resolve
from tvsetup.engine import Engine
from tvsetup.planner import Action, Plan
from tv_setup_engine_test import FakeDriver
from tv_setup_planner_test import accepted


class UIDeployTests(unittest.TestCase):
    def test_dry_run_is_offline_even_for_apply(self):
        with patch.object(ui_deploy, 'setup_main') as setup, patch.object(ui_deploy.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ui_deploy.main(['apply', '--device', 'qn90a', '--dry-run', '--launch']), 0)
            setup.assert_not_called(); run.assert_not_called()

    def test_failed_or_interrupted_checks_never_inspect_a_device(self):
        for result in (SimpleNamespace(returncode=1), OSError('missing npm'), subprocess.TimeoutExpired('npm', 300)):
            with self.subTest(result=result), patch.object(ui_deploy, 'setup_main') as setup, patch.object(ui_deploy.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                if isinstance(result, Exception): run.side_effect = result
                else: run.return_value = result
                self.assertEqual(ui_deploy.main(['apply', '--device', 's90d', '--yes']), 1)
                setup.assert_not_called()

    def test_apply_checks_source_and_passes_explicit_launch(self):
        with patch.object(ui_deploy, 'setup_main', return_value=0) as setup, patch.object(ui_deploy.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(ui_deploy.main(['apply', '--device', 's90d', '--yes', '--launch']), 0)
            self.assertEqual(run.call_args.args[0], ['npm', 'test'])
            setup.assert_called_once_with(['apply', '--device', 's90d', '--yes', '--non-interactive', '--activate'], ui_only=True)

    def test_recovery_does_not_require_node_or_expand_scope(self):
        with patch.object(ui_deploy, 'setup_main', return_value=3) as setup, patch.object(ui_deploy.subprocess, 'run') as run:
            self.assertEqual(ui_deploy.main(['rollback', '--device', 'qn90a', '--run', 'saved', '--yes']), 3)
            setup.assert_called_once_with(['rollback', '--device', 'qn90a', '--yes', '--non-interactive', '--run', 'saved'], ui_only=True)
            run.assert_not_called()

    def test_scope_rejects_other_components_packages_and_artifact_overrides(self):
        choices = resolve('s90d', overrides={'components': ['hub']})
        cli.ui_scope(choices, [Action('hub', 'hub', 'package', None, {}, {'package': 'MiniHub001'})])
        for action in (Action('x', 'home', 'setting', None, 1, {}), Action('x', 'hub', 'package', None, {}, {'package': 'OtherApp'})):
            with self.assertRaises(Refused): cli.ui_scope(choices, [action])
        with self.assertRaises(Refused): cli.ui_scope({**choices, 'artifacts': {'hub': '/old.wgt'}})
        with self.assertRaises(Refused): cli.ui_scope(resolve('s90d'))

    def test_ui_launch_uses_only_app_commands_on_both_models_and_checks_foreground(self):
        with tempfile.TemporaryDirectory() as tmp:
            for device in ('s90d', 'qn90a'):
                tv = Mock(); tv.snapshot.return_value = {'settings': {'memory/appfw/current_fullscreen_appid': 'MiniHub001.Hub'}}
                driver = SimpleNamespace(profile=profile(device), tv=tv)
                cli.activate(driver, {'scope': 'ui'}, Path(tmp)/'journal.json')
                tv.root.assert_not_called(); tv.sdk.assert_called_once()
                self.assertIn('app_launcher -s MiniHub001.Hub', tv.sdk.call_args.args[0])
                tv.snapshot.return_value = {'settings': {}}
                with self.assertRaisesRegex(Refused, 'foreground not confirmed'):
                    cli.activate(driver, {'scope': 'ui'}, Path(tmp)/'journal.json')

    def test_full_setup_run_is_rejected_before_recovery_transport(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, 'STATE', Path(tmp)), patch.object(cli, 'load_site', return_value={}), patch.object(cli, 'configured_profile', return_value=profile('s90d')), patch.object(cli, 'binding', return_value='same'), patch.object(cli, 'Transport') as transport, contextlib.redirect_stderr(io.StringIO()):
            atomic_json(Path(tmp)/'runs/other/journal.json', {'device': 's90d', 'scope': 'setup'})
            self.assertEqual(cli.main(['rollback', '--device', 's90d', '--run', 'other', '--yes'], ui_only=True), 1)
            transport.assert_not_called()

    def test_missing_hub_requires_initial_setup_before_signing(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, 'STATE', Path(tmp)), patch.object(cli, 'load_site', return_value={}), patch.object(cli, 'configured_profile', return_value=profile('s90d')), patch.object(cli, 'binding', return_value='same'), patch.object(cli, 'Transport') as transport, patch.object(cli, 'Driver') as driver, contextlib.redirect_stderr(io.StringIO()):
            state = accepted('s90d'); state['packages'] = []
            transport.return_value.snapshot.return_value = state
            self.assertEqual(cli.main(['apply', '--device', 's90d', '--yes'], ui_only=True), 1)
            driver.assert_not_called()

    def test_apply_ignores_saved_component_selection_and_keeps_global_choices(self):
        class HubDriver:
            def __init__(self, tv, *args): self.tv = tv
            def snapshot(self): return copy.deepcopy(self.tv.state)
            def prepare(self, action): return {}
            def backup(self, action, info, state): return info
            def execute(self, action, info, state): self.tv.state['files'].update(action.after)
            def verify(self, action, before, after):
                assert all(after['files'][p] == h for p, h in action.after.items())

        for device, launch in (('s90d', False), ('qn90a', False), ('s90d', True), ('qn90a', True)):
            with self.subTest(device=device, launch=launch), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                saved = {'components': ['dashboard', 'cleanup'], 'exclude': ['hub'], 'artifacts': {'hub': '/old.wgt'}}
                atomic_json(root/(device+'-choices.json'), saved)
                tv = Mock(); tv.state = accepted(device)
                target = '/opt/usr/apps/MiniHub001/res/wgt/style.css'
                tv.state['files'][target] = 'old-style'
                tv.snapshot.side_effect = lambda **kwargs: copy.deepcopy(tv.state)
                with patch.object(cli, 'STATE', root), patch.object(cli, 'load_site', return_value={}), patch.object(cli, 'configured_profile', return_value=profile(device)), patch.object(cli, 'binding', return_value='same'), patch.object(cli, 'Transport', return_value=tv), patch.object(cli, 'Driver', HubDriver), patch.object(cli, 'NAS') as nas, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    arguments = ['apply', '--device', device, '--yes'] + (['--activate'] if launch else [])
                    self.assertEqual(cli.main(arguments, ui_only=True), 1 if launch else 0)
                    self.assertEqual(read_json(root/(device+'-choices.json')), saved)
                    doc = read_json(next((root/'runs').glob('*/journal.json')))
                    self.assertEqual(doc['scope'], 'ui'); self.assertEqual(doc['phase'], 'complete')
                    self.assertEqual([r['action']['options']['package'] for r in doc['actions']], ['MiniHub001'])
                    self.assertEqual(doc['choices']['artifacts'], {})
                    if launch:
                        self.assertIn('uncertain', doc['activation'])
                        tv.sdk.assert_called_once()
                        tv.root.assert_not_called()
                    nas.return_value.check_pairing.assert_not_called(); nas.return_value.add_plan.assert_not_called()

    def test_finalization_resume_preserves_choices_and_updates_ledger(self):
        for saved in (None, {'components': ['startup', 'hub'], 'telemetry_enabled': False}):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root/'s90d-choices.json'
                if saved is not None: atomic_json(path, saved)
                driver = FakeDriver()
                engine = Engine(driver, root/'runs/ui', 's90d', {'components': ['hub']}, state_dir=root, scope='ui')
                engine.start(Plan('s90d', actions=[Action('1', 'hub', 'file', None, 'new', {'path': '/test'})]), driver.snapshot())
                with patch('tvsetup.engine.atomic_json', side_effect=OSError('disk full')):
                    with self.assertRaises(OSError): engine.finalize()
                resumed = Engine(None, engine.folder, 's90d', engine.choices, state_dir=root)
                resumed.load(); resumed.finalize()
                self.assertEqual(read_json(path), saved)
                self.assertEqual(read_json(root/'s90d-ledger.json')['files'], {'/test': 'new'})
                resumed.driver = driver; resumed.rollback()
                self.assertEqual(read_json(path), saved)
                self.assertIsNone(read_json(root/'s90d-ledger.json'))


if __name__ == '__main__': unittest.main()
