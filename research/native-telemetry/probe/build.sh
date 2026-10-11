#!/bin/sh
# Build only. The output and signed packages belong outside the source tree.
set -eu
: "${PROBE_OUTPUT_DIR:?Set an absolute private output directory}"
case "$PROBE_OUTPUT_DIR" in /*) ;; *) echo 'Output directory must be absolute' >&2; exit 2;; esac
probe_source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$PROBE_OUTPUT_DIR"
"${ARM_CC:-arm-linux-gnueabi-gcc}" -O2 -Wall -Wextra -Werror \
  -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp \
  -o "$PROBE_OUTPUT_DIR/probe" "$probe_source/probe.c"
"${ARM_CC:-arm-linux-gnueabi-gcc}" -O2 -Wall -Wextra -Werror \
  -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp \
  -o "$PROBE_OUTPUT_DIR/resident-probe" "$probe_source/resident.c"
dotnet build "$probe_source/owner/OwnerProbe.csproj" -c Release --nologo -v quiet
dotnet build "$probe_source/launch/Launch.csproj" -c Release --nologo -v quiet
