/* Native crash guardian: owns descendants, lock, journal and runtime namespace.
 * Original Couchroot code. SPDX-License-Identifier: 0BSD */
static pid_t guardian_pid;
static volatile sig_atomic_t guardian_stop;
static int guardian_journal_owned;
static void guardian_signal(int sig) {
  (void)sig;
  guardian_stop = 1;
}
static void guardian_journal(void) {
  char identity[32];
  if (!job_identity(getpid(), identity))
    fatal("guardian identity");
  J *j = obj();
  str(j, "worker_id", worker_id);
  str(j, "boot_id", current_boot);
  num(j, "pid", getpid());
  str(j, "process_start", identity);
  int fd = openat(jobs_dir, "guardian",
                  O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0)
    fatal("unresolved guardian journal; inspect before recovery");
  guardian_journal_owned = 1;
  const char *s = json(j);
  int good = job_write(fd, s, strlen(s)) && !fsync(fd);
  close(fd);
  json_object_put(j);
  if (!good || fsync(jobs_dir))
    fatal("guardian journal persistence");
}
static int guardian_recover_records(void) {
  int scan = openat(jobs_dir, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  DIR *d = scan < 0 ? NULL : fdopendir(scan);
  if (!d) {
    if (scan >= 0)
      close(scan);
    return 0;
  }
  struct dirent *entry;
  int good = 1;
  while ((entry = readdir(d))) {
    size_t len = strlen(entry->d_name);
    if (len < 5 || strcmp(entry->d_name + len - 5, ".json") || len > 69)
      continue;
    char id[65];
    memcpy(id, entry->d_name, len - 5);
    id[len - 5] = 0;
    if (!job_valid_id(id))
      continue;
    int fd = openat(jobs_dir, entry->d_name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    struct stat st;
    char bytes[2048];
    if (fd < 0) {
      good = 0;
      continue;
    }
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid ||
        (st.st_mode & 077) || st.st_size < 1 ||
        st.st_size >= (off_t)sizeof bytes) {
      close(fd);
      good = 0;
      continue;
    }
    ssize_t n = read(fd, bytes, sizeof bytes - 1);
    close(fd);
    if (n != st.st_size) {
      good = 0;
      continue;
    }
    bytes[n] = 0;
    J *r = parse(bytes);
    const char *owner = r ? textval(r, "worker_id") : NULL;
    if (!owner || strcmp(owner, worker_id)) {
      if (r)
        json_object_put(r);
      continue;
    }
    const char *state = textval(r, "state");
    if (!state) {
      json_object_put(r);
      good = 0;
      continue;
    }
    char next[80];
    snprintf(next, sizeof next, "%s.json.next", id);
    /* The exclusive scope lock and owner field make this an owned interrupted
     * atomic-save temporary, never a reason to replay the command. */
    if (unlinkat(jobs_dir, next, 0) && errno != ENOENT) {
      json_object_put(r);
      good = 0;
      continue;
    }
    if (!strcmp(state, "completed") || !strcmp(state, "cancelled") ||
        !strcmp(state, "timed_out") || !strcmp(state, "interrupted")) {
      json_object_put(r);
      continue;
    }
    str(r, "state", "interrupted");
    str(r, "recovery", "guardian-reaped-descendants");
    boolean(r, "output_available", 0);
    json_object_object_add(r, "exit_code", NULL);
    boolean(r, "timed_out", 0);
    fd = openat(jobs_dir, next,
                O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) {
      json_object_put(r);
      good = 0;
      continue;
    }
    const char *s = json(r);
    int saved = job_write(fd, s, strlen(s)) && !fsync(fd);
    close(fd);
    json_object_put(r);
    if (!saved || renameat(jobs_dir, next, jobs_dir, entry->d_name))
      good = 0;
  }
  closedir(d);
  if (fsync(jobs_dir))
    good = 0;
  return good;
}
static int guardian_children(int terminate) {
  /* waitid(P_PID, WNOWAIT) proves direct-child ownership atomically, including
   * a live child for which WNOHANG returns no exit event. This single-threaded
   * parent does not reap while iterating, so confirmed PIDs cannot be reused.
   * Avoid reading every TV process's status: cold /proc reads delay recovery.
   */
  DIR *proc = opendir("/proc");
  if (!proc)
    return -1;
  struct dirent *entry;
  int count = 0;
  while ((entry = readdir(proc))) {
    char *end;
    long pid = strtol(entry->d_name, &end, 10);
    if (*end || pid < 1 || pid > INT_MAX)
      continue;
    siginfo_t info;
    memset(&info, 0, sizeof info);
    if (waitid(P_PID, (id_t)pid, &info, WEXITED | WNOHANG | WNOWAIT)) {
      if (errno == ECHILD || errno == ESRCH || errno == EINTR)
        continue;
      closedir(proc);
      return -1;
    }
    count++;
    if (terminate && kill((pid_t)pid, SIGKILL) && errno != ESRCH) {
      closedir(proc);
      return -1;
    }
  }
  closedir(proc);
  return count;
}
static int guardian_drain(void) {
  double deadline = stamp() + 5000;
  for (;;) {
    if (guardian_children(1) < 0)
      return 0;
    int status;
    pid_t pid;
    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
    }
    if (pid < 0 && errno == ECHILD)
      return 1;
    if (pid < 0 && errno != EINTR)
      return 0;
    if (stamp() > deadline)
      return 0;
    usleep(10000);
  }
}
/* Fatal faults must not enter the TV's slow default signal teardown while
 * detached children continue running. Exit the damaged process immediately;
 * only the independent guardian performs cleanup. Use an alternate stack so
 * this path also works when the protocol thread exhausts its normal stack. */
static unsigned char fatal_stack[65536];
static void worker_fatal_signal(int sig) { _exit(128 + sig); }
static void worker_fault_handlers(void) {
  stack_t stack = {.ss_sp = fatal_stack, .ss_size = sizeof fatal_stack};
  if (sigaltstack(&stack, NULL))
    fatal("fatal signal stack");
  struct sigaction action;
  memset(&action, 0, sizeof action);
  action.sa_handler = worker_fatal_signal;
  action.sa_flags = SA_ONSTACK | SA_RESETHAND;
  sigfillset(&action.sa_mask);
  const int signals[] = {SIGSEGV, SIGBUS, SIGILL, SIGFPE, SIGABRT};
  for (size_t i = 0; i < sizeof signals / sizeof *signals; i++)
    if (sigaction(signals[i], &action, NULL))
      fatal("fatal signal handler");
}
static void guardian_start(void) {
  if (prctl(PR_SET_CHILD_SUBREAPER, 1))
    fatal("native subreaper");
  guardian_pid = getpid();
  sigset_t blocked, previous;
  sigemptyset(&blocked);
  sigaddset(&blocked, SIGTERM);
  sigaddset(&blocked, SIGINT);
  sigaddset(&blocked, SIGALRM);
  if (sigprocmask(SIG_BLOCK, &blocked, &previous))
    fatal("guardian signal mask");
  signal(SIGTERM, guardian_signal);
  signal(SIGINT, guardian_signal);
  signal(SIGALRM, guardian_signal);
  pid_t pid = fork();
  if (pid < 0)
    fatal("fork native worker");
  if (!pid) {
    runtime_owned = 0;
    guardian_journal_owned = 0;
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != guardian_pid)
      _exit(125);
    signal(SIGTERM, stop_signal);
    signal(SIGINT, stop_signal);
    signal(SIGALRM, stop_signal);
    if (sigprocmask(SIG_SETMASK, &previous, NULL))
      _exit(125);
    worker_fault_handlers();
    alarm(300);
    return;
  }
  signal(SIGTERM, guardian_signal);
  signal(SIGINT, guardian_signal);
  signal(SIGALRM, guardian_signal);
  if (sigprocmask(SIG_SETMASK, &previous, NULL))
    _exit(125);
  alarm(310);
  int status = 0, worker_status = 0, worker_done = 0;
  double stopping_at = 0;
  while (!worker_done) {
    if (guardian_stop) {
      if (!stopping_at) {
        kill(pid, SIGTERM);
        stopping_at = stamp();
      } else if (stamp() - stopping_at > 3000)
        kill(pid, SIGKILL);
    }
    pid_t got;
    while ((got = waitpid(-1, &status, WNOHANG)) > 0)
      if (got == pid) {
        worker_done = 1;
        worker_status = status;
      }
    if (got < 0 && ((!worker_done && errno == ECHILD) ||
                    (errno != ECHILD && errno != EINTR)))
      _exit(125);
    if (!worker_done)
      usleep(10000);
  }
  alarm(0);
  /* Do not release ownership or publish interruption while any descendant can
   * still run. Unexpected retention leaves the durable journal fail-closed. */
  double recovery_started = stamp();
  int drained = guardian_drain();
  if (getenv("COUCHROOT_NATIVE_RECOVERY_TIMING"))
    fprintf(stderr, "prototype: guardian drain %.0f ms\n",
            stamp() - recovery_started);
  if (!drained || !guardian_recover_records() || !runtime_sweep()) {
    fputs("prototype: guardian recovery incomplete; journal retained\n",
          stderr);
    _exit(125);
  }
  if (unlinkat(jobs_dir, "guardian", 0) || fsync(jobs_dir))
    _exit(125);
  guardian_journal_owned = 0;
  jobs_cleanup();
  if (directory >= 0)
    close(directory);
  _exit(WIFEXITED(worker_status) ? WEXITSTATUS(worker_status)
                                 : 128 + WTERMSIG(worker_status));
}
