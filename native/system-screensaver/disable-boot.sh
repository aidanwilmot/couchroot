#!/bin/sh
# Invoked as reviewed inline commands through the existing root collector.
set -eu
[ "$(id -u)" = 0 ]
cache=/opt/etc/systemd/oneservice
state=/opt/minimal-saver
original=3ffa26a62b1550c3e85993953bb59cf3cc38d688ddfd4f9d500cc37b6db15123
patched=6cf17c5e96002b350bc7a7f4ba9a4c1b55a2d3fe9213570bcb7c3beab750598c
current=$(sha256sum "$cache" | cut -d ' ' -f 1)
if [ "$current" = "$patched" ]; then
    [ "$(sha256sum "$state/oneservice.original" | cut -d ' ' -f 1)" = "$original" ]
    [ ! -e "$cache.minimal-saver-restore" ]
    cp --preserve=all "$state/oneservice.original" "$cache.minimal-saver-restore"
    chmod 0644 "$cache.minimal-saver-restore"
    mv -f "$cache.minimal-saver-restore" "$cache"
    systemctl daemon-reload
elif [ "$current" != "$original" ]; then
    echo 'Cache changed independently; refusing to overwrite it' >&2
    exit 1
fi
rm -f "$state/enabled"
[ "$(sha256sum "$cache" | cut -d ' ' -f 1)" = "$original" ]
echo 'Automatic loading disabled; original service cache restored'
