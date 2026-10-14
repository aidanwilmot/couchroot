/* Experimental sidecar, not installed or selected by the production service.
 * Original Couchroot code. SPDX-License-Identifier: 0BSD */
#include "common.h"
#include "progress.h"
typedef struct {
  int fd, upload;
  char id[33], name[256], temp[48], sha[65], expected[65];
  int64_t size;
} Transfer;
static Transfer transfers[8];
static unsigned experiment_seconds = 300;
static int directory = -1;
static char root[PATH_MAX], launcher[PATH_MAX], launcher_sha[65], worker_id[33];
static volatile sig_atomic_t active_child = 0;
static void release(Transfer *t) {
  if (t->fd >= 0)
    close(t->fd);
  if (t->temp[0] && directory >= 0)
    unlinkat(directory, t->temp, 0);
  memset(t, 0, sizeof *t);
  t->fd = -1;
}
static void jobs_cleanup(void);
static void helpers_cleanup(void);
static void runtime_cleanup(void);
static void containment_worker_stop(void);
static void cleanup(void) {
  if (active_child > 0) {
    pid_t pid = active_child;
    kill(-pid, SIGKILL);
    kill(pid, SIGKILL);
    active_child = 0;
    while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {
    }
  }
  runtime_cleanup();
  jobs_cleanup();
  containment_worker_stop();
  for (int i = 0; i < 8; i++)
    release(&transfers[i]);
  if (directory >= 0)
    close(directory);
}
static int leaf(const char *path, const char **name) {
  size_t n = strlen(root);
  if (!path || strncmp(path, root, n) || path[n] != '/')
    return 0;
  const char *p = path + n + 1;
  if (!*p || strlen(p) > 255 || strchr(p, '/') || !strcmp(p, ".") ||
      !strcmp(p, "..") || !strcmp(p, ".jobs") || !strcmp(p, ".views") ||
      !strncmp(p, ".upload-", 8))
    return 0;
  *name = p;
  return 1;
}
static int regular(int fd, int64_t *size) {
  struct stat s;
  if (fstat(fd, &s) || !S_ISREG(s.st_mode) || s.st_size < 0 ||
      s.st_size > LIMIT)
    return 0;
  *size = s.st_size;
  return 1;
}
static Transfer *lookup(const char *id) {
  for (int i = 0; i < 8; i++)
    if (id && transfers[i].fd >= 0 && !strcmp(id, transfers[i].id))
      return &transfers[i];
  return NULL;
}
static J *failure(const char *s) {
  J *j = obj();
  boolean(j, "ok", 0);
  str(j, "error", s);
  str(j, "outcome", "failed");
  return j;
}
static J *success(J *value) {
  J *j = obj();
  boolean(j, "ok", 1);
  json_object_object_add(j, "result", value);
  return j;
}
static J *snapshot(Transfer *t) {
  J *j = obj();
  str(j, "transfer_id", t->id);
  num(j, "size", t->size);
  str(j, "sha256", t->sha);
  str(j, "expected_sha256", t->expected);
  num(j, "chunk_bytes", CHUNK);
  int64_t size;
  if (!regular(t->fd, &size))
    fatal("transfer stat");
  num(j, "offset", t->upload ? size : 0);
  boolean(j, "upload", t->upload);
  char *p = format("%s/%s", root, t->name);
  str(j, "path", p);
  free(p);
  return j;
}
static J *writechunk(const char *id, int64_t offset, const unsigned char *data,
                     size_t length, const char *sha) {
  Transfer *t = lookup(id);
  if (!t)
    return failure("Unknown transfer");
  if (!t->upload)
    return failure("Not an upload");
  char actual[65];
  digest(data, length, actual);
  if (!length || length > CHUNK || !sha || strcmp(actual, sha))
    return failure("Invalid chunk digest");
  int64_t size;
  if (!regular(t->fd, &size))
    return failure("Transfer stat failed");
  if (offset != size || offset < 0 || length > (uint64_t)(t->size - offset) ||
      offset > t->size)
    return failure("Offset conflict");
  size_t at = 0;
  while (at < length) {
    ssize_t n = pwrite(t->fd, data + at, length - at, offset + at);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0)
      return failure("Chunk write failed; inspect offset");
    at += n;
  }
  if (fsync(t->fd))
    return failure("Chunk flush failed; inspect offset");
  J *j = obj();
  num(j, "offset", offset + length);
  return success(j);
}
typedef struct {
  unsigned char *out, *err;
  size_t outlen, errlen;
  int code, timed, truncated;
} Result;
static Result execute(const char *command, int timeout, int app) {
  Result r = {0};
  r.out = allocate(CHUNK + 1);
  r.err = allocate(CHUNK + 128);
  int pipes[2][2];
  if (pipe2(pipes[0], O_CLOEXEC) || pipe2(pipes[1], O_CLOEXEC))
    fatal("pipe");
  pid_t pid = fork();
  if (pid < 0)
    fatal("fork");
  if (!pid) {
    if (setsid() < 0)
      _exit(126);
    if (dup2(pipes[0][1], 1) < 0 || dup2(pipes[1][1], 2) < 0)
      _exit(126);
    int null = open("/dev/null", O_RDONLY);
    if (null < 0 || dup2(null, 0) < 0)
      _exit(126);
    close(null);
    for (int i = 0; i < 2; i++) {
      close(pipes[i][0]);
      close(pipes[i][1]);
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
  active_child = pid;
  close(pipes[0][1]);
  close(pipes[1][1]);
  struct pollfd f[2] = {{pipes[0][0], POLLIN, 0}, {pipes[1][0], POLLIN, 0}};
  for (int i = 0; i < 2; i++)
    if (ioctl(f[i].fd, FIONBIO, &(int){1}) < 0)
      fatal("nonblocking pipe");
  double deadline = stamp() + timeout;
  int finished = 0, status = 0, openpipes = 2;
  while (!finished || openpipes) {
    progress_touch(&progress_main);
    if (stamp() >= deadline && !r.timed) {
      r.timed = 1;
      kill(-pid, SIGKILL);
      kill(pid, SIGKILL);
    }
    if (!finished) {
      siginfo_t info;
      memset(&info, 0, sizeof info);
      if (waitid(P_PID, pid, &info, WEXITED | WNOHANG | WNOWAIT) < 0) {
        if (errno != EINTR) {
          active_child = 0;
          fatal("waitid");
        }
      } else if (info.si_pid)
        finished = 1;
    }
    if (r.timed && stamp() > deadline + 2000)
      break;
    int rc = poll(f, 2, 10);
    if (rc < 0 && errno != EINTR)
      fatal("poll");
    for (int i = 0; i < 2; i++) {
      if (f[i].fd < 0 || !f[i].revents)
        continue;
      unsigned char buffer[8192];
      ssize_t n = read(f[i].fd, buffer, sizeof buffer);
      if (n == 0) {
        close(f[i].fd);
        f[i].fd = -1;
        openpipes--;
      } else if (n > 0) {
        size_t *used = i ? &r.errlen : &r.outlen;
        unsigned char *out = i ? r.err : r.out;
        size_t keep = (size_t)n;
        if (keep > CHUNK - *used) {
          keep = CHUNK - *used;
          r.truncated |= 1 << i;
        }
        memcpy(out + *used, buffer, keep);
        *used += keep;
      } else if (errno != EINTR && errno != EAGAIN)
        fatal("pipe read");
    }
  }
  /* Keep the leader waitable until its process group is killed; a reaped PID
   * must never remain a cancellation target while descendants hold pipes. */
  kill(-pid, SIGKILL);
  kill(pid, SIGKILL);
  active_child = 0;
  while (waitpid(pid, &status, 0) < 0)
    if (errno != EINTR)
      fatal("wait");
  for (int i = 0; i < 2; i++)
    if (f[i].fd >= 0)
      close(f[i].fd);
  active_child = 0;
  if (r.truncated) {
    const char *streams = r.truncated == 3   ? "stdout and stderr"
                          : r.truncated == 1 ? "stdout"
                                             : "stderr";
    int n = snprintf(
        (char *)r.err + r.errlen, 128,
        "\n[samsung-tv-root: %s exceeded the 1 MiB capture limit]\n", streams);
    if (n < 0 || n >= 128)
      fatal("output notice");
    r.errlen += (size_t)n;
  }
  r.code = r.timed             ? 124
           : WIFEXITED(status) ? WEXITSTATUS(status)
                               : 128 + WTERMSIG(status);
  return r;
}
static void result_free(Result *r) {
  free(r->out);
  free(r->err);
}
static int verified_launcher(void) {
  int fd = open(launcher, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0)
    return 0;
  struct stat s;
  char actual[65];
  int good = !fstat(fd, &s) && S_ISREG(s.st_mode) && s.st_uid == 0 &&
             !(s.st_mode & 022) && filedigest(fd, actual) &&
             !strcmp(actual, launcher_sha);
  close(fd);
  return good;
}
#include "jobs.h"

#include "helpers.h"

#include "runtime.h"

static void stop_signal(int sig);
#include "containment.h"

#include "guardian.h"
#include "reconcile.h"
static void runtime_cleanup(void) {
  if (runtime_owned && runtime_sweep() && containment_cleanup() &&
      guardian_journal_owned) {
    unlinkat(jobs_dir, "guardian", 0);
    fsync(jobs_dir);
    guardian_journal_owned = 0;
  }
}
static volatile sig_atomic_t signal_socket = -1;
static void stop_signal(int sig) {
  (void)sig;
  if (signal_socket >= 0)
    shutdown(signal_socket, SHUT_RDWR);
  pid_t pid = active_child;
  if (pid > 0) {
    kill(-pid, SIGKILL);
    kill(pid, SIGKILL);
  }
}
#include "fault-test.h"
static J *operation(J *request, Wire *w, const char *seq) {
  const char *op = textval(request, "op");
  if (!op)
    return failure("Invalid operation");
#ifdef NATIVE_WORKER_FAULT_TEST
  if (!strcmp(op, "test.stall")) {
    int64_t thread = number(request, "thread");
    if (thread != 0 && thread != 1)
      return failure("invalid stall target");
    fault_test_requested = thread ? 4 : 3;
    return success(obj());
  }
  if (!strcmp(op, "test.fault")) {
    int64_t thread = number(request, "thread");
    if (thread != 0 && thread != 1)
      return failure("Invalid fault test thread");
    fault_test_requested = thread ? 2 : 1;
    return success(obj());
  }
#endif
  if (!strncmp(op, "job.", 4))
    return job_operation(request, op);
  if (!strncmp(op, "helper.", 7))
    return helper_operation(request, op);
  if (!strcmp(op, "status")) {
    J *j = obj(), *caps = json_object_new_array();
    char b[128];
    readtext("/proc/sys/kernel/random/boot_id", b, sizeof b);
    str(j, "boot_id", b);
    readtext("/proc/uptime", b, sizeof b);
    json_object_object_add(j, "uptime_seconds",
                           json_object_new_double(strtod(b, NULL)));
    str(j, "worker_id", worker_id);
    str(j, "implementation", "native-prototype");
    num(j, "guardian_pid", guardian_pid);
    boolean(j, "stale_guardian_reconciled", guardian_reconciled);
    str(j, "fault_supervision", "ptrace-owned-descendants");
    num(j, "worker_dumpable", prctl(PR_GET_DUMPABLE));
    str(j, "freezer_group", freezer_name);
    num(j, "heartbeat_timeout_ms", 1000);
    num(j, "progress_timeout_ms", PROGRESS_GRACE_MS);
    num(j, "lifetime_seconds", experiment_seconds);
    J *app = obj();
    str(app, "path", launcher);
    str(app, "sha256", launcher_sha);
    boolean(app, "independently_staged", 1);
    json_object_object_add(j, "app_launcher", app);
    const char *names[] = {"prototype-scoped-files-v1",
                           "binary-upload-v1",
                           "binary-download-v1",
                           "prototype-app-exec-v1",
                           "prototype-jobs-v1",
                           "prototype-helper-lifecycle-v1",
                           "prototype-independent-launcher-v1",
                           "prototype-crash-guardian-v1"};
    for (size_t i = 0; i < sizeof names / sizeof *names; i++)
      json_object_array_add(caps, json_object_new_string(names[i]));
    json_object_object_add(j, "capabilities", caps);
    return success(j);
  }
  if (!strcmp(op, "app.exec")) {
    const char *command = textval(request, "command");
    int64_t timeout;
    if (!command || !*command || strlen(command) > 16384 ||
        !integer(request, "timeout_ms", &timeout) || timeout < 100 ||
        timeout > 25000)
      return failure("Invalid app command");
    if (!verified_launcher())
      return failure("Verified app launcher unavailable");
    Result r = execute(command, (int)timeout, 1);
    J *j = obj();
    num(j, "exit_code", r.code);
    boolean(j, "timed_out", r.timed);
    boolean(j, "output_truncated", r.truncated);
    json_object_object_add(j, "stdout",
                           json_object_new_string_len((char *)r.out, r.outlen));
    json_object_object_add(j, "stderr",
                           json_object_new_string_len((char *)r.err, r.errlen));
    result_free(&r);
    return success(j);
  }
  if (!strcmp(op, "file.begin") || !strcmp(op, "file.open")) {
    Transfer *t = NULL;
    for (int i = 0; i < 8; i++)
      if (transfers[i].fd < 0) {
        t = &transfers[i];
        break;
      }
    if (!t)
      return failure("Transfer limit");
    const char *name;
    if (!leaf(textval(request, "path"), &name))
      return failure("Prototype path outside experiment directory");
    int upload = !strcmp(op, "file.begin");
    int64_t size = 0;
    const char *sha = NULL, *expected = NULL;
    if (upload) {
      sha = textval(request, "sha256");
      expected = textval(request, "expected_sha256");
      if (!integer(request, "size", &size) || size < 0 || size > LIMIT ||
          !hexvalid(sha, 64) || !expected ||
          (strcmp(expected, "absent") && !hexvalid(expected, 64)))
        return failure("Invalid upload metadata");
    }
    unsigned char id[16];
    random_bytes(id, sizeof id);
    hex(id, sizeof id, t->id);
    strcpy(t->name, name);
    t->upload = upload;
    t->size = size;
    if (upload) {
      strcpy(t->sha, sha);
      strcpy(t->expected, expected);
      memcpy(t->temp, ".upload-", 8);
      memcpy(t->temp + 8, t->id, sizeof t->id);
      t->fd = openat(directory, t->temp,
                     O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    } else
      t->fd = openat(directory, name,
                     O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (t->fd < 0) {
      t->temp[0] =
          0; // Never unlink an existing file after exclusive creation failed.
      release(t);
      return failure("Cannot open transfer");
    }
    if (!regular(t->fd, &size) || (!upload && !filedigest(t->fd, t->sha))) {
      release(t);
      return failure("Not a bounded regular file");
    }
    if (!upload)
      t->size = size;
    return success(snapshot(t));
  }
  if (strncmp(op, "file.", 5))
    return failure("Unsupported in native prototype (no fallback)");
  Transfer *t = lookup(textval(request, "transfer_id"));
  if (!t)
    return failure("Unknown transfer");
  if (!strcmp(op, "file.status"))
    return success(snapshot(t));
  if (!strcmp(op, "file.close")) {
    release(t);
    J *j = obj();
    boolean(j, "closed", 1);
    return success(j);
  }
  if (!strcmp(op, "file.read")) {
    int64_t offset, length;
    if (t->upload || !integer(request, "offset", &offset) ||
        !integer(request, "length", &length) || offset < 0 ||
        offset > t->size || length < 1 || length > CHUNK)
      return failure("Invalid byte range");
    if (length > t->size - offset)
      length = t->size - offset;
    unsigned char *data = allocate((size_t)length);
    size_t at = 0;
    while (at < (size_t)length) {
      ssize_t n = pread(t->fd, data + at, (size_t)length - at, offset + at);
      if (n < 0 && errno == EINTR)
        continue;
      if (n <= 0) {
        free(data);
        return failure("File changed during read");
      }
      at += n;
    }
    char sha[65];
    digest(data, length, sha);
    char *header = format("OPDATA\t%s\t%" PRId64 "\t%" PRId64 "\t%s", seq,
                          offset, length, sha);
    sendframe(w, header);
    writeall(w->fd, data, length);
    free(header);
    free(data);
    return NULL;
  }
  if (!strcmp(op, "file.commit")) {
    int64_t size;
    char actual[65];
    if (!t->upload || !regular(t->fd, &size) || size != t->size ||
        !filedigest(t->fd, actual) || strcmp(actual, t->sha))
      return failure("Upload digest or size mismatch");
    if (!strcmp(t->expected, "absent")) {
      if (linkat(directory, t->temp, directory, t->name, 0))
        return failure("Target exists or cannot be created");
    } else {
      int fd = openat(directory, t->name,
                      O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
      int good = fd >= 0 && regular(fd, &size) && filedigest(fd, actual) &&
                 !strcmp(actual, t->expected);
      if (fd >= 0)
        close(fd);
      if (!good)
        return failure("Target hash conflict");
      if (renameat(directory, t->temp, directory, t->name))
        return failure("Atomic replacement failed");
    }
    J *j = obj();
    boolean(j, "committed", 1);
    str(j, "sha256", t->sha);
    num(j, "size", t->size);
    release(t);
    return success(j);
  }
  return failure("Unsupported file operation in native prototype");
}
int main(int argc, char **argv) {
#ifdef NATIVE_WORKER_FAULT_TEST
  if (argc == 2 && !strcmp(argv[1], "--test-child-fault"))
    fault_test_memory(NULL);
  if (argc == 2 && !strcmp(argv[1], "--test-child-thread-fault")) {
    fault_test_requested = 2;
    fault_test_execute();
  }
#endif
  if (argc != 7) {
    fputs("usage: worker HOST PORT TOKEN EXPERIMENT_DIRECTORY "
          "LAUNCHER_SOURCE SHA256\n",
          stderr);
    return 64;
  }
  if (getuid() || geteuid() || getgid() || getegid())
    return 77;
  signal(SIGPIPE, SIG_IGN);
  signal(SIGTERM, stop_signal);
  signal(SIGINT, stop_signal);
  signal(SIGALRM, stop_signal);
  const char *lifetime = getenv("COUCHROOT_NATIVE_LIFETIME_SECONDS");
  int64_t seconds;
  if (lifetime) {
    if (!decimal(lifetime, &seconds) || seconds < 300 || seconds > 86400)
      fatal("prototype lifetime must be 300..86400 seconds");
    experiment_seconds = (unsigned)seconds;
  }
  alarm(experiment_seconds);
  libraries();
  for (int i = 0; i < 8; i++)
    transfers[i].fd = -1;
  atexit(cleanup);
  char resolved[PATH_MAX];
  if (!realpath(argv[4], resolved) || strcmp(resolved, argv[4]) ||
      strlen(resolved) > PATH_MAX - 257)
    fatal("canonical experiment directory required");
  strcpy(root, resolved);
  directory = open(root, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  struct stat st;
  if (directory < 0 || fstat(directory, &st) || st.st_uid != 0 ||
      (st.st_mode & 077))
    fatal("private root-owned directory required");
  if (strlen(argv[5]) >= sizeof launcher || !hexvalid(argv[6], 64))
    fatal("launcher arguments");
  strcpy(launcher_sha, argv[6]);
  unsigned char id[16];
  random_bytes(id, sizeof id);
  hex(id, sizeof id, worker_id);
  struct rlimit core_limit = {0, 0};
  if (setrlimit(RLIMIT_CORE, &core_limit) || prctl(PR_SET_DUMPABLE, 0))
    fatal("disable prototype core dumps");
  signal(SIGCHLD, SIG_DFL);
  jobs_storage();
  guardian_reconcile();
  helpers_init();
  guardian_journal(0);
  launcher_stage(argv[5]);
  containment_prepare();
  guardian_journal(1);
  guardian_start();
  jobs_init();
  Wire w = {0};
  int token = open(argv[3], O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (token < 0 || fstat(token, &st) || !S_ISREG(st.st_mode) ||
      st.st_uid != 0 || (st.st_mode & 077))
    fatal("private token required");
  char encoded[128];
  ssize_t n = read(token, encoded, sizeof encoded - 1);
  close(token);
  if (n < 1 || n > 64)
    fatal("token size");
  encoded[n] = 0;
  while (n && isspace((unsigned char)encoded[n - 1]))
    encoded[--n] = 0;
  size_t decoded;
  unsigned char *key = decode(encoded, &decoded);
  if (!key || decoded != 32)
    fatal("token encoding");
  memcpy(w.secret, key, 32);
  memset(key, 0, decoded);
  free(key);
  if (unlink(argv[3]))
    fatal("consume token");
  int64_t port;
  if (!decimal(argv[2], &port) || port < 1 || port > 65535)
    fatal("port");
  struct sockaddr_in addr = {.sin_family = AF_INET,
                             .sin_port = htons((uint16_t)port)};
  if (inet_pton(AF_INET, argv[1], &addr.sin_addr) != 1)
    fatal("host");
  w.fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (w.fd < 0)
    fatal("socket");
  signal_socket = w.fd;
  int one = 1;
  setsockopt(w.fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
  struct timeval limit = {experiment_seconds, 0};
  setsockopt(w.fd, SOL_SOCKET, SO_RCVTIMEO, &limit, sizeof limit);
  setsockopt(w.fd, SOL_SOCKET, SO_SNDTIMEO, &limit, sizeof limit);
  if (connect(w.fd, (struct sockaddr *)&addr, sizeof addr))
    fatal("connect");
  char *hello = line(&w), *f[10];
  if (fields(hello, f, 10) != 2 || strcmp(f[0], "SAMSUNG-TV-ROOT/1") ||
      !unhex(f[1], w.nonce, 32))
    fatal("hello");
  free(hello);
  char smack[128];
#ifdef NATIVE_WORKER_TEST
  strcpy(smack, "host-test-without-Smack");
#else
  readtext("/proc/self/attr/current", smack, sizeof smack);
#endif
  char caps[32] = "", statusline[256];
  FILE *statusfile = fopen("/proc/self/status", "r");
  if (!statusfile)
    fatal("process identity");
  while (fgets(statusline, sizeof statusline, statusfile))
    if (sscanf(statusline, "CapEff: %31s", caps) == 1)
      break;
  fclose(statusfile);
  if (!*caps)
    fatal("effective capabilities");
  char *label = base64(smack, strlen(smack)),
       *auth = format("AUTH\t%d\t0\t0\t0\t0\t%s\t%s", getpid(), caps, label);
  sendframe(&w, auth);
  free(label);
  free(auth);
  int64_t previous = 0;
  for (;;) {
    progress_idle(&progress_main);
    char *frame = receive(&w);
    progress_touch(&progress_main);
    int count = fields(frame, f, 10);
    int64_t seq;
    if (count < 2 || !decimal(f[1], &seq) || seq <= previous)
      fatal("sequence");
    previous = seq;
    if (!strcmp(f[0], "SHUTDOWN") && count == 2) {
      char *p = format("BYE\t%s", f[1]);
      sendframe(&w, p);
      free(p);
      free(frame);
      break;
    }
    J *reply = NULL;
    if (!strcmp(f[0], "OPWRITE")) {
      int64_t offset, length;
      if (count != 6 || !hexvalid(f[2], 32) || !decimal(f[3], &offset) ||
          !decimal(f[4], &length) || offset > LIMIT || length < 1 ||
          length > CHUNK || length > LIMIT - offset || !hexvalid(f[5], 64))
        fatal("upload header");
      unsigned char *data = allocate(length);
      exact(&w, data, length);
      reply = writechunk(f[2], offset, data, length, f[5]);
      free(data);
    } else if (!strcmp(f[0], "OP") && count == 3) {
      size_t len;
      unsigned char *bytes = decode(f[2], &len);
      if (!bytes || len > 20000 || strlen((char *)bytes) != len)
        fatal("operation encoding");
      J *request = parse((char *)bytes);
      free(bytes);
      if (!request)
        fatal("operation JSON");
      reply = operation(request, &w, f[1]);
      json_object_put(request);
    } else if (!strcmp(f[0], "EXEC") && count == 4) {
      int64_t timeout;
      size_t len;
      unsigned char *command = decode(f[3], &len);
      if (!decimal(f[2], &timeout) || timeout < 100 || timeout > 300000 ||
          !command || !len || len > 65536 || strlen((char *)command) != len)
        fatal("exec input");
      Result r = execute((char *)command, (int)timeout, 0);
      char *out = base64(r.out, r.outlen), *err = base64(r.err, r.errlen),
           *p = format("RESULT\t%s\t%d\t%d\t%s\t%s", f[1], r.code, r.timed, out,
                       err);
      sendframe(&w, p);
      free(p);
      free(out);
      free(err);
      result_free(&r);
      free(command);
    } else if (!strcmp(f[0], "PING") && count == 2) {
      char *p = format("PONG\t%s\t0\t0\t0\t0", f[1]);
      sendframe(&w, p);
      free(p);
    } else
      fatal("unsupported frame");
    if (reply) {
      const char *s = json(reply);
      char *b = base64(s, strlen(s)), *p = format("OPRESULT\t%s\t%s", f[1], b);
      sendframe(&w, p);
      free(b);
      free(p);
      json_object_put(reply);
    }
    free(frame);
#ifdef NATIVE_WORKER_FAULT_TEST
    fault_test_execute();
#endif
  }
  memset(w.secret, 0, 32);
  signal_socket = -1;
  close(w.fd);
  return 0;
}
