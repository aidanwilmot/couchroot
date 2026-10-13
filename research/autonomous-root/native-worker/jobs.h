/* Prototype job supervision. Original Couchroot code. SPDX-License-Identifier:
 * 0BSD */
#include <dirent.h>
#include <pthread.h>
#include <sys/file.h>
#include <sys/prctl.h>

typedef struct {
  unsigned char *bytes;
  int64_t end;
} JobLog;
typedef struct {
  char id[65], boot[80], started[40], identity[32], state[20];
  pid_t pid;
  int pipes[2], finished, reaped, code, timed, save_failed;
  double deadline, drain_deadline;
  JobLog logs[2];
} Job;
static Job jobs[16];
static int jobs_dir = -1, jobs_lock = -1, jobs_started, jobs_stop;
static pthread_t jobs_thread;
static pthread_mutex_t jobs_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t jobs_changed = PTHREAD_COND_INITIALIZER;
static char current_boot[80];
static volatile sig_atomic_t stopping;
static int job_identity(pid_t pid, char result[32]) {
  char path[64], buf[4096];
  snprintf(path, sizeof path, "/proc/%d/stat", pid);
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  if (fd < 0)
    return 0;
  ssize_t n = read(fd, buf, sizeof buf - 1);
  close(fd);
  if (n <= 0)
    return 0;
  buf[n] = 0;
  char *p = strrchr(buf, ')'), *save;
  if (!p)
    return 0;
  int index = 0;
  for (char *s = strtok_r(p + 2, " ", &save); s;
       s = strtok_r(NULL, " ", &save), index++)
    if (index == 19 && strlen(s) < 32) {
      strcpy(result, s);
      return 1;
    }
  return 0;
}
static int job_valid_id(const char *id) {
  if (!id || strlen(id) < 16 || strlen(id) > 64)
    return 0;
  for (const unsigned char *p = (const unsigned char *)id; *p; p++)
    if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
          (*p >= '0' && *p <= '9') || *p == '-'))
      return 0;
  return 1;
}
static int job_write(int fd, const void *buf, size_t n) {
  const unsigned char *p = buf;
  while (n) {
    ssize_t got = write(fd, p, n);
    if (got < 0 && errno == EINTR)
      continue;
    if (got <= 0)
      return 0;
    p += got;
    n -= got;
  }
  return 1;
}
/* No library JSON objects cross the supervisor lock. Records contain only
 * validated identifiers, kernel integers and generated timestamps, never
 * command text. */
static int job_save(Job *j, int exclusive) {
  char name[80], temp[85], bytes[768], code[24];
  snprintf(name, sizeof name, "%s.json", j->id);
  snprintf(temp, sizeof temp, "%s.next", name);
  if (j->finished)
    snprintf(code, sizeof code, "%d", j->code);
  else
    strcpy(code, "null");
  int n = snprintf(bytes, sizeof bytes,
                   "{\"id\":\"%s\",\"boot_id\":\"%s\",\"state\":\"%s\","
                   "\"started_at\":\"%s\",\"pid\":%d,\"process_start\":\"%s\","
                   "\"exit_code\":%s,\"timed_out\":%s}",
                   j->id, j->boot, j->state, j->started, j->pid, j->identity,
                   code, j->timed ? "true" : "false");
  if (n < 0 || n >= (int)sizeof bytes)
    return 0;
  int fd = openat(jobs_dir, exclusive ? name : temp,
                  O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0)
    return 0;
  int good = job_write(fd, bytes, n) && !fsync(fd);
  if (close(fd))
    good = 0;
  if (!exclusive && good && renameat(jobs_dir, temp, jobs_dir, name))
    good = 0;
  if (!exclusive && !good)
    unlinkat(jobs_dir, temp, 0);
  if (good && fsync(jobs_dir))
    good = 0;
  return good;
}
static J *job_snapshot(Job *j) {
  J *r = obj();
  str(r, "id", j->id);
  str(r, "boot_id", j->boot);
  str(r, "state", j->state);
  str(r, "started_at", j->started);
  num(r, "pid", j->pid);
  str(r, "process_start", j->identity);
  json_object_object_add(r, "exit_code",
                         j->finished ? json_object_new_int64(j->code) : NULL);
  boolean(r, "timed_out", j->timed);
  boolean(r, "output_available", 1);
  boolean(r, "persistence_failed", j->save_failed);
  return r;
}
static void job_kill(Job *j) {
  /* Keep the leader unreaped until after the group kill, preventing PID reuse.
   */
  if (j->pid > 0 && !j->reaped) {
    kill(-j->pid, SIGKILL);
    kill(j->pid, SIGKILL);
  }
}
static void log_add(JobLog *log, const unsigned char *p, size_t n) {
  size_t at = (size_t)(log->end % CHUNK),
         first = n < CHUNK - at ? n : CHUNK - at;
  memcpy(log->bytes + at, p, first);
  memcpy(log->bytes, p + first, n - first);
  log->end += n;
}
static J *log_read(JobLog *log, int64_t cursor) {
  int64_t start = log->end > CHUNK ? log->end - CHUNK : 0,
          at = cursor < start ? start : cursor;
  size_t n = (size_t)(log->end - at);
  if (n > 65536)
    n = 65536;
  unsigned char bytes[65536];
  size_t offset = at % CHUNK, first = n < CHUNK - offset ? n : CHUNK - offset;
  memcpy(bytes, log->bytes + offset, first);
  memcpy(bytes + first, log->bytes, n - first);
  char *encoded = base64(bytes, n);
  J *r = obj();
  str(r, "data", encoded);
  free(encoded);
  num(r, "next_cursor", at + n);
  num(r, "end_cursor", log->end);
  boolean(r, "truncated", cursor < start);
  return r;
}
static void *job_monitor(void *unused) {
  (void)unused;
  for (;;) {
    pthread_mutex_lock(&jobs_mutex);
    int stop = jobs_stop || stopping;
    for (int i = 0; i < 16; i++) {
      Job *j = &jobs[i];
      if (!j->id[0] || j->finished)
        continue;
      double now = stamp();
      if (stop || (now >= j->deadline && !strcmp(j->state, "running"))) {
        j->timed = !stop;
        strcpy(j->state, stop ? "interrupted" : "timed_out");
        job_kill(j);
        if (!j->drain_deadline)
          j->drain_deadline = now + 2000;
      }
      for (int stream = 0; stream < 2; stream++)
        if (j->pipes[stream] >= 0) {
          unsigned char bytes[8192];
          /* Bound each pass so a noisy job cannot starve cancellation or
           * siblings. */
          for (int batch = 0; batch < 32; batch++) {
            ssize_t n = read(j->pipes[stream], bytes, sizeof bytes);
            if (n > 0)
              log_add(&j->logs[stream], bytes, n);
            else {
              if (!n || (errno != EAGAIN && errno != EINTR)) {
                close(j->pipes[stream]);
                j->pipes[stream] = -1;
              }
              break;
            }
          }
        }
      siginfo_t info;
      memset(&info, 0, sizeof info);
      if (waitid(P_PID, j->pid, &info, WEXITED | WNOHANG | WNOWAIT) < 0) {
        /* Never signal an identity after losing ownership of its wait status.
         */
        if (errno != EINTR) {
          j->reaped = 1;
          strcpy(j->state, "unknown");
          j->code = 125;
          j->finished = 1;
        }
      } else if (info.si_pid) {
        if (!j->drain_deadline)
          j->drain_deadline = now + 2000;
        if ((j->pipes[0] < 0 && j->pipes[1] < 0) || now >= j->drain_deadline ||
            stop) {
          job_kill(j);
          int status = 0;
          pid_t got;
          do {
            got = waitpid(j->pid, &status, 0);
          } while (got < 0 && errno == EINTR);
          j->reaped = 1;
          j->finished = 1;
          j->code = got < 0             ? 125
                    : WIFEXITED(status) ? WEXITSTATUS(status)
                                        : 128 + WTERMSIG(status);
          if (!strcmp(j->state, "running"))
            strcpy(j->state, "completed");
          if (!strcmp(j->state, "cancelling"))
            strcpy(j->state, "cancelled");
        }
      }
      if (j->finished) {
        for (int s = 0; s < 2; s++)
          if (j->pipes[s] >= 0) {
            close(j->pipes[s]);
            j->pipes[s] = -1;
          }
        j->save_failed = !job_save(j, 0);
      }
    }
    int active = 0;
    for (int i = 0; i < 16; i++)
      if (jobs[i].id[0] && !jobs[i].finished)
        active = 1;
    if (!stop && !active)
      pthread_cond_wait(&jobs_changed, &jobs_mutex);
    pthread_mutex_unlock(&jobs_mutex);
    if (stop && !active)
      break;
    usleep(10000);
  }
  return NULL;
}
static void jobs_init(void) {
  if (mkdirat(directory, ".jobs", 0700) && errno != EEXIST)
    fatal("job directory");
  jobs_dir = openat(directory, ".jobs",
                    O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  struct stat st;
  if (jobs_dir < 0 || fstat(jobs_dir, &st) || st.st_uid || (st.st_mode & 077))
    fatal("private jobs directory");
  jobs_lock =
      openat(jobs_dir, "lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (jobs_lock < 0 || fstat(jobs_lock, &st) || !S_ISREG(st.st_mode) ||
      st.st_uid || (st.st_mode & 077) || flock(jobs_lock, LOCK_EX | LOCK_NB))
    fatal("exclusive job ownership");
  readtext("/proc/sys/kernel/random/boot_id", current_boot,
           sizeof current_boot);
  if (pthread_create(&jobs_thread, NULL, job_monitor, NULL))
    fatal("job supervisor");
  jobs_started = 1;
}
static void jobs_cleanup(void) {
  if (jobs_started) {
    pthread_mutex_lock(&jobs_mutex);
    jobs_stop = 1;
    pthread_cond_signal(&jobs_changed);
    pthread_mutex_unlock(&jobs_mutex);
    pthread_join(jobs_thread, NULL);
    jobs_started = 0;
  }
  for (int i = 0; i < 16; i++)
    for (int s = 0; s < 2; s++) {
      free(jobs[i].logs[s].bytes);
      jobs[i].logs[s].bytes = NULL;
    }
  if (jobs_lock >= 0) {
    close(jobs_lock);
    jobs_lock = -1;
  }
  if (jobs_dir >= 0) {
    close(jobs_dir);
    jobs_dir = -1;
  }
}
static J *saved_job(J *request, const char *op, const char *id) {
  char name[80], bytes[2048];
  snprintf(name, sizeof name, "%s.json", id);
  int fd = openat(jobs_dir, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  struct stat st;
  if (fd < 0)
    return failure("Unknown job");
  if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid ||
      (st.st_mode & 077) || st.st_size < 1 ||
      st.st_size >= (off_t)sizeof bytes) {
    close(fd);
    return failure("Invalid job record");
  }
  ssize_t n = read(fd, bytes, sizeof bytes - 1);
  close(fd);
  if (n != st.st_size)
    return failure("Job record read failed");
  bytes[n] = 0;
  J *record = parse(bytes);
  const char *state = record ? textval(record, "state") : NULL,
             *boot = record ? textval(record, "boot_id") : NULL;
  if (!state || !boot) {
    if (record)
      json_object_put(record);
    return failure("Invalid job record");
  }
  int terminal = !strcmp(state, "completed") || !strcmp(state, "cancelled") ||
                 !strcmp(state, "timed_out") || !strcmp(state, "interrupted");
  int rebooted = strcmp(boot, current_boot) != 0;
  J *r;
  if (!strcmp(op, "job.status")) {
    r = obj();
    str(r, "id", id);
    str(r, "boot_id", boot);
    str(r, "state", terminal ? state : rebooted ? "interrupted" : "unknown");
    boolean(r, "output_available", 0);
    json_object_object_add(r, "record", record);
    return success(r);
  }
  if (!strcmp(op, "job.forget") && (terminal || rebooted)) {
    int ok = !unlinkat(jobs_dir, name, 0) && !fsync(jobs_dir);
    json_object_put(record);
    if (!ok)
      return failure("Cannot forget saved job");
    r = obj();
    boolean(r, "forgotten", 1);
    return success(r);
  }
  /* A disconnected worker cannot prove ownership of a process group atomically
   * on these old kernels. Refuse stale cancellation instead of risking PID
   * reuse. */
  (void)request;
  json_object_put(record);
  return failure("Operation unavailable for saved job; inspect status");
}
static J *job_operation_locked(J *request, const char *op) {
  const char *id = textval(request, "id");
  if (!job_valid_id(id))
    return failure("Invalid job ID");
  Job *j = NULL, *empty = NULL;
  for (int i = 0; i < 16; i++) {
    if (!jobs[i].id[0])
      empty = &jobs[i];
    else if (!strcmp(jobs[i].id, id))
      j = &jobs[i];
  }
  if (!strcmp(op, "job.start")) {
    int64_t timeout;
    const char *command = textval(request, "command"),
               *profile = textval(request, "profile");
    if (!integer(request, "timeout_ms", &timeout) || timeout < 100 ||
        timeout > 86400000 || !command || !*command ||
        strlen(command) > 16384 || !profile ||
        (strcmp(profile, "root") && strcmp(profile, "app")))
      return failure("Invalid job request");
    int app = !strcmp(profile, "app");
    if (app && !verified_launcher())
      return failure("Verified app launcher unavailable");
    if (j || !empty)
      return failure("Job already exists or retention limit reached");
    int count = 0,
        scan = openat(jobs_dir, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    DIR *d = scan < 0 ? NULL : fdopendir(scan);
    if (!d) {
      if (scan >= 0)
        close(scan);
      return failure("Cannot inspect job retention");
    }
    struct dirent *e;
    while ((e = readdir(d)))
      if (strstr(e->d_name, ".json"))
        count++;
    closedir(d);
    if (count >= 64)
      return failure("Saved job retention limit reached");
    j = empty;
    memset(j, 0, sizeof *j);
    j->pipes[0] = j->pipes[1] = -1;
    strcpy(j->id, id);
    strcpy(j->boot, current_boot);
    strcpy(j->state, "unknown");
    time_t now = time(NULL);
    struct tm utc;
    gmtime_r(&now, &utc);
    strftime(j->started, sizeof j->started, "%Y-%m-%dT%H:%M:%SZ", &utc);
    if (!job_save(j, 1)) {
      memset(j, 0, sizeof *j);
      return failure(
          "Job intent already exists or cannot be persisted; not launched");
    }
    int pipes[2][2] = {{-1, -1}, {-1, -1}}, gate[2] = {-1, -1};
    for (int s = 0; s < 2; s++)
      j->logs[s].bytes = calloc(1, CHUNK);
    if (!j->logs[0].bytes || !j->logs[1].bytes || pipe2(pipes[0], O_CLOEXEC) ||
        pipe2(pipes[1], O_CLOEXEC) || pipe2(gate, O_CLOEXEC))
      goto launch_failed;
    for (int s = 0; s < 2; s++)
      if (ioctl(pipes[s][0], FIONBIO, &(int){1}))
        goto launch_failed;
    pid_t owner = getpid(), pid = fork();
    if (pid < 0)
      goto launch_failed;
    if (!pid) {
      /* Only async-signal-safe libc calls after fork from the supervisor
       * process. */
      if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != owner ||
          setsid() < 0)
        _exit(126);
      close(gate[1]);
      char permit;
      ssize_t got;
      do {
        got = read(gate[0], &permit, 1);
      } while (got < 0 && errno == EINTR);
      if (got != 1 || permit != '1')
        _exit(126);
      close(gate[0]);
      if (dup2(pipes[0][1], 1) < 0 || dup2(pipes[1][1], 2) < 0)
        _exit(126);
      int null = open("/dev/null", O_RDONLY);
      if (null < 0 || dup2(null, 0) < 0)
        _exit(126);
      close(null);
      for (int s = 0; s < 2; s++) {
        close(pipes[s][0]);
        close(pipes[s][1]);
      }
      if (app)
        execve(launcher,
               (char *const[]){launcher, "--command", (char *)command, NULL},
               environ);
      else
        execve("/bin/sh", (char *const[]){"sh", "-c", (char *)command, NULL},
               environ);
      _exit(127);
    }
    j->pid = pid;
    close(gate[0]);
    gate[0] = -1;
    for (int s = 0; s < 2; s++) {
      close(pipes[s][1]);
      pipes[s][1] = -1;
      j->pipes[s] = pipes[s][0];
      pipes[s][0] = -1;
    }
    j->deadline = stamp() + timeout;
    strcpy(j->state, "running");
    if (!job_identity(pid, j->identity) || !job_save(j, 0) ||
        !job_write(gate[1], "1", 1)) {
      job_kill(j);
      close(gate[1]);
      gate[1] = -1;
      strcpy(j->state, "cancelling");
      pthread_cond_signal(&jobs_changed);
      return failure("Launch failed after intent; inspect job status");
    }
    close(gate[1]);
    pthread_cond_signal(&jobs_changed);
    return success(job_snapshot(j));
  launch_failed:
    for (int s = 0; s < 2; s++) {
      for (int p = 0; p < 2; p++)
        if (pipes[s][p] >= 0)
          close(pipes[s][p]);
      free(j->logs[s].bytes);
      j->logs[s].bytes = NULL;
    }
    for (int p = 0; p < 2; p++)
      if (gate[p] >= 0)
        close(gate[p]);
    memset(j, 0, sizeof *j);
    return failure("Job intent retained; launch failed");
  }
  if (!j)
    return saved_job(request, op, id);
  if (!strcmp(op, "job.status"))
    return success(job_snapshot(j));
  if (!strcmp(op, "job.output")) {
    int64_t out, err;
    if (!integer(request, "stdout_cursor", &out) ||
        !integer(request, "stderr_cursor", &err) || out < 0 || err < 0 ||
        out > j->logs[0].end || err > j->logs[1].end)
      return failure("Invalid output cursor");
    J *r = obj();
    json_object_object_add(r, "stdout", log_read(&j->logs[0], out));
    json_object_object_add(r, "stderr", log_read(&j->logs[1], err));
    str(r, "state", j->state);
    return success(r);
  }
  if (!strcmp(op, "job.cancel")) {
    if (!j->finished && !strcmp(j->state, "running")) {
      job_kill(j);
      strcpy(j->state, "cancelling");
      j->drain_deadline = stamp() + 2000;
      j->save_failed = !job_save(j, 0);
    }
    return success(job_snapshot(j));
  }
  if (!strcmp(op, "job.forget")) {
    if (!j->finished || !j->reaped)
      return failure("Job still active");
    char name[80];
    snprintf(name, sizeof name, "%s.json", j->id);
    if (unlinkat(jobs_dir, name, 0) || fsync(jobs_dir))
      return failure("Cannot forget job record");
    for (int s = 0; s < 2; s++)
      free(j->logs[s].bytes);
    memset(j, 0, sizeof *j);
    J *r = obj();
    boolean(r, "forgotten", 1);
    return success(r);
  }
  return failure("Unsupported job operation");
}
static J *job_operation(J *request, const char *op) {
  pthread_mutex_lock(&jobs_mutex);
  J *r = job_operation_locked(request, op);
  pthread_mutex_unlock(&jobs_mutex);
  return r;
}
