/* Successful storage I/O advances the protocol thread's progress lease.
 * Never call these from the job monitor, guardian or pulse thread.
 * EINTR, EOF and failed calls do not prove progress. A blocked syscall stays
 * subject to the existing watchdog; no timer thread extends its lease.
 * Original Couchroot code. SPDX-License-Identifier: 0BSD */
static void request_progress(void) { progress_touch(&progress_main); }
static int request_filedigest(int fd, char out[65]) {
  return filedigest_progress(fd, out, request_progress);
}
static ssize_t request_read(int fd, void *buf, size_t size) {
  ssize_t n = read(fd, buf, size);
  if (n > 0)
    request_progress();
  return n;
}
static ssize_t request_pread(int fd, void *buf, size_t size, off_t offset) {
  ssize_t n = pread(fd, buf, size, offset);
  if (n > 0)
    request_progress();
  return n;
}
static ssize_t request_pwrite(int fd, const void *buf, size_t size, off_t offset) {
  ssize_t n = pwrite(fd, buf, size, offset);
  if (n > 0)
    request_progress();
  return n;
}
static int request_write(int fd, const void *buf, size_t size) {
  const unsigned char *p = buf;
  while (size) {
    ssize_t n = write(fd, p, size);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0)
      return 0;
    request_progress();
    p += n;
    size -= n;
  }
  return 1;
}
static int request_sync(int fd) {
  int result = fsync(fd);
  if (!result)
    request_progress();
  return result;
}
