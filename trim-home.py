#!/usr/bin/env python3
"""Release Samsung Home memory once, or restore it, through the SDK."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--restore', action='store_true',
                      help='relaunch Samsung Home and its helpers, then return to Minimal Hub')
    mode.add_argument('--include-home', action='store_true',
                      help='also unload Samsung Home; its next opening may take about 9 seconds')
    args = parser.parse_args()
    os.umask(0o077)
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    # The existing wrapper verifies the configured TV model and developer host.
    preamble = '''set -eu
check_hub() {
    current=$(vconftool get memory/appfw/current_fullscreen_appid)
    test "$current" = 'memory/appfw/current_fullscreen_appid, value = MiniHub001.Hub (String)' || {
        echo 'Open Minimal Hub before running this command.' >&2
        exit 3
    }
}
check_hub
snapshot() {
    echo "MEMORY_$1"
    grep -E '^(MemAvailable|SwapFree):' /proc/meminfo
    cat /sys/block/zram0/mm_stat
}
snapshot BEFORE
'''
    if args.restore:
        action = '''trap 'app_launcher -s MiniHub001.Hub >/dev/null 2>&1 || true' EXIT
if ! app_launcher -r com.samsung.tv.csfs; then
    app_launcher -s com.samsung.tv.csfs
    # Cold Home creates its helpers asynchronously. Do not race that startup
    # with a second launch of a helper that is already being created.
    n=0
    while [ "$n" -lt 25 ]; do
        if app_launcher -r com.samsung.tv.home.media >/dev/null 2>&1 &&
           app_launcher -r com.samsung.tv.home.sidebar >/dev/null 2>&1; then break; fi
        sleep 0.5
        n=$((n+1))
    done
fi
for app in com.samsung.tv.home.media com.samsung.tv.home.sidebar; do
    if ! app_launcher -r "$app"; then app_launcher -s "$app"; fi
done
sleep 5
app_launcher -s MiniHub001.Hub
sleep 2
for app in com.samsung.tv.csfs com.samsung.tv.home.media com.samsung.tv.home.sidebar; do
    app_launcher -r "$app"
done
trap - EXIT
'''
    else:
        targets = 'com.samsung.tv.home.media com.samsung.tv.home.sidebar'
        if args.include_home:
            targets += ' com.samsung.tv.csfs'
            preamble += '''test "$(vconftool get db/appfw/home_appid)" = 'db/appfw/home_appid, value = MiniHub001.Hub (String)' || {
    echo 'Minimal Hub must be assigned to the Home button before unloading Samsung Home.' >&2
    exit 3
}
'''
        else:
            # Refuse before changing anything if the requested warm-Home state
            # is already absent. --restore is the explicit recovery operation.
            preamble += 'app_launcher -r com.samsung.tv.csfs\n'
        action = '''for app in TARGETS; do
    check_hub
    if app_launcher -r "$app"; then app_launcher -t "$app"; fi
done
sleep 5
for app in TARGETS; do
    if app_launcher -r "$app"; then
        echo "App still running: $app; no forced kill attempted." >&2
        exit 4
    fi
done
'''.replace('TARGETS', targets)
    ending = '''check_hub
snapshot AFTER
echo HOME_MEMORY_OPERATION_COMPLETE
'''
    if not args.include_home:
        ending = 'app_launcher -r com.samsung.tv.csfs\n' + ending
    with tempfile.TemporaryDirectory(prefix='home-helpers-', dir=toolkit) as folder:
        script = Path(folder) / 'helpers.sh'
        script.write_text(preamble + action + ending)
        subprocess.run([str(Path.home() / '.local/bin/samsung-tv'),
                        'run', str(script), '--timeout', '30'], check=True)


if __name__ == '__main__':
    main()
