/* TV-local paired launch benchmark. SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static double stamp(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(1); }
    return t.tv_sec * 1000.0 + t.tv_nsec / 1000000.0;
}
static double cpu(struct timeval t) { return t.tv_sec * 1000.0 + t.tv_usec / 1000.0; }

static int sample(const char *dll, const char *native, int managed, int round) {
    double start = stamp();
    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return 1; }
    if (!pid) {
        alarm(15);
        if (managed) execl("/usr/bin/dotnet", "dotnet", dll, "--app-exec", "Og==", (char *)NULL);
        else execl(native, native, "--command", ":", (char *)NULL);
        perror("exec launcher"); _exit(127);
    }
    struct rusage usage; int status; pid_t waited;
    do { waited = wait4(pid, &status, 0, &usage); } while (waited < 0 && errno == EINTR);
    if (waited < 0) { perror("wait4"); return 1; }
    int code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    printf("{\"kind\":\"%s\",\"round\":%d,\"elapsed_ms\":%.3f,\"cpu_ms\":%.3f,\"maxrss_kib\":%ld,\"exit_code\":%d}\n",
        managed ? "dotnet" : "native", round, stamp() - start,
        cpu(usage.ru_utime) + cpu(usage.ru_stime), usage.ru_maxrss, code);
    fflush(stdout);
    return code != 0;
}
int main(int argc, char **argv) {
    if (argc != 4) { fputs("usage: bench WORKER_DLL NATIVE_LAUNCHER ROUNDS\n", stderr); return 64; }
    char *end; long rounds = strtol(argv[3], &end, 10);
    if (*end || rounds < 1 || rounds > 100) return 64;
    /* Three warmup pairs; alternate order to reduce order bias. */
    for (int i = -3; i < rounds; i++) {
        int first = i % 2 == 0;
        if (sample(argv[1], argv[2], first, i) || sample(argv[1], argv[2], !first, i)) return 1;
    }
    return 0;
}
