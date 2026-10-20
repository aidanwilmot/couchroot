#!/bin/sh
# Upgrade the known persistent geometric renderer to the reviewed Asteroids build.
# Run in PID 1's mount namespace via control.py update. Keep a complete old pair.
set -eu
state=/opt/minimal-saver
stage=/home/owner/share/tmp/sdk_tools/minimal-saver-update
stock=/usr/apps/com.samsung.tv.spotlight-ss/lib/arm/libgl-demo-app.so
old=e1a24d13c3336aefb11c7de9a867f58d6069efbc9b4169e4d3a3a41304838b01
new=db5656113275e613d9475c09af1c768cd8ad57d60eac31213214684721cc418a
oldboot=f3e6b6433938ba2bcbddfc1cbd21d5d156237af3455529268119ed5e0ee9b82c
newboot=628205965e629530c645fb069b1f6006abe2431ce6ad5d7066c007ce6fa95ccb
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
[ "$(id -u)" = 0 ]
[ "$(readlink /proc/self/ns/mnt)" = "$(readlink /proc/1/ns/mnt)" ]
[ ! -L "$state" ]
[ -f "$state/enabled" ]
[ "$(hash /opt/etc/systemd/oneservice)" = 6cf17c5e96002b350bc7a7f4ba9a4c1b55a2d3fe9213570bcb7c3beab750598c ]
[ "$(hash "$stage/libgl-demo-app.so")" = "$new" ]
[ "$(hash "$stage/Boot.dll")" = "$newboot" ]
awk -v p="$stock" '$5==p && $4=="/minimal-saver/libgl-demo-app.so" && $6 ~ /^ro,/ {found=1} END {exit !found}' /proc/self/mountinfo
if [ "$(hash "$stock")" = "$new" ]; then
    [ "$(hash "$state/libgl-demo-app.so")" = "$new" ]
    [ "$(hash "$state/Boot.dll")" = "$newboot" ]
    rm -f "$stage/libgl-demo-app.so" "$stage/Boot.dll"
    rmdir "$stage"
    echo 'Asteroids renderer and reboot helper already installed'
    exit 0
fi
[ "$(hash "$stock")" = "$old" ]
[ "$(hash "$state/libgl-demo-app.so")" = "$old" ]
[ "$(hash "$state/Boot.dll")" = "$oldboot" ]
backup=$state/before-asteroids
[ ! -e "$backup" ]
mkdir -m 0700 "$backup"
cp --preserve=all "$state/libgl-demo-app.so" "$state/Boot.dll" "$backup/"
[ ! -e "$state/libgl-demo-app.so.new" ]
[ ! -e "$state/Boot.dll.new" ]
# Preserve the renderer's original SMACK label; replace by rename, never overwrite
# the mounted/mapped inode. The boot cache and signed diagnostic remain untouched.
cp --preserve=all "$state/libgl-demo-app.so" "$state/libgl-demo-app.so.new"
cat "$stage/libgl-demo-app.so" > "$state/libgl-demo-app.so.new"
cp --preserve=all "$state/Boot.dll" "$state/Boot.dll.new"
cat "$stage/Boot.dll" > "$state/Boot.dll.new"
[ "$(hash "$state/libgl-demo-app.so.new")" = "$new" ]
[ "$(hash "$state/Boot.dll.new")" = "$newboot" ]
/usr/bin/input_keyevent XF86Back
sleep 7
! ps -eo comm | grep -Eq '^DN_(spotlight-ss|ver-launcher)$'
umount "$stock"
restore() {
    trap - EXIT
    if awk -v p="$stock" '$5==p {found=1} END {exit !found}' /proc/self/mountinfo; then umount "$stock" || return; fi
    cp --preserve=all "$backup/libgl-demo-app.so" "$state/libgl-demo-app.so.restore"
    cp --preserve=all "$backup/Boot.dll" "$state/Boot.dll.restore"
    mv -f "$state/libgl-demo-app.so.restore" "$state/libgl-demo-app.so"
    mv -f "$state/Boot.dll.restore" "$state/Boot.dll"
    /usr/bin/dotnet "$state/Boot.dll"
    sync
}
trap restore EXIT
[ "$(hash "$stock")" = 4f0b36d9639a194936def6250a03db1383db284f11f74d83ec7dda50420befaa ]
mv -f "$state/libgl-demo-app.so.new" "$state/libgl-demo-app.so"
mv -f "$state/Boot.dll.new" "$state/Boot.dll"
sync
/usr/bin/dotnet "$state/Boot.dll"
grep -q '^active:' "$state/last-boot.log"
[ "$(hash "$stock")" = "$new" ]
trap - EXIT
rm -f "$stage/libgl-demo-app.so" "$stage/Boot.dll"
rmdir "$stage"
echo 'Asteroids renderer and reboot helper installed; previous pair backed up'
echo 'A full reboot and native visual check are required to validate app-loader acceptance.'
cat "$state/last-boot.log"
ls -lZ "$state/libgl-demo-app.so" "$state/Boot.dll"
