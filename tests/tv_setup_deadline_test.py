"""Global observation budgets, lost reboot replies and actual host process cleanup."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from tvsetup.cli import reboot_verify, verification
from tvsetup.common import DeadlineExpired, Refused, read_json, run
from tvsetup.config import profile
from tv_setup_planner_test import accepted


class Clock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class RebootDeadlineTests(unittest.TestCase):
    def initial(self,device):
        state=accepted(device);calls=[]
        class Initial:
            def snapshot(self,**kwargs):return state
            def root(self,script):calls.append(script)
        return state,calls,Initial()

    def test_nested_inspections_share_remaining_budget_and_cannot_return_late_success(self):
        for device in ('qn90a','s90d'):
            for failure in ('timeout','late-success','unavailable'):
                with self.subTest(device=device,failure=failure),tempfile.TemporaryDirectory() as tmp:
                    clock=Clock();state,calls,tv=self.initial(device);budgets=[]
                    def observe(p,evidence,nas,remaining):
                        budgets.append(remaining)
                        if failure=='unavailable':clock.now+=8;raise Refused('disconnected')
                        clock.now+=remaining+1
                        if failure=='timeout':raise DeadlineExpired('nested root inspection blocked')
                        return {'boot':'new','verification':{'startup':'confirmed','telemetry':'fresh','scope':'test'}}
                    with patch('tvsetup.cli.time.monotonic',clock.monotonic),patch('tvsetup.cli.time.sleep',clock.sleep),patch('tvsetup.cli.observe',side_effect=observe):
                        with self.assertRaisesRegex(Refused,'not verified within deadline'):
                            reboot_verify(profile(device),tv,Path(tmp),30)
                    self.assertEqual(len(calls),1)
                    self.assertEqual(read_json(Path(tmp)/'reboot-verification.json')['phase'],'unverified')
                    self.assertLessEqual(max(budgets),25)
                    self.assertEqual(budgets,sorted(budgets,reverse=True))
                    self.assertNotIn('app_launcher',calls[0]);self.assertNotIn('systemctl start',calls[0])

    def test_new_boot_and_fresh_evidence_both_models(self):
        for device in ('qn90a','s90d'):
            with tempfile.TemporaryDirectory() as tmp:
                clock=Clock();before,calls,tv=self.initial(device);after=copy.deepcopy(before);after['boot']='new-boot'
                after['boot_status']=json.dumps(dict(boot='new-boot',accepted=True,outcome='foreground-confirmed',entered=10)) if device=='qn90a' else 'boot_id=new-boot ack=True resume=True'
                after['telemetry_status']=json.dumps(dict(boot='new-boot',sent=5,uptime=99,monitoring=True))
                observations=[dict(boot=before['boot'],verification=verification(profile(device),after)),dict(boot='new-boot',verification=verification(profile(device),after))]
                with patch('tvsetup.cli.time.monotonic',clock.monotonic),patch('tvsetup.cli.time.sleep',clock.sleep),patch('tvsetup.cli.observe',side_effect=observations):
                    result=reboot_verify(profile(device),tv,Path(tmp),30)
                self.assertEqual(len(calls),1);self.assertEqual(clock.now,10)
                self.assertNotIn('not established',result['startup'])

    def test_lost_reboot_request_reply_is_never_retried_or_followed_by_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,calls,tv=self.initial('qn90a')
            def lost(script):calls.append(script);raise Refused('request reply lost')
            tv.root=lost
            with patch('tvsetup.cli.observe',side_effect=AssertionError('observed uncertain request')):
                with self.assertRaisesRegex(Refused,'request reply lost'):reboot_verify(profile('qn90a'),tv,Path(tmp),30)
            self.assertEqual(len(calls),1)
            self.assertEqual(read_json(Path(tmp)/'reboot-verification.json')['phase'],'requesting')

    def test_interruption_records_unverified_without_reboot_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock();state,calls,tv=self.initial('s90d')
            with patch('tvsetup.cli.time.monotonic',clock.monotonic),patch('tvsetup.cli.time.sleep',clock.sleep),patch('tvsetup.cli.observe',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):reboot_verify(profile('s90d'),tv,Path(tmp),30)
            self.assertEqual(len(calls),1)
            self.assertEqual(read_json(Path(tmp)/'reboot-verification.json')['phase'],'unverified')


class ProcessSupervisorTests(unittest.TestCase):
    def test_deadline_kills_nested_helpers_instead_of_leaving_them_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'heartbeat'
            leaf='import pathlib,sys,time\np=pathlib.Path(sys.argv[1]);end=time.monotonic()+8\nwhile time.monotonic()<end:\n p.write_text(str(time.monotonic()));time.sleep(0.03)\n'
            parent='import os,sys\nfrom tvsetup.common import run\nos.environ["TV_SETUP_SUPERVISED_PGID"]=str(os.getpgrp())\nrun([sys.executable,"-c",sys.argv[1],sys.argv[2]],timeout=20)\n'
            started=time.monotonic()
            with self.assertRaises(DeadlineExpired):run([sys.executable,'-c',parent,leaf,marker],timeout=0.8,supervise=True)
            self.assertLess(time.monotonic()-started,4)
            self.assertTrue(marker.exists())
            last=marker.read_text();time.sleep(0.15);self.assertEqual(last,marker.read_text())
    def test_exhausted_budget_never_starts_a_process(self):
        with patch('tvsetup.common.subprocess.Popen',side_effect=AssertionError('spawned')):
            with self.assertRaises(DeadlineExpired):run(['unused'],timeout=0,supervise=True)
