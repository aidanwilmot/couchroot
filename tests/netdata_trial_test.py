"""Validate the benchmark configuration and parse real firmware proc formats."""
import configparser
from pathlib import Path
import unittest
from unittest.mock import Mock

from tvsetup.netdata_trial import configuration, sample, validate_trial_paths
from tvsetup.common import Refused


class NetdataTrialTests(unittest.TestCase):
    def test_only_reviewed_collectors_and_local_listener(self):
        config=configparser.ConfigParser(interpolation=None)
        config.read_string(configuration('/opt/trial','/tmp/trial'))
        enabled={name for name,value in config['plugin:proc'].items() if value=='yes'}
        self.assertEqual(enabled,{'/proc/stat','/proc/meminfo','/proc/diskstats','/proc/uptime','/proc/net/dev'})
        self.assertEqual(config['db']['mode'],'ram')
        self.assertEqual(config['web']['bind to'],'127.0.0.1:21999')
        self.assertEqual(config['ml']['enabled'],'no')
        self.assertEqual(config['plugins']['enable running new plugins'],'no')
        for name in ('log','lib','cache'):
            self.assertTrue(config['directories'][name].startswith('/tmp/trial/'))

    def test_cleanup_rejects_a_foreign_directory(self):
        with self.assertRaises(Refused):
            validate_trial_paths({'scope':'netdata-native-trial','device':'s90d','run':'20260921T172726Z-540fcd64','ram':'/tmp'},Path('/runs/20260921T172726Z-540fcd64'))

    def test_missing_kernel_io_accounting_is_unavailable_not_zero(self):
        stat='4013 (netdata) S 1 4013 4013 0 -1 4194560 5159 84 378 0 20 52 0 0 30 10 21 0 2085256 211922944 120'
        tv=Mock()
        tv.root.return_value=('SAMPLE_TIME 8361.16 26537.47\nPID_BEGIN=4013\n'+stat+'\n'
            'Uid:\t5001\t5001\t5001\t5001\nVmRSS:\t480 kB\nThreads:\t21\nPID_END\n')
        result=sample(tv,{'unit':'test'})
        self.assertEqual(result['processes'][0]['ticks'],72)
        self.assertIsNone(result['processes'][0]['write_bytes'])


if __name__=='__main__': unittest.main()
