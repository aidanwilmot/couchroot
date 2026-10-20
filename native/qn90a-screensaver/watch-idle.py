#!/usr/bin/env python3
"""Bounded read-only QN90A idle evidence; no key, launch, setter or root helper.

Run with the private research Python immediately after the recorded wake key.
Each SDK request finishes within 45 seconds. The Mac sampler performs 330 seconds of sampling waits plus SDK overhead, then
exits; no monitoring service or unattended automation is installed on the TV.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path.home() / '.local/share/samsung-tv-research'))
from samsung_tv import device, capture

cfg = {'tv_host': '192.0.2.11', 'expected_model': 'QN85QN90AAFXZA',
       'expected_platform': '21_NIKEM2_QTV'}
callback = device(cfg)
start = time.monotonic()
for batch in range(11):
    interval = 1 if batch >= 9 else 5
    script = """set -eu
grep -q '^Version=T-NKM2AKUC-2301.1;' /etc/prd_info.ini
cat /proc/sys/kernel/random/boot_id
"""
    script += 'for step in ' + ' '.join(map(str, range(30 // interval))) + '; do\n'
    script += """date -u +%FT%TZ
cat /proc/uptime
vconftool get memory/window_system/screensaver_on_off
vconftool get memory/appfw/current_fullscreen_appid
vconftool get memory/appfw/current_partial_appid
"""
    script += f'sleep {interval}\ndone\n'
    capture(cfg, callback, script, 45, f'qn90a-five-minute-idle-{batch:02}')
print(f'Completed {time.monotonic() - start:.1f}s of read-only observation')
