set -eu
printf '\nORIGINAL CONFIGURATION HASHES\n'
sha256sum /etc/passwd /usr/share/sdbd/public.pem
printf '\nORIGINAL OWNER ACCOUNT\n'
grep '^owner:' /etc/passwd
printf '\nTEMPORARY FILE CLEANUP\n'
test ! -e /home/owner/share/tmp/sdk_tools/codex-namespace-proof
test ! -e /home/owner/share/tmp/sdk_tools/on-demand
printf 'Probe directories absent\n'
printf '\nSHELL IDENTITY\n'
id
printf '\nHOME PROCESSES\n'
ps -eo pid,uid,comm | grep -E 'DN_v.home|DN_tv.home|home.media' || true
printf '\nHOST MOUNT PROPAGATION\n'
head -n 3 /proc/self/mountinfo
