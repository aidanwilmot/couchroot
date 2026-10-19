/* Startup/idle sampler for the native WebView Hub process tree. Diagnostic only:
 * run as root through the journaled transport, bounded by its own deadline.
 *
 *   procsample OUT_DIR EXE_PREFIX SECONDS INTERVAL_MS [SNAPSHOT_SECONDS,...]
 *
 * Roots are processes whose executable path starts with EXE_PREFIX (the Hub
 * install directory); every descendant (Chromium's efl_webprocess children,
 * platform workers) is included. Samples go to OUT_DIR/samples as tab-separated
 *   uptime pid ppid tid comm state utime stime minflt majflt threads rss_pages
 * with one line per thread (tid == pid for the process line). At each snapshot
 * offset (seconds after start) and at the end, OUT_DIR/memory receives PSS and
 * private/shared totals per process, split into the Chromium engine library,
 * other file mappings, anonymous memory and device (GPU) mappings, plus
 * MemAvailable. Once a second OUT_DIR/system receives the aggregate /proc/stat
 * CPU line, running/blocked task counts and every process's CPU ticks, so
 * contention from other boot work is visible. Nothing on the device is changed. */
#define _POSIX_C_SOURCE 200809L
#include <ctype.h>
#include <dirent.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAX_PROCS 4096
static int pids[MAX_PROCS], ppids[MAX_PROCS], roots[MAX_PROCS], member[MAX_PROCS], count, scans;
static int known_pid[MAX_PROCS], known_ppid[MAX_PROCS], known_root[MAX_PROCS], known;
static const char *prefix;

static double uptime(void) {
    double value = -1; FILE *f = fopen("/proc/uptime", "r");
    if (f) { if (fscanf(f, "%lf", &value) != 1) value = -1; fclose(f); }
    return value;
}
/* Fields after the parenthesized comm, which may itself contain spaces. */
static int read_stat(const char *path, char *comm, size_t size, char *state, int *ppid, unsigned long long *out) {
    char line[1024]; FILE *f = fopen(path, "r");
    if (!f) return 0;
    size_t n = fread(line, 1, sizeof line - 1, f); fclose(f); line[n] = 0;
    char *open = strchr(line, '('), *close = strrchr(line, ')');
    if (!open || !close || close < open) return 0;
    size_t length = (size_t)(close - open - 1) < size - 1 ? (size_t)(close - open - 1) : size - 1;
    memcpy(comm, open + 1, length); comm[length] = 0;
    for (char *p = comm; *p; p++) if (*p == '\t' || *p == '\n') *p = ' ';
    /* After state (proc(5) fields 4..24): ppid pgrp session tty tpgid flags minflt
     * cminflt majflt cmajflt utime stime cutime cstime priority nice threads
     * itrealvalue starttime vsize rss. */
    unsigned long long v[21] = { 0 }; int field = 0;
    char *p = close + 2; *state = *p;
    for (char *token = strtok(p + 2, " "); token && field < 21; token = strtok(NULL, " ")) v[field++] = strtoull(token, NULL, 10);
    if (field < 21) return 0;
    *ppid = (int)v[0];
    out[0] = v[10]; out[1] = v[11]; out[2] = v[6]; out[3] = v[8]; out[4] = v[16]; out[5] = v[20];
    return 1; /* utime stime minflt majflt threads rss */
}
/* Boot-time overhead matters: a known process keeps its parent and root flag.
 * Roots are rechecked every scan (few); other processes every tenth scan, so an
 * exec into the Hub executable is still found within a second. */
static int is_root(int pid) {
    char exe[PATH_MAX], link[64]; ssize_t n;
    snprintf(link, sizeof link, "/proc/%d/exe", pid);
    n = readlink(link, exe, sizeof exe - 1);
    exe[n > 0 ? n : 0] = 0;
    return n > 0 && !strncmp(exe, prefix, strlen(prefix));
}
static void scan(void) {
    DIR *d = opendir("/proc"); struct dirent *e; count = 0;
    if (!d) return;
    int full = scans++ % 10 == 0;
    while ((e = readdir(d)) && count < MAX_PROCS) {
        if (!isdigit((unsigned char)e->d_name[0])) continue;
        int pid = atoi(e->d_name), ppid = 0, root = -1;
        for (int k = 0; k < known; k++) if (known_pid[k] == pid) { ppid = known_ppid[k]; root = known_root[k]; break; }
        if (root < 0) {
            char path[64], comm[64], state; unsigned long long v[6];
            snprintf(path, sizeof path, "/proc/%d/stat", pid);
            if (!read_stat(path, comm, sizeof comm, &state, &ppid, v)) continue;
        }
        if (root < 0 || root || full) root = is_root(pid);
        pids[count] = pid; ppids[count] = ppid; roots[count] = root; member[count] = root; count++;
    }
    closedir(d);
    for (int changed = 1; changed;) { /* Descendants of a root are members. */
        changed = 0;
        for (int i = 0; i < count; i++) if (!member[i])
            for (int j = 0; j < count; j++) if (member[j] && pids[j] == ppids[i]) { member[i] = changed = 1; break; }
    }
    memcpy(known_pid, pids, sizeof pids); memcpy(known_ppid, ppids, sizeof ppids); memcpy(known_root, roots, sizeof roots);
    known = count;
}
static void sample(FILE *out) {
    double now = uptime();
    for (int i = 0; i < count; i++) {
        if (!member[i]) continue;
        char path[96]; snprintf(path, sizeof path, "/proc/%d/task", pids[i]);
        DIR *d = opendir(path); struct dirent *e;
        if (!d) continue;
        while ((e = readdir(d))) {
            if (!isdigit((unsigned char)e->d_name[0])) continue;
            char stat[320], comm[64], state; int ppid; unsigned long long v[6];
            snprintf(stat, sizeof stat, "/proc/%d/task/%s/stat", pids[i], e->d_name);
            if (read_stat(stat, comm, sizeof comm, &state, &ppid, v))
                fprintf(out, "%.2f\t%d\t%d\t%s\t%s\t%c\t%llu\t%llu\t%llu\t%llu\t%llu\t%llu\n", now, pids[i], ppids[i],
                        e->d_name, comm, state, v[0], v[1], v[2], v[3], v[4], v[5]);
        }
        closedir(d);
    }
    fflush(out);
}
/* Full smaps walk (works without smaps_rollup). Values in kB. */
static void memory(FILE *out, const char *label) {
    double now = uptime(); long available = -1; char line[512];
    FILE *m = fopen("/proc/meminfo", "r");
    if (m) { while (fgets(line, sizeof line, m)) if (sscanf(line, "MemAvailable: %ld", &available) == 1) break; fclose(m); }
    fprintf(out, "snapshot\t%s\t%.2f\tMemAvailable=%ld\n", label, now, available);
    for (int i = 0; i < count; i++) {
        if (!member[i]) continue;
        char path[64], cmd[160] = ""; snprintf(path, sizeof path, "/proc/%d/cmdline", pids[i]);
        FILE *c = fopen(path, "r");
        if (c) { size_t n = fread(cmd, 1, sizeof cmd - 1, c); fclose(c); for (size_t k = 0; k < n; k++) if (!cmd[k]) cmd[k] = ' '; cmd[n] = 0; }
        snprintf(path, sizeof path, "/proc/%d/smaps", pids[i]);
        FILE *s = fopen(path, "r");
        if (!s) continue;
        /* [0]=engine [1]=other file [2]=anon/heap/stack [3]=device */
        long pss[4] = { 0 }, private_kb[4] = { 0 }, shared[4] = { 0 }, rss = 0, swap = 0; int kind = 2;
        while (fgets(line, sizeof line, s)) {
            unsigned long start, end; char perms[8], name[384] = ""; long value;
            if (sscanf(line, "%lx-%lx %7s %*s %*s %*s %383[^\n]", &start, &end, perms, name) >= 3) {
                char *n = name; while (*n == ' ') n++;
                kind = strstr(n, "libchromium-impl.so") ? 0 : !strncmp(n, "/dev/", 5) ? 3 : (*n == '/' ? 1 : 2);
                continue;
            }
            if (sscanf(line, "Pss: %ld", &value) == 1) pss[kind] += value;
            else if (sscanf(line, "Rss: %ld", &value) == 1) rss += value;
            else if (sscanf(line, "Private_Clean: %ld", &value) == 1 || sscanf(line, "Private_Dirty: %ld", &value) == 1) private_kb[kind] += value;
            else if (sscanf(line, "Shared_Clean: %ld", &value) == 1 || sscanf(line, "Shared_Dirty: %ld", &value) == 1) shared[kind] += value;
            else if (sscanf(line, "Swap: %ld", &value) == 1) swap += value;
        }
        fclose(s);
        fprintf(out, "process\t%d\t%d\trss=%ld\tswap=%ld\tpss=%ld,%ld,%ld,%ld\tprivate=%ld,%ld,%ld,%ld\tshared=%ld,%ld,%ld,%ld\t%s\n",
                pids[i], ppids[i], rss, swap, pss[0], pss[1], pss[2], pss[3], private_kb[0], private_kb[1], private_kb[2],
                private_kb[3], shared[0], shared[1], shared[2], shared[3], cmd);
    }
    fflush(out);
}
/* Whole-system view: what else competes for CPU while the Hub starts. */
static void system_sample(FILE *out) {
    double now = uptime(); char line[512];
    FILE *f = fopen("/proc/stat", "r");
    if (f) {
        while (fgets(line, sizeof line, f)) {
            line[strcspn(line, "\n")] = 0;
            if (!strncmp(line, "cpu ", 4) || !strncmp(line, "procs_", 6)) fprintf(out, "stat\t%.2f\t%s\n", now, line);
        }
        fclose(f);
    }
    DIR *d = opendir("/proc"); struct dirent *e;
    if (!d) return;
    while ((e = readdir(d))) {
        if (!isdigit((unsigned char)e->d_name[0])) continue;
        char path[300], comm[64], state; int ppid; unsigned long long v[6];
        snprintf(path, sizeof path, "/proc/%s/stat", e->d_name);
        if (read_stat(path, comm, sizeof comm, &state, &ppid, v))
            fprintf(out, "proc\t%.2f\t%s\t%d\t%s\t%c\t%llu\t%llu\t%llu\n", now, e->d_name, ppid, comm, state, v[0], v[1], v[3]);
    }
    closedir(d);
    fflush(out);
}
int main(int argc, char **argv) {
    if (argc < 5 || argv[2][0] != '/') { fputs("usage: procsample OUT_DIR EXE_PREFIX SECONDS INTERVAL_MS [S1,S2...]\n", stderr); return 2; }
    prefix = argv[2];
    double seconds = atof(argv[3]), interval = atof(argv[4]) / 1000, snaps[16]; int snap_count = 0, taken = 0;
    if (seconds <= 0 || seconds > 600 || interval < 0.02 || interval > 5) return 2;
    for (char *t = argc > 5 ? strtok(argv[5], ",") : NULL; t && snap_count < 16; t = strtok(NULL, ",")) snaps[snap_count++] = atof(t);
    char path[PATH_MAX];
    snprintf(path, sizeof path, "%s/samples", argv[1]); FILE *samples = fopen(path, "w");
    snprintf(path, sizeof path, "%s/memory", argv[1]); FILE *mem = fopen(path, "w");
    snprintf(path, sizeof path, "%s/system", argv[1]); FILE *sys = fopen(path, "w");
    if (!samples || !mem || !sys) return 3;
    double next_system = 0;
    struct timespec begin, t; clock_gettime(CLOCK_MONOTONIC, &begin);
    for (;;) {
        clock_gettime(CLOCK_MONOTONIC, &t);
        double elapsed = (t.tv_sec - begin.tv_sec) + (t.tv_nsec - begin.tv_nsec) / 1e9;
        scan();
        sample(samples);
        if (elapsed >= next_system) { system_sample(sys); next_system = (double)(long)elapsed + 1; }
        if (taken < snap_count && elapsed >= snaps[taken]) { char label[32]; snprintf(label, sizeof label, "t+%g", snaps[taken++]); memory(mem, label); }
        if (elapsed >= seconds) break;
        struct timespec pause = { (time_t)interval, (long)((interval - (time_t)interval) * 1e9) };
        nanosleep(&pause, NULL);
    }
    memory(mem, "end");
    system_sample(sys);
    fclose(samples); fclose(mem); fclose(sys); return 0;
}
