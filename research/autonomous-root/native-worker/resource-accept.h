/* Resource limits affect only the controller-owned experimental worker.
 * SPDX-License-Identifier: 0BSD */
#include <sys/syscall.h>
static void resource_no_witness(const char *path) {
  struct stat st;
  if (!lstat(path, &st) || errno != ENOENT)
    fatal("resource rejection executed a command");
}
static void resource_reject_job(const char *id, const char *marker) {
  J *j = job_req("job.start", id);
  char *cmd = format("touch '%s'", marker);
  str(j, "command", cmd);
  str(j, "profile", "root");
  num(j, "timeout_ms", 1000);
  free(cmd);
  rejected(j);
  resource_no_witness(marker);
}
static void resource_limit_checks(void) {
  char *marker = format("%s/resource-unexpected-command", scope);
  for (int i = 0; i < 64; i++) {
    char *path = format("%s/.jobs/native-saved-limit-%02d.json", filescope, i);
    J *r = obj();
    char id[64];
    snprintf(id, sizeof id, "native-saved-limit-%02d", i);
    str(r, "id", id);
    str(r, "worker_id", "ffffffffffffffffffffffffffffffff");
    str(r, "boot_id", boot);
    str(r, "state", "completed");
    num(r, "exit_code", i);
    int fd =
        open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0)
      fatal("saved retention fixture");
    writeall(fd, json(r), strlen(json(r)));
    if (fsync(fd) || close(fd))
      fatal("saved retention persistence");
    free(path);
    discard(r);
  }
  resource_reject_job("native-retention-rejected", marker);
  for (int i = 0; i < 64; i++) {
    char id[64];
    snprintf(id, sizeof id, "native-saved-limit-%02d", i);
    J *r = call(job_req("job.status", id)), *result = get(r, "result");
    if (strcmp(textval(result, "state"), "completed") ||
        number(get(result, "record"), "exit_code") != i)
      fatal("retention rejection changed saved outcome");
    discard(r);
  }
  discard(call(job_req("job.forget", "native-saved-limit-00")));
  discard(
      start_job("native-capacity-recovered", "printf recovered", 2000, "app"));
  await_job("native-capacity-recovered", "completed", 0, 3000);
  discard(call(job_req("job.forget", "native-capacity-recovered")));
  for (int i = 1; i < 64; i++) {
    char id[64];
    snprintf(id, sizeof id, "native-saved-limit-%02d", i);
    discard(call(job_req("job.forget", id)));
  }
  mark("saved_retention_limit_preserves_records_and_app_capacity_recovers");

  /* prlimit64 is available since Linux 2.6.36. Use its fixed-width kernel ABI
   * so the ARM32 controller does not confuse it with libc's 32-bit rlim_t.
   * The target comes from this live authenticated child, never a saved PID.
   */
  struct {
    uint64_t current, maximum;
  } original, limited;
  if (syscall(SYS_prlimit64, worker_pid, RLIMIT_NOFILE, NULL, &original))
    fatal("read native descriptor limit");
  char *fdpath = format("/proc/%d/fd", worker_pid);
  DIR *d = opendir(fdpath);
  free(fdpath);
  if (!d)
    fatal("native descriptor inventory");
  unsigned highest = 0;
  struct dirent *entry;
  while ((entry = readdir(d))) {
    char *end;
    unsigned long fd = strtoul(entry->d_name, &end, 10);
    if (!*end && fd > highest)
      highest = fd;
  }
  closedir(d);
  limited.current = highest + 4;
  limited.maximum = original.maximum;
  if (limited.current >= original.current ||
      syscall(SYS_prlimit64, worker_pid, RLIMIT_NOFILE, &limited, NULL))
    fatal("constrain native descriptor limit");
  resource_reject_job("native-descriptor-limit", marker);
  if (syscall(SYS_prlimit64, worker_pid, RLIMIT_NOFILE, &original, NULL))
    fatal("restore native descriptor limit");
  J *r = call(job_req("job.status", "native-descriptor-limit"));
  if (strcmp(textval(get(r, "result"), "state"), "unknown"))
    fatal("descriptor exhaustion lost launch intent");
  discard(r);
  resource_reject_job("native-descriptor-limit", marker);
  discard(start_job("native-descriptor-recovered", "printf recovered", 2000,
                    "app"));
  await_job("native-descriptor-recovered", "completed", 0, 3000);
  discard(call(job_req("job.forget", "native-descriptor-recovered")));
  finish(0);
  launch();
  r = call(job_req("job.status", "native-descriptor-limit"));
  if (strcmp(textval(get(r, "result"), "state"), "interrupted") ||
      get(get(get(r, "result"), "record"), "exit_code") != NULL)
    fatal("descriptor intent restart reconciliation");
  discard(r);
  resource_no_witness(marker);
  discard(call(job_req("job.forget", "native-descriptor-limit")));
  free(marker);
  mark("descriptor_exhaustion_no_launch_then_app_execution_and_reconciliation");
}
