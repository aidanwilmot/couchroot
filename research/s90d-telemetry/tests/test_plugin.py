"""Exercise plugin output across duplicate, stale and returning TV snapshots."""
import importlib.util,importlib.machinery,io,json,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from test_metrics import sample

class Finished(Exception):pass
class PluginTests(unittest.TestCase):
 def test_devices_do_not_repeat_stale_values_or_share_baselines(self):
  source=Path(__file__).resolve().parents[1]/'nas/s90d.plugin'
  loader=importlib.machinery.SourceFileLoader('telemetry_plugin',str(source))
  spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);data=root/'s90d-data';data.mkdir()
   devices={'s90d':dict(name='Basement',chart_prefix='s90d',snapshot='latest.json'),'qn90a':dict(name='Living room',chart_prefix='qn90a',snapshot='qn90a.json')}
   (data/'devices.json').write_text(json.dumps(devices));clock=[1000];step=[0]
   def write(id,up,seq):
    s=dict(sample(up,seq),device=id,received_at=clock[0]);(data/devices[id]['snapshot']).write_text(json.dumps(s))
   write('s90d',100,1);write('qn90a',500,1)
   def advance(_):
    step[0]+=1
    if step[0]==1:clock[0]=1010 # duplicates, still fresh
    elif step[0]==2:clock[0]=1040 # both stale
    elif step[0]==3:write('s90d',140,2) # S90D returns, no baseline
    elif step[0]==4:
     clock[0]=1050;write('s90d',150,3) # legitimate zero network rate
    else:raise Finished()
   output=io.StringIO()
   with patch.object(module,'__file__',str(root/'s90d.plugin')),patch.object(module.time,'time',lambda:clock[0]),patch.object(module.time,'sleep',advance),redirect_stdout(output):
    with self.assertRaises(Finished):module.main()
   text=output.getvalue()
   self.assertIn('CHART s90d.cpu',text);self.assertIn('CHART qn90a.cpu',text)
   self.assertEqual(text.count('BEGIN s90d.memory\n'),3)
   self.assertEqual(text.count('BEGIN qn90a.memory\n'),1)
   self.assertEqual(text.count('BEGIN s90d.network\n'),1)
   self.assertEqual(text.count('BEGIN qn90a.network\n'),0)
   self.assertIn('BEGIN qn90a.availability\nSET online = 0',text)
