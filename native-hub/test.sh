#!/bin/sh
set -eu
native_test_source=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
native_test_tmp=$(mktemp -d)
trap 'rm -rf "$native_test_tmp"' EXIT HUP INT TERM
cc -D_DARWIN_C_SOURCE -std=c99 -O2 -Wall -Wextra -Werror \
 -Wno-misleading-indentation -Wno-unused-function \
 "$native_test_source/ui_test.c" -lm -ldl -o "$native_test_tmp/ui-test"
"$native_test_tmp/ui-test" "$@"
cc -D_DARWIN_C_SOURCE -O2 -Wall -Wextra -Wno-unused-function -Wno-misleading-indentation \
 "$native_test_source/guard_test.c" -ldl -o "$native_test_tmp/guard-test"
"$native_test_tmp/guard-test"
