/* SPDX-License-Identifier: 0BSD
 * Observe one or two processes through pidfds. Never signal or acquire privileges.
 * BOUND -> caller confirms authenticated identity -> ARM -> ARMED -> EXITED.
 * This helper alone cannot establish which process a numeric PID identifies.
 */
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/syscall.h>
#include <sys/resource.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <time.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Older target headers predate pidfds. ARM EABI and AArch64 use number 434. */
#ifndef SYS_pidfd_open
#if defined(__arm__) || defined(__aarch64__) || defined(__x86_64__)
#define SYS_pidfd_open 434
#else
#error Missing pidfd_open syscall number for this architecture
#endif
#endif

static int fail(const char *reason) {
    fprintf(stderr, "observer: %s\n", reason);
    return 1;
}
static int valid_boot(const char *s) {
    if (strlen(s) != 36) return 0;
    for (int i = 0; i < 36; i++) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (s[i] != '-') return 0;
        } else if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
    }
    return 1;
}
static int boot_matches(const char *expected) {
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 0;
    char buf[38]; size_t used = 0;
    while (used < sizeof(buf)) {
        ssize_t n = read(fd, buf + used, sizeof(buf) - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); return 0; }
        if (!n) break;
        used += (size_t)n;
    }
    close(fd);
    return used == 37 && buf[36] == '\n' && !memcmp(buf, expected, 36);
}
static int close_inherited(void) {
    DIR *dir = opendir("/proc/self/fd");
    if (!dir) return 0;
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(dir))) {
        char *end; long fd = strtol(entry->d_name, &end, 10);
        if (*entry->d_name && !*end && fd > 2 && fd <= INT_MAX && fd != dirfd(dir)) close((int)fd);
        errno = 0;
    }
    int ok = errno == 0;
    closedir(dir);
    return ok;
}
/* TV kernels may abort on exhaustion instead of returning EMFILE. Do not
 * allocate even a proc directory handle until spare capacity is established.
 * External concurrent limit changes remain outside this admission check. */
static int capacity(int needed) {
    struct rlimit limit;
    if (getrlimit(RLIMIT_NOFILE, &limit)) return 0;
    rlim_t bound = limit.rlim_cur < 4096 ? limit.rlim_cur : 4096;
    for (int fd = 0; (rlim_t)fd < bound; fd++) {
        /* F_GETFD needs no newer libc fcntl wrapper or large-file structure. */
        if (syscall(SYS_fcntl, fd, F_GETFD, 0) < 0) {
            if (errno != EBADF) return 0;
            if (!--needed) return 1;
        }
    }
    return 0;
}
static long long milliseconds(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -1;
    return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}
static int emit(const char *message) {
    size_t left = strlen(message);
    while (left) {
        ssize_t n = write(STDOUT_FILENO, message, left);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return 0;
        message += n; left -= (size_t)n;
    }
    return 1;
}
static pid_t parse_pid(const char *s) {
    if (!*s || *s == '0') return 0;
    for (const char *p = s; *p; p++) if (*p < '0' || *p > '9') return 0;
    errno = 0; char *end; long pid = strtol(s, &end, 10);
    return errno || *end || pid <= 1 || pid > INT_MAX || pid == getpid() ? 0 : (pid_t)pid;
}
static void close_targets(struct pollfd *fds, int count) {
    for (int i = 0; i < count; i++) if (fds[i].fd >= 0) close(fds[i].fd);
}
int main(int argc, char **argv) {
    if ((argc != 3 && argc != 4) || !valid_boot(argv[1])) return fail("invalid arguments");
    int count = argc - 2;
    pid_t pids[2] = {parse_pid(argv[2]), count == 2 ? parse_pid(argv[3]) : 0};
    if (!pids[0] || (count == 2 && (!pids[1] || pids[0] == pids[1]))) return fail("invalid pid");
    if (getuid() != geteuid() || getgid() != getegid()) return fail("changed credentials");
    sigset_t signals;
    sigemptyset(&signals);
    if (sigprocmask(SIG_SETMASK, &signals, NULL) || signal(SIGALRM, SIG_DFL) == SIG_ERR) return fail("signal setup failed");
    signal(SIGPIPE, SIG_IGN);
    alarm(35); /* Independent bound even if a pipe write or proc read stalls. */
    if (!capacity(1) || !close_inherited() || !capacity(count + 1) || !boot_matches(argv[1])) return fail("initial observation unavailable");
    struct pollfd fds[3] = {{-1, POLLIN, 0}, {-1, POLLIN, 0}, {-1, POLLIN, 0}};
    for (int i = 0; i < count; i++) {
        fds[i].fd = (int)syscall(SYS_pidfd_open, pids[i], 0);
        if (fds[i].fd < 0) { close_targets(fds, count); return fail("pidfd unavailable"); }
    }
    fds[count].fd = STDIN_FILENO;
    if (poll(fds, count, 0) != 0 || !boot_matches(argv[1])) { close_targets(fds, count); return fail("process already exited or boot changed"); }
    if (!emit("BOUND\n")) { close_targets(fds, count); return fail("output unavailable"); }
    long long now = milliseconds(), deadline = now + 10000;
    size_t arm_used = 0; int armed = 0, result = 1;
    if (now < 0) { close_targets(fds, count); return fail("clock unavailable"); }
    for (;;) {
        now = milliseconds();
        if (now < 0 || now >= deadline) { fail("deadline expired"); break; }
        int ready = poll(fds, count + 1, (int)(deadline - now));
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0) { fail("poll failed"); break; }
        /* Caller disappearance or malformed control always invalidates evidence. */
        if (fds[count].revents & (POLLERR | POLLHUP | POLLNVAL)) { fail("controller disconnected"); break; }
        if (fds[count].revents & POLLIN) {
            char bytes[8]; ssize_t n = read(STDIN_FILENO, bytes, sizeof(bytes));
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0 || armed || (size_t)n > 4 - arm_used || memcmp(bytes, "ARM\n" + arm_used, (size_t)n)) { fail("invalid control"); break; }
            arm_used += (size_t)n;
            if (arm_used == 4) {
                if (poll(fds, count, 0) != 0 || !boot_matches(argv[1])) { fail("process exited before arm"); break; }
                if (!emit("ARMED\n")) { fail("output unavailable"); break; }
                armed = 1; deadline = milliseconds() + 20000;
            }
        }
        int remaining = 0, invalid = 0;
        for (int i = 0; i < count; i++) {
            if (fds[i].fd < 0) continue;
            if (fds[i].revents & (POLLERR | POLLNVAL)) { invalid = 1; break; }
            if (fds[i].revents & (POLLIN | POLLHUP)) {
                if (!armed) { invalid = 1; break; }
                close(fds[i].fd); fds[i].fd = -1;
            } else remaining++;
        }
        if (invalid) { fail("unconfirmed process handle or exit"); break; }
        if (!remaining) {
            if (!boot_matches(argv[1])) { fail("boot changed at exit"); break; }
            if (!emit("EXITED\n")) { fail("output unavailable"); break; }
            result = 0; break;
        }
    }
    close_targets(fds, count);
    return result;
}
