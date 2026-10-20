#!/bin/sh
# Run as root in PID 1's mount namespace. Restores only our known overlay.
set -eu
stock=/usr/apps/com.samsung.tv.spotlight-ss/lib/arm/libgl-demo-app.so
original=4f0b36d9639a194936def6250a03db1383db284f11f74d83ec7dda50420befaa
replacement=db5656113275e613d9475c09af1c768cd8ad57d60eac31213214684721cc418a
[ "$(id -u)" = 0 ]
[ "$(readlink /proc/self/ns/mnt)" = "$(readlink /proc/1/ns/mnt)" ]
current=$(sha256sum "$stock" | cut -d ' ' -f 1)
if [ "$current" = "$replacement" ] || [ "$current" = e1a24d13c3336aefb11c7de9a867f58d6069efbc9b4169e4d3a3a41304838b01 ] || [ "$current" = 9b555ee2eb6ae72ffb91447ebee6426c5bf34af7afd31980f6975429f41eec88 ]; then
    /usr/bin/input_keyevent XF86Back
    sleep 7
    awk -v p="$stock" '$5==p && ($4=="/usr/home/owner/share/minimal-saver/libgl-demo-app.so" || $4=="/minimal-saver/libgl-demo-app.so") {found=1} END {exit !found}' /proc/self/mountinfo
    umount "$stock"
fi
[ "$(sha256sum "$stock" | cut -d ' ' -f 1)" = "$original" ]
# A normal remote key dismisses any renderer process already holding old bytes.
/usr/bin/input_keyevent XF86Back
rm -f /opt/usr/home/owner/share/minimal-saver/libgl-demo-app.so
if [ -d /opt/usr/home/owner/share/minimal-saver ]; then
    rmdir /opt/usr/home/owner/share/minimal-saver
fi
printf 'Samsung renderer restored and original hash verified\n'
