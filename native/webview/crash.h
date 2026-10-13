/* Crash capture for the boot supervisor. Included by launcher.h.
 *
 * QN90A's kernel holds a crashing process about 20 s before it exits (Samsung's
 * minimal-core wait) and writes no core; in-process signal handlers are not
 * invoked. The process stays readable by its same-user parent meanwhile. The
 * supervisor checks one stat line per poll; once the child carries PF_SIGNALED
 * it records every thread's user stack and program counters
 * (/proc/<pid>/task/<tid>/syscall), a bounded scan of each stack for words that
 * point into executable mappings (candidate return addresses, resolved to
 * library+offset), and the executable mappings themselves. The scan is
 * heuristic: stale words appear, so frames are confirmed offline against the
 * libraries. Words are 32-bit, as on the QN90A's ARMv7 userspace. */
#include <dirent.h>
#include <fcntl.h>
#include <stdint.h>

#ifndef PROC_ROOT
#define PROC_ROOT "/proc" /* Overridable only for desktop tests. */
#endif
#define TASK_PF_EXITING 0x00000004
#define TASK_PF_SIGNALED 0x00000400
#if defined(__linux__)
/* /proc/<pid>/mem offsets are addresses above 2 GiB; 32-bit ARM's off_t is
 * 32-bit and _FILE_OFFSET_BITS=64 would need glibc 2.28 (fcntl64). glibc has
 * exported pread64 since 2.2. */
extern ssize_t pread64(int, void *, size_t, int64_t);
#define crash_pread(fd, buffer, size, address) pread64(fd, buffer, size, (int64_t)(address))
#else
#define crash_pread(fd, buffer, size, address) pread(fd, buffer, size, (off_t)(address))
#endif
#define CRASH_MAPS_MAX 65536    /* The QN90A Hub has ~1450 mappings; the table grows as needed. */
#define CRASH_FAULT_SCAN 24576   /* Bytes scanned above sp: threads not yet exiting. */
#define CRASH_FAULT_FRAMES 96
#define CRASH_THREAD_SCAN 8192   /* Other threads (already exiting). */
#define CRASH_THREAD_FRAMES 24

typedef struct { unsigned long start, end, offset; int exec; char name[64]; } CrashMap;

static int crash_stat(const char *path, char *comm, size_t size, char *state, unsigned long *flags) {
    char line[512]; FILE *f = fopen(path, "r");
    if (!f) return 0;
    size_t n = fread(line, 1, sizeof line - 1, f); fclose(f); line[n] = 0;
    char *open = strchr(line, '('), *close = strrchr(line, ')');
    if (!open || !close || close < open) return 0;
    size_t length = (size_t)(close - open - 1) < size - 1 ? (size_t)(close - open - 1) : size - 1;
    memcpy(comm, open + 1, length); comm[length] = 0;
    for (char *c = comm; *c; c++) if (*c < 0x20 || *c == 0x7f) *c = '?';
    int ppid, pgrp, session, tty, tpgid;
    return sscanf(close + 2, "%c %d %d %d %d %d %lu", state, &ppid, &pgrp, &session, &tty, &tpgid, flags) == 7;
}
static int crash_detected(pid_t pid) {
    char path[64], comm[64], state; unsigned long flags = 0;
    snprintf(path, sizeof path, PROC_ROOT "/%d/stat", (int)pid);
    return crash_stat(path, comm, sizeof comm, &state, &flags) && (flags & TASK_PF_SIGNALED);
}
/* "nr args... sp pc" or "-1 sp pc" for a blocked task; "running" otherwise. */
static int crash_registers(const char *path, unsigned long *sp, unsigned long *pc) {
    char line[256], *token[12]; int count = 0; FILE *f = fopen(path, "r");
    if (!f) return 0;
    if (!fgets(line, sizeof line, f)) line[0] = 0;
    fclose(f);
    for (char *p = strtok(line, " \n"); p && count < 12; p = strtok(NULL, " \n")) token[count++] = p;
    if (count < 3) return 0;
    *sp = strtoul(token[count - 2], NULL, 16); *pc = strtoul(token[count - 1], NULL, 16);
    return 1;
}
static const CrashMap *crash_find(const CrashMap *maps, size_t count, unsigned long address) {
    for (size_t i = 0; i < count; i++) if (address >= maps[i].start && address < maps[i].end) return &maps[i];
    return NULL;
}
static void crash_where(const CrashMap *maps, size_t count, unsigned long address, char *out, size_t size) {
    const CrashMap *m = crash_find(maps, count, address);
    if (m && m->exec) snprintf(out, size, "%s+0x%lx", m->name, address - m->start + m->offset);
    else snprintf(out, size, "0x%lx", address);
}
static void crash_stack(int mem, const CrashMap *maps, size_t count, const char *tid, unsigned long sp, size_t limit, int frames) {
    const CrashMap *stack = crash_find(maps, count, sp);
    if (mem < 0 || !stack || stack->exec) return;
    size_t length = stack->end - sp < limit ? stack->end - sp : limit;
    static uint32_t words[CRASH_FAULT_SCAN / 4];
    ssize_t n = crash_pread(mem, words, length & ~(size_t)3, sp);
    for (ssize_t i = 0; n > 0 && i < n / 4 && frames > 0; i++) {
        const CrashMap *m = crash_find(maps, count, words[i]);
        if (!m || !m->exec) continue;
        printf("launcher-crash-stack tid=%s sp+0x%lx %s+0x%lx\n", tid, (unsigned long)i * 4, m->name,
               (unsigned long)words[i] - m->start + m->offset);
        frames--;
    }
}
static void crash_snapshot(pid_t pid) {
    char path[96]; printf("launcher-child-crashing pid=%d\n", (int)pid);
    CrashMap *maps = NULL; size_t count = 0, capacity = 0;
    snprintf(path, sizeof path, PROC_ROOT "/%d/maps", (int)pid);
    FILE *f = fopen(path, "r"); char line[512];
    while (f && count < CRASH_MAPS_MAX && fgets(line, sizeof line, f)) {
        if (count == capacity) {
            CrashMap *grown = realloc(maps, (capacity ? capacity * 2 : 2048) * sizeof *maps);
            if (!grown) break;
            maps = grown; capacity = capacity ? capacity * 2 : 2048;
        }
        CrashMap *m = &maps[count]; char perms[8] = ""; int end = 0;
        if (sscanf(line, "%lx-%lx %7s %lx %*s %*s%n", &m->start, &m->end, perms, &m->offset, &end) < 4) continue;
        char *name = line + end; while (*name == ' ') name++;
        name[strcspn(name, "\n")] = 0;
        char *base = strrchr(name, '/');
        snprintf(m->name, sizeof m->name, "%s", base ? base + 1 : (*name ? name : "anon"));
        m->exec = perms[2] == 'x'; count++;
    }
    if (f) fclose(f);
    snprintf(path, sizeof path, PROC_ROOT "/%d/mem", (int)pid);
    int mem = open(path, O_RDONLY);
    snprintf(path, sizeof path, PROC_ROOT "/%d/task", (int)pid);
    DIR *d = opendir(path); struct dirent *e;
    while (d && (e = readdir(d))) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char file[160], comm[64], state, where[96] = "?"; unsigned long flags = 0, sp = 0, pc = 0;
        snprintf(file, sizeof file, "%s/%.20s/stat", path, e->d_name);
        if (!crash_stat(file, comm, sizeof comm, &state, &flags)) continue;
        snprintf(file, sizeof file, "%s/%.20s/syscall", path, e->d_name);
        int registers = crash_registers(file, &sp, &pc);
        if (registers) crash_where(maps, count, pc, where, sizeof where);
        int faulting = !(flags & TASK_PF_EXITING);
        printf("launcher-crash-thread tid=%s name=%s state=%c flags=0x%lx%s sp=0x%lx pc=%s\n",
               e->d_name, comm, state, flags, faulting ? " faulting=1" : "", sp, where);
        if (registers) crash_stack(mem, maps, count, e->d_name, sp, faulting ? CRASH_FAULT_SCAN : CRASH_THREAD_SCAN,
                                   faulting ? CRASH_FAULT_FRAMES : CRASH_THREAD_FRAMES);
    }
    if (d) closedir(d);
    if (mem >= 0) close(mem);
    snprintf(path, sizeof path, PROC_ROOT "/%d/maps", (int)pid);
    f = fopen(path, "r");
    while (f && fgets(line, sizeof line, f)) {
        char perms[8] = "";
        if (sscanf(line, "%*s %7s", perms) == 1 && perms[2] == 'x') printf("launcher-crash-map %s", line);
    }
    if (f) fclose(f);
    free(maps); fflush(stdout);
}
