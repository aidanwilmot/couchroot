import tempfile
import unittest
from pathlib import Path
from tvsetup.root_launcher import build
from tvsetup.common import Refused
from tvsetup.artifacts import Builder

class RootLauncherBuildTests(unittest.TestCase):
    def test_source_build_checks_architecture_and_glibc(self):
        for invalid in ('architecture','glibc',None):
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp).resolve();calls=[]
                def command(argv):
                    calls.append(argv)
                    if 'arm-linux-gnueabi-readelf' in argv:
                        return 'GLIBC_2.34' if invalid=='glibc' else 'GLIBC_2.4 GLIBC_2.17'
                    blob=bytearray(52);blob[:6]=b'\x7fELF\x01\x01';blob[18]=40 if invalid!='architecture' else 62
                    (folder/'app-launcher').write_bytes(blob)
                    return ''
                if invalid:
                    with self.assertRaises(Refused):build(folder,command)
                else:self.assertEqual(build(folder,command),folder/'app-launcher')
                self.assertTrue(all('--network' in c and 'none' in c for c in calls))
                self.assertIn('--launcher-only',calls[0])

    def test_native_resource_is_passed_only_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp).resolve();builder=Builder({'framework':'net6.0'},{},folder);calls=[];builder.command=calls.append
            builder.build_managed(folder/'Worker.csproj',folder/'out',native_app_launcher=folder/'native')
            self.assertIn('-p:NativeAppLauncher='+str(folder/'native'),calls[-1])
            builder.build_managed(folder/'Other.csproj',folder/'out')
            self.assertFalse(any(str(x).startswith('-p:NativeAppLauncher') for x in calls[-1]))

if __name__=='__main__':unittest.main()
