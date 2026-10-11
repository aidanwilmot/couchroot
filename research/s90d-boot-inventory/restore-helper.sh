#!/bin/sh
# Restore the exact pre-trace helper; do not remove recorded evidence.
set -eu
[ "$(id -u)" = 0 ]
root=/opt/boot-inventory
[ "$(sha256sum "$root/Boot.before.dll" | cut -d ' ' -f 1)" = 628205965e629530c645fb069b1f6006abe2431ce6ad5d7066c007ce6fa95ccb ]
[ "$(sha256sum /opt/minimal-saver/Boot.dll | cut -d ' ' -f 1)" = 881a2905980349e022ad42057c07a7ec467495d902b82b162f0e09a11f773894 ]
rm -f "$root/enabled"
cp --preserve=all "$root/Boot.before.dll" /opt/minimal-saver/Boot.dll.restore
mv /opt/minimal-saver/Boot.dll.restore /opt/minimal-saver/Boot.dll
sha256sum /opt/minimal-saver/Boot.dll
