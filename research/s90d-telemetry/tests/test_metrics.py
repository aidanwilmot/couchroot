import importlib.machinery
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nas'))
from metrics import validate, calculate

def sample(uptime=100, seq=1):
 return dict(schema=1,boot='00000000-0000-4000-8000-000000000032',seq=seq,uptime=uptime,
 stat='cpu 100 0 50 850 0 0 0 0 0 0\n',meminfo='MemTotal: 2048 kB\nMemAvailable: 1024 kB\n',
 netdev=' eth0: 10240 0 0 0 0 0 0 0 20480 0 0 0 0 0 0 0\n',
 diskstats='179 0 mmcblk0 0 0 10 0 0 0 20 0 0 0 0\n179 1 mmcblk0p1 0 0 10 0 0 0 20 0 0 0 0\n',
 collector_cpu_seconds=1,collector_rss_bytes=1048576)

class MetricsTests(unittest.TestCase):
 def test_actual_elapsed_time_and_partition_exclusion(self):
  a=sample();b=sample(110,2);b['stat']='cpu 130 0 70 900 0 0 0 0\n';b['netdev']=b['netdev'].replace('10240','20480');b['diskstats']=b['diskstats'].replace('0 0 10','0 0 30');b['collector_cpu_seconds']=1.1
  result=calculate(validate(b),validate(a))
  self.assertEqual(result['cpu']['user'],30)
  self.assertEqual(result['network']['read'],1)
  self.assertEqual(result['disk']['read'],1)
  self.assertAlmostEqual(result['collector_cpu']['cpu'],1)
 def test_restart_outage_and_counter_reset_do_not_invent_rates(self):
  a=sample();b=sample(110,2);b['boot']='00000000-0000-4000-8000-000000000033'
  self.assertNotIn('cpu',calculate(b,a))
  b=sample(200,2);self.assertNotIn('cpu',calculate(b,a))
  b=sample(110,2);b['stat']='cpu 1 0 1 1 0 0 0 0\n';self.assertNotIn('cpu',calculate(b,a))
 def test_reject_invalid_and_oversized_samples(self):
  for field,value in [('uptime',float('nan')),('seq',True),('meminfo','broken'),('stat','x'*16385)]:
   data=sample();data[field]=value
   with self.assertRaises((ValueError,StopIteration)):validate(data)
 def test_status_gaps_do_not_repeat_metrics(self):
  data=sample();self.assertEqual(set(calculate(data,None)),{'memory','collector_memory','uptime'})
 def test_one_interface_reset_cannot_be_hidden_by_another(self):
  a=sample();b=sample(110,2)
  a['netdev']+=' wlan0: 10000 0 0 0 0 0 0 0 10000 0 0 0 0 0 0 0\n'
  b['netdev']=b['netdev'].replace('10240','5000')+' wlan0: 50000 0 0 0 0 0 0 0 50000 0 0 0 0 0 0 0\n'
  self.assertNotIn('network',calculate(b,a))
 def test_unavailable_counters_and_process_restart(self):
  a=sample();b=sample(110,2)
  for key in ('stat','meminfo','netdev','diskstats'): b[key]=None
  self.assertEqual(set(calculate(validate(b),a)),{'collector_cpu','collector_memory','uptime'})
  b=sample(110,2);b['session']='00000000-0000-4000-8000-000000000034'
  self.assertNotIn('collector_cpu',calculate(b,a))
  b=sample(110,1);self.assertNotIn('cpu',calculate(b,a))
  b=sample(110,2);b['diskstats']='';self.assertNotIn('disk',calculate(b,a))
if __name__=='__main__':unittest.main()
