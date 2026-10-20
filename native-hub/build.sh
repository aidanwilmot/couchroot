#!/bin/sh
# Build only. Keep the ARM artifact outside the source repository.
set -eu
: "${NATIVE_HUB_OUTPUT_DIR:?Set an absolute private output directory}"
case "$NATIVE_HUB_OUTPUT_DIR" in /*) ;; *) exit 2;; esac
mkdir -p "$NATIVE_HUB_OUTPUT_DIR"
native_source=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# Stream the source so host/container shared-filesystem caching cannot expose a
# partially refreshed source file. Only the output directory is mounted.
(python3 - "$native_source" <<'PYBUILD'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
print('#define PLATFORM_TRACE_READS 1')
print((p.parent/'native/common/platform-core.h').read_text())
print((p/'native-guard.h').read_text().replace('#include "../native/common/platform-core.h"',''))
print((p.parent/'native/common/preferences.h').read_text())
print((p/'hub-model.h').read_text().replace('#include "../native/common/preferences.h"',''))
s=(p/'prototype.c').read_text().replace('#include "hub-ui.h"', (p/'hub-ui.h').read_text().replace('#include "hub-model.h"','').replace('#include "hub-art.h"',(p/'hub-art.h').read_text().replace('#include "hub-cards.h"',(p/'hub-cards.h').read_text())))
s=s.replace('#include "hub-profile.h"',(p/'hub-profile.h').read_text())
s=s.replace('#include "hub-platform.h"',(p/'hub-platform.h').read_text()).replace('#include "hub-lifecycle.h"',(p/'hub-lifecycle.h').read_text())
print(s)
PYBUILD
) | docker run --rm -i --platform linux/amd64 --network none \
 -v "$NATIVE_HUB_OUTPUT_DIR:/out" samsung-native-collector:bullseye \
 arm-linux-gnueabi-gcc -D_GNU_SOURCE -D_POSIX_C_SOURCE=200809L -x c -std=c99 -O2 -Wall -Wextra -Werror \
 -Wno-misleading-indentation -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp \
 - -ldl -lm -lpthread -o /out/native-hub

# Reject accidentally introduced interfaces newer than this firmware baseline.
docker run --rm --platform linux/amd64 --network none \
 -v "$NATIVE_HUB_OUTPUT_DIR:/out:ro" samsung-native-collector:bullseye \
 arm-linux-gnueabi-readelf -V /out/native-hub | python3 -c '
import re,sys
versions=set(re.findall(r"GLIBC_(\d+)\.(\d+)",sys.stdin.read()))
assert versions, "No GLIBC version information found"
bad=sorted(v for v in versions if tuple(map(int,v)) > (2,17))
if bad: raise SystemExit("Unsupported GLIBC requirements: " + repr(bad))
print("ARM build: GLIBC requirements <= 2.17")
'

# The UI/profiler needs libpthread present before loading the platform libraries.
docker run --rm --platform linux/amd64 --network none \
 -v "$NATIVE_HUB_OUTPUT_DIR:/out:ro" samsung-native-collector:bullseye \
 arm-linux-gnueabi-readelf -d /out/native-hub | python3 -c '
import sys
if "[libpthread.so.0]" not in sys.stdin.read(): raise SystemExit("Missing startup libpthread dependency")
print("ARM build: libpthread loaded at startup")
'
