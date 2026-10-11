#include "collector.h"
#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

double uptime_seconds(void) {
    struct timespec t;
    return clock_gettime(CLOCK_BOOTTIME, &t) ? -1 : t.tv_sec + t.tv_nsec / 1e9;
}

struct json_object *sample(uint64_t sequence, const char *boot, const char *session, const char *device) {
    struct json_object *obj = json_object_new_object();
    if (!obj) return NULL;
    struct timespec cpu;
    unsigned long pages, resident;
    char *statm = read_bounded("/proc/self/statm", 256);
    if (!statm || sscanf(statm, "%lu %lu", &pages, &resident) != 2 ||
        clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &cpu)) {
        free(statm); json_object_put(obj); return NULL;
    }
    free(statm);
    json_object_object_add(obj, "schema", json_object_new_int(1));
    json_object_object_add(obj, "boot", json_object_new_string(boot));
    json_object_object_add(obj, "session", json_object_new_string(session));
    json_object_object_add(obj, "device", json_object_new_string(device));
    json_object_object_add(obj, "seq", json_object_new_int64((int64_t)sequence));
    json_object_object_add(obj, "uptime", json_object_new_double(uptime_seconds()));
    json_object_object_add(obj, "collector_cpu_seconds", json_object_new_double(cpu.tv_sec + cpu.tv_nsec / 1e9));
    json_object_object_add(obj, "collector_rss_bytes", json_object_new_int64((int64_t)resident * sysconf(_SC_PAGESIZE)));
    const char *keys[] = {"stat", "meminfo", "netdev", "diskstats"};
    const char *paths[] = {"/proc/stat", "/proc/meminfo", "/proc/net/dev", "/proc/diskstats"};
    for (int i = 0; i < 4; ++i) {
        char *text = read_bounded(paths[i], COUNTER_LIMIT);
        json_object_object_add(obj, keys[i], text ? json_object_new_string(text) : NULL);
        free(text);
    }
    return obj;
}
