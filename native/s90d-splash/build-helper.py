"""Build a separate splash-compatible helper, retaining normal saver behavior."""
from pathlib import Path
import hashlib
import subprocess

root = Path(__file__).resolve().parent
base = root.parent / 'system-screensaver/boot'
out = root / 'bin/helper'
out.mkdir(parents=True, exist_ok=True)
source = (base / 'Program.cs').read_text()
for needle in ('static int Main() {', 'return diagnosticStatus;'):
    if source.count(needle) != 1:
        raise SystemExit('Normal helper changed; review integration points.')
source = source.replace('static int Main() {', 'static int Main() {\n        Splash.Start();')
source = source.replace('return diagnosticStatus;', 'Splash.Finish();\n        return diagnosticStatus;')
(out / 'Program.cs').write_text(source)
(out / 'Splash.cs').write_text((root / 'Splash.cs').read_text())
(out / 'Boot.csproj').write_text((base / 'Boot.csproj').read_text())
subprocess.run(['dotnet', 'build', str(out / 'Boot.csproj'), '-c', 'Release', '--nologo'], check=True)
artifact = out / 'bin/Release/net6.0/Boot.dll'
print(artifact)
print(hashlib.sha256(artifact.read_bytes()).hexdigest())
