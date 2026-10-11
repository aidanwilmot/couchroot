#!/usr/bin/env python3
"""Fixed system-screensaver operations for QN90A 2301.1 only."""
import argparse, importlib.util
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('operation', choices=['script-probe','apply','inspect','capture','wake','memory-apply','memory-restore','module-restore','idle-trial','restore','timeout-restore','timeout-five-minutes'])
args=parser.parse_args()
spec=importlib.util.spec_from_file_location('root_check', Path(__file__).with_name('qn90a-root-check.py'))
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.run('saver-'+args.operation)
