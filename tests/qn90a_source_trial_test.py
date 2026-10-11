import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tvsetup.common import Refused
from tvsetup.operations import Driver
from tvsetup.planner import Action
from tvsetup import qn90a_source_trial as trial


class Qn90aSourceTrialTests(unittest.TestCase):
    def setUp(self):
        self.base = {trial.CONFIG: 'base-config-hash'}
        self.restore = {trial.CONFIG: 'restore-config-hash'}
        self.forward = {trial.CONFIG: 'trial-config-hash'}
        self.materials = {
            'base': self.base,
            'restore': self.restore,
            'trial': self.forward,
            'restore_path': Path('/private/restore-MiniHub001.wgt'),
            'restore_sha256': 'restore-package-sha',
        }
        self.action = Action('001-source-package', 'source-role', 'package', self.base,
                             self.forward, {'package': 'MiniHub001', 'artifact': 'hub',
                                            'previous_version': '0.4.11'})

    def test_before_equivalent_normalizes_only_exact_prebuilt_inverse(self):
        self.assertEqual(trial.before_equivalent(self.restore, self.materials), self.base)
        self.assertEqual(trial.before_equivalent(self.forward, self.materials), self.forward)
        drifted = {trial.CONFIG: 'tampered-config-hash'}
        self.assertEqual(trial.before_equivalent(drifted, self.materials), drifted)
        extra = {**self.restore, '/extra/member': 'unexpected'}
        self.assertEqual(trial.before_equivalent(extra, self.materials), extra)

    def test_role_verification_rejects_unregistered_or_wrong_role(self):
        driver = object.__new__(trial.SourceDriver)
        good = {'hub_source_role': 'MiniHub001.Hub|MiniHub001.Hub|MiniHub001|1|0|'}
        bad_values = (
            'MiniHub001.Hub|MiniHub001.Hub|MiniHub001|0|0|',
            'MiniHub001.Hub|MiniHub001.Hub|MiniHub001|1|1|',
            None,
        )
        with patch.object(Driver, 'verify', return_value=None):
            driver.verify(self.action, {}, good)
            for value in bad_values:
                with self.subTest(value=value), self.assertRaisesRegex(Refused, 'WAS has not registered'):
                    driver.verify(self.action, {}, {'hub_source_role': value})

    def test_rollback_uses_exact_prebuilt_inverse_only_from_trial_state(self):
        driver = object.__new__(trial.SourceDriver)
        driver.materials = self.materials
        driver.tv = object()
        observed_trial = {'packages': [['MiniHub001']], 'files': dict(self.forward)}
        restored_state = {'hub_source_role': 'MiniHub001.Hub|MiniHub001.Hub|MiniHub001|0|0|'}
        seen = {}

        def execute(action, info, state):
            seen['action'] = action
            seen['info'] = info
            seen['state'] = state

        with tempfile.TemporaryDirectory() as folder:
            info = {'backup_files': {}}
            with patch.object(Driver, 'execute', side_effect=execute), \
                 patch.object(trial.SourceDriver, 'snapshot', return_value=restored_state):
                driver.rollback(self.action, info, observed_trial)
        inverse = seen['action']
        self.assertEqual(inverse.before, self.forward)
        self.assertEqual(inverse.after, self.restore)
        self.assertEqual(seen['info'], {'artifact': str(self.materials['restore_path']),
                                       'sha256': self.materials['restore_sha256']})

    def test_already_restored_noop_still_requires_role_removal(self):
        driver = object.__new__(trial.SourceDriver)
        driver.materials = self.materials
        driver.tv = object()
        restored_files = {'packages': [['MiniHub001']], 'files': dict(self.restore),
                          'hub_source_role': 'MiniHub001.Hub|MiniHub001.Hub|MiniHub001|1|0|'}
        with patch.object(Driver, 'execute') as execute:
            with self.assertRaisesRegex(Refused, 'did not remove the WAS role'):
                driver.rollback(self.action, {'backup_files': {}}, restored_files)
            execute.assert_not_called()

        restored_files['hub_source_role'] = 'MiniHub001.Hub|MiniHub001.Hub|MiniHub001|0|0|'
        with patch.object(Driver, 'execute') as execute:
            driver.rollback(self.action, {'backup_files': {}}, restored_files)
            execute.assert_not_called()

    def test_external_package_drift_blocks_prebuilt_inverse(self):
        driver = object.__new__(trial.SourceDriver)
        driver.materials = self.materials
        driver.tv = object()
        drifted = {'packages': [['MiniHub001']], 'files': {trial.CONFIG: 'external-config-hash'}}
        with patch.object(Driver, 'execute') as execute:
            with self.assertRaisesRegex(Refused, 'Package drift blocks'):
                driver.rollback(self.action, {'backup_files': {}}, drifted)
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
