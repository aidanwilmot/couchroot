/* Native application bridge for the bundled Hub UI. Included by host.c.
 *
 * Page -> host: the trusted page sets document.title to
 *   hubbridge:1:<request-id>:discover
 *   hubbridge:1:<request-id>:launch:<app-id>
 *   hubbridge:1:<request-id>:ready     initial UI rendered (before its frame)
 *   hubbridge:1:<request-id>:painted   that rendered UI has been presented
 * Host -> page: ewk_view_script_execute calls HubNativePlatform.receive(json).
 *
 * Requests are accepted only while the view still shows the URL the host
 * loaded. There is no network listener, shell, or filesystem operation.
 * Platform calls never run in this (multi-threaded Chromium) process: a
 * posix_spawn'ed copy of this executable does the work and reports on a pipe,
 * which the EFL thread drains without blocking. The mechanisms match the
 * QN90A-verified native Hub prototype (native-hub/): app-manager
 * enumeration and /usr/bin/app_launcher with the AMD quiet-launch hint. */
#include <fcntl.h>
#include <spawn.h>
#ifdef APP_LAUNCHER
#define PLATFORM_APP_LAUNCHER APP_LAUNCHER
#endif
#include "../common/platform-core.h"
/* Bullseye's ARM fcntl default symbol is GLIBC_2.28. QN90A needs the legacy
 * interface (as in native-hub/); only integer flags are used here. */
#if defined(__linux__) && defined(__arm__) && defined(__GLIBC__)
__asm__(".symver fcntl, fcntl@GLIBC_2.4");
#endif
#include <stdbool.h>
#include <sys/wait.h>

#ifndef APP_LAUNCHER
#define APP_LAUNCHER "/usr/bin/app_launcher"
#endif
#ifndef APP_MANAGER_LIBRARY
#define APP_MANAGER_LIBRARY "libcapi-appfw-app-manager.so.0"
#endif
#ifndef SELF_EXE
#define SELF_EXE "/proc/self/exe"
#endif
#define BRIDGE_PREFIX "hubbridge:"
#define BRIDGE_HOME_APP "com.samsung.tv.csfs"
#define BRIDGE_MAX_APPS 128
#define BRIDGE_OUTPUT_MAX (64 * 1024)

extern char **environ;
FN(Bool, ewk_view_script_execute, (Obj *, const char *, void *, void *));
FN(const char *, ewk_view_url_get, (const Obj *));
FN(Bool, ewk_view_visibility_set, (Obj *, Bool));

typedef struct {
    pid_t pid; int fd; double deadline; size_t length;
    char request[33], app[257]; char output[BRIDGE_OUTPUT_MAX];
} BridgeJob;
static void launcher_app_accepted(const char *id); /* launcher.h: app-return tracking. */
static BridgeJob bridge_jobs[2]; /* [0] discovery, [1] launch: one of each at a time. */
static int bridge_enabled;

static int bridge_app_id(const char *id) {
    size_t n = strlen(id);
    if (n < 1 || n > 256) return 0;
    for (; *id; id++)
        if (!((*id >= 'a' && *id <= 'z') || (*id >= 'A' && *id <= 'Z') ||
              (*id >= '0' && *id <= '9') || strchr("_.-", *id))) return 0;
    return 1;
}
static int bridge_request_id(const char *id) {
    size_t n = strlen(id);
    if (n < 1 || n > 32) return 0;
    for (; *id; id++)
        if (!((*id >= 'a' && *id <= 'z') || (*id >= 'A' && *id <= 'Z') || (*id >= '0' && *id <= '9'))) return 0;
    return 1;
}

/* JSON string escaping for the response script. Non-ASCII UTF-8 passes
 * through except U+2028/U+2029, which older script parsers reject. */
typedef struct { char *data; size_t length, capacity; int overflow; } Text;
static void text_add(Text *t, const char *s, size_t n) {
    if (t->overflow || t->length + n + 1 > t->capacity) { t->overflow = 1; return; }
    memcpy(t->data + t->length, s, n); t->length += n; t->data[t->length] = 0;
}
static void text_put(Text *t, const char *s) { text_add(t, s, strlen(s)); }
static void text_json(Text *t, const char *s) {
    text_add(t, "\"", 1);
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        char escape[8];
        if (*p == '"' || *p == '\\') { escape[0] = '\\'; escape[1] = (char)*p; text_add(t, escape, 2); }
        else if (*p < 0x20 || *p == 0x7f) { snprintf(escape, sizeof escape, "\\u%04x", *p); text_add(t, escape, 6); }
        else if (p[0] == 0xe2 && p[1] == 0x80 && (p[2] == 0xa8 || p[2] == 0xa9)) {
            text_put(t, p[2] == 0xa8 ? "\\u2028" : "\\u2029"); p += 2;
        } else text_add(t, (const char *)p, 1);
    }
    text_add(t, "\"", 1);
}
static void bridge_reply(const char *request, const char *body_json) {
    static char script[BRIDGE_OUTPUT_MAX * 2 + 512];
    Text t = { script, 0, sizeof script, 0 };
    script[0] = 0;
    text_put(&t, "window.HubNativePlatform&&HubNativePlatform.receive({\"v\":1,\"id\":");
    text_json(&t, request);
    text_put(&t, ","); text_put(&t, body_json); text_put(&t, "});");
    if (t.overflow) { fprintf(stderr, "webview bridge-reply-overflow id=%s\n", request); return; }
    if (!view || !ewk_view_script_execute || !ewk_view_script_execute(view, script, NULL, NULL))
        fprintf(stderr, "webview bridge-reply-failed id=%s\n", request);
}
static void bridge_error(const char *request, const char *name, const char *message) {
    char body[512]; Text t = { body, 0, sizeof body, 0 };
    body[0] = 0;
    text_put(&t, "\"ok\":false,\"error\":{\"name\":"); text_json(&t, name);
    text_put(&t, ",\"message\":"); text_json(&t, message); text_put(&t, "}");
    bridge_reply(request, body);
    printf("webview bridge-result id=%s error=%s\n", request, name);
}

/* Discovery output: "A\t<id>\t<name>\t<icon>\t<package>\n" lines, then "OK\n". */
static void bridge_finish_discovery(BridgeJob *job) {
    static char body[BRIDGE_OUTPUT_MAX * 2];
    Text t = { body, 0, sizeof body, 0 };
    body[0] = 0;
    int count = 0, complete = 0;
    text_put(&t, "\"ok\":true,\"apps\":[");
    for (char *line = job->output, *next; line && *line; line = next) {
        next = strchr(line, '\n');
        if (!next) break; /* Incomplete final line: worker did not finish. */
        *next++ = 0;
        if (!strcmp(line, "OK")) { complete = 1; break; }
        char *field[5]; int fields = 0;
        for (char *f = line; fields < 5; fields++) {
            field[fields] = f;
            char *tab = strchr(f, '\t');
            if (!tab) { fields++; break; }
            *tab = 0; f = tab + 1;
        }
        if (fields != 5 || strcmp(field[0], "A") || !bridge_app_id(field[1])) continue;
        text_put(&t, count++ ? ",{\"id\":" : "{\"id\":"); text_json(&t, field[1]);
        text_put(&t, ",\"name\":"); text_json(&t, field[2]);
        text_put(&t, ",\"iconPath\":"); text_json(&t, field[3]);
        text_put(&t, ",\"packageId\":"); text_json(&t, field[4]);
        text_put(&t, ",\"show\":true}");
    }
    text_put(&t, "]");
    if (!complete || t.overflow) { bridge_error(job->request, "UnknownError", "Installed apps could not be listed."); return; }
    bridge_reply(job->request, body);
    printf("webview bridge-result id=%s apps=%d\n", job->request, count);
}
static void bridge_finish_launch(BridgeJob *job) {
    if (!strcmp(job->output, "OK\n")) {
        bridge_reply(job->request, "\"ok\":true");
        printf("webview bridge-result id=%s launch=accepted\n", job->request);
        launcher_app_accepted(job->app);
    } else bridge_error(job->request, "NotFoundError", "The TV did not accept the launch request.");
}
static void bridge_close(BridgeJob *job) {
    if (job->fd >= 0) close(job->fd);
    if (job->pid > 0) waitpid(job->pid, NULL, WNOHANG); /* Ecore may already have reaped it. */
    job->fd = -1; job->pid = 0; job->length = 0;
}
/* Called from the EFL watch timer. Reads never block. */
static void bridge_poll(void) {
    for (int kind = 0; kind < 2; kind++) {
        BridgeJob *job = &bridge_jobs[kind];
        if (job->pid <= 0) continue;
        for (;;) {
            if (job->length >= sizeof job->output - 1) { kill(job->pid, SIGKILL); job->length = 0; job->output[0] = 0; break; }
            ssize_t n = read(job->fd, job->output + job->length, sizeof job->output - 1 - job->length);
            if (n > 0) { job->length += (size_t)n; job->output[job->length] = 0; continue; }
            if (n == 0) { /* Worker closed its output: complete or failed. */
                if (kind == 0) bridge_finish_discovery(job); else bridge_finish_launch(job);
                bridge_close(job);
            } else if (errno != EAGAIN && errno != EINTR) {
                bridge_error(job->request, "UnknownError", "Platform worker failed.");
                bridge_close(job);
            }
            break;
        }
        if (job->pid > 0 && now() > job->deadline) {
            kill(job->pid, SIGKILL);
            bridge_error(job->request, "UnknownError", "The TV platform did not respond.");
            bridge_close(job);
        }
    }
}
static void bridge_start(int kind, const char *request, const char *app_id) {
    BridgeJob *job = &bridge_jobs[kind];
    if (job->pid > 0) { bridge_error(request, "UnknownError", "Another request is still running."); return; }
    int fds[2];
    if (platform_pipe(fds)) { bridge_error(request, "UnknownError", "Platform worker unavailable."); return; }
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, fds[1], 1);
    posix_spawn_file_actions_addclose(&actions, fds[0]);
    char *const discover[] = { "minimal-hub-webview", "--bridge-discover", NULL };
    char *const launch[] = { "minimal-hub-webview", "--bridge-launch", (char *)app_id, NULL };
    pid_t pid = 0;
    int result = posix_spawn(&pid, SELF_EXE, &actions, NULL, kind == 0 ? discover : launch, environ);
    posix_spawn_file_actions_destroy(&actions);
    close(fds[1]);
    if (result) { close(fds[0]); bridge_error(request, "UnknownError", "Platform worker unavailable."); return; }
    fcntl(fds[0], F_SETFL, O_NONBLOCK);
    job->pid = pid; job->fd = fds[0]; job->length = 0; job->output[0] = 0;
    job->deadline = now() + (kind == 0 ? 7 : 9); /* Inside the page's 8 s / 10 s guards. */
    snprintf(job->request, sizeof job->request, "%s", request);
    snprintf(job->app, sizeof job->app, "%s", app_id ? app_id : "");
    printf("webview bridge-request id=%s op=%s%s%s\n", request, kind == 0 ? "discover" : "launch",
           app_id ? " app=" : "", app_id ? app_id : "");
}
/* Returns 1 when the title was a bridge message (handled or rejected). */
static int bridge_message(const char *title) {
    if (strncmp(title, BRIDGE_PREFIX, strlen(BRIDGE_PREFIX))) return 0;
    if (!bridge_enabled) { fputs("webview bridge-rejected reason=disabled\n", stderr); return 1; }
    const char *current = ewk_view_url_get ? ewk_view_url_get(view) : NULL;
    /* Same document: the fragment (one-time preference import) may be removed. */
    size_t document = strcspn(url, "#");
    if (!current || strncmp(current, url, document) || (current[document] && current[document] != '#')) {
        fprintf(stderr, "webview bridge-rejected reason=origin url=%.200s\n", current ? current : "(none)");
        return 1;
    }
    char copy[320];
    if (strlen(title) >= sizeof copy) { fputs("webview bridge-rejected reason=length\n", stderr); return 1; }
    strcpy(copy, title + strlen(BRIDGE_PREFIX));
    /* Exactly version:id:op[:app]. App IDs cannot contain ':' (validated). */
    char *part[5] = { 0 }; int parts = 0;
    for (char *p = copy; parts < 5;) {
        part[parts++] = p;
        char *colon = strchr(p, ':');
        if (!colon) break;
        *colon = 0; p = colon + 1;
    }
    if (parts > 4) { fputs("webview bridge-rejected reason=format\n", stderr); return 1; }
    if (parts < 3 || strcmp(part[0], "1") || !bridge_request_id(part[1])) {
        fputs("webview bridge-rejected reason=format\n", stderr); return 1;
    }
    if (parts == 3 && !strcmp(part[2], "ready")) {
        page_ready(); bridge_reply(part[1], "\"ok\":true");
    }
    else if (parts == 3 && !strcmp(part[2], "painted")) {
        page_painted(); bridge_reply(part[1], "\"ok\":true");
    }
    else if (parts == 3 && !strcmp(part[2], "discover")) bridge_start(0, part[1], NULL);
    else if (parts == 4 && !strcmp(part[2], "launch") && bridge_app_id(part[3])) bridge_start(1, part[1], part[3]);
    else bridge_error(part[1], "InvalidValuesError", "Unsupported request.");
    return 1;
}
static void bridge_shutdown(void) {
    for (int kind = 0; kind < 2; kind++)
        if (bridge_jobs[kind].pid > 0) { kill(bridge_jobs[kind].pid, SIGKILL); bridge_close(&bridge_jobs[kind]); }
}
/* Launch acceptance is not foreground proof. The page treats becoming
 * hidden as the app having taken over, so window focus drives visibility. */
static void bridge_visibility(Bool visible) {
    /* Only meaningful for a loaded page: hub.js reads it after a launch. */
    if (bridge_enabled && view && loaded && !failed && (!defer_show || presented) && ewk_view_visibility_set) ewk_view_visibility_set(view, visible);
}

/* ---- Worker processes (fresh, single-threaded; never load EFL or EWK) ---- */
static int worker_write(const char *s) {
    size_t n = strlen(s);
    while (n) { ssize_t w = write(1, s, n); if (w < 0 && errno == EINTR) continue; if (w <= 0) return 0; s += w; n -= (size_t)w; }
    return 1;
}
/* Same consumer boundary as web/bridge.js eligible(); bridge.js re-applies it. */
static int worker_consumer(const char *id, const char *package) {
    return platform_consumer(id, package, 1);
}
static void worker_clean(char *s, size_t limit) { /* No tabs/newlines/control bytes; bounded. */
    size_t n = 0;
    for (; s[n] && n < limit; n++) if ((unsigned char)s[n] < 0x20 || s[n] == 0x7f) s[n] = ' ';
    s[n] = 0;
}
static int (*app_id_get)(void *, char **), (*app_label_get)(void *, char **), (*app_package_get)(void *, char **);
static int (*app_icon_get)(void *, char **), (*app_nodisplay_get)(void *, bool *), (*app_component_get)(void *, int *);
static int worker_count, worker_overflow;
static bool worker_app(void *app, void *unused) {
    (void)unused;
    bool hidden = true; int component = -1; char *id = NULL, *name = NULL, *package = NULL, *icon = NULL;
    /* Component 0 is a UI application (app_info_app_component_type_e). */
    if (app_nodisplay_get(app, &hidden) || hidden || app_component_get(app, &component) || component != 0) return true;
    if (app_id_get(app, &id) || !id || !bridge_app_id(id) || !strcmp(id, BRIDGE_HOME_APP) || !strcmp(id, "MiniHub001.Hub")) goto done;
    if (app_package_get(app, &package) || !worker_consumer(id, package)) goto done;
    if (app_label_get(app, &name) || !name || !*name) goto done;
    if (app_icon_get(app, &icon) || !icon || icon[0] != '/') { free(icon); icon = NULL; }
    if (worker_count == BRIDGE_MAX_APPS) { worker_overflow = 1; goto done; }
    worker_clean(name, 120); if (icon) worker_clean(icon, 512);
    char line[1024];
    int length = snprintf(line, sizeof line, "A\t%s\t%s\t%s\t%s\n", id, name, icon ? icon : "", package ? package : "");
    if (length < 0 || (size_t)length >= sizeof line) { worker_overflow = 1; goto done; }
    if (worker_write(line)) worker_count++;
done:
    free(id); free(name); free(package); free(icon);
    return true;
}
static int worker_discover(void) {
    alarm(6);
    void *library = dlopen(APP_MANAGER_LIBRARY, RTLD_NOW | RTLD_LOCAL);
    if (!library) return 10;
    int (*foreach_app)(bool (*)(void *, void *), void *);
    *(void **)(&foreach_app) = dlsym(library, "app_manager_foreach_app_info");
    *(void **)(&app_id_get) = dlsym(library, "app_info_get_app_id");
    *(void **)(&app_label_get) = dlsym(library, "app_info_get_label");
    *(void **)(&app_package_get) = dlsym(library, "app_info_get_package");
    *(void **)(&app_icon_get) = dlsym(library, "app_info_get_icon");
    *(void **)(&app_nodisplay_get) = dlsym(library, "app_info_is_nodisplay");
    *(void **)(&app_component_get) = dlsym(library, "app_info_get_app_component_type");
    if (!foreach_app || !app_id_get || !app_label_get || !app_package_get || !app_icon_get ||
        !app_nodisplay_get || !app_component_get) return 11;
    if (foreach_app(worker_app, NULL) != 0 || worker_overflow) return 12;
    return worker_write("OK\n") ? 0 : 13;
}
static int worker_launch(const char *id) {
    if (!bridge_app_id(id)) return 20;
    alarm(8);
    char uid[16]; snprintf(uid, sizeof uid, "%u", (unsigned)getuid());
    pid_t pid; int status = 0;
    int spawned = platform_spawn_app(&pid, APP_LAUNCHER, id, uid, strcmp(id, BRIDGE_HOME_APP) != 0, 1);
    if (spawned) return 21;
    while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return 22;
    if (!WIFEXITED(status) || WEXITSTATUS(status)) return 23;
    return worker_write("OK\n") ? 0 : 24;
}
