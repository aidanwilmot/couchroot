"""Run production service lifecycle on the host: python3 tests/telemetry_service_test.py."""
from pathlib import Path
import subprocess
import tempfile
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]


def project(path,files,properties='',reference=''):
    path.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework>'
                    '<EnableDefaultCompileItems>false</EnableDefaultCompileItems>'+properties+'</PropertyGroup><ItemGroup>'+
                    ''.join('<Compile Include="'+escape(str(f),{'"':'&quot;'})+'"/>' for f in files)+reference+'</ItemGroup></Project>')


def main():
    with tempfile.TemporaryDirectory(prefix='telemetry-service-test-') as tmp:
        root=Path(tmp);harness=ROOT/'tests/telemetry-service-harness'
        collector=root/'collector';collector.mkdir();project(collector/'Telemetry.csproj',[harness/'Collector.cs'])
        project(root/'Harness.csproj',[harness/'Harness.cs',ROOT/'telemetry/qn90a-startup/Program.cs'],
                '<OutputType>Exe</OutputType><StartupObject>Harness</StartupObject>',
                '<ProjectReference Include="collector/Telemetry.csproj"/>')
        subprocess.run(['dotnet','build',root/'Harness.csproj','-c','Release','--nologo','-v','quiet'],check=True,timeout=90)
        subprocess.run(['dotnet',root/'bin/Release/net10.0/Harness.dll'],check=True,timeout=15)


if __name__=='__main__':main()
