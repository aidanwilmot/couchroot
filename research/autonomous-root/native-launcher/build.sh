#!/bin/sh
# Original Couchroot prototype build. SPDX-License-Identifier: 0BSD
set -eu
if test "$#" -lt 1 || test "$#" -gt 2 || { test "$#" -eq 2 && test "$2" != --launcher-only; }; then
    echo 'usage: build.sh OUTPUT_DIRECTORY [--launcher-only] (outside the source tree)' >&2
    exit 64
fi
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$1"
targets="app-launcher bench"
if test "$#" -eq 2; then targets=app-launcher; fi
for name in $targets; do
    "${CC:-arm-linux-gnueabi-gcc}" -std=c99 -O2 -Wall -Wextra -Werror \
        -fstack-protector-strong -D_FORTIFY_SOURCE=2 -Wl,-z,relro,-z,now \
        -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp \
        "$src/$name.c" -o "$1/$name"
done
