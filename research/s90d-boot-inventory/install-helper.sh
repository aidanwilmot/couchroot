#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
grep -q '^Version=T-PTMDAKUC-0090-2130.0;' /etc/prd_info.ini
root=/opt/boot-inventory
stage=/home/owner/share/tmp/sdk_tools
[ ! -L "$root" ]
[ "$(sha256sum /opt/minimal-saver/Boot.dll | cut -d ' ' -f 1)" = 628205965e629530c645fb069b1f6006abe2431ce6ad5d7066c007ce6fa95ccb ]
[ "$(sha256sum "$stage/Boot.trace.dll" | cut -d ' ' -f 1)" = 881a2905980349e022ad42057c07a7ec467495d902b82b162f0e09a11f773894 ]
[ "$(sha256sum "$stage/Recorder.dll" | cut -d ' ' -f 1)" = 9e7a5706fca1aa2b525b19b546579ae1d6f9f2b8773094e06aac389b66b23dcd ]
[ ! -e "$root/Boot.before.dll" ]
cp --preserve=all /opt/minimal-saver/Boot.dll "$root/Boot.before.dll"
cp --preserve=all /opt/minimal-saver/Boot.dll /opt/minimal-saver/Boot.dll.trace-new
cat "$stage/Boot.trace.dll" > /opt/minimal-saver/Boot.dll.trace-new
cp --preserve=all "$root/Recorder.dll" "$root/Recorder.dll.new"
cat "$stage/Recorder.dll" > "$root/Recorder.dll.new"
mv "$root/Recorder.dll.new" "$root/Recorder.dll"
mv /opt/minimal-saver/Boot.dll.trace-new /opt/minimal-saver/Boot.dll
: > "$root/enabled"
chmod 0600 "$root/enabled"
rm -f "$stage/Boot.trace.dll" "$stage/Recorder.dll"
sha256sum /opt/minimal-saver/Boot.dll "$root/Recorder.dll" "$root/Boot.before.dll"
