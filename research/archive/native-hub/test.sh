#!/bin/sh
set -eu
native_test_source=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
native_test_tmp=$(mktemp -d)
trap 'rm -rf "$native_test_tmp"' EXIT HUP INT TERM
cc -D_DARWIN_C_SOURCE -std=c99 -O2 -Wall -Wextra -Werror \
 -Wno-misleading-indentation -Wno-unused-function \
 "$native_test_source/ui_test.c" -lm -ldl -pthread -o "$native_test_tmp/ui-test"
"$native_test_tmp/ui-test" "$@"
cc -D_DARWIN_C_SOURCE -O2 -Wall -Wextra -Wno-unused-function -Wno-misleading-indentation \
 "$native_test_source/guard_test.c" -ldl -o "$native_test_tmp/guard-test"
"$native_test_tmp/guard-test"
# The real profiler thread exists only on Linux; macOS compiles its inert stub.
if [ "$(uname -s)" = Linux ]; then
 native_test_tsan=
 [ "${COUCHROOT_TSAN:-}" = 1 ] && native_test_tsan=-fsanitize=thread
 cc -std=c99 -O2 -g -Wall -Wextra -Werror -Wno-misleading-indentation -Wno-unused-function $native_test_tsan \
  "$native_test_source/profile_test.c" -pthread -o "$native_test_tmp/profile-test"
 "$native_test_tmp/profile-test" >/dev/null
else
 echo "native profiler thread test skipped: requires Linux"
fi
