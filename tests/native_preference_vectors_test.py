"""One fixture through both real C preference entry points."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class NativePreferences(unittest.TestCase):
    def test_shared_entries_in_both_native_readers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'preferences';exe=root/'reader';source=root/'reader.c'
            for launcher in ('native-hub','webview'):
                if launcher=='native-hub':
                    code='#include "'+str(ROOT/'native-hub/hub-model.h')+'"\nint main(int argc,char **argv){(void)argc;HubSaved saved;return hub_load(&saved,argv[1])?0:1;}\n'
                else:
                    code='#define main host_main\n#include "'+str(ROOT/'native/webview/host.c')+'"\n#undef main\nint main(int argc,char **argv){(void)argc;setenv("COUCHROOT_NATIVE_STATE",argv[1],1);return launcher_import_fragment()?0:1;}\n'
                source.write_text(code)
                subprocess.run(['cc','-D_GNU_SOURCE','-D_DARWIN_C_SOURCE','-std=c99','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',str(source),'-ldl','-o',str(exe)],check=True)
                for case in json.loads((ROOT/'tests/fixtures/preferences.json').read_text()):
                    with self.subTest(launcher=launcher,case=case['name']):
                        state.write_text('COUCHROOT1 0 0 0 0\n'+''.join(a['id']+'\t'+a['name']+'\n' for a in case['apps']))
                        result=subprocess.run([str(exe),str(state)],capture_output=True)
                        self.assertEqual(result.returncode==0,case['native'],result.stderr.decode())
