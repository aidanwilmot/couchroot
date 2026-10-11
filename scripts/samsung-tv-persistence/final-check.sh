set -eu
printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id
cat /proc/uptime
test ! -e /home/owner/share/tmp/sdk_tools/codex-namespace-proof
test ! -e /home/owner/share/tmp/sdk_tools/on-demand
if ps -eo args | grep -E '^/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/codex-namespace-proof/' >/dev/null; then
  echo 'A root helper is still running' >&2; exit 3
fi
if grep -E ' /etc/passwd | /usr/share/sdbd/public.pem ' /proc/self/mountinfo; then
  echo 'Unexpected host bind mount' >&2; exit 3
fi
test "$(id -u)" = 901
ls -la /home/owner/share/tmp/sdk_tools
printf 'No root helpers, private overrides, or staged root payloads remain.\n'
systemctl show sdbd.service sdbd_tcp.socket -p ActiveState -p SubState
