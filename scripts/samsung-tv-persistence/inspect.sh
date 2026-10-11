set -u
printf '\nBOOT\n'
cat /proc/sys/kernel/random/boot_id /proc/uptime /etc/tizen-release /etc/info.ini
printf '\nENTRY POINT\n'
systemctl cat sdbd.service sdbd_tcp.socket AT-HUB.service
systemctl show sdbd.service sdbd_tcp.socket -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p DropInPaths -p MainPID
printf '\nPERSISTENT PATHS\n'
for p in /etc/systemd/system /opt/etc/systemd /opt/etc /opt/etc/parseinfo.sh /opt/etc/get_top_process.sh /home/owner/apps_rw/com.samsung.tv.store/data/develop_mode /home/owner/share/tmp/sdk_tools /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher /run/sdbd-env; do
 ls -ldZ "$p" 2>/dev/null
 stat -c '%n %u:%g %a %s' "$p" 2>/dev/null
 if test -w "$p"; then printf 'SDK_WRITABLE %s\n' "$p"; fi
done
printf '\nCAPABILITIES\n'
command -v getcap >/dev/null && getcap /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher
cat /proc/self/attr/current
grep -E '^(Uid|Gid|Cap|NoNewPrivs)' /proc/self/status
printf '\nORIGINAL HASHES\n'
sha256sum /etc/passwd /usr/share/sdbd/public.pem /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher /opt/etc/parseinfo.sh
printf '\nBOOT LINKS\n'
ls -l /etc/systemd/system/*/sdb* /usr/lib/systemd/system/*/sdb* /etc/rc.local /etc/rc.d/rc.local 2>/dev/null
printf '\nREBOOT COMMAND\n'
ls -l /sbin/reboot /usr/sbin/reboot
printf '\nHEALTH\n'
systemctl --failed --no-pager
ps -eo pid,uid,comm | grep -E 'sdb|home|csfs|webapp|wrt|Plex|YouTube'
printf '\nSTAGING\n'
ls -la /home/owner/share/tmp/sdk_tools
printf '\nMOUNTS\n'
cat /proc/self/mountinfo
true
