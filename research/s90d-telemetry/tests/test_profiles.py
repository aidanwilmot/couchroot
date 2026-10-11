import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from profiles import load
class ProfilesTests(unittest.TestCase):
 def test_history_namespace_and_paths(self):
  original=load()
  for changes in ({'chart_prefix':'s90d'},{'snapshot':'../latest.json'},{'host':original['s90d']['host']},{'framework':'net6.0'}):
   records=copy.deepcopy(original);records['qn90a'].update(changes)
   with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as f:
    json.dump(records,f);f.flush()
    with self.assertRaises(ValueError):load(f.name)
