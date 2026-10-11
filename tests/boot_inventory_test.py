import importlib.util
from pathlib import Path
import struct
import unittest

root=Path(__file__).resolve().parents[1]/'research/s90d-boot-inventory'
def module(name):
    spec=importlib.util.spec_from_file_location(name,root/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
reader=module('read-trace');summary=module('summarize')
def record(kind,payload):
    return b'0000'+struct.pack('<H',len(payload))+bytes([kind])+payload

class BootInventoryTest(unittest.TestCase):
    def test_leveldb_fragments(self):
        first=b'a'*(32768-7)
        self.assertEqual(list(reader.log_records(record(2,first)+record(4,b'end'))),[first+b'end'])
    def test_partial_record_not_reported(self):
        self.assertEqual(list(reader.log_records(record(1,b'abc')[:-1])),[])
    def test_clock_units_and_missing_values(self):
        rows=summary.parse('Id=a.service\nType=oneshot\nExecMainStartTimestampMonotonic=1000000\nExecMainExitTimestampMonotonic=3500000\n\nId=b.service\nType=simple\nExecMainStartTimestampMonotonic=0\n')
        self.assertEqual(rows[0]['process_lifetime_s'],2.5)
        self.assertIsNone(rows[1]['process_start_s'])
        self.assertIsNone(rows[1]['process_lifetime_s'])
    def test_reversed_restart_timestamps_not_negative_duration(self):
        rows=summary.parse('Id=a.service\nExecMainStartTimestampMonotonic=5000000\nExecMainExitTimestampMonotonic=1000000\n')
        self.assertIsNone(rows[0]['process_lifetime_s'])

if __name__=='__main__':unittest.main()
