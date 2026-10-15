/* Isolated glibc fixture: fail only the explicitly named protocol process.
 * Never packaged or loaded on a TV. SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* The Linux test image uses glibc. Calling its allocator directly avoids
 * recursive calloc while the dynamic loader resolves interposed symbols. */
extern void *__libc_calloc(size_t, size_t);
static unsigned allocation_count;
static int selected(const char *operation, unsigned occurrence) {
  const char *file = getenv("COUCHROOT_TEST_LAUNCH_FAILURE");
  if (!file)
    return 0;
  int fd = open(file, O_RDONLY | O_CLOEXEC);
  if (fd < 0)
    return 0;
  char bytes[96], mode[16];
  ssize_t n = read(fd, bytes, sizeof bytes - 1);
  close(fd);
  if (n <= 0)
    return 0;
  bytes[n] = 0;
  long pid;
  unsigned at;
  if (sscanf(bytes, "%ld %15s %u", &pid, mode, &at) != 3 ||
      pid != getpid() || strcmp(operation, mode))
    return 0;
  if (!strcmp(operation, "calloc"))
    occurrence = ++allocation_count;
  return occurrence == at;
}
void *calloc(size_t n, size_t size) {
  if (n == 1 && size == 1048576 && selected("calloc", 0)) {
    errno = ENOMEM;
    return NULL;
  }
  return __libc_calloc(n, size);
}
pid_t fork(void) {
  pid_t (*original)(void) = dlsym(RTLD_NEXT, "fork");
  if (!original)
    _exit(94);
  if (selected("fork", 1)) {
    errno = EAGAIN;
    return -1;
  }
  return original();
}
