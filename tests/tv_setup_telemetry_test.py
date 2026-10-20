import copy
import json
import re
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock

from tvsetup.config import profile, resolve
from tvsetup.planner import plan, EMPTY, Action
from tvsetup.operations import Driver
from tvsetup.telemetry import DATA, LEGACY_MARKER, service_ready
from tvsetup.common import Refused
from tvsetup.transport import Transport, paths
from tvsetup.artifacts import manifest_bytes
from tv_setup_planner_test import accepted


class TelemetryMigrationTests(unittest.TestCase):
    def test_samsung_manifest_elements_remain_unprefixed(self):
        # Serialize in alternating order: ElementTree namespace state is global.
        for namespace,tag in [('http://tizen.org/ns/packages','manifest'),
                              ('http://www.w3.org/ns/widgets','widget'),
                              ('http://tizen.org/ns/packages','manifest')]:
            source=f'<{tag} xmlns="{namespace}" version="0.4.0"/>'
            result=manifest_bytes(ET.fromstring(source))
            self.assertIn(('<'+tag+' ').encode(),result)
            self.assertNotIn(b'ns0:',result)
            self.assertEqual(ET.fromstring(result).tag,'{'+namespace+'}'+tag)

    def test_private_parent_absence_is_rechecked_as_root(self):
        tv=Transport.__new__(Transport);tv.profile=profile('s90d')
        values={'integrity':'ok','boot':'test-boot','uptime':'100 50'}
        values.update({'file'+str(i):'ABSENT' for i,_ in enumerate(paths('s90d'))})
        def sdk(script,timeout):
            names=re.findall(r'TVSETUP_BEGIN:([A-Za-z0-9_.-]+)',script)
            return ''.join('\nTVSETUP_BEGIN:'+n+'\n'+values.get(n,'')+'\nTVSETUP_END:'+n+'\n' for n in names)
        def root_reads(queries):
            output={}
            for name,script in queries.items():
                if name.startswith('hash'):output[name]=EMPTY if LEGACY_MARKER in script else 'ABSENT'
                elif name=='legacy_pairing_config':output[name]={'device_id':'s90d'}
                elif name=='pairing_config':output[name]=None
                else:output[name]=''
            return output
        tv.sdk=sdk;tv.root_reads=root_reads
        s=tv.snapshot(privileged=True)
        self.assertEqual(s['files'][LEGACY_MARKER],EMPTY)
        self.assertEqual(s['legacy_pairing_config']['device_id'],'s90d')
        self.assertIsNone(s['pairing_config'])

    def legacy(self):
        state=accepted('s90d')
        state['packages']=[r for r in state['packages'] if r[0]!='MiniTelemetry']
        state['files']={p:h for p,h in state['files'].items() if '/MiniTelemetry/' not in p}
        state['files'][LEGACY_MARKER]=EMPTY
        state['files']['/opt/minimal-telemetry/config.json']='a'*64
        return state

    def test_migration_drains_first_pairs_before_enable_and_preserves_helper(self):
        state=self.legacy();before=copy.deepcopy(state)
        p=plan(profile('s90d'),resolve('s90d',overrides={'components':['hub','telemetry']}),state)
        self.assertFalse(p.issues)
        self.assertEqual(p.actions[0].options['artifact'],'legacy-disable')
        self.assertIsNone(p.actions[0].after)
        pairing=next(i for i,a in enumerate(p.actions) if a.kind=='pairing')
        enabling=next(i for i,a in enumerate(p.actions) if a.options.get('path')==DATA+'/enabled')
        self.assertLess(pairing,enabling)
        self.assertFalse(any(a.options.get('path','').startswith('/opt/minimal-saver') for a in p.actions))
        self.assertFalse(any(a.kind=='preferences' for a in p.actions))
        self.assertEqual(state,before)

    def test_unknown_legacy_marker_refused(self):
        s=self.legacy();s['files'][LEGACY_MARKER]='f'*64
        self.assertTrue(plan(profile('s90d'),resolve('s90d'),s).issues)

    def test_service_requires_hub_adapter(self):
        s=self.legacy();s['files'].pop('/opt/usr/apps/MiniHub001/res/wgt/telemetry-service.js')
        self.assertTrue(plan(profile('s90d'),resolve('s90d',overrides={'components':['telemetry']}),s).issues)

    def test_retirement_is_narrow_and_resume_rechecks_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            tv=Mock();d=Driver(tv,profile('s90d'),resolve('s90d'),Path(tmp))
            a=Action('retire','telemetry','file',EMPTY,None,dict(path=LEGACY_MARKER,artifact='legacy-disable'))
            self.assertEqual(d.prepare(a),{})
            state=self.legacy();d.execute(a,{},state)
            script=tv.root.call_args.args[0]
            self.assertLess(script.index('rm '),script.index('flock -w 18'))
            state['files'][LEGACY_MARKER]=None
            d.verify(a,{},state)
            self.assertEqual(tv.root.call_args.args[0],service_ready(profile('s90d')))
            a.options['path']='/unrelated'
            with self.assertRaises(Refused):d.prepare(a)

    def test_rollback_drains_service_before_restoring_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tv=Mock();d=Driver(tv,profile('s90d'),resolve('s90d'),Path(tmp))
            a=Action('retire','telemetry','file',EMPTY,None,dict(path=LEGACY_MARKER,artifact='legacy-disable'))
            d.rollback(a,dict(backup='/backup',backup_sha256=EMPTY),{'files':{LEGACY_MARKER:None}})
            script=tv.root.call_args_list[0].args[0]
            self.assertIn('test ! -e '+DATA+'/enabled',script)
            self.assertLess(script.index('flock -w 18'),script.index('cp --preserve'))
            self.assertIn('restart AT-HUB',tv.root.call_args_list[-1].args[0])
