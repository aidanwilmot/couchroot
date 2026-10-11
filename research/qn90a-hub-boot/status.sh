set -eu
cat /proc/sys/kernel/random/boot_id /proc/uptime
for key in memory/system/boot_done memory/appfw/current_fullscreen_appid memory/appfw/current_partial_appid db/appfw/home_appid db/appfw/overlay_home_appid db/first_screen/type db/menu/smart_hub/ontvsetting/auto_start; do vconftool get "$key"; done
for file in /tmp/minimal-hub-boot/status.json /tmp/minimal-telemetry-qn90a/status.json /opt/minimal-hub-boot/deployment.json; do if test -f "$file"; then cat "$file"; echo; else echo "ABSENT $file"; fi; done
sqlite3 /opt/dbspace/.app-context.db 'select rowid,* from key_filter where key="XF86Home"; select rowid,* from task_filter where appid in ("MiniHub001.Hub","MiniHubBoot.Start"); select rowid,* from managed_app where appid="MiniHubBoot.Start"; pragma quick_check;'
if test -f /opt/usr/apps/MiniHubBoot/bin/Boot.dll; then sha256sum /opt/usr/apps/MiniHubBoot/bin/Boot.dll /opt/usr/apps/MiniHubBoot/bin/Boot.deps.json /opt/usr/apps/MiniHubBoot/bin/Boot.runtimeconfig.json; fi
ps -eo pid,ppid,uid,comm | grep -E 'Mini|DN_|dotnet|webapp|wrt|enlight|tvctx|tv-viewer|welcome' || true
ps -eo args | awk '/^\/opt\/usr\/apps\/MiniTelemetry\/bin\/Service.dll([[:space:]]|$)/{n++}END{print "telemetry_service_processes=" n+0}'
ps -eo args | awk '/^\/opt\/usr\/apps\/MiniHubBoot\/bin\/Boot.dll([[:space:]]|$)/{n++}END{print "boot_helper_processes=" n+0}'
