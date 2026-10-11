#!/bin/sh
# Run as root in PID 1's mount namespace, after staging the reviewed library.
set -eu
stock=/usr/apps/com.samsung.tv.spotlight-ss/lib/arm/libgl-demo-app.so
original=4f0b36d9639a194936def6250a03db1383db284f11f74d83ec7dda50420befaa
replacement=db5656113275e613d9475c09af1c768cd8ad57d60eac31213214684721cc418a
stage=/home/owner/share/tmp/sdk_tools/minimal-saver-renderer.so
state=/opt/usr/home/owner/share/minimal-saver
library=$state/libgl-demo-app.so
[ "$(id -u)" = 0 ]
[ "$(readlink /proc/self/ns/mnt)" = "$(readlink /proc/1/ns/mnt)" ]
grep -q 'T-PTMDAKUC' /etc/prd_info.ini
[ "$(sha256sum "$stage" | cut -d ' ' -f 1)" = "$replacement" ]
current=$(sha256sum "$stock" | cut -d ' ' -f 1)
if [ "$current" = "$replacement" ]; then rm -f "$stage"; echo 'Replacement already active'; exit 0; fi
[ "$current" = "$original" ]
# Refuse unknown prior mount instead of stacking over it.
! awk -v p="$stock" '$5==p {found=1} END {exit !found}' /proc/self/mountinfo
[ ! -L "$state" ]
mkdir -p "$state"
chmod 0755 "$state"
[ ! -L "$library" ]
if [ -e "$library" ]; then
    [ "$(sha256sum "$library" | cut -d ' ' -f 1)" = "$replacement" ]
fi
# Preserve Samsung's existing file ownership, mode, and SMACK label.
cp --preserve=all "$stock" "$library"
cat "$stage" > "$library"
[ "$(sha256sum "$library" | cut -d ' ' -f 1)" = "$replacement" ]
ls -lZ "$library"
mounted=no
trap 'if [ "$mounted" = yes ]; then umount "$stock"; fi' EXIT
mount --bind "$library" "$stock"
mounted=yes
mount -o remount,bind,ro "$stock"
if [ "$(sha256sum "$stock" | cut -d ' ' -f 1)" != "$replacement" ]; then
    exit 1
fi
mounted=no
trap - EXIT
rm -f "$stage"
echo 'Renderer overlay installed; original firmware file unchanged'
awk -v p="$stock" '$5==p' /proc/self/mountinfo
