#!/bin/sh
# Install a bounded compatibility variant of the existing screensaver boot helper.
set -eu
[ "$(id -u)" = 0 ]
state=/opt/minimal-splash
live=/opt/minimal-saver/Boot.dll
upload=/home/owner/share/tmp/sdk_tools/MinimalHubSplash.dll
original=628205965e629530c645fb069b1f6006abe2431ce6ad5d7066c007ce6fa95ccb
replacement=4a6fdb3d979ab13ed8d38b2bc6e1b9b94e5a04294312d0f9b50cc7f1f0a6c987
# Previous validated build, before diagnostic-I/O error containment.
previous=e10a33fc26a03eea25f2ce0fe63da6d29ed49633068e9cd470ebc59d710b39f7
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
[ ! -L "$state" ] && [ ! -L "$live" ]
case "${1:-}" in
apply)
    grep -qx 'Version=T-PTMDAKUC-0090-2130.0;' /etc/prd_info.ini
    [ "$(vconftool get db/appfw/home_appid)" = 'db/appfw/home_appid, value = MiniHub001.Hub (String)' ]
    [ "$(hash /usr/bin/boot_splashscreen)" = da40cc2088fd63d06fd3170fcb0e797b45125335e154b67912108bce21b29882 ]
    [ "$(hash /usr/apps/com.samsung.tv.csfs/shared/res/homeloading.edj)" = 9895cdeba1abef45c60cf13057cc662f159caf94db17436713cbc9d5649b587f ]
    [ "$(hash "$upload")" = "$replacement" ]
    if [ ! -d "$state" ]; then
        [ "$(hash "$live")" = "$original" ]
        mkdir -m 0700 "$state"
        cp --preserve=all "$live" "$state/Boot.before.dll"
    fi
    [ "$(stat -c '%a %u %g' "$state")" = '700 0 0' ]
    [ ! -L "$state/Boot.before.dll" ]
    [ "$(hash "$state/Boot.before.dll")" = "$original" ]
    current=$(hash "$live")
    [ "$current" = "$original" ] || [ "$current" = "$replacement" ] || [ "$current" = "$previous" ]
    [ ! -e "$live.splash-new" ] && [ ! -L "$live.splash-new" ]
    cp --preserve=all "$live" "$live.splash-new"
    cat "$upload" > "$live.splash-new"
    [ "$(hash "$live.splash-new")" = "$replacement" ]
    mv "$live.splash-new" "$live"
    [ ! -L "$state/enabled" ]
    : > "$state/enabled"
    chmod 0600 "$state/enabled"
    rm "$upload"
    echo 'Splash compatibility helper installed; native resource passed explicitly'
    ;;
status)
    sha256sum "$live"
    if [ -e "$state/enabled" ]; then
        [ "$(hash "$live")" = "$replacement" ]
        echo 'Splash compatibility enabled'
        cat "$state/last-boot.log" 2>/dev/null || true
    else echo 'Splash compatibility disabled'; fi
    ;;
rollback)
    [ -d "$state" ] && [ ! -L "$state/Boot.before.dll" ]
    [ "$(hash "$state/Boot.before.dll")" = "$original" ]
    current=$(hash "$live")
    [ "$current" = "$replacement" ] || [ "$current" = "$original" ] || [ "$current" = "$previous" ]
    [ ! -e "$live.splash-restore" ] && [ ! -L "$live.splash-restore" ]
    rm -f "$state/enabled"
    cp --preserve=all "$state/Boot.before.dll" "$live.splash-restore"
    mv "$live.splash-restore" "$live"
    echo 'Original screensaver helper restored; splash compatibility disabled'
    ;;
*) echo 'Expected apply, status, or rollback' >&2; exit 2 ;;
esac
sha256sum "$live"
