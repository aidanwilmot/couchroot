/* Independently staged native launcher and owned runtime recovery.
 * Original Couchroot code. SPDX-License-Identifier: 0BSD */
static int launcher_mounted, runtime_owned = 1;
static char launcher_directory[PATH_MAX];
static int runtime_mountpoint(const char *path) {
  FILE *f = fopen("/proc/self/mountinfo", "r");
  if (!f)
    return -1;
  char linebuf[8192];
  int found = 0;
  while (fgets(linebuf, sizeof linebuf, f)) {
    char *save, *s = strtok_r(linebuf, " ", &save);
    for (int i = 0; i < 4 && s; i++)
      s = strtok_r(NULL, " ", &save);
    if (s && !strcmp(s, path)) {
      found = 1;
      break;
    }
  }
  if (ferror(f))
    found = -1;
  fclose(f);
  return found;
}
static int runtime_remove_view(const char *id, const char *binary_name) {
  char path[PATH_MAX];
  if (snprintf(path, sizeof path, "%s/%s", helper_owner_path, id) >=
      (int)sizeof path)
    return 0;
  int mounted = runtime_mountpoint(path);
  if (mounted < 0)
    return 0;
  if (mounted && umount2(path, UMOUNT_NOFOLLOW))
    return 0;
  int fd =
      openat(helper_owner, id, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0)
    return errno == ENOENT;
  struct stat st;
  int good = !fstat(fd, &st) && !st.st_uid && !(st.st_mode & 022);
  if (good) {
    int scan = openat(fd, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    DIR *d = scan < 0 ? NULL : fdopendir(scan);
    if (!d) {
      if (scan >= 0)
        close(scan);
      good = 0;
    } else {
      struct dirent *e;
      while ((e = readdir(d)))
        if (strcmp(e->d_name, ".") && strcmp(e->d_name, "..") &&
            strcmp(e->d_name, binary_name))
          good = 0;
      closedir(d);
    }
  }
  if (good && fstatat(fd, binary_name, &st, AT_SYMLINK_NOFOLLOW) == 0) {
    if (!S_ISREG(st.st_mode) || st.st_uid || st.st_nlink != 1)
      good = 0;
    else if (unlinkat(fd, binary_name, 0))
      good = 0;
  } else if (good && errno != ENOENT)
    good = 0;
  close(fd);
  if (good && unlinkat(helper_owner, id, AT_REMOVEDIR))
    good = 0;
  return good;
}
static int runtime_sweep(void) {
  if (helper_owner < 0)
    return 1;
  /* Called only after all worker descendants have been reaped. Never scan or
   * remove another worker's directory, even if it appears stale. */
  int scan = openat(helper_owner, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  DIR *d = scan < 0 ? NULL : fdopendir(scan);
  if (!d) {
    if (scan >= 0)
      close(scan);
    return 0;
  }
  struct dirent *e;
  int good = 1;
  while ((e = readdir(d))) {
    if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, ".."))
      continue;
    if (!strcmp(e->d_name, ".launcher")) {
      if (!runtime_remove_view(e->d_name, "app-launcher"))
        good = 0;
    } else if (hexvalid(e->d_name, 32)) {
      if (!runtime_remove_view(e->d_name, "helper"))
        good = 0;
    } else
      good = 0;
  }
  closedir(d);
  if (!good)
    return 0;
  memset(helpers, 0, sizeof helpers);
  launcher_mounted = 0;
  helpers_cleanup();
  struct stat st;
  return lstat(helper_owner_path, &st) < 0 && errno == ENOENT;
}
static void launcher_stage(const char *source) {
  const char *name;
  if (!leaf(source, &name))
    fatal("launcher source must be inside the experiment scope");
  int fd = openat(directory, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  struct stat st;
  unsigned char header[52];
  char digest_value[65];
  if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid ||
      (st.st_mode & 022) || st.st_size < 52 || st.st_size > CHUNK ||
      pread(fd, header, sizeof header, 0) != (ssize_t)sizeof header ||
      !filedigest(fd, digest_value) || strcmp(digest_value, launcher_sha))
    fatal("launcher source integrity");
  if (memcmp(header, "\177ELF", 4))
    fatal("launcher source ELF");
#ifndef NATIVE_WORKER_TEST
  if (header[4] != 1 || header[5] != 1 || header[18] != 40 || header[19] != 0)
    fatal("launcher must be ARM ELF32 little endian");
#endif
  if (!helper_storage() || mkdirat(helper_owner, ".launcher", 0700))
    fatal("launcher storage");
  int dir = openat(helper_owner, ".launcher",
                   O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0 || helper_label(dir))
    fatal("launcher directory label");
  int target = openat(dir, "app-launcher",
                      O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0500);
  if (target < 0)
    fatal("launcher create");
  unsigned char bytes[65536];
  off_t copied = 0;
  while (copied < st.st_size) {
    ssize_t n = read(fd, bytes, sizeof bytes);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0 || copied + n > st.st_size || !job_write(target, bytes, n))
      fatal("launcher copy");
    copied += n;
  }
  close(fd);
  if (!filedigest(target, digest_value) || strcmp(digest_value, launcher_sha) ||
      fchmod(target, 0500) || helper_label(target) || fsync(target) ||
      fsync(dir))
    fatal("launcher staging integrity");
  close(target);
  close(dir);
  if (snprintf(launcher_directory, sizeof launcher_directory, "%s/.launcher",
               helper_owner_path) >= (int)sizeof launcher_directory ||
      snprintf(launcher, sizeof launcher, "%s/app-launcher",
               launcher_directory) >= (int)sizeof launcher)
    fatal("launcher path");
#ifndef NATIVE_WORKER_TEST
  if (mount(launcher_directory, launcher_directory, NULL, MS_BIND, NULL))
    fatal("launcher bind mount");
  launcher_mounted = 1;
  if (mount(NULL, launcher_directory, NULL,
            MS_BIND | MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL))
    fatal("launcher read-only view");
#endif
  if (!verified_launcher())
    fatal("staged launcher digest");
}
