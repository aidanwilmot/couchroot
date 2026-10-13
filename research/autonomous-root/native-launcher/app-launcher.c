/* Original Couchroot app-user launcher prototype. SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int fail(const char *step) {
    fprintf(stderr, "app-launcher: %s: %s\n", step, strerror(errno));
    return 77;
}

int main(int argc, char **argv) {
    if (argc != 3 || strcmp(argv[1], "--command")) {
        fputs("usage: app-launcher --command SHELL_COMMAND\n", stderr);
        return 64;
    }
    /* Never install setuid. Only the already authenticated root worker calls this. */
    if (getuid() != 0 || geteuid() != 0) { errno = EPERM; return fail("requires root"); }
    int fd = open("/proc/self/attr/current", O_WRONLY | O_CLOEXEC);
    if (fd < 0) return fail("open Smack label");
    ssize_t n = write(fd, "User", 4);
    int saved = errno;
    close(fd);
    if (n != 4) { errno = n < 0 ? saved : EIO; return fail("set Smack label"); }
    if (setgroups(0, NULL) || setgid(100) || setuid(5001)) return fail("drop credentials");
    if (getuid() != 5001 || geteuid() != 5001 || getgid() != 100 || getegid() != 100 || getgroups(0, NULL) != 0) {
        errno = EPERM; return fail("verify credentials");
    }
    char label[32] = {0};
    fd = open("/proc/self/attr/current", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return fail("read Smack label");
    n = read(fd, label, sizeof(label) - 1); saved = errno; close(fd);
    if (n < 0) { errno = saved; return fail("read Smack label"); }
    if (n != 4 || memcmp(label, "User", 4)) { errno = EPERM; return fail("verify Smack label"); }
    struct stat st;
    const char *system_bus = stat("/sys/fs/kdbus/0-system", &st) == 0 && S_ISDIR(st.st_mode)
        ? "kernel:path=/sys/fs/kdbus/0-system/bus" : "unix:path=/run/dbus/system_bus_socket";
    const char *env[][2] = {
        {"HOME", "/home/owner"}, {"USER", "owner"}, {"LOGNAME", "owner"},
        {"XDG_RUNTIME_DIR", "/run/user/5001"}, {"WAYLAND_DISPLAY", "wayland-0"},
        {"DBUS_SESSION_BUS_ADDRESS", "kernel:path=/sys/fs/kdbus/5001-user/bus"},
        {"DBUS_SYSTEM_BUS_ADDRESS", system_bus}, {"PATH", "/usr/bin:/bin:/usr/sbin:/sbin"}
    };
    /* Match the managed profile's environment overrides for this comparison. */
    for (size_t i = 0; i < sizeof(env) / sizeof(env[0]); i++)
        if (setenv(env[i][0], env[i][1], 1)) return fail("set environment");
    if (chdir("/home/owner")) return fail("set working directory");
    execl("/bin/sh", "sh", "-c", argv[2], (char *)NULL);
    return fail("exec shell");
}
