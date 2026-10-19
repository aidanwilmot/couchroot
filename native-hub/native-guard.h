#ifndef NATIVE_GUARD_INCLUDED
#define NATIVE_GUARD_INCLUDED
#define PLATFORM_TRACE_READS 1
#include "../native/common/platform-core.h"
static int native_boot_guard(void) { return platform_boot_guard(); }
#endif
