"""Independent observer fixtures; all kernel records are synthetic socket input."""
import json
import hashlib
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(os.environ.get('COUCHROOT_PARITY_CONTAINER'), 'Linux fixture required')
class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        native = Path(__file__).resolve().parents[1]/'research/autonomous-root/native-worker'
        source = cls.root/'fixture.c'
        source.write_text(r'''
#include "common.h"
static int stat_reads;
static int fixture_openat(int directory,const char *name,int flags,...) {
  if(!strcmp(name,"stat") && ++stat_reads==2 && getenv("CHANGE_IDENTITY"))
    name="stat-next";
  return openat(directory,name,flags);
}
#define openat fixture_openat
#include "observe-process.h"
#undef openat
int main(int argc,char **argv) {
  if(argc!=3)return 64;
  libraries();
  int directory=open(argv[1],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  J *sample=observe_process(directory,123,(uint64_t)strtoull(argv[2],NULL,10));
  puts(json(sample));json_object_put(sample);close(directory);return 0;
}
''')
        flags = ['gcc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(native)]
        cls.fixture = cls.root/'fixture'
        cls.observer = cls.root/'observer'
        subprocess.run(flags+[str(source), '-ldl', '-pthread', '-o', str(cls.fixture)], check=True)
        subprocess.run(flags+['-DNATIVE_OBSERVER_TEST', str(native/'observe.c'), '-ldl', '-pthread', '-o', str(cls.observer)], check=True)
        selector = cls.root/'selector.c'
        selector.write_text(r'''
#define main observer_program
#include "observe.c"
#undef main
int main(int argc,char **argv) {
  if(argc!=4)return 64;
  libraries();
  int directory=open(argv[1],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  int candidate=observe_native_path(argv[2]);
  printf("%d %d\n",candidate,candidate && observe_native(directory,123,999,argv[3]));
  close(directory);return 0;
}
''')
        cls.selector = cls.root/'selector'
        subprocess.run(flags+[str(selector), '-ldl', '-pthread', '-o', str(cls.selector)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def stat(start=999, user=12, system=8):
        fields = ['0']*30
        fields[0] = 'S'
        for index, value in [(1, 1), (11, user), (12, system), (19, start), (20, 40960), (21, 5)]:
            fields[index] = str(value)
        return '123 (name with ) spaces) '+' '.join(fields)+'\n'

    def sample(self, *, change=False, missing=False, malformed=False, expected=999):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/'stat').write_text('malformed\n' if malformed else self.stat())
            (p/'stat-next').write_text(self.stat(start=1000))
            if not missing:
                (p/'fd').mkdir(); (p/'fd/1').touch(); (p/'fd/2').touch()
                (p/'task').mkdir(); (p/'task/123').mkdir()
                (p/'mountinfo').write_text('one\ntwo\n')
                (p/'status').write_text('VmHWM: 100 kB\n')
                (p/'smaps').write_text('Rss: 20 kB\nPss: 8 kB\nPrivate_Clean: 2 kB\nPrivate_Dirty: 3 kB\nSwap: 1 kB\nRss: 30 kB\nPss: 4 kB\n')
            env = dict(os.environ)
            if change:
                env['CHANGE_IDENTITY'] = '1'
            result = subprocess.run([self.fixture, tmp, str(expected)], env=env, check=True, capture_output=True)
            return json.loads(result.stdout)

    def test_identity_bracketed_counters_and_mapping_sums(self):
        s = self.sample()
        self.assertTrue(s['identity_valid'])
        self.assertEqual(s['start_ticks'], '999')
        self.assertEqual((s['user_ticks'], s['system_ticks']), ('12', '8'))
        self.assertEqual((s['descriptors'], s['threads'], s['mounts']), (2, 1, 2))
        self.assertEqual((s['rss_kib'], s['pss_kib']), (50, 12))
        self.assertEqual((s['private_clean_kib'], s['private_dirty_kib']), (2, 3))
        self.assertIsNone(s['swap_pss_kib'])
        self.assertIsNone(s['idle_wakeups'])
        self.assertEqual(s['errors'], {})

    def test_missing_fields_are_unknown_with_errors_not_zero(self):
        s = self.sample(missing=True)
        self.assertTrue(s['identity_valid'])
        for key in ('descriptors', 'threads', 'mounts', 'rss_kib', 'pss_kib', 'peak_rss_kib'):
            self.assertIsNone(s[key])
        self.assertEqual(set(s['errors']), {'descriptors', 'threads', 'mounts', 'smaps'})

    def test_reused_pid_before_or_during_sample_is_invalid(self):
        for kwargs in (dict(expected=1000), dict(change=True)):
            with self.subTest(kwargs=kwargs):
                s = self.sample(**kwargs)
                self.assertFalse(s['identity_valid'])
                self.assertIn('identity', s['errors'])

    def test_malformed_stat_does_not_produce_zero_counters(self):
        s = self.sample(malformed=True)
        self.assertFalse(s['identity_valid'])
        self.assertIn('stat_before', s['errors'])
        self.assertNotIn('user_ticks', s)

    def test_private_bind_root_discovery_still_requires_mapped_executable_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/'exe').symlink_to(self.observer)
            digest = hashlib.sha256(self.observer.read_bytes()).hexdigest()
            for hint, expected, output in [('/worker', digest, b'1 1\n'),
                    ('/worker', '0'*64, b'1 0\n'),
                    ('/opt/couchroot-worker-fixture/code/worker', digest, b'1 1\n'),
                    ('/usr/bin/worker', digest, b'0 0\n')]:
                with self.subTest(hint=hint, digest=expected):
                    result = subprocess.run([self.selector, tmp, hint, expected], check=True, capture_output=True)
                    self.assertEqual(result.stdout, output)

    def run_observer(self, *, stop=False, lose_coordinator=False):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            coordinator = subprocess.Popen(['sleep', '10'])
            left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            process = None
            try:
                start = Path('/proc/'+str(coordinator.pid)+'/stat').read_text().rsplit(') ', 1)[1].split()[19]
                process = subprocess.Popen([self.observer, tmp, '2', '250', str(coordinator.pid), start, '0'*64],
                    env={**os.environ, 'COUCHROOT_TEST_KERNEL_FD': str(right.fileno())},
                    pass_fds=(right.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                right.close()
                deadline = time.monotonic()+4
                while not (p/'observer.ready').exists() or not (p/'observer.ready').stat().st_size:
                    if process.poll() is not None or time.monotonic()>deadline:
                        self.fail('observer did not become ready: '+repr(process.communicate(timeout=2)))
                    time.sleep(.01)
                left.sendall(b'6,200,123,-;synthetic\n')
                if lose_coordinator:
                    coordinator.terminate(); coordinator.wait(timeout=2)
                if stop:
                    time.sleep(.6); process.send_signal(signal.SIGTERM)
                _, stderr = process.communicate(timeout=6)
                report = json.loads((p/'observer.json').read_text())
                rows = [json.loads(line) for line in (p/'resources.ndjson').read_text().splitlines()]
                kernel = json.loads((p/'kernel.json').read_text())
                self.assertEqual(len(rows), report['samples'])
                self.assertTrue(kernel['complete'], kernel)
                self.assertEqual(kernel['records'], 1)
                for file in p.iterdir():
                    self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                return process.returncode, report, rows, stderr
            finally:
                left.close(); right.close()
                if process and process.poll() is None:
                    process.kill(); process.communicate()
                if coordinator.poll() is None:
                    coordinator.terminate(); coordinator.wait(timeout=2)

    def test_bounded_observation_persists_kernel_and_sample_windows(self):
        code, report, rows, stderr = self.run_observer()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(report['interval_complete'])
        self.assertFalse(report['stopped_by_signal'])
        self.assertGreaterEqual(len(rows), 4)
        self.assertTrue(all(row['coordinator_present'] for row in rows))
        for row in rows:
            self.assertLessEqual(row['started_monotonic_ms'], row['finished_monotonic_ms'])
            self.assertLessEqual(row['finished_monotonic_ms'], report['monotonic_end_ms'])
            self.assertEqual({p['role'] for p in row['processes']}, {'coordinator', 'observer'})
            self.assertTrue(all(p['identity_valid'] for p in row['processes']))

    def test_signal_stops_observation_without_discarding_evidence(self):
        code, report, rows, stderr = self.run_observer(stop=True)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(report['stopped_by_signal'])
        self.assertGreater(len(rows), 1)

    def test_lost_coordinator_fails_coverage_but_preserves_evidence(self):
        code, report, rows, _ = self.run_observer(lose_coordinator=True)
        self.assertEqual(code, 1)
        self.assertFalse(report['interval_complete'])
        self.assertTrue(report['sampling_failed'])
        self.assertTrue(any(not row['coordinator_present'] for row in rows))

    def test_existing_output_is_preserved_and_invalid_bounds_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); (p/'resources.ndjson').write_text('foreign')
            args = [str(self.observer), tmp, '2', '250', '1', '1', '0'*64]
            r = subprocess.run(args, capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual((p/'resources.ndjson').read_text(), 'foreign')
            self.assertFalse((p/'kernel.raw').exists())
            args[2] = '241'
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 64)


if __name__ == '__main__':
    unittest.main()
