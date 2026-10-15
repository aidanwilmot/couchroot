"""Offline bundle binding and opt-in transport failure/replay boundaries."""
import json
import struct
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tvsetup.common import Refused, sha
from tvsetup.config import profile
from tvsetup import native_root, root


class NativeBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name); self.bundle=self.folder/'bundle'; self.bundle.mkdir()
        self.artifacts=self.bundle/'artifacts'; self.artifacts.mkdir()
        self.out=self.folder/'out'; self.out.mkdir()
        self.profile={**profile('qn90a'),'host':'192.0.2.11','device_id':'uuid:00000000-0000-4000-8000-000000000001'}
        self.manifest=dict(schema=1,kind='native-acquisition-managed-entry',model='qn90a',
                           framework=self.profile['framework'],runtime=self.profile['runtime'],reproducible_builds=2,
                           source={n:sha((native_root.SOURCE/n).read_bytes()) for n in ('acquire.c','build.sh','NativeEntry.cs')},artifacts={})
        for name in native_root.FILES:
            data=('fixture '+name).encode(); (self.artifacts/name).write_bytes(data)
            self.manifest['artifacts'][name]=dict(sha256=sha(data),size=len(data))
        self.save()

    def save(self):
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))

    def test_validated_bytes_are_snapshotted_with_guarded_operation(self):
        outputs=native_root.prepare(self.profile,self.bundle,self.out,'guard\necho ok\n')
        self.assertEqual(set(outputs.values()),(set(native_root.FILES)-{'libacquire.so'})|{'code/libacquire.so','operation.sh'})
        (self.artifacts/'NativeEntry.dll').write_bytes(b'changed later')
        self.assertEqual((self.out/'NativeEntry.dll').read_bytes(),b'fixture NativeEntry.dll')
        self.assertEqual((self.out/'operation.sh').read_text(),'guard\necho ok\n')

    def test_wrong_profile_or_source_and_cleanup_refuse(self):
        for key,value in [('model','s90d'),('framework','net9.0'),('runtime','0.0.0'),('source',{}),('reproducible_builds',1)]:
            with self.subTest(key=key):
                old=self.manifest[key];self.manifest[key]=value;self.save()
                with self.assertRaises(Refused):native_root.prepare(self.profile,self.bundle,self.out,'true')
                self.manifest[key]=old;self.save()
        with self.assertRaisesRegex(Refused,'cleanup'):native_root.prepare(self.profile,self.bundle,self.out,'true',0)
        for script in ['echo\0bad', 'x'*65536]:
            with self.assertRaisesRegex(Refused,'64 KiB'):native_root.prepare(self.profile,self.bundle,self.out,script)

    def test_artifact_drift_and_symlinks_refuse(self):
        p=self.artifacts/'libacquire.so'; data=p.read_bytes();p.write_bytes(b'drift')
        with self.assertRaisesRegex(Refused,'drift'):native_root.prepare(self.profile,self.bundle,self.out,'true')
        p.unlink(); other=self.folder/'other';other.write_bytes(data);p.symlink_to(other)
        with self.assertRaisesRegex(Refused,'regular'):native_root.prepare(self.profile,self.bundle,self.out,'true')

    def test_lost_native_reply_cleans_owned_files_without_managed_fallback(self):
        calls=[];uploads=[]
        class Client:
            def __init__(self,*args):pass
            def connect(self):pass
            def require_device(self):pass
            def capture(self,*args,**kwargs):
                return SimpleNamespace(transport_returncode=0,output='a'*64+'  /etc/passwd\n'+'b'*64+'  /usr/share/sdbd/public.pem\n[exit:0]\n')
            def push(self,source,target):uploads.append(str(target))
        def capture(cfg,callback,script,timeout,label):
            calls.append((label,script))
            if label=='setup-root-operation':raise Refused('lost native reply')
        def command(argv,**kwargs):
            if '-out' in argv:Path(argv[argv.index('-out')+1]).write_bytes(b'fixture')
            return ''
        toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=Client,capture=capture)
        with patch.object(root,'PRIVATE',self.folder),patch.object(root,'load',return_value=toolkit),patch.object(root,'run',side_effect=command),patch.object(root,'build',side_effect=AssertionError('managed fallback replay')):
            with self.assertRaisesRegex(Refused,'lost native reply'):root.execute(self.profile,'true',native_bundle=self.bundle)
        self.assertEqual([x[0] for x in calls],['setup-root-stage','setup-root-operation','setup-root-cleanup'])
        self.assertIn('/NativeEntry.dll probe',calls[1][1]);self.assertIn('env -i ',calls[1][1])
        self.assertNotIn('NamespaceRootProbe.dll',calls[1][1])
        self.assertTrue(all('test-private.pem' not in x for x in uploads))
        self.assertIn('rm -f /home/owner/share/tmp/sdk_tools/couchroot-native-root-qn90a/code/libacquire.so',calls[2][1])
        self.assertIn('sha256sum /etc/passwd',calls[2][1])

    def test_bad_bundle_fails_before_device_contact(self):
        self.manifest['model']='s90d';self.save()
        toolkit=SimpleNamespace(device=lambda cfg:(_ for _ in ()).throw(AssertionError('device contacted')))
        with patch.object(root,'PRIVATE',self.folder),patch.object(root,'load',return_value=toolkit):
            with self.assertRaisesRegex(Refused,'mismatch'):root.execute(self.profile,'true',native_bundle=self.bundle)

    def test_library_abi_dependency_and_version_gate(self):
        data=bytearray(52);data[:7]=b'\x7fELF\x01\x01\x01'
        struct.pack_into('<H',data,16,3);struct.pack_into('<H',data,18,40)
        struct.pack_into('<I',data,36,5<<24)
        report='(NEEDED) Shared library: [libc.so.6]\nGLIBC_2.17\n'
        self.assertEqual(native_root.inspect_library(data,report)['glibc_max'],'2.17.0')
        for offset,value in [(16,2),(18,183)]:
            wrong=bytearray(data);struct.pack_into('<H',wrong,offset,value)
            with self.assertRaises(Refused):native_root.inspect_library(wrong,report)
        wrong=bytearray(data);struct.pack_into('<I',wrong,36,(5<<24)|0x400)
        with self.assertRaises(Refused):native_root.inspect_library(wrong,report)
        for suffix in ['GLIBC_2.28','(NEEDED) Shared library: [libforeign.so]',
                       'Requesting program interpreter: /lib/ld-linux.so.3']:
            with self.assertRaises(Refused):native_root.inspect_library(data,report+suffix)

if __name__=='__main__':unittest.main()
