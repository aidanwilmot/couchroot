"""Exercise product-source locations through the real setup package builder."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from tvsetup.artifacts import Builder
from tvsetup.config import profile
from tvsetup.planner import Action


class ProductLayoutTests(unittest.TestCase):
    def test_service_builder_resolves_adapter_bootstrap_and_collector(self):
        for device in ('qn90a', 's90d'):
            with self.subTest(device=device), tempfile.TemporaryDirectory() as tmp:
                p={**profile(device),'signing_profile':'fixture','author_cert_sha256':'a'*64,'distributor_cert_sha256':'b'*64}
                builder=Builder(p,{'artifacts':{}},Path(tmp));projects=[]
                def managed(project,output,**kwargs):
                    self.assertTrue(project.is_file(),project)
                    projects.append(project.stem);output.mkdir(parents=True,exist_ok=True)
                    (output/(project.stem+'.dll')).write_bytes(b'fixture')
                def command(argv,**kwargs):
                    if argv[0]=='dotnet':
                        project=Path(argv[2]);self.assertTrue(project.is_file(),project)
                        projects.append(project.stem);out=Path(argv[argv.index('-o')+1]);out.mkdir()
                        (out/'Telemetry.dll').write_bytes(b'fixture')
                def verify(path,*args):
                    with zipfile.ZipFile(path) as package:
                        return {name:package.read(name) for name in package.namelist()},'0.0.0'
                action=Action('service','telemetry','package',None,{},dict(artifact='service',package='MiniTelemetry',previous_version=None))
                with patch.object(builder,'build_managed',side_effect=managed),patch.object(builder,'command',side_effect=command),patch('tvsetup.artifacts.verify_package',side_effect=verify):
                    _,members=builder.package(action)
                self.assertEqual(projects,['Service','Bootstrap','Telemetry'])
                self.assertTrue({'bin/Service.dll','bin/Bootstrap.dll','bin/Telemetry.dll'} <= members.keys())
