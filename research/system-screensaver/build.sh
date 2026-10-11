#!/bin/sh
# Linux build with gcc-arm-linux-gnueabi, libc6-dev-armel-cross and GLES2 headers.
# GLES_LIBRARY_DIR must contain this TV's libGLESv2.so.2 (private, not in git).
set -eu
: "${GLES_LIBRARY_DIR:?Set to a directory containing the TV libGLESv2.so.2}"
cd "$(dirname "$0")"
mkdir -p bin
arm-linux-gnueabi-gcc -std=c99 -D_POSIX_C_SOURCE=200809L \
  -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp \
  -O2 -Wall -Wextra -Werror -fPIC -shared \
  -Wl,-soname,libgl-demo-app.so -Wl,-z,defs \
  -I/usr/include -L"$GLES_LIBRARY_DIR" \
  -o bin/libgl-demo-app.so renderer.c -l:libGLESv2.so.2 -lm
arm-linux-gnueabi-readelf -h -V bin/libgl-demo-app.so
sha256sum bin/libgl-demo-app.so
