#!/bin/sh
# Reviewed firmware-specific installer. Run through control.py enable-boot.
set -eu
[ "$(id -u)" = 0 ]
[ "$(readlink /proc/self/ns/mnt)" = "$(readlink /proc/1/ns/mnt)" ]
state=/opt/minimal-saver
stage=/home/owner/share/tmp/sdk_tools/minimal-saver-boot
cache=/opt/etc/systemd/oneservice
[ "$(sha256sum "$cache" | cut -d ' ' -f 1)" = 3ffa26a62b1550c3e85993953bb59cf3cc38d688ddfd4f9d500cc37b6db15123 ]
[ "$(sha256sum "$cache.table" | cut -d ' ' -f 1)" = afba7a1d0bf0d2ae60b9f1d63c44001efff868eea03238c1ff2b4fd70f9b5433 ]
[ "$(sha256sum /opt/etc/parseinfo.sh | cut -d ' ' -f 1)" = c6369e7dec69408e176daa252d436acf6f8e265f560504d8bd831c8023c71d61 ]
[ ! -L "$state" ]
[ ! -e "$cache.minimal-saver-new" ]
[ "$(sha256sum "$stage/Boot.dll" | cut -d ' ' -f 1)" = "628205965e629530c645fb069b1f6006abe2431ce6ad5d7066c007ce6fa95ccb" ]
[ "$(sha256sum "$stage/Boot.runtimeconfig.json" | cut -d ' ' -f 1)" = "aeb46a15366e38511c192ccf65312442c64e8753b3c16fd2ca0b4cb34a5c59f3" ]
[ "$(sha256sum "$stage/Boot.deps.json" | cut -d ' ' -f 1)" = "1fc77836e08738a12f514afc9ce98ffec6bd756a11854962b2d9f3575819d049" ]
[ "$(sha256sum "$stage/oneservice.patched" | cut -d ' ' -f 1)" = "6cf17c5e96002b350bc7a7f4ba9a4c1b55a2d3fe9213570bcb7c3beab750598c" ]
if [ -d "$state" ]; then
    [ "$(sha256sum "$state/oneservice.original" | cut -d ' ' -f 1)" = 3ffa26a62b1550c3e85993953bb59cf3cc38d688ddfd4f9d500cc37b6db15123 ]
    [ "$(sha256sum "$state/oneservice.table.original" | cut -d ' ' -f 1)" = afba7a1d0bf0d2ae60b9f1d63c44001efff868eea03238c1ff2b4fd70f9b5433 ]
else
    mkdir -m 0700 "$state"
    cp --preserve=all "$cache" "$state/oneservice.original"
    cp --preserve=all "$cache.table" "$state/oneservice.table.original"
    cp --preserve=all /opt/etc/parseinfo.sh "$state/parseinfo.original.sh"
fi
if [ ! -e "$state/libgl-demo-app.so" ]; then
    cp --preserve=all /opt/usr/home/owner/share/minimal-saver/libgl-demo-app.so "$state/libgl-demo-app.so"
    chown root:root "$state/libgl-demo-app.so"
fi
[ "$(sha256sum "$state/libgl-demo-app.so" | cut -d ' ' -f 1)" = db5656113275e613d9475c09af1c768cd8ad57d60eac31213214684721cc418a ]
for f in Boot.dll Boot.runtimeconfig.json Boot.deps.json; do
    [ ! -e "$state/$f.new" ]
    cp "$stage/$f" "$state/$f.new"
    chown root:root "$state/$f.new"
    chmod 0600 "$state/$f.new"
    mv -f "$state/$f.new" "$state/$f"
done
: > "$state/enabled"
chmod 0600 "$state/enabled"
# First test the helper directly in the main mount namespace. The cache remains original.
/usr/bin/dotnet "$state/Boot.dll"
cat "$state/last-boot.log"
grep -Eq '^(active:|already active)' "$state/last-boot.log"
cp --preserve=all "$cache" "$cache.minimal-saver-new"
cat "$stage/oneservice.patched" > "$cache.minimal-saver-new"
[ "$(sha256sum "$cache.minimal-saver-new" | cut -d ' ' -f 1)" = 6cf17c5e96002b350bc7a7f4ba9a4c1b55a2d3fe9213570bcb7c3beab750598c ]
mv -f "$cache.minimal-saver-new" "$cache"
sync
systemctl daemon-reload
systemctl show AT-HUB.service -p ExecStart -p ActiveState -p SubState
sha256sum "$cache" "$cache.table" /opt/etc/parseinfo.sh
rm -f "$stage/Boot.dll" "$stage/Boot.runtimeconfig.json" "$stage/Boot.deps.json" "$stage/oneservice.patched"
rmdir "$stage"
