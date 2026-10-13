#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu
: "${1:?output directory outside the checkout}"
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$1"
for name in worker bench accept; do
 "${CC:-arm-linux-gnueabi-gcc}" -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-function \
  -fstack-protector-strong -D_FORTIFY_SOURCE=2 -Wl,-z,relro,-z,now \
  ${ARCH_FLAGS:--march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp} \
  "$src/$name.c" -ldl -pthread -o "$1/$name"
done

sh "$src/../native-launcher/build.sh" "$1" --launcher-only
