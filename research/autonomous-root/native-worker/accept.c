/* On-TV native lifecycle acceptance; never replaces the deployed worker.
 * Original Couchroot code. SPDX-License-Identifier: 0BSD */
#include "common.h"

#include "controller.h"
static const char *binary, *app, *appsha, *source_helper;
static char boot[80], namespace_before[80];
static void launch(void) {
  sequence = 0;
  memset(&w, 0, sizeof w);
  random_bytes(w.secret, 32);
  random_bytes(w.nonce, 32);
  char *token = format("%s/token", scope), *encoded = base64(w.secret, 32);
  int fd = open(token, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
  if (fd < 0)
    fatal("token create");
  writeall(fd, encoded, strlen(encoded));
  close(fd);
  free(encoded);
  int listener = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (listener < 0)
    fatal("listener");
  struct sockaddr_in a = {.sin_family = AF_INET,
                          .sin_addr = {htonl(INADDR_LOOPBACK)}};
  if (bind(listener, (struct sockaddr *)&a, sizeof a) || listen(listener, 1))
    fatal("listen");
  socklen_t n = sizeof a;
  if (getsockname(listener, (struct sockaddr *)&a, &n))
    fatal("listener port");
  char port[16];
  snprintf(port, sizeof port, "%u", ntohs(a.sin_port));
  child = fork();
  if (child < 0)
    fatal("fork");
  if (!child) {
    execl(binary, binary, "127.0.0.1", port, token, filescope, app, appsha,
          (char *)NULL);
    _exit(127);
  }
  struct pollfd ready = {listener, POLLIN, 0};
  if (poll(&ready, 1, 15000) != 1)
    fatal("native connection timeout");
  w.fd = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
  close(listener);
  if (w.fd < 0)
    fatal("accept");
  int one = 1;
  setsockopt(w.fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
  struct timeval timeout = {40, 0};
  setsockopt(w.fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
  setsockopt(w.fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
  char nonce[65];
  hex(w.nonce, 32, nonce);
  char *hello = format("SAMSUNG-TV-ROOT/1\t%s\n", nonce);
  writeall(w.fd, hello, strlen(hello));
  free(hello);
  char *auth = receive(&w), *f[10];
  if (fields(auth, f, 10) != 8 || strcmp(f[0], "AUTH") || atoi(f[1]) != child)
    fatal("AUTH");
  for (int i = 2; i <= 5; i++)
    if (strcmp(f[i], "0"))
      fatal("not root");
  free(auth);
  J *r = call(req("status"));
  if (strcmp(textval(get(r, "result"), "boot_id"), boot))
    fatal("boot changed");
  json_object_put(r);
  char path[64], ns[80];
  snprintf(path, sizeof path, "/proc/%d/ns/mnt", child);
  ssize_t len = readlink(path, ns, sizeof ns - 1);
  if (len < 0)
    fatal("native mount namespace");
  ns[len] = 0;
  if (!strcmp(ns, namespace_before))
    fatal("native mount namespace not isolated");
}
static void finish(int disconnect) {
  if (disconnect == 2)
    kill(child, SIGTERM);
  else if (disconnect)
    shutdown(w.fd, SHUT_RDWR);
  else {
    char *bye = format("SHUTDOWN\t%d", ++sequence);
    sendframe(&w, bye);
    free(bye);
    char *s = receive(&w);
    if (strncmp(s, "BYE\t", 4))
      fatal("shutdown");
    free(s);
  }
  close(w.fd);
  w.fd = -1;
  int status;
  double deadline = stamp() + 5000;
  pid_t got;
  do {
    got = waitpid(child, &status, WNOHANG);
    if (got == 0)
      usleep(10000);
  } while (got == 0 && stamp() < deadline);
  if (got != child)
    fatal("native did not stop");
  child = 0;
  if (!disconnect && (!WIFEXITED(status) || WEXITSTATUS(status)))
    fatal("native shutdown failed");
}
static J *job_req(const char *op, const char *id) {
  J *j = req(op);
  str(j, "id", id);
  return j;
}
static J *start_job(const char *id, const char *cmd, int timeout,
                    const char *profile) {
  J *j = job_req("job.start", id);
  str(j, "command", cmd);
  num(j, "timeout_ms", timeout);
  str(j, "profile", profile);
  return call(j);
}
static void discard(J *r) { json_object_put(r); }
static void await_job(const char *id, const char *state, int code, int max_ms) {
  double deadline = stamp() + max_ms;
  for (;;) {
    J *r = call(job_req("job.status", id));
    J *result = get(r, "result");
    J *exit_code = get(result, "exit_code");
    if (exit_code && !json_object_is_type(exit_code, 0)) {
      if (strcmp(textval(result, "state"), state) ||
          number(result, "exit_code") != code ||
          json_object_get_boolean(get(result, "persistence_failed"))) {
        fprintf(stderr, "job mismatch %s\n", json(r));
        fatal("job completion");
      }
      discard(r);
      return;
    }
    discard(r);
    if (stamp() >= deadline)
      fatal("job wait timeout");
    usleep(20000);
  }
}
static J *output(const char *id, int64_t out, int64_t err) {
  J *j = job_req("job.output", id);
  num(j, "stdout_cursor", out);
  num(j, "stderr_cursor", err);
  return call(j);
}
static void contains(J *r, const char *stream, const char *expected) {
  const char *s = textval(get(get(r, "result"), stream), "data");
  size_t n;
  unsigned char *bytes = s ? decode(s, &n) : NULL;
  if (!bytes || !strstr((char *)bytes, expected))
    fatal("job output mismatch");
  free(bytes);
}
static void mark(const char *check) {
  J *j = obj();
  str(j, "check", check);
  boolean(j, "passed", 1);
  puts(json(j));
  fflush(stdout);
  discard(j);
}
static char *stage_helper(char **id) {
  char *path = format("%s/helper-source", filescope);
  int fd = open(source_helper, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  struct stat st;
  if (fd < 0 || fstat(fd, &st) || st.st_size < 1 || st.st_size > CHUNK)
    fatal("helper source");
  unsigned char *data = allocate(st.st_size);
  ssize_t n = read(fd, data, st.st_size);
  close(fd);
  if (n != st.st_size)
    fatal("helper read");
  char sha[65];
  digest(data, n, sha);
  char *transfer = begin(path, n, sha, "absent");
  upload(transfer, 0, data, n, 1);
  transfer_op("file.commit", transfer, 1);
  free(transfer);
  free(data);
  J *j = req("helper.prepare");
  str(j, "path", path);
  str(j, "sha256",
      "0000000000000000000000000000000000000000000000000000000000000000");
  rejected(j);
  j = req("helper.prepare");
  str(j, "path", path);
  str(j, "sha256", sha);
  J *r = call(j);
  *id = strdup(textval(get(r, "result"), "helper_id"));
  char *staged = strdup(textval(get(r, "result"), "path"));
  discard(r);
  char *cmd = format("test \"$(sha256sum '%s' | cut -d' ' -f1)\" = '%s' && if "
                     "printf x > '%s'; then exit 1; else exit 0; fi",
                     staged, sha, staged);
  command(cmd, 5000, 0, 0);
  free(cmd);
  /* Controller retains .NET's namespace and must not see the native bind mount.
   */
  FILE *mounts = fopen("/proc/self/mountinfo", "r");
  char linebuf[8192];
  if (!mounts)
    fatal("mountinfo");
  while (fgets(linebuf, sizeof linebuf, mounts))
    if (strstr(linebuf, *id))
      fatal("helper mount leaked into controller");
  fclose(mounts);
  free(path);
  mark("helper_digest_readonly_and_namespace");
  return staged;
}
int main(int argc, char **argv) {
  if (argc != 7) {
    fprintf(stderr,
            "accept WORKER TOKEN_SCOPE FILE_SCOPE LAUNCHER SHA HELPER\n");
    return 64;
  }
  binary = argv[1];
  scope = argv[2];
  filescope = argv[3];
  app = argv[4];
  appsha = argv[5];
  source_helper = argv[6];
  signal(SIGPIPE, SIG_IGN);
  libraries();
  atexit(stop_child);
  alarm(150);
  readtext("/proc/sys/kernel/random/boot_id", boot, sizeof boot);
  ssize_t ns = readlink("/proc/self/ns/mnt", namespace_before,
                        sizeof namespace_before - 1);
  if (ns < 0)
    fatal("parent namespace");
  namespace_before[ns] = 0;
  launch();
  char *helper_id, *helper_path = stage_helper(&helper_id);
  discard(start_job("native-long-job-01",
                    "printf begin; sleep 27; printf end; exit 7", 40000,
                    "root"));
  discard(start_job("native-app-job-001", helper_path, 5000, "app"));
  await_job("native-app-job-001", "completed", 0, 7000);
  J *r = output("native-app-job-001", 0, 0);
  contains(r, "stdout", "uid=5001 euid=5001 gid=100 smack=User");
  discard(r);
  mark("native_staged_helper_app_job_identity");
  J *j = req("helper.release");
  str(j, "helper_id", helper_id);
  rejected(j);
  j = job_req("job.start", "native-long-job-01");
  str(j, "command", ":");
  str(j, "profile", "root");
  num(j, "timeout_ms", 1000);
  rejected(j);
  rejected(job_req("job.forget", "native-long-job-01"));
  char *cmd = format("sleep 2; touch '%s/survivor'", filescope);
  discard(start_job("native-timeout-001", cmd, 100, "root"));
  discard(start_job("native-cancel-0001", cmd, 5000, "root"));
  free(cmd);
  discard(call(job_req("job.cancel", "native-cancel-0001")));
  command("sleep 2.2; printf foreground", 5000, 0, 0);
  await_job("native-timeout-001", "timed_out", 137, 5000);
  await_job("native-cancel-0001", "cancelled", 137, 5000);
  cmd = format("test ! -e '%s/survivor'", filescope);
  command(cmd, 5000, 0, 0);
  free(cmd);
  cmd =
      format("(sleep .5; touch '%s/foreground-survivor') & exit 0", filescope);
  command(cmd, 100, 124, 1);
  free(cmd);
  usleep(600000);
  cmd = format("test ! -e '%s/foreground-survivor'", filescope);
  command(cmd, 5000, 0, 0);
  free(cmd);
  mark("timeout_cancel_during_foreground_and_no_survivor");
  discard(start_job(
      "native-output-001",
      "head -c 1200000 /dev/zero; printf tail; printf error >&2; exit 9", 10000,
      "root"));
  await_job("native-output-001", "completed", 9, 12000);
  r = output("native-output-001", 0, 0);
  J *stream = get(get(r, "result"), "stdout");
  size_t count;
  unsigned char *bytes = decode(textval(stream, "data"), &count);
  if (!bytes || count != 65536 ||
      !json_object_get_boolean(get(stream, "truncated")) ||
      number(stream, "end_cursor") != 1200004)
    fatal("bounded ring");
  free(bytes);
  contains(r, "stderr", "error");
  discard(r);
  r = output("native-output-001", 1200000, 0);
  contains(r, "stdout", "tail");
  discard(r);
  j = job_req("job.output", "native-output-001");
  num(j, "stdout_cursor", 1200005);
  num(j, "stderr_cursor", 0);
  rejected(j);
  mark("nonzero_exit_bounded_logs_and_cursors");
  /* Leave protocol idle while the >25-second job continues. */
  usleep(26000000);
  await_job("native-long-job-01", "completed", 7, 10000);
  r = output("native-long-job-01", 0, 0);
  contains(r, "stdout", "beginend");
  discard(r);
  mark("background_job_over_25_seconds_and_idle_connection");
  j = req("helper.release");
  str(j, "helper_id", helper_id);
  discard(call(j));
  cmd = format("test ! -e '%s'", helper_path);
  command(cmd, 5000, 0, 0);
  free(cmd);
  j = req("helper.release");
  str(j, "helper_id", helper_id);
  rejected(j);
  free(helper_id);
  free(helper_path);
  mark("helper_release_and_unknown_id");
  /* Fill all helper slots and ensure rollback/release permits reuse. */
  char *source = format("%s/helper-source", filescope);
  int fd = open(source, O_RDONLY | O_CLOEXEC);
  char sha[65];
  if (fd < 0 || !filedigest(fd, sha))
    fatal("source digest");
  close(fd);
  char *ids[8];
  for (int i = 0; i < 8; i++) {
    j = req("helper.prepare");
    str(j, "path", source);
    str(j, "sha256", sha);
    r = call(j);
    ids[i] = strdup(textval(get(r, "result"), "helper_id"));
    discard(r);
  }
  j = req("helper.prepare");
  str(j, "path", source);
  str(j, "sha256", sha);
  rejected(j);
  for (int i = 0; i < 8; i++) {
    j = req("helper.release");
    str(j, "helper_id", ids[i]);
    discard(call(j));
    free(ids[i]);
  }
  mark("helper_retention_limit_and_release");
  /* A remaining owned view and running job must be cleaned on disconnect. */
  j = req("helper.prepare");
  str(j, "path", source);
  str(j, "sha256", sha);
  r = call(j);
  helper_path = strdup(textval(get(r, "result"), "path"));
  discard(r);
  cmd = format("sleep 2; touch '%s/disconnected-survivor'", filescope);
  discard(start_job("native-disconnect-01", cmd, 10000, "root"));
  free(cmd);
  finish(1);
  if (access(helper_path, F_OK) == 0)
    fatal("helper survived disconnect");
  free(helper_path);
  usleep(2200000);
  char *survivor = format("%s/disconnected-survivor", filescope);
  if (access(survivor, F_OK) == 0)
    fatal("job survived disconnect");
  free(survivor);
  mark("disconnect_cleans_job_and_helper");
  launch();
  r = call(job_req("job.status", "native-long-job-01"));
  J *saved = get(r, "result");
  if (strcmp(textval(saved, "state"), "completed") ||
      json_object_get_boolean(get(saved, "output_available")))
    fatal("saved job status");
  discard(r);
  r = call(job_req("job.status", "native-disconnect-01"));
  if (strcmp(textval(get(r, "result"), "state"), "interrupted"))
    fatal("saved interrupted job");
  discard(r);
  j = job_req("job.start", "native-long-job-01");
  str(j, "command", ":");
  str(j, "profile", "root");
  num(j, "timeout_ms", 1000);
  rejected(j);
  const char *jobs[] = {"native-long-job-01", "native-app-job-001",
                        "native-timeout-001", "native-cancel-0001",
                        "native-output-001",  "native-disconnect-01"};
  for (size_t i = 0; i < sizeof jobs / sizeof *jobs; i++)
    discard(call(job_req("job.forget", jobs[i])));
  mark("restart_saved_status_no_replay_and_forget");
  for (int mode = 0; mode <= 2; mode += 2) {
    j = req("helper.prepare");
    str(j, "path", source);
    str(j, "sha256", sha);
    r = call(j);
    helper_path = strdup(textval(get(r, "result"), "path"));
    discard(r);
    discard(start_job("native-stop-job-01", "sleep 30", 60000, "root"));
    finish(mode);
    if (access(helper_path, F_OK) == 0)
      fatal("helper survived worker stop");
    free(helper_path);
    launch();
    r = call(job_req("job.status", "native-stop-job-01"));
    if (strcmp(textval(get(r, "result"), "state"), "interrupted"))
      fatal("job survived worker stop");
    discard(r);
    discard(call(job_req("job.forget", "native-stop-job-01")));
    mark(mode == 0 ? "graceful_stop_cleans_active_job_and_helper"
                   : "signal_stop_cleans_active_job_and_helper");
  }
  finish(0);
  if (unlink(source))
    fatal("remove helper source");
  free(source);
  char *lock = format("%s/.jobs/lock", filescope),
       *dir = format("%s/.jobs", filescope);
  if (unlink(lock) || rmdir(dir))
    fatal("job storage not empty");
  free(lock);
  free(dir);
  mark("graceful_shutdown_and_owned_storage_cleanup");
  return 0;
}
