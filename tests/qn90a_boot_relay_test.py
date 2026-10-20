"""Compile unchanged production Tick with deterministic host I/O and native stubs.

Run explicitly: python3 tests/qn90a_boot_relay_test.py
Requires the repository's .NET 10 SDK and a C compiler. No TV access.
"""
from pathlib import Path
import os
import platform
import subprocess
import tempfile
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / 'tests/qn90a-boot-relay-harness'


def main():
    with tempfile.TemporaryDirectory(prefix='qn90a-boot-test-') as directory:
        work = Path(directory)
        native = work / ('native.dylib' if platform.system() == 'Darwin' else 'native.so')
        subprocess.run([os.environ.get('CC', 'cc'), '-dynamiclib' if platform.system() == 'Darwin' else '-shared',
                        '-fPIC', str(HARNESS / 'Native.c'), '-o', str(native)], check=True)
        files = (HARNESS / 'Harness.cs', REPO / 'native/qn90a-boot-relay/Program.cs')
        project = work / 'Harness.csproj'
        project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                           '<TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType>'
                           '<StartupObject>Harness</StartupObject><EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
                           '<Nullable>enable</Nullable></PropertyGroup><ItemGroup>' +
                           ''.join('<Compile Include="'+escape(str(path), {'"': '&quot;'})+'" />' for path in files) +
                           '</ItemGroup></Project>')
        subprocess.run(['dotnet', 'build', str(project), '-c', 'Release', '--nologo', '-v', 'quiet',
                        '-p:WarningLevel=0'], check=True, timeout=90)
        subprocess.run(['dotnet', str(work / 'bin/Release/net10.0/Harness.dll'), str(native)],
                       check=True, timeout=30)


if __name__ == '__main__':
    main()
