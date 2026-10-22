#!/usr/bin/env python3
"""One-time idle-app memory cleanup for the owner’s QN90A / 2310.0."""
import argparse
import os
from pathlib import Path
import sys

TARGETS = ('org.tizen.primevideo', 'com.samsung.tv.cobalt-yt', 'com.samsung.tv.csfs')
HUB = 'MiniHub001.Hub'


def script(restore):
    preamble = '''set -eu
grep -q '^Version=T-NKM2UABC-2310.0;' /etc/prd_info.ini
check_hub() {
    test "$(vconftool get memory/appfw/current_fullscreen_appid)" = 'memory/appfw/current_fullscreen_appid, value = MiniHub001.Hub (String)' || {
        echo 'Open Minimal Hub before running this command.' >&2
        exit 3
    }
    case "$(vconftool get memory/appfw/current_partial_appid)" in
      'memory/appfw/current_partial_appid, value =  (String)'|'memory/appfw/current_partial_appid, value = MiniHub001.Hub (String)') ;;
      *) echo 'Close the system overlay first.' >&2; exit 3 ;;
    esac
}
snapshot() {
    echo "MEMORY_$1"
    grep -E '^(MemAvailable|SwapFree):' /proc/meminfo
    cat /sys/block/zram0/mm_stat
}
check_hub
snapshot BEFORE
'''
    if restore:
        action = '''trap 'app_launcher -s MiniHub001.Hub >/dev/null 2>&1 || true' EXIT
'''
        for app in TARGETS:
            key = 'current_partial_appid' if app == 'com.samsung.tv.csfs' else 'current_fullscreen_appid'
            action += f'''echo RESTORE={app}
cat /proc/uptime
app_launcher -s {app}
n=0
while [ "$n" -lt 30 ]; do
    current=$(vconftool get memory/appfw/{key})
    if [ "$current" = 'memory/appfw/{key}, value = {app} (String)' ]; then break; fi
    sleep 0.5
    n=$((n+1))
done
cat /proc/uptime
test "$current" = 'memory/appfw/{key}, value = {app} (String)'
app_launcher -r {app}
'''
        action += '''app_launcher -s MiniHub001.Hub
sleep 2
check_hub
trap - EXIT
'''
    else:
        action = ''
        for app in TARGETS:
            action += f'''check_hub
echo TRIM={app}
if app_launcher -r {app}; then app_launcher -t {app}; fi
'''
        action += 'sleep 5\n'
        for app in TARGETS:
            action += f'''if app_launcher -r {app}; then
    echo '{app} stayed running or restarted; no forced kill attempted.' >&2
    exit 4
fi
'''
    return preamble + action + 'check_hub\nsnapshot AFTER\necho QN90A_MEMORY_OPERATION_COMPLETE\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true', help='open Prime Video, YouTube and Samsung Home, verify each, then return to Minimal Hub')
    args = parser.parse_args()
    os.umask(0o077)
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    sys.path.insert(0, str(toolkit))
    from samsung_tv import device, capture
    cfg = {'tv_host': '192.0.2.11', 'expected_model': 'QA50QN90AAKXXA',
           'expected_platform': '21_NIKEM2_QTV'}
    callback = device(cfg)
    capture(cfg, callback, script(args.restore), 60 if args.restore else 20,
            'qn90a-memory-restore' if args.restore else 'qn90a-memory-trim')


if __name__ == '__main__':
    main()
