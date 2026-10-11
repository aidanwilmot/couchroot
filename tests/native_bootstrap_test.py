"""Boot reconciliation and uncertain submission tests; no TV operations."""
import copy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tvsetup.common import Refused, read_json
from tvsetup.native_bootstrap import (Bootstrap, SCOPE, argv, decision, description,
                                     layout, parse_observation, validate_doc)

BOOT = '00000000-1111-4111-8111-111111111111'
NEXT = '00000000-2222-4222-8222-222222222222'


def journal():
    identity = '20260921T200000Z-test1234'
    return dict(schema=1, scope=SCOPE, run=identity, device='qn90a', expires=2000,
                desired=True, phase='prepared', files={n:'a'*64 for n in
                ('collector','config.json','preferences.json','enabled')}, **layout(identity))


def observation(doc, boot=BOOT, state='active'):
    props = dict(LoadState='loaded', ActiveState=state, SubState='running', MainPID='1234',
                 Description=description(doc), User='5001', Group='100',
                 SmackProcessLabel='User::Pkg::MiniTelemetry', Restart='on-failure', Nice='10',
                 RestartUSec='2s', StartLimitIntervalUSec='1min', StartLimitBurst='3',
                 RuntimeMaxUSec='10min', BindReadOnlyPaths=doc['code'],
                 ExecStart='{ path='+doc['code']+'/collector ; argv[]='+argv(doc)+' ; ignore_errors=no ; }')
    return dict(boot=boot, unit=props)


def absent(boot=BOOT):
    return dict(boot=boot, unit=dict(LoadState='not-found', ActiveState='inactive'))


class ReconcileTests(unittest.TestCase):
    def setUp(self): self.doc = journal()

    def test_first_boot_and_new_boot_create(self):
        self.assertEqual(decision(self.doc, absent(), 1000), 'create')
        self.doc['generation'] = BOOT
        self.assertEqual(decision(self.doc, absent(NEXT), 1000), 'create')

    def test_healthy_reconnect_does_not_launch(self):
        self.doc['generation'] = BOOT
        self.assertEqual(decision(self.doc, observation(self.doc), 1000), 'running')

    def test_host_cannot_undo_explicit_stop_even_after_reboot(self):
        self.doc.update(generation=BOOT, desired=False)
        self.assertEqual(decision(self.doc, absent(NEXT), 1000), 'quiet')
        self.assertEqual(decision(self.doc, observation(self.doc), 1000), 'stop')

    def test_timer_expiry_and_explicit_stop_after_unit_gc_do_not_restart(self):
        self.doc['generation'] = BOOT
        self.assertEqual(decision(self.doc, absent(), 1000), 'quiescent')
        self.assertEqual(decision(self.doc, observation(self.doc, state='inactive'), 1000), 'quiescent')

    def test_rate_limit_is_not_reset_by_host(self):
        self.doc['generation'] = BOOT
        obs = observation(self.doc, state='failed'); obs['unit']['Result'] = 'start-limit-hit'
        self.assertEqual(decision(self.doc, obs, 1000), 'quiescent')

    def test_global_deadline_prevents_new_boot_launch(self):
        self.assertEqual(decision(self.doc, absent(NEXT), 2001), 'quiet')
        self.doc['generation'] = BOOT
        self.assertEqual(decision(self.doc, observation(self.doc), 2001), 'stop')

    def test_existing_foreign_unit_refused_even_when_stopping(self):
        self.doc.update(generation=BOOT, desired=False)
        for field in ('Description','User','Group','Restart','ExecStart','BindReadOnlyPaths',
                      'SmackProcessLabel','StartLimitBurst','RuntimeMaxUSec'):
            with self.subTest(field=field):
                obs = observation(self.doc); obs['unit'][field] = 'foreign'
                with self.assertRaises(Refused): decision(self.doc, obs, 1000)

    def test_unrecorded_unit_refused(self):
        with self.assertRaises(Refused): decision(self.doc, observation(self.doc), 1000)

    def test_paths_and_manifests_cannot_be_retargeted_through_journal(self):
        for field, value in [('base','/opt'),('runtime','/tmp/minimal-telemetry-qn90a'),
                             ('unit','zone-manager'),('expires',float('nan')),('desired','yes')]:
            with self.subTest(field=field):
                doc = copy.deepcopy(self.doc); doc[field] = value
                with self.assertRaises(Refused): validate_doc(doc)
        self.doc['files']['../foreign'] = 'a'*64
        with self.assertRaises(Refused): validate_doc(self.doc)

    def test_partial_observation_cannot_trigger_start(self):
        for text in ('', 'PILOT_BOOT\n'+BOOT+'\nPILOT_UNIT\nLoadState=not-found',
                     'PILOT_BOOT\ninvalid\nPILOT_UNIT\nLoadState=not-found\nPILOT_END'):
            with self.assertRaises(Refused): parse_observation(text)
        value = parse_observation('PILOT_BOOT\n'+BOOT+'\nPILOT_UNIT\nLoadState=not-found\nPILOT_END')
        self.assertEqual(value, dict(boot=BOOT,unit={'LoadState':'not-found'}))


class SubmissionTests(unittest.TestCase):
    def test_target_change_while_waiting_for_lock_is_refused(self):
        from tvsetup.native_bootstrap_trial import locked_run
        before = journal(); after = copy.deepcopy(before); after['device'] = 's90d'
        with patch('tvsetup.native_bootstrap_trial.read_json', side_effect=[before, after]), \
             patch('tvsetup.native_bootstrap_trial.lock', return_value=contextlib.nullcontext()), \
             patch('tvsetup.native_bootstrap_trial.binding') as binding:
            with self.assertRaisesRegex(Refused, 'target changed'):
                with locked_run(before['run'], {}): self.fail('Retargeted journal accepted')
        binding.assert_not_called()

    def test_partial_cleanup_does_not_prevent_stopping_verified_unit(self):
        from unittest.mock import Mock
        doc = journal(); doc['generation'] = BOOT
        with tempfile.TemporaryDirectory() as tmp:
            tv = Mock(); bootstrap = Bootstrap(tv, doc, Path(tmp))
            with patch.object(bootstrap, 'observe', return_value=observation(doc)), \
                 patch.object(bootstrap, 'payload_guards', side_effect=Refused('Payload already removed')):
                bootstrap.stop()
            tv.root.assert_called_once_with('systemctl stop '+doc['unit']+'.service\n')
            self.assertFalse(read_json(Path(tmp)/'journal.json')['desired'])

    def test_offline_stop_or_cleanup_persists_cancellation_before_connecting(self):
        from tvsetup.native_bootstrap_trial import operate
        for command in ('stop', 'cleanup'):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                doc = journal(); folder = Path(tmp)
                with patch('tvsetup.native_bootstrap_trial.locked_run', return_value=contextlib.nullcontext((folder, doc))), \
                     patch('tvsetup.native_bootstrap_trial.configured_profile', return_value={}), \
                     patch('tvsetup.native_bootstrap_trial.Transport', side_effect=RuntimeError('SDK unavailable')):
                    with self.assertRaises(RuntimeError): operate(command, doc['run'], {})
                self.assertFalse(read_json(folder/'journal.json')['desired'])
                self.assertEqual(read_json(folder/'journal.json')['phase'], 'stopping')

    def test_watcher_survives_sdk_runtime_error_without_printing_raw_output(self):
        from tvsetup.native_bootstrap_trial import watch
        identity = journal()['run']
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'runs'/identity; folder.mkdir(parents=True)
            with patch('tvsetup.native_bootstrap_trial.STATE', Path(tmp)), \
                 patch('tvsetup.native_bootstrap_trial.load_site', return_value={}), \
                 patch('tvsetup.native_bootstrap_trial.operate', side_effect=[RuntimeError('private transport output'), {'result':'running'}]) as operation, \
                 patch('time.monotonic', side_effect=[0,0,0,1,1,2]), patch('time.sleep'), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                watch(identity, 2)
            self.assertEqual(operation.call_count, 2)
            self.assertNotIn('private transport output', output.getvalue())
            self.assertIn('private transport output', (folder/'watch-errors.log').read_text())

    def test_lost_reply_does_not_submit_bootstrap_twice(self):
        doc = journal()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)

            class TV:
                def __init__(self): self.started = False; self.writes = []
                def root(self, script):
                    # Intent must be durable before the TV starts anything.
                    saved = read_json(folder/'journal.json')
                    assert saved['generation'] == BOOT and saved['phase'] == 'starting'
                    self.started = True; self.writes.append(script)
                    raise Refused('Simulated lost reply after successful start')

            tv = TV(); bootstrap = Bootstrap(tv, doc, folder)
            with patch.object(bootstrap, 'observe', side_effect=lambda: observation(doc) if tv.started else absent()), patch('time.time', return_value=1000):
                with self.assertRaises(Refused): bootstrap.ensure()
                self.assertEqual(bootstrap.ensure(), 'running')
            self.assertEqual(len(tv.writes), 1)
            script = tv.writes[0]
            self.assertLess(script.index('-expiry --on-active='), script.index('--description='))
            self.assertNotIn('/apps_rw/MiniTelemetry/', script)
            self.assertNotIn('systemctl restart', script)

    def test_lost_reply_without_a_unit_does_not_retry_same_boot(self):
        doc = journal(); doc.update(generation=BOOT,phase='starting')
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap = Bootstrap(None, doc, Path(tmp))
            with patch.object(bootstrap, 'observe', return_value=absent()), patch('time.time', return_value=1000):
                self.assertEqual(bootstrap.ensure(), 'quiescent')


if __name__ == '__main__': unittest.main()
