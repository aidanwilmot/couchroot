import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tvsetup.autonomous_root_trial import PilotDriver,DATA,PREFIX,PROVISION,PACKAGE
from tvsetup.common import Refused,sha
from tvsetup.planner import Action

class PilotTests(unittest.TestCase):
    def test_provisioning_is_exactly_scoped_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);source=folder/'input';source.write_bytes(b'disabled')
            driver=PilotDriver(None,{'id':'qn90a'},{},folder)
            action=Action('001-file','autonomous-root','file',None,sha(b'disabled'),dict(path=DATA+'/config.json',source=str(source)))
            self.assertEqual(driver.prepare(action)['sha256'],sha(b'disabled'))
            action.options['path']='/etc/passwd'
            with self.assertRaises(Refused):driver.prepare(action)
            action.options['path']=DATA+'/config.json';source.write_bytes(b'drift')
            with self.assertRaises(Refused):driver.prepare(action)
    def test_verification_preserves_production_and_developer_host(self):
        with tempfile.TemporaryDirectory() as d:
            driver=PilotDriver(None,{'id':'qn90a'},{},Path(d))
            target=DATA+'/config.json';action=Action('001-file','autonomous-root','file',None,'new',dict(path=target))
            before=dict(files={target:None,'/production':'old'},developer_host='192.0.2.1')
            after=dict(files={target:'new','/production':'old'},developer_host='192.0.2.1')
            driver.verify(action,before,after)
            after['files']['/production']='changed'
            with self.assertRaises(Refused):driver.verify(action,before,after)
            after['files']['/production']='old';after['developer_host']='127.0.0.1'
            with self.assertRaises(Refused):driver.verify(action,before,after)
