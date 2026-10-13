/* TV-local side-by-side worker measurement. SPDX-License-Identifier: 0BSD */
#include "common.h"
static pid_t child;
static Wire w;
static int sequence;
static const char *scope;
static void stop_child(void) {
  if (child > 0) {
    kill(child, SIGKILL);
    waitpid(child, NULL, 0);
    child = 0;
  }
  if (w.fd > 0) {
    close(w.fd);
    w.fd = -1;
  }
}
static J *request(J *j) {
  char *b = base64(json(j), strlen(json(j))),
       *p = format("OP\t%d\t%s", ++sequence, b);
  sendframe(&w, p);
  free(p);
  free(b);
  char *s = receive(&w), *f[4];
  if (fields(s, f, 4) != 3 || strcmp(f[0], "OPRESULT") ||
      atoi(f[1]) != sequence)
    fatal("operation response");
  size_t len;
  unsigned char *data = decode(f[2], &len);
  if (!data || strlen((char *)data) != len)
    fatal("response encoding");
  J *r = parse((char *)data);
  if (!r)
    fatal("response JSON");
  free(data);
  free(s);
  return r;
}
static J *req(const char *op) {
  J *j = obj();
  str(j, "op", op);
  return j;
}
static J *call(J *j) {
  J *r = request(j);
  json_object_put(j);
  if (!json_object_get_boolean(get(r, "ok"))) {
    fprintf(stderr, "operation failed: %s\n", json(r));
    fatal("operation failure");
  }
  return r;
}
static void rejected(J *j) {
  J *r = request(j);
  json_object_put(j);
  if (json_object_get_boolean(get(r, "ok")))
    fatal("unexpected success");
  if (!textval(r, "outcome") || strcmp(textval(r, "outcome"), "failed"))
    fatal("wrong failure outcome");
  json_object_put(r);
}
static void command(const char *cmd, int timeout, int expected, int timed) {
  char *b = base64(cmd, strlen(cmd)),
       *p = format("EXEC\t%d\t%d\t%s", ++sequence, timeout, b);
  sendframe(&w, p);
  free(p);
  free(b);
  char *s = receive(&w), *f[8];
  int n = fields(s, f, 8);
  if (n != 6 || strcmp(f[0], "RESULT") || atoi(f[1]) != sequence ||
      atoi(f[2]) != expected || atoi(f[3]) != timed)
    fatal("command result");
  free(s);
}
static void upload(const char *id, int64_t offset, const unsigned char *data,
                   int length, int good) {
  char sha[65];
  digest(data, length, sha);
  char *p = format("OPWRITE\t%d\t%s\t%" PRId64 "\t%d\t%s", ++sequence, id,
                   offset, length, sha);
  sendframe(&w, p);
  writeall(w.fd, data, length);
  free(p);
  char *s = receive(&w), *f[4];
  if (fields(s, f, 4) != 3 || strcmp(f[0], "OPRESULT") ||
      atoi(f[1]) != sequence)
    fatal("upload response");
  size_t n;
  unsigned char *raw = decode(f[2], &n);
  J *r = raw ? parse((char *)raw) : NULL;
  if (!r || json_object_get_boolean(get(r, "ok")) != good)
    fatal("upload outcome");
  if (good && number(get(r, "result"), "offset") != offset + length)
    fatal("upload offset");
  json_object_put(r);
  free(raw);
  free(s);
}
static char *begin(const char *path, int64_t size, const char *sha,
                   const char *expected) {
  J *j = req("file.begin");
  str(j, "path", path);
  num(j, "size", size);
  str(j, "sha256", sha);
  str(j, "expected_sha256", expected);
  J *r = call(j);
  const char *id = textval(get(r, "result"), "transfer_id");
  if (!id)
    fatal("transfer id");
  char *result = strdup(id);
  json_object_put(r);
  return result;
}
static void transfer_op(const char *op, const char *id, int good) {
  J *j = req(op);
  str(j, "transfer_id", id);
  if (good) {
    J *r = call(j);
    json_object_put(r);
  } else
    rejected(j);
}
static void download(const char *id, int64_t offset, int length,
                     const unsigned char *expected, int expected_length) {
  J *j = req("file.read");
  str(j, "transfer_id", id);
  num(j, "offset", offset);
  num(j, "length", length);
  char *b = base64(json(j), strlen(json(j))),
       *p = format("OP\t%d\t%s", ++sequence, b);
  sendframe(&w, p);
  free(p);
  free(b);
  json_object_put(j);
  char *s = receive(&w), *f[6];
  int64_t got_offset, got_length;
  if (fields(s, f, 6) != 5 || strcmp(f[0], "OPDATA") ||
      atoi(f[1]) != sequence || !decimal(f[2], &got_offset) ||
      got_offset != offset || !decimal(f[3], &got_length) ||
      got_length != expected_length || !hexvalid(f[4], 64))
    fatal("download header");
  unsigned char *raw = allocate(expected_length);
  exact(&w, raw, expected_length);
  char sha[65];
  digest(raw, expected_length, sha);
  if (strcmp(sha, f[4]) || memcmp(raw, expected, expected_length))
    fatal("download digest");
  free(raw);
  free(s);
}
static double worker_cpu(pid_t pid) {
  char path[64], buf[4096];
  snprintf(path, sizeof path, "/proc/%d/stat", pid);
  readtext(path, buf, sizeof buf);
  char *p = strrchr(buf, ')');
  if (!p)
    fatal("stat");
  p += 2;
  int index = 0;
  double ticks = 0;
  char *save;
  for (char *v = strtok_r(p, " ", &save); v;
       v = strtok_r(NULL, " ", &save), index++)
    if (index == 11 || index == 12)
      ticks += strtod(v, NULL);
  return ticks * 1000.0 / sysconf(_SC_CLK_TCK);
}
static J *memory(pid_t pid) {
  char path[64], linebuf[512];
  snprintf(path, sizeof path, "/proc/%d/smaps", pid);
  FILE *f = fopen(path, "r");
  if (!f)
    fatal("smaps");
  long rss = 0, pss = 0, private = 0, swap = 0, swappss = 0, n;
  while (fgets(linebuf, sizeof linebuf, f)) {
    if (sscanf(linebuf, "Rss: %ld kB", &n) == 1)
      rss += n;
    else if (sscanf(linebuf, "Pss: %ld kB", &n) == 1)
      pss += n;
    else if (sscanf(linebuf, "Private_Clean: %ld kB", &n) == 1 ||
             sscanf(linebuf, "Private_Dirty: %ld kB", &n) == 1)
    private += n;
    else if (sscanf(linebuf, "Swap: %ld kB", &n) == 1) swap += n;
    else if (sscanf(linebuf, "SwapPss: %ld kB", &n) == 1) swappss += n;
  }
  fclose(f);
  J *j = obj();
  num(j, "rss_kib", rss);
  num(j, "pss_kib", pss);
  num(j, "private_kib", private);
  num(j, "swap_kib", swap);
  num(j, "swap_pss_kib", swappss);
  return j;
}
static J *workload(void) {
  int size = 8 * CHUNK + 17;
  unsigned char *data = allocate(size);
  random_bytes(data, size);
  char sha[65];
  digest(data, size, sha);
  char *path = format("%s/bench-file", scope);
  char *id = begin(path, size, sha, "absent");
  upload(id, 1, data, CHUNK, 0);
  double cpu = worker_cpu(child), start = stamp();
  for (int offset = 0; offset < size; offset += CHUNK)
    upload(id, offset, data + offset,
           size - offset > CHUNK ? CHUNK : size - offset, 1);
  transfer_op("file.commit", id, 1);
  double up = stamp() - start, upcpu = worker_cpu(child) - cpu;
  free(id);
  J *j = req("file.open");
  str(j, "path", path);
  J *r = call(j);
  id = strdup(textval(get(r, "result"), "transfer_id"));
  if (strcmp(textval(get(r, "result"), "sha256"), sha))
    fatal("file hash");
  json_object_put(r);
  cpu = worker_cpu(child);
  start = stamp();
  for (int offset = 0; offset < size; offset += CHUNK) {
    int n = size - offset > CHUNK ? CHUNK : size - offset;
    download(id, offset, n, data + offset, n);
  }
  double down = stamp() - start, downcpu = worker_cpu(child) - cpu;
  download(id, CHUNK - 7, 17, data + CHUNK - 7, 17);
  download(id, size, 1, data, 0);
  transfer_op("file.close", id, 1);
  free(id);
  char replacement_sha[65];
  digest(data, 17, replacement_sha);
  id =
      begin(path, 17, replacement_sha,
            "0000000000000000000000000000000000000000000000000000000000000000");
  upload(id, 0, data, 17, 1);
  transfer_op("file.commit", id, 0);
  transfer_op("file.close", id, 1);
  free(id);
  id = begin(path, 17, replacement_sha, sha);
  upload(id, 0, data, 17, 1);
  upload(id, 0, data, 17, 0);
  transfer_op("file.commit", id, 1);
  free(id);
  if (unlink(path))
    fatal("file cleanup");
  free(path);
  free(data);
  J *out = obj();
  json_object_object_add(out, "upload_ms", json_object_new_double(up));
  json_object_object_add(out, "upload_cpu_ms", json_object_new_double(upcpu));
  json_object_object_add(out, "download_ms", json_object_new_double(down));
  json_object_object_add(out, "download_cpu_ms",
                         json_object_new_double(downcpu));
  return out;
}
static J *parity(int native) {
  command("printf stdout; printf stderr >&2; exit 7", 1000, 7, 0);
  command("sleep 2", 100, 124, 1);
  J *j = req("app.exec");
  str(j, "command",
      "id; cat /proc/self/attr/current; printf '\\n%s' \"$XDG_RUNTIME_DIR\"; "
      "exit 7");
  num(j, "timeout_ms", 5000);
  J *r = call(j), *result = get(r, "result");
  const char *out = textval(result, "stdout");
  if (number(result, "exit_code") != 7 || !out || !strstr(out, "uid=5001") ||
      !strstr(out, "User") || !strstr(out, "/run/user/5001"))
    fatal("app identity");
  json_object_put(r);
  j = req("app.exec");
  str(j, "command", "printf '%s' \"apostrophe's \\\"double\\\" and café\"");
  num(j, "timeout_ms", 5000);
  r = call(j);
  if (strcmp(textval(get(r, "result"), "stdout"),
             "apostrophe's \"double\" and café"))
    fatal("app quoting");
  json_object_put(r);
  const char *helper = getenv("COUCHROOT_BENCH_HELPER");
  if (helper) {
    j = req("app.exec");
    str(j, "command", helper);
    num(j, "timeout_ms", 5000);
    r = call(j);
    result = get(r, "result");
    out = textval(result, "stdout");
    if (number(result, "exit_code") || !out ||
        !strstr(out, "uid=5001 euid=5001 gid=100 smack=User"))
      fatal("borrowed helper execution");
    json_object_put(r);
  }
  J *record = obj();
  boolean(record, "root_exit_and_timeout", 1);
  boolean(record, "app_identity_environment_quotes", 1);
  boolean(record, "borrowed_unsigned_helper", helper != NULL);
  if (native) {
    j = req("job.status");
    str(j, "id", "prototype-missing-job");
    rejected(j);
    j = req("helper.release");
    str(j, "helper_id", "00000000000000000000000000000000");
    rejected(j);
    str(record, "jobs", "unsupported");
    str(record, "helper_lifecycle", "unsupported");
  } else {
    str(record, "jobs", "deployed acceptance; not timed here");
    str(record, "helper_lifecycle", "deployed acceptance; not timed here");
  }
  return record;
}
static void sample(const char *dll, const char *binary, const char *app,
                   const char *appsha, int native, int round) {
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
  struct sockaddr_in address = {.sin_family = AF_INET,
                                .sin_addr = {htonl(INADDR_LOOPBACK)}};
  if (bind(listener, (struct sockaddr *)&address, sizeof address) ||
      listen(listener, 1))
    fatal("listen");
  socklen_t length = sizeof address;
  if (getsockname(listener, (struct sockaddr *)&address, &length))
    fatal("getsockname");
  char port[16];
  snprintf(port, sizeof port, "%u", ntohs(address.sin_port));
  double start = stamp();
  child = fork();
  if (child < 0)
    fatal("fork worker");
  if (!child) {
    alarm(90);
    if (native)
      execl(binary, binary, "127.0.0.1", port, token, scope, app, appsha,
            (char *)NULL);
    else
      execl("/usr/bin/dotnet", "dotnet", dll, "127.0.0.1", port, token, scope,
            (char *)NULL);
    _exit(127);
  }
  struct pollfd ready = {listener, POLLIN, 0};
  if (poll(&ready, 1, 15000) != 1)
    fatal("worker connect timeout");
  w.fd = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
  if (w.fd < 0)
    fatal("accept");
  close(listener);
  int one = 1;
  setsockopt(w.fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
  struct timeval timeout = {30, 0};
  setsockopt(w.fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
  setsockopt(w.fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
  char nonce[65];
  hex(w.nonce, 32, nonce);
  char *hello = format("SAMSUNG-TV-ROOT/1\t%s\n", nonce);
  writeall(w.fd, hello, strlen(hello));
  free(hello);
  char *auth = receive(&w), *fields_a[10];
  if (fields(auth, fields_a, 10) != 8 || strcmp(fields_a[0], "AUTH") ||
      atoi(fields_a[1]) != child)
    fatal("AUTH identity");
  for (int i = 2; i <= 5; i++)
    if (strcmp(fields_a[i], "0"))
      fatal("AUTH not root");
  free(auth);
  J *r = call(req("status"));
  json_object_put(r);
  double startup = stamp() - start, startcpu = worker_cpu(child);
  J *report = obj();
  str(report, "kind", native ? "native" : "dotnet");
  num(report, "round", round);
  json_object_object_add(report, "startup_ms", json_object_new_double(startup));
  json_object_object_add(report, "startup_cpu_ms",
                         json_object_new_double(startcpu));
  json_object_object_add(report, "ready_memory", memory(child));
  if (round >= 0) {
    json_object_object_add(report, "parity", parity(native));
    json_object_object_add(report, "transfer", workload());
    json_object_object_add(report, "loaded_memory", memory(child));
    double idlecpu = worker_cpu(child), idle = stamp();
    usleep(1000000);
    json_object_object_add(report, "idle_cpu_ms",
                           json_object_new_double(worker_cpu(child) - idlecpu));
    json_object_object_add(report, "idle_elapsed_ms",
                           json_object_new_double(stamp() - idle));
  }
  char *bye = format("SHUTDOWN\t%d", ++sequence);
  sendframe(&w, bye);
  free(bye);
  char *response = receive(&w);
  if (strncmp(response, "BYE\t", 4))
    fatal("shutdown response");
  free(response);
  close(w.fd);
  w.fd = -1;
  int status;
  struct rusage usage;
  while (wait4(child, &status, 0, &usage) < 0)
    if (errno != EINTR)
      fatal("wait4");
  child = 0;
  if (!WIFEXITED(status) || WEXITSTATUS(status))
    fatal("worker exit");
  num(report, "peak_rss_kib", usage.ru_maxrss);
  puts(json(report));
  fflush(stdout);
  json_object_put(report);
  free(token);
}
int main(int argc, char **argv) {
  if (argc != 7) {
    fputs("usage: bench DOTNET_DLL NATIVE_WORKER EXPERIMENT_DIRECTORY "
          "APP_LAUNCHER SHA256 ROUNDS\n",
          stderr);
    return 64;
  }
  if (getuid() || geteuid())
    return 77;
  signal(SIGPIPE, SIG_IGN);
  alarm(240);
  atexit(stop_child);
  libraries();
  scope = argv[3];
  int64_t rounds;
  if (!decimal(argv[6], &rounds) || rounds < 1 || rounds > 20)
    return 64;
  for (int i = -2; i < rounds; i++) {
    int first = (i % 2) == 0;
    sample(argv[1], argv[2], argv[4], argv[5], first, i);
    sample(argv[1], argv[2], argv[4], argv[5], !first, i);
  }
  return 0;
}
