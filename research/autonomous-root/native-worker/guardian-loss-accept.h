/* Actual guardian death and conservative journal takeover on the TV.
 * These test fixtures remain inside the experiment scope.
 * SPDX-License-Identifier: 0BSD */
static void loss_journal_write(const char *path, const char *bytes,
                               int exclusive) {
  int fd = open(path,
                O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC |
                    (exclusive ? O_EXCL : O_TRUNC),
                0600);
  if (fd < 0)
    fatal("guardian-loss fixture create");
  writeall(fd, bytes, strlen(bytes));
  if (fsync(fd))
    fatal("guardian-loss fixture persistence");
  close(fd);
}
static void loss_rejected(J *journal, const char *path) {
  char *before = strdup(json(journal));
  loss_journal_write(path, before, 0);
  int errors[2];
  if (pipe2(errors, O_CLOEXEC))
    fatal("reconciliation probe pipe");
  pid_t probe = fork();
  if (probe < 0)
    fatal("reconciliation probe fork");
  if (!probe) {
    dup2(errors[1], STDERR_FILENO);
    close(errors[0]);
    close(errors[1]);
    execl(binary, binary, "127.0.0.1", "1", "/nonexistent-native-test-token",
          filescope, app, appsha, (char *)NULL);
    _exit(127);
  }
  close(errors[1]);
  int status;
  double deadline = stamp() + 20000;
  pid_t got;
  do {
    got = waitpid(probe, &status, WNOHANG);
    if (!got)
      usleep(10000);
  } while (!got && stamp() < deadline);
  if (got != probe) {
    kill(probe, SIGKILL);
    waitpid(probe, NULL, 0);
    fatal("reconciliation rejection probe hung");
  }
  char message[4096] = {0}, after[4096];
  ssize_t n = read(errors[0], message, sizeof message - 1);
  close(errors[0]);
  readtext(path, after, sizeof after);
  if (n <= 0 || !WIFEXITED(status) || !WEXITSTATUS(status) ||
      !strstr(message, "unresolved guardian journal") || strcmp(before, after))
    fatal("unsafe journal reconciliation");
  free(before);
  discard(journal);
}
static void guardian_loss_checks(int frozen) {
  J *status = call(req("status"));
  char *old_launcher =
      strdup(textval(get(get(status, "result"), "app_launcher"), "path"));
  char *group = strdup(textval(get(status, "result"), "freezer_group"));
  discard(status);
  char *journal_path = format("%s/.jobs/guardian", filescope);
  char journal_bytes[4096];
  readtext(journal_path, journal_bytes, sizeof journal_bytes);
  char *backup = format("%s/guardian-test-backup", filescope);
  loss_journal_write(backup, journal_bytes, 1);
  char *helper_source = format("%s/helper-source", filescope), sha[65];
  int fd = open(helper_source, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0 || !filedigest(fd, sha))
    fatal("guardian loss helper source");
  close(fd);
  J *j = req("helper.prepare");
  str(j, "path", helper_source);
  str(j, "sha256", sha);
  J *r = call(j);
  char *helper_path = strdup(textval(get(r, "result"), "path"));
  discard(r);
  free(helper_source);
  discard(start_job("native-loss-complete", "exit 7", 5000, "root"));
  await_job("native-loss-complete", "completed", 7, 7000);
  char *cmd = format("setsid sh -c \"sleep 2; touch '%s/loss-survivor'\" "
                     ">/dev/null 2>&1 & printf ready; sleep 30",
                     filescope);
  discard(start_job("native-loss-root-01", cmd, 60000, "root"));
  free(cmd);
  discard(
      start_job("native-loss-app-001", "printf ready; sleep 30", 60000, "app"));
  for (int i = 0; i < 2; i++) {
    const char *id = i ? "native-loss-app-001" : "native-loss-root-01";
    double until = stamp() + 5000;
    for (;;) {
      r = output(id, 0, 0);
      size_t n;
      unsigned char *bytes =
          decode(textval(get(get(r, "result"), "stdout"), "data"), &n);
      int ready = bytes && strstr((char *)bytes, "ready");
      free(bytes);
      discard(r);
      if (ready)
        break;
      if (stamp() >= until)
        fatal("guardian loss job readiness");
      usleep(10000);
    }
  }
  char ns_path[80];
  snprintf(ns_path, sizeof ns_path, "/proc/%d/ns/mnt", worker_pid);
  int pin = open(ns_path, O_RDONLY | O_CLOEXEC);
  if (pin < 0)
    fatal("retain test namespace");
  char *mount_pin = format("%s/guardian-ns-pin", filescope);
  int pin_file = open(mount_pin, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
  if (pin_file < 0)
    fatal("namespace pin fixture");
  close(pin_file);
  if (mount(ns_path, mount_pin, NULL, MS_BIND, NULL))
    fatal("bind test namespace handle");
  if (frozen) {
    char *state_path = format("/sys/fs/cgroup/freezer/%s/freezer.state", group);
    int state_fd = open(state_path, O_WRONLY | O_NOFOLLOW | O_CLOEXEC);
    if (state_fd < 0)
      fatal("test freezer open");
    writeall(state_fd, "FROZEN", 6);
    close(state_fd);
    double frozen_until = stamp() + 750;
    char state[32];
    for (;;) {
      readtext(state_path, state, sizeof state);
      if (!strcmp(state, "FROZEN"))
        break;
      if (stamp() >= frozen_until)
        fatal("test freezer readiness");
      usleep(1000);
    }
    free(state_path);
  }
  /* child is our unreaped guardian, not a PID taken from the journal. */
  if (kill(child, SIGKILL))
    fatal("guardian loss injection");
  int exit_status;
  if (waitpid(child, &exit_status, 0) != child || !WIFSIGNALED(exit_status) ||
      WTERMSIG(exit_status) != SIGKILL)
    fatal("guardian loss status");
  child = 0;
  close(w.fd);
  w.fd = -1;
  char *lock_path = format("%s/.jobs/lock", filescope);
  fd = open(lock_path, O_RDONLY | O_CLOEXEC);
  free(lock_path);
  double until = stamp() + 5000;
  if (fd < 0)
    fatal("guardian loss lock");
  while (flock(fd, LOCK_EX | LOCK_NB)) {
    if ((errno != EWOULDBLOCK && errno != EAGAIN) || stamp() >= until)
      fatal("guardian loss descendants retained lock");
    usleep(10000);
  }
  flock(fd, LOCK_UN);
  close(fd);
  usleep(2200000);
  char *marker = format("%s/loss-survivor", filescope);
  if (!access(marker, F_OK))
    fatal("guardian loss left running descendants");
  free(marker);
  loss_rejected(parse(journal_bytes), journal_path);
  close(pin);
  /* No fd retains the namespace now; its nsfs bind mount must still block
   * backing-file deletion. The fixture exists only in controller's namespace.
   */
  loss_rejected(parse(journal_bytes), journal_path);
  if (umount2(mount_pin, UMOUNT_NOFOLLOW) || unlink(mount_pin))
    fatal("namespace pin fixture removal");
  free(mount_pin);
  mark("stale_journal_refuses_namespace_bind_mount_pin");
  usleep(2200000);
  marker = format("%s/loss-survivor", filescope);
  if (!access(marker, F_OK))
    fatal("thawed guardian-loss descendant survived");
  free(marker);
  mark(frozen ? "frozen_guardian_loss_thaws_pending_exitkill_without_replay"
              : "guardian_loss_exitkill_and_pinned_namespace_refusal");
  const char *keys[] = {"schema", "scope_ino", "runtime_ino", "freezer_ino"};
  for (size_t i = 0; i < sizeof keys / sizeof *keys; i++) {
    j = parse(journal_bytes);
    num(j, keys[i], number(j, keys[i]) + 1);
    loss_rejected(j, journal_path);
  }
  j = parse(journal_bytes);
  boolean(j, "prepared", 0);
  loss_rejected(j, journal_path);
  j = parse(journal_bytes);
  str(j, "boot_id", "different-boot");
  loss_rejected(j, journal_path);
  char process[4096];
  readtext("/proc/self/stat", process, sizeof process);
  char *tail = strrchr(process, ')'), *save, *start = NULL;
  int index = 0;
  for (char *field = tail ? strtok_r(tail + 2, " ", &save) : NULL; field;
       field = strtok_r(NULL, " ", &save), index++)
    if (index == 19) {
      start = field;
      break;
    }
  if (!start)
    fatal("controller identity");
  j = parse(journal_bytes);
  num(j, "pid", getpid());
  str(j, "process_start", start);
  loss_rejected(j, journal_path);
  mark("stale_journal_scope_resource_boot_and_live_identity_refusal");
  /* Simulate PID reuse. The still-live controller must never be signaled. */
  j = parse(journal_bytes);
  num(j, "pid", getpid());
  str(j, "process_start", "0");
  loss_journal_write(journal_path, json(j), 0);
  discard(j);
  launch();
  r = call(req("status"));
  if (!json_object_get_boolean(
          get(get(r, "result"), "stale_guardian_reconciled")))
    fatal("guardian journal was not reconciled");
  discard(r);
  if (!access(helper_path, F_OK) || !access(old_launcher, F_OK))
    fatal("guardian loss left runtime storage");
  char *old_group = format("/sys/fs/cgroup/freezer/%s", group);
  if (!access(old_group, F_OK))
    fatal("guardian loss left freezer group");
  for (int i = 0; i < 2; i++) {
    const char *id = i ? "native-loss-app-001" : "native-loss-root-01";
    r = call(job_req("job.status", id));
    J *result = get(r, "result"), *record = get(result, "record");
    if (strcmp(textval(result, "state"), "interrupted") ||
        strcmp(textval(record, "recovery"), "stale-guardian-reconciled") ||
        get(record, "exit_code") != NULL)
      fatal("guardian loss record outcome");
    discard(r);
    j = job_req("job.start", id);
    str(j, "command", ":");
    str(j, "profile", "root");
    num(j, "timeout_ms", 1000);
    rejected(j);
    discard(call(job_req("job.forget", id)));
  }
  r = call(job_req("job.status", "native-loss-complete"));
  if (strcmp(textval(get(r, "result"), "state"), "completed") ||
      number(get(get(r, "result"), "record"), "exit_code") != 7)
    fatal("guardian loss changed completed record");
  discard(r);
  discard(call(job_req("job.forget", "native-loss-complete")));
  discard(start_job("native-loss-recovered", "printf recovered", 5000, "app"));
  await_job("native-loss-recovered", "completed", 0, 7000);
  discard(call(job_req("job.forget", "native-loss-recovered")));
  if (unlink(backup))
    fatal("guardian loss fixture cleanup");
  free(backup);
  free(helper_path);
  free(old_launcher);
  free(group);
  free(old_group);
  free(journal_path);
  mark("guardian_loss_reconciles_without_pid_signals_or_job_replay");
}

#ifdef NATIVE_WORKER_FAULT_TEST
static void startup_recovery_checks(void) {
  const char *stages[] = {"namespace",        "runtime",
                          "launcher-created", "launcher-partial-copy",
                          "launcher-copy",    "launcher",
                          "contained",        "ready",
                          "journal-runtime",  "journal-contained",
                          "journal-ready"};
  for (size_t i = 0; i < sizeof stages / sizeof *stages; i++) {
    finish(0);
    pid_t probe = fork();
    if (probe < 0)
      fatal("startup recovery probe fork");
    if (!probe) {
      if (setenv("COUCHROOT_NATIVE_STARTUP_FAULT", stages[i], 1))
        _exit(127);
      execl(binary, binary, "127.0.0.1", "1", "/nonexistent-native-test-token",
            filescope, app, appsha, (char *)NULL);
      _exit(127);
    }
    double deadline = stamp() + 10000;
    int status;
    pid_t got;
    do {
      got = waitpid(probe, &status, WNOHANG);
      if (!got)
        usleep(10000);
    } while (!got && stamp() < deadline);
    if (got != probe) {
      kill(probe, SIGKILL);
      waitpid(probe, NULL, 0);
      fatal("startup recovery probe hung");
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 86)
      fatal("startup recovery injection did not run");
    char *path = format("%s/.jobs/guardian", filescope), bytes[4096];
    readtext(path, bytes, sizeof bytes);
    free(path);
    J *journal = parse(bytes);
    const char *id = journal ? textval(journal, "worker_id") : NULL;
    if (!hexvalid(id, 32))
      fatal("startup recovery journal identity");
    char *old = format("/opt/couchroot-agent/native-helpers/%s", id),
         *group = format("/sys/fs/cgroup/freezer/couchroot-native-%s", id);
    discard(journal);
    launch();
    J *r = call(req("status"));
    if (!json_object_get_boolean(
            get(get(r, "result"), "stale_guardian_reconciled")))
      fatal("startup reconciliation not reported");
    discard(r);
    struct stat st;
    if (!lstat(old, &st) || errno != ENOENT || !lstat(group, &st) ||
        errno != ENOENT)
      fatal("startup reconciliation retained resources");
    free(old);
    free(group);
    discard(start_job("native-startup-app", "printf startup-recovered", 5000,
                      "app"));
    await_job("native-startup-app", "completed", 0, 7000);
    discard(call(job_req("job.forget", "native-startup-app")));
    char check[128];
    snprintf(check, sizeof check, "startup_checkpoint_recovery_%s", stages[i]);
    mark(check);
  }
}
#endif
