"""Shared predicates and local malformed-/proc boundaries; no TV access."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]

class PlatformCoreTests(unittest.TestCase):
    def compile_run(self, source, args=(), sanitize=False):
        with tempfile.TemporaryDirectory() as tmp:
            c=Path(tmp)/'test.c';exe=Path(tmp)/'test';c.write_text(source)
            flags=['-std=c99','-D_GNU_SOURCE','-D_DARWIN_C_SOURCE','-Wall','-Wextra','-Werror','-Wno-unused-function']
            if sanitize:flags+=['-fsanitize=address','-g']
            subprocess.run(['cc',*flags,str(c),'-ldl','-o',str(exe)],check=True)
            return subprocess.run([str(exe),*args],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

    def test_webview_uses_shared_matrix(self):
        self.compile_run('#define main host_main\n#include "'+str(SOURCE/'host.c')+'"\n#undef main\n#include "'+str(SOURCE.parent/'common/platform-matrix.h')+'"\nint main(void){platform_matrix();return 0;}\n')

    def test_signal_mask_and_truncated_proc_stat_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            stat=Path(tmp)/'stat';stat.write_text('1 ('+'x'*507+')')
            self.compile_run('''#define main host_main
#include "'''+str(SOURCE/'host.c')+'''"
#undef main
#include <assert.h>
int main(int argc,char **argv){(void)argc;char comm[64],state;unsigned long flags;
 assert(!crash_stat(argv[1],comm,sizeof comm,&state,&flags));
 set_signal(SIGTERM,SIG_IGN);struct sigaction action;assert(!sigaction(SIGTERM,NULL,&action));
 assert(sigismember(&action.sa_mask,SIGINT));assert(sigismember(&action.sa_mask,SIGTERM));return 0;}
''',[str(stat)],True)
            stat.write_text('1 ('+'x'*1019+')')
            self.compile_run('''#define main sample_main
#include "'''+str(SOURCE/'procsample.c')+'''"
#undef main
#include <assert.h>
int main(int argc,char **argv){(void)argc;char comm[64],state;int parent;unsigned long long out[6];
 assert(!read_stat(argv[1],comm,sizeof comm,&state,&parent,out));return 0;}
''',[str(stat)],True)
