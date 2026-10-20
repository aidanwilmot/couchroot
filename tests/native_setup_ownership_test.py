"""Real Linux UID separation; fake only the vendor namespace/identity launcher.

Runs in the existing native CI container as root; no device or network access.
SDK=901 owns directories; SDB uploads as owner=5001; unrelated user=6000.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tvsetup import root
from tvsetup.common import Refused
from tvsetup.config import profile


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'Linux UID fixture (native CI container)')
class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name); self.folder.chmod(0o755)
        self.base = self.folder/'sdk_tools'; self.base.mkdir(mode=0o777); self.base.chmod(0o777)
        self.shared = self.base/'on-demand'; self.shared.mkdir(mode=0o755); os.chown(self.shared, 5001, 100)
        self.agent = self.shared/'archive-root-agent.tar.gz'; self.agent.write_text('agent bytes'); os.chown(self.agent,5001,100)
        self.operation = ''; self.commands = []; self.fault = None; self.launched = 0

    def shell(self, script, uid=901, check=True):
        def identity():
            os.setgroups([]); os.setgid(uid); os.setuid(uid); os.umask(0)
        result = subprocess.run(['sh'],input=script,preexec_fn=identity,text=True,capture_output=True)
        if check and result.returncode:
            raise Refused(result.stderr or result.stdout or 'remote command failed')
        return result

    def execute(self, device, script='printf sensitive; printf scratch >"$TV_SETUP_READ_TMP"', capture=True):
        outer = self
        probe = 'codex-qn90a-root-proof' if device == 'qn90a' else 'codex-namespace-proof'
        prefix = self.base/probe
        class Client:
            def __init__(self,*args): pass
            def connect(self): pass
            def require_device(self): pass
            def push(self,source,target):
                # Uploaded mode deliberately differs from the host file's mode.
                # The real ownership bug must be exercised, not mocked away.
                data=Path(source).read_bytes(); dest=Path(target)
                dest.write_bytes(data); os.chown(dest,5001,100); dest.chmod(0o644)
                if outer.fault == 'tamper' and dest.name == 'RootIdentity.dll': dest.write_text('tampered')
                self_check=outer.shell('test -w '+root.Q(str(dest.parent)),uid=5001,check=False)
                outer.assertEqual(self_check.returncode,0)
            def pull(self,remote,local):
                result=outer.shell('cat '+root.Q(str(remote)),uid=5001)
                Path(local).write_text(result.stdout)
            def capture(self,command,**kwargs):
                if '/usr/share/sdbd/public.pem' in command:
                    return SimpleNamespace(transport_returncode=0,output='a'*64+'  /etc/passwd\n'+'b'*64+'  /usr/share/sdbd/public.pem\n[exit:0]\n')
                # A different user cannot read secrets, even after root wrote them.
                for name in ('result.txt','read.tmp'):
                    path=prefix/'private'/name
                    outer.assertEqual(path.stat().st_uid,901)
                    outer.assertEqual(path.stat().st_mode & 0o777,0o600)
                    for uid in (5001,6000):
                        outer.assertNotEqual(outer.shell('cat '+root.Q(str(path)),uid=uid,check=False).returncode,0)
                result=outer.shell(command,check=False)
                return SimpleNamespace(transport_returncode=0,output=result.stdout+'\n[exit:'+str(result.returncode)+']\n')
        def build(profile,folder,script,cleanup_index=None):
            outer.operation=script
            outputs={}
            for name in ('NamespaceRootProbe.dll','RootIdentity.dll'):
                path=folder/name;path.write_text('fixture executable');outputs[path]=name
            return outputs
        def openssl(args,**kwargs):
            if '-out' in args:Path(args[args.index('-out')+1]).write_text('fixture signed bytes')
        real_hash=root.hash_guard
        def guard(path,digest):
            return real_hash(path,digest) if str(path).startswith(str(outer.base)) else ''
        def capture_step(cfg,callback,command,timeout,label):
            outer.commands.append((label,command))
            if label == 'setup-root-operation':
                # Execute every SDK-side guard/trap as SDK. Substitute only the
                # hardware-specific launcher, then run the payload as real uid 0.
                before=command.split('/usr/bin/dotnet ',1)[0]
                outer.shell(before+'true\n') if 'completed()' not in before else outer.shell(before.replace("trap 'status=$?; completed || :; exit \"$status\"' EXIT",'')+'true\n')
                if outer.fault == 'before-root': raise Refused('injected before root')
                outer.assertNotEqual(outer.shell('cat '+root.Q(str(prefix/'private/result.txt')),uid=6000,check=False).returncode,0)
                outer.launched += 1
                alias=prefix/'shared-on-demand'
                if alias.exists():alias.rmdir()
                alias.symlink_to(outer.shared,target_is_directory=True)
                try:
                    result=outer.shell(outer.operation,uid=0,check=False)
                finally:
                    alias.unlink();alias.mkdir()
                if result.returncode:raise Refused('root operation failed')
            else:
                outer.shell(command)
        toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=Client,capture=capture_step)
        p={**profile(device),'host':'192.0.2.11','device_id':'fixture'}
        with patch.object(root,'BASE',str(self.base)+'/'),patch.object(root,'PRIVATE',self.folder), \
             patch.object(root,'load',return_value=toolkit),patch.object(root,'build',side_effect=build), \
             patch.object(root,'run',side_effect=openssl),patch.object(root,'managed_guard',return_value='set -eu\n'), \
             patch.object(root,'hash_guard',side_effect=guard):
            return root.execute(p,script,capture_result=capture)

    def test_capture_with_owner_uploads_and_owner_only_shared_directory(self):
        for device in ('qn90a','s90d'):
            with self.subTest(device=device):
                self.assertEqual(self.execute(device),'sensitive')
                self.assertEqual(list(self.base.iterdir()),[self.shared])
                self.assertEqual(self.agent.read_text(),'agent bytes')

    def test_failed_acquisition_cleans_owner_uploads_and_does_not_skip_later_files(self):
        self.fault='before-root'
        for device in ('qn90a','s90d'):
            with self.subTest(device=device):
                with self.assertRaises(Refused):self.execute(device,capture=False)
                self.assertEqual(list(self.base.iterdir()),[self.shared])
                self.assertEqual(list(self.shared.iterdir()),[self.agent])

    def test_old_shared_archives_are_removed_only_after_root_and_never_reused(self):
        for device,probe in [('qn90a','codex-qn90a-root-proof'),('s90d','codex-namespace-proof')]:
            for suffix in ('.tar.gz','.tar.gz.signature'):
                p=self.shared/(probe+suffix);p.write_text('untrusted leftover');os.chown(p,5001,100)
            self.assertEqual(self.execute(device),'sensitive')
            self.assertEqual(list(self.shared.iterdir()),[self.agent])

    def test_root_failure_keeps_private_output_and_still_cleans(self):
        with self.assertRaises(Refused) as failure:self.execute('qn90a','printf failure-output; exit 7')
        self.assertEqual(failure.exception.output,'failure-output')
        self.assertEqual(list(self.base.iterdir()),[self.shared])

    def test_tampered_upload_cannot_reach_root_and_is_cleaned(self):
        self.fault='tamper'
        with self.assertRaises(Refused):self.execute('qn90a')
        self.assertEqual(self.launched,0)
        self.assertEqual(list(self.base.iterdir()),[self.shared])

    def test_lost_stage_callback_still_cleans_and_never_runs_operation(self):
        original=self.shell
        def lost(script,**kwargs):
            result=original(script,**kwargs)
            if "stat -c '%U:%G:%a'" in script:raise Refused('lost stage reply')
            return result
        self.shell=lost
        with self.assertRaises(Refused):self.execute('s90d')
        self.assertEqual(self.launched,0)
        self.assertEqual(list(self.base.iterdir()),[self.shared])
