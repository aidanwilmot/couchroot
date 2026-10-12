#!/bin/sh
# QN90A compositor diagnostic; run only through the journaled root transport.
# The installer must bound this unit and provide an independent stop unit.
set -eu
umask 077
out=/tmp/couchroot-boot-capture
mkdir -p "$out"
exec > "$out/timeline" 2>&1
cat /proc/sys/kernel/random/boot_id > "$out/boot-id"
finish() {
 enlightenment_info -dump_buffers 0 >> "$out/buffer-control" 2>&1 || true
 read at rest < /proc/uptime
 printf 'capture-stopped %s\n' "$at"
}
trap finish EXIT
trap 'exit 130' INT TERM HUP
read at rest < /proc/uptime
printf 'capture-start %s\n' "$at"
enlightenment_info -dump_buffers 1 -c 512 -s 0.125 -p "$out" > "$out/buffer-control" 2>&1
last=none
count=0
ready=0
while test "$count" -lt 400; do
 read at rest < /proc/uptime
 rows=$(enlightenment_info -topwins 2>/dev/null | grep 'Minimal Hub' || true)
 if test "$rows" != "$last"; then
  printf 'windows %s\n%s\n' "$at" "$rows"
  last="$rows"
 fi
 available=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
 if test "$available" -lt 350000; then printf 'capture-aborted-low-memory %s %s\n' "$at" "$available"; exit 1; fi
 if grep -q 'event=page-present' /tmp/couchroot-native-hub/boot.log 2>/dev/null; then
  ready=$((ready+1))
  if test "$ready" -ge 25; then printf 'capture-ready-tail-complete %s\n' "$at"; break; fi
 fi
 count=$((count+1))
 sleep 0.1
done
printf 'capture-completed samples=%s\n' "$count"
