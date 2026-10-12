/* Boot launcher role: a drop-in for couchroot `native-hub` in the installed
 * QN90A hook chain. Included by host.c.
 *
 *   native-hub --native-guard --stay   boot admission, then a supervisor that
 *                                      runs and restarts the WebView Hub
 *   native-hub --source-rearm-wait     normal-init boots: bounded re-arm only
 *
 * Environment set by the hook: COUCHROOT_NATIVE_HOME=1 (Home grab),
 * COUCHROOT_NATIVE_SOURCE_REARM=1 (15 s saved-source re-arm),
 * COUCHROOT_NATIVE_STATE (native preferences, read once for import),
 * COUCHROOT_WEBVIEW_ENGINE=upgrade|default.
 *
 * Guard, re-arm and Home/return decisions are ported from couchroot
 * native-hub (0BSD, commit fdb8c06): native-guard.h, hub-platform.h and
 * hub-lifecycle.h. Platform reads run in a persistent single-threaded worker,
 * never in the Chromium process. The hook's casting monitor requires a
 * `first-render-complete` line in this process's stdout. */
#include <sys/socket.h>
#include <stdint.h>
#if !defined(O_NOFOLLOW) && !defined(__linux__)
#define O_NOFOLLOW 0 /* Desktop test builds only; POSIX.1-2008 Linux defines it. */
#endif

/* Fixed firmware paths; overridable only so desktop tests can run the logic. */
#ifndef UPTIME_PATH
#define UPTIME_PATH "/proc/uptime"
#endif
#ifndef MARKER_PATH
#define MARKER_PATH "/tmp/couchroot-early-hub-enabled"
#endif
#ifndef WM_READY_PATH
#define WM_READY_PATH "/run/.wm_ready"
#endif
#ifndef WAYLAND_SOCKET_PATH
#define WAYLAND_SOCKET_PATH "/run/user/5001/wayland-0"
#endif
#ifndef NORMAL_MODE_PATH
#define NORMAL_MODE_PATH "/tmp/init_mode_normal"
#endif
#ifndef NORMAL_BOOT_WAIT_LIMIT
#define NORMAL_BOOT_WAIT_LIMIT 120
#endif
#ifndef RESTART_DELAY
#define RESTART_DELAY 1
#endif
#define HUB_WEB_APP "MiniHub001.Hub"
#define TV_VIEWER "org.tizen.tv-viewer"
#define REARM_SOURCE "isp-service"

/* ---- Boot admission (native-guard.h) ---- */
static int native_settings_match(const char *source, const char *isp, const char *power, const char *foreground) {
    return source && isp && power && foreground && !strcmp(source, "isp-service") &&
        !strcmp(isp, HUB_WEB_APP) && !strcmp(power, "lcdon") && !strcmp(foreground, "");
}
static void ng_stamp(const char *event) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    printf("%s %.3f\n", event, t.tv_sec + t.tv_nsec / 1e9); fflush(stdout);
}
static double ng_uptime(void) {
    double value = -1; FILE *f = fopen(UPTIME_PATH, "r");
    if (f) { if (fscanf(f, "%lf", &value) != 1) value = -1; fclose(f); }
    return value;
}
static int ng_marker(void) { return access(MARKER_PATH, F_OK) == 0; }
static int ng_display(void) {
    struct stat s;
    return access(WM_READY_PATH, F_OK) == 0 && stat(WAYLAND_SOCKET_PATH, &s) == 0 && S_ISSOCK(s.st_mode);
}
/* Dynamic ABI declarations match libvconf and libsystemd's public C APIs. */
static int native_settings_read_checked(int (*match)(const char *, const char *, const char *, const char *)) {
    void *vc = dlopen("libvconf.so.0", RTLD_NOW | RTLD_LOCAL), *sd = dlopen("libsystemd.so.0", RTLD_NOW | RTLD_LOCAL);
    if (!vc || !sd) { if (vc) dlclose(vc); if (sd) dlclose(sd); return 0; }
    char *(*get_str)(const char *) = NULL;
    int (*open_system)(void **) = NULL, (*set_timeout)(void *, uint64_t) = NULL;
    int (*call)(void *, const char *, const char *, const char *, const char *, void *, void **, const char *, ...) = NULL;
    int (*read_reply)(void *, const char *, ...) = NULL;
    void *(*unref_bus)(void *) = NULL, *(*unref_message)(void *) = NULL;
#define NG_LOAD(handle, pointer, symbol) do { *(void **)(&pointer) = dlsym(handle, symbol); if (!pointer) goto missing; } while (0)
    NG_LOAD(vc, get_str, "vconf_get_str");
    NG_LOAD(sd, open_system, "sd_bus_open_system");
    NG_LOAD(sd, set_timeout, "sd_bus_set_method_call_timeout");
    NG_LOAD(sd, call, "sd_bus_call_method");
    NG_LOAD(sd, read_reply, "sd_bus_message_read");
    NG_LOAD(sd, unref_bus, "sd_bus_unref");
    NG_LOAD(sd, unref_message, "sd_bus_message_unref");
#undef NG_LOAD
    {
        char *source = get_str("db/boot/last_service"), *isp = get_str("db/was/isp_app_id");
        void *bus = NULL, *reply = NULL; const char *power = NULL;
        int rc = open_system(&bus);
        if (rc >= 0) rc = set_timeout(bus, 2000000);
        if (rc >= 0) rc = call(bus, "org.tizen.system.deviced", "/Org/Tizen/System/DeviceD/Display",
                               "org.tizen.system.deviced.display", "GetState", NULL, &reply, "");
        if (rc >= 0) rc = read_reply(reply, "s", &power);
        if (rc <= 0) power = NULL;
        char *foreground = get_str("memory/appfw/current_fullscreen_appid");
        printf("native-values source=%s isp=%s power=%s foreground=[%s]\n", source ? source : "<missing>",
               isp ? isp : "<missing>", power ? power : "<missing>", foreground ? foreground : "<missing>");
        int ok = match(source, isp, power, foreground);
        free(source); free(isp); free(foreground);
        if (reply) unref_message(reply);
        if (bus) unref_bus(bus);
        dlclose(sd); dlclose(vc); return ok;
    }
missing:
    dlclose(sd); dlclose(vc); return 0;
}
static int native_settings_read(void) { return native_settings_read_checked(native_settings_match); }
/* Remote power-button restarts can begin in normal mode with the display still
 * in standby. Do not draw over standby or the TV viewer. Wait for lcdon, ask the
 * signed Hub to retire the viewer through Samsung's app lifecycle, then admit
 * only over that Hub. A different source, ISP owner or foreground app cancels.
 * This runs before EFL/Chromium initialization, bounded by both uptime and wall
 * time; it is not a new rule for manual entry or the early background path. */
enum { NORMAL_WAIT, NORMAL_LAUNCH, NORMAL_READY, NORMAL_CANCEL };
static int normal_state;
static int normal_settings_note(const char *source, const char *isp, const char *power, const char *fg) {
    normal_state = NORMAL_WAIT;
    if ((source && strcmp(source, REARM_SOURCE)) || (isp && strcmp(isp, HUB_WEB_APP)) ||
        (fg && *fg && strcmp(fg, HUB_WEB_APP) && strcmp(fg, TV_VIEWER))) normal_state = NORMAL_CANCEL;
    else if (source && isp && power && fg && !strcmp(power, "lcdon"))
        normal_state = !strcmp(fg, HUB_WEB_APP) ? NORMAL_READY : NORMAL_LAUNCH;
    return normal_state == NORMAL_READY;
}
static int normal_launch_web(void) {
    char uid[16]; snprintf(uid, sizeof uid, "%u", (unsigned)getuid());
    char *args[] = { "app_launcher", "-s", HUB_WEB_APP, "-u", uid, "__NO_LOADING_LAUNCH", "enable", NULL };
    posix_spawn_file_actions_t actions; pid_t pid;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_addopen(&actions, 1, "/dev/null", O_WRONLY, 0);
    posix_spawn_file_actions_addopen(&actions, 2, "/dev/null", O_WRONLY, 0);
    int result = posix_spawn(&pid, APP_LAUNCHER, &actions, NULL, args, environ);
    posix_spawn_file_actions_destroy(&actions);
    if (result) return 0;
    double until = now() + 8;
    for (;;) {
        int status = 0; pid_t r = waitpid(pid, &status, WNOHANG);
        if (r == pid) return WIFEXITED(status) && !WEXITSTATUS(status);
        if ((r < 0 && errno != EINTR) || now() >= until) {
            kill(pid, SIGKILL);
            while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
            return 0;
        }
        struct timespec delay = { 0, 100000000 }; nanosleep(&delay, NULL);
    }
}
static int normal_boot_guard(void) {
    double up = ng_uptime();
    if (up < 0 || up >= 120 || !ng_marker()) return 0;
    double until = now() + (120 - up < NORMAL_BOOT_WAIT_LIMIT ? 120 - up : NORMAL_BOOT_WAIT_LIMIT);
    alarm((unsigned)(until - now()) + 2); /* Grace for the last bounded sleep. */
    ng_stamp("normal-boot-wait");
    double launch_due = 0; int submitted = 0;
    while (now() < until && ng_marker()) {
        up = ng_uptime(); if (up < 0 || up >= 120) break;
        if (ng_display()) {
            normal_state = NORMAL_WAIT;
            int ready = native_settings_read_checked(normal_settings_note);
            if (normal_state == NORMAL_CANCEL) { ng_stamp("normal-boot-cancelled"); break; }
            if (ready) {
                /* The IPC can span the deadline or a cancellation. */
                if (now() >= until || !ng_marker() || !ng_display()) break;
                alarm(0); ng_stamp("normal-boot-handoff-ready"); return 1;
            }
            if (normal_state == NORMAL_LAUNCH && !submitted && now() >= launch_due && now() + 9 < until) {
                submitted = normal_launch_web();
                ng_stamp(submitted ? "normal-boot-web-submitted" : "normal-boot-web-retry");
                launch_due = now() + 5;
            }
        }
        struct timespec delay = { 0, 200000000 }; nanosleep(&delay, NULL);
    }
    alarm(0); return 0;
}
static int native_boot_guard(void) {
    if (access(NORMAL_MODE_PATH, F_OK) == 0) return normal_boot_guard();
    double up = ng_uptime();
    if (up < 0 || up >= 46 || !ng_marker()) return 0;
    alarm((unsigned)(46 - up) + 1); /* Bounds all admission, including library IPC. */
    while (!ng_display()) {
        up = ng_uptime(); if (up < 0 || up >= 46 || !ng_marker()) return 0;
        struct timespec delay = { 0, 200000000 }; nanosleep(&delay, NULL);
    }
    ng_stamp("native-compositor-ready");
    if (!native_settings_read()) return 0;
    up = ng_uptime();
    int ok = up >= 0 && up < 46 && ng_marker() && ng_display();
    alarm(0); return ok;
}

/* ---- Saved-source re-arm and Home predicates (hub-platform.h) ---- */
static int home_settings_match(const char *source, const char *isp, const char *power, const char *foreground) {
    return source && isp && power && foreground && !strcmp(source, "isp-service") && !strcmp(isp, HUB_WEB_APP) && !strcmp(power, "lcdon");
}
/* Recheck after hidden rendering: never replace an app/source selected while loading. */
static int presentation_settings_match(const char *source, const char *isp, const char *power, const char *foreground) {
    return home_settings_match(source, isp, power, foreground) &&
        (!foreground[0] || !strcmp(foreground, HUB_WEB_APP));
}
static int home_source_rearm;
static int home_settings_note(const char *source, const char *isp, const char *power, const char *foreground) {
    home_source_rearm = source && isp && power && foreground && strcmp(source, REARM_SOURCE) &&
        !strcmp(isp, HUB_WEB_APP) && !strcmp(power, "lcdon");
    return home_settings_match(source, isp, power, foreground);
}
enum { REARM_OK = 0, REARM_NEEDED = 1, REARM_FOREGROUND = 2, REARM_NOT_ISP = 3, REARM_FAILED = 4, REARM_UNREADABLE = 5 };
typedef struct { int result, viewer; char previous[64]; } RearmReport;
static int rearm_decision(const char *isp, const char *last, const char *foreground) {
    if (!isp || !last || !foreground) return REARM_UNREADABLE;
    if (strcmp(isp, HUB_WEB_APP)) return REARM_NOT_ISP;
    return strcmp(last, REARM_SOURCE) ? REARM_NEEDED : REARM_OK;
}
static RearmReport source_rearm(char *(*get)(const char *), int (*set)(const char *, const char *)) {
    RearmReport r = { REARM_UNREADABLE, 0, "" };
    if (!get || !set) return r;
    char *isp = get("db/was/isp_app_id"), *last = get("db/boot/last_service"), *fg = get("memory/appfw/current_fullscreen_appid");
    if (last) snprintf(r.previous, sizeof r.previous, "%s", last);
    r.result = rearm_decision(isp, last, fg); r.viewer = fg && !strcmp(fg, TV_VIEWER);
    if (r.result == REARM_NEEDED) {
        char *check = NULL;
        if (set("db/boot/last_service", REARM_SOURCE) != 0 || !(check = get("db/boot/last_service")) || strcmp(check, REARM_SOURCE))
            r.result = REARM_FAILED;
        free(check);
    }
    free(isp); free(last); free(fg); return r;
}
static const char *rearm_name(int result) {
    static const char *names[] = { "ok", "rearmed", "skipped-foreground", "not-isp", "failed", "unreadable" };
    return result >= 0 && result <= 5 ? names[result] : "unknown";
}
static int vconf_api(char *(**get)(const char *), int (**set)(const char *, const char *)) {
    void *vc = dlopen("libvconf.so.0", RTLD_NOW | RTLD_LOCAL);
    if (!vc) return 0;
    *(void **)get = dlsym(vc, "vconf_get_str"); *(void **)set = dlsym(vc, "vconf_set_str");
    return *get && *set;
}
/* Normal-init boots (launcher not dispatched): every 15 s for at most 15 min. */
static int source_rearm_wait(void) {
    char *(*get)(const char *) = NULL; int (*set)(const char *, const char *) = NULL;
    if (!vconf_api(&get, &set)) return 10;
    for (int i = 0; i < 60; i++) {
        alarm(10); RearmReport r = source_rearm(get, set); alarm(0);
        if (r.result != REARM_UNREADABLE) {
            printf("source-rearm %s previous=%s\n", rearm_name(r.result), r.previous); fflush(stdout);
            return r.result == REARM_FAILED ? 11 : 0;
        }
        sleep(15);
    }
    puts("source-rearm gave-up"); return 12;
}

/* ---- Persistent platform worker (fd 3; one-line text replies) ----
 *   P -> "P <safe>"                                  hidden-window presentation
 *   S -> "S <status> <safe> <foreground>"            strict boot predicates
 *   H -> "H <status> <safe> <rearm> <foreground>"    explicit Home predicates
 *   R -> "R <result> <viewer> <previous>"            saved-source re-arm
 *   F -> "F <ok>"                                    web Hub launch (Home over Live TV) */
static int launcher_worker(void) {
    set_signal(SIGPIPE, SIG_IGN);
    char *(*get)(const char *) = NULL; int (*set)(const char *, const char *) = NULL;
    vconf_api(&get, &set);
    char command;
    while (read(3, &command, 1) == 1) {
        char line[512]; int safe;
        if (command == 'P') {
            alarm(5);
            safe = native_settings_read_checked(presentation_settings_match) && ng_display();
            snprintf(line, sizeof line, "P %d\n", safe);
        } else if (command == 'S' || command == 'H') {
            alarm(5);
            home_source_rearm = 0;
            safe = command == 'H' ? native_settings_read_checked(home_settings_note) : native_settings_read();
            char *fg = get ? get("memory/appfw/current_fullscreen_appid") : NULL;
            int status = fg && strlen(fg) <= 256 && !strpbrk(fg, " \n") ? 0 : 1;
            if (command == 'H') snprintf(line, sizeof line, "H %d %d %d %s\n", status, safe, home_source_rearm, status ? "" : fg);
            else snprintf(line, sizeof line, "S %d %d %s\n", status, safe, status ? "" : fg);
            free(fg);
        } else if (command == 'R') {
            alarm(5);
            RearmReport r = source_rearm(get, set);
            for (char *p = r.previous; *p; p++) if (*p == ' ' || *p == '\n') *p = '_';
            snprintf(line, sizeof line, "R %d %d %s\n", r.result, r.viewer, r.previous);
        } else if (command == 'F') {
            alarm(12);
            char uid[16]; snprintf(uid, sizeof uid, "%u", (unsigned)getuid());
            char *args[] = { "app_launcher", "-s", HUB_WEB_APP, "-u", uid, "__NO_LOADING_LAUNCH", "enable", NULL };
            posix_spawn_file_actions_t actions; pid_t pid; int status = 0, ok = 0;
            posix_spawn_file_actions_init(&actions);
            posix_spawn_file_actions_addopen(&actions, 1, "/dev/null", O_WRONLY, 0);
            posix_spawn_file_actions_addopen(&actions, 2, "/dev/null", O_WRONLY, 0);
            if (!posix_spawn(&pid, APP_LAUNCHER, &actions, NULL, args, environ)) {
                pid_t r;
                do { r = waitpid(pid, &status, 0); } while (r < 0 && errno == EINTR);
                ok = r == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0;
            }
            posix_spawn_file_actions_destroy(&actions);
            snprintf(line, sizeof line, "F %d\n", ok);
        } else return 2;
        size_t n = strlen(line); const char *p = line;
        while (n) { ssize_t w = write(3, p, n); if (w < 0 && errno == EINTR) continue; if (w <= 0) return 3; p += w; n -= (size_t)w; }
        alarm(0);
    }
    return 0;
}

/* ---- Supervisor: admission once, then run and restart the Hub process ---- */
static volatile sig_atomic_t supervisor_stop; static volatile pid_t supervisor_child;
static void supervisor_signal(int sig) { supervisor_stop = 1; if (supervisor_child > 0) kill(supervisor_child, sig); }
static int launcher_supervise(void) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    ng_stamp("main-entered");
    if (!native_boot_guard()) { ng_stamp("admission-denied"); return 8; }
    ng_stamp("admission-passed");
    set_signal(SIGTERM, supervisor_signal); set_signal(SIGINT, supervisor_signal);
    double window = now(); int restarts = 0;
    for (;;) {
        char *args[] = { "native-hub", "--launcher-child", NULL };
        pid_t pid;
        if (posix_spawn(&pid, SELF_EXE, NULL, NULL, args, environ)) { ng_stamp("launcher-spawn-failed"); return 1; }
        supervisor_child = pid;
        if (supervisor_stop) kill(pid, SIGTERM);
        int status = 0; pid_t r;
        do { r = waitpid(pid, &status, 0); } while (r < 0 && errno == EINTR);
        supervisor_child = 0;
        if (supervisor_stop) { ng_stamp("launcher-stopped"); return 0; }
        if (r == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0) { ng_stamp("launcher-exited"); return 0; }
        printf("launcher-child-ended %s=%d\n", WIFSIGNALED(status) ? "signal" : "exit",
               WIFSIGNALED(status) ? WTERMSIG(status) : WEXITSTATUS(status));
        if (now() - window > 600) { window = now(); restarts = 0; }
        if (++restarts > 5) { ng_stamp("launcher-restart-limit"); return 1; }
        sleep(RESTART_DELAY);
        if (supervisor_stop) return 0;
        ng_stamp("launcher-restart");
    }
}

/* ---- Hub-process side: Home grab, fallback, re-arm and app return ---- */
FN(Bool, evas_object_key_grab, (Obj *, const char *, uint64_t, uint64_t, Bool));
FN(void, evas_object_event_callback_add, (Obj *, int, void (*)(void *, Obj *, Obj *, void *), const void *));
FN(void, ecore_evas_raise, (Obj *));
FN(void, ecore_evas_activate, (Obj *));
typedef struct { char *keyname; } KeyPrefix; /* Only the documented first field is read. */
#define EVAS_KEY_DOWN 10 /* Evas 1.25 legacy Evas_Callback_Type, as verified by native-hub. */
#define EVAS_KEY_UP 11

static int launcher_mode, launcher_home, launcher_rearm, launcher_grabbed;
static pid_t lw_pid = -1; static int lw_fd = -1; static char lw_pending;
static double lw_deadline, lw_due, rearm_due, snapshot_due;
static char lw_line[640]; static size_t lw_used;
static int home_requested, home_checking; static double home_pressed = -1, home_until;
/* Return from a launched app needs an observed foreground, then two safe empty snapshots. */
static struct { int away, empty, waiting; double deadline; } lifecycle;
enum { FALLBACK_IDLE, FALLBACK_LAUNCHING, FALLBACK_REARMING, FALLBACK_RESUMING };
static struct { int state; double until; } fallback;
static int fallback_sent; /* The single 'F' request of the current attempt has been sent. */

static void launcher_show(const char *event) {
    lifecycle.away = lifecycle.empty = lifecycle.waiting = 0;
    ecore_evas_show(window); ecore_evas_raise(window); ecore_evas_activate(window);
    if (view && loaded && !failed) view_focus(1);
    bridge_visibility(1);
    ng_stamp(event);
}
static void launcher_app_accepted(const char *id) {
    if (!launcher_mode || !strcmp(id, BRIDGE_HOME_APP)) return;
    lifecycle.waiting = 1; lifecycle.away = lifecycle.empty = 0; lifecycle.deadline = now() + 10; snapshot_due = now();
}
static void launcher_focus_in(void) {
    if (launcher_mode && (lifecycle.away || lifecycle.waiting)) {
        lifecycle.away = lifecycle.empty = lifecycle.waiting = 0; ng_stamp("native-return-focused");
    }
}
static void fallback_end(const char *event) {
    if (fallback.state == FALLBACK_RESUMING) { home_requested = 0; home_until = 0; }
    fallback.state = FALLBACK_IDLE; ng_stamp(event);
}
static void home_grab_start(void) {
    if (!launcher_home || launcher_grabbed) return;
    Obj *(*get_window)(Obj *) = NULL; Bool (*grab)(Obj *, const char *, int, int, int, int) = NULL;
    *(void **)(&get_window) = dlsym(elm_library, "ecore_evas_wayland2_window_get");
    *(void **)(&grab) = dlsym(elm_library, "ecore_wl2_window_keygrab_set");
    Obj *win = get_window ? get_window(window) : NULL;
    /* QN90A 1.25.1: mode 3 is overridable-exclusive; it ends with this connection. */
    launcher_grabbed = win && grab && grab(win, "XF86Home", 0, 0, 0, 3);
    ng_stamp(launcher_grabbed ? "native-home-grab-ready" : "native-home-grab-unavailable");
}
static void home_key(void *data, Obj *canvas_unused, Obj *obj, void *info) {
    (void)canvas_unused; (void)obj;
    KeyPrefix *e = info;
    if (!e || !e->keyname || strcmp(e->keyname, "XF86Home") || !launcher_grabbed) return;
    double t = now();
    if (data == NULL) { if (home_pressed < 0) home_pressed = t; return; } /* Key down. */
    if (home_pressed < 0) return;
    double held = t - home_pressed; home_pressed = -1;
    if (held < 0 || held > 1.5 || home_requested || home_checking) return;
    if (fallback.state != FALLBACK_IDLE) { ng_stamp("native-home-busy"); return; }
    home_requested = 1; home_until = t + 3; ng_stamp("native-home-request");
}
static void lw_close(void) {
    if (fallback.state == FALLBACK_RESUMING) fallback_end("native-home-resume-cancelled");
    /* A lost launch reply is never retried: the request may already have run. */
    if (fallback.state == FALLBACK_LAUNCHING && lw_pending == 'F') fallback_end("native-home-fallback-failed");
    if (lw_fd >= 0) close(lw_fd);
    if (lw_pid > 0) { kill(lw_pid, SIGKILL); waitpid(lw_pid, NULL, WNOHANG); }
    lw_fd = -1; lw_pid = -1; lw_pending = 0; lw_used = 0; home_checking = 0; home_requested = 0; lifecycle.empty = 0;
}
static int lw_start(void) {
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, pair)) return 0;
    if (pair[1] == 3) { int moved = dup(pair[1]); close(pair[1]); if (moved < 0) { close(pair[0]); return 0; } pair[1] = moved; }
    fcntl(pair[0], F_SETFD, FD_CLOEXEC); fcntl(pair[1], F_SETFD, FD_CLOEXEC);
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, pair[1], 3); /* dup2 clears close-on-exec on fd 3. */
    posix_spawn_file_actions_addopen(&actions, 1, "/dev/null", O_WRONLY, 0);
    char *args[] = { "native-hub", "--launcher-worker", NULL };
    int result = posix_spawn(&lw_pid, SELF_EXE, &actions, NULL, args, environ);
    posix_spawn_file_actions_destroy(&actions);
    close(pair[1]);
    if (result) { close(pair[0]); lw_pid = -1; return 0; }
    lw_fd = pair[0]; fcntl(lw_fd, F_SETFL, O_NONBLOCK); return 1;
}
static void lw_reply(char *line) {
    double t = now();
    char kind = line[0];
    if (kind == 'P') { presentation_result(!strcmp(line, "P 1")); return; }
    if (kind == 'H' || kind == 'S') {
        int status = 1, safe = 0, rearm = 0, consumed = 0;
        if (kind == 'H') sscanf(line, "H %d %d %d %n", &status, &safe, &rearm, &consumed);
        else sscanf(line, "S %d %d %n", &status, &safe, &consumed);
        const char *fg = consumed ? line + consumed : "";
        int valid = consumed && !status, viewer = valid && !strcmp(fg, TV_VIEWER);
        if (kind == 'H') {
            home_checking = 0;
            int resuming = fallback.state == FALLBACK_RESUMING;
            if (!valid || t > home_until) { ng_stamp("native-home-denied"); if (resuming) fallback_end("native-home-resume-cancelled"); return; }
            if (resuming) {
                /* Finish only over the web Hub this attempt opened, or nothing. */
                if (!safe || (fg[0] && strcmp(fg, HUB_WEB_APP)) || !ng_display()) { fallback_end("native-home-resume-cancelled"); return; }
                fallback.state = FALLBACK_IDLE;
            } else if (fallback.state != FALLBACK_IDLE) { ng_stamp("native-home-busy"); return; }
            else if (launcher_rearm && ((!safe && rearm) || (safe && viewer)) && ng_display()) {
                /* Live TV in front or a non-ISP saved source: leave through the web Hub,
                 * re-arm, then finish this press if nothing else took over. */
                fallback.state = FALLBACK_LAUNCHING; fallback_sent = 0; fallback.until = t + 20; ng_stamp("native-home-source-fallback");
                return;
            }
            if (!safe || !ng_display()) { ng_stamp("native-home-denied"); return; }
            launcher_show("native-home-activate");
            return;
        }
        /* Window focus can return before Samsung clears its app key: focus-in
         * acknowledges a return, it never raises the window by itself. */
        if (!valid || focused) { lifecycle.empty = 0; return; }
        if (fg[0]) { if (!lifecycle.away) ng_stamp("app-foreground-observed"); lifecycle.away = 1; lifecycle.empty = 0; lifecycle.waiting = 0; return; }
        if (!safe) { lifecycle.empty = 0; return; }
        if (lifecycle.away && ++lifecycle.empty >= 2) launcher_show("native-return-safe");
        return;
    }
    if (kind == 'R') {
        int result = REARM_UNREADABLE, viewer = 0; char previous[64] = "";
        sscanf(line, "R %d %d %63s", &result, &viewer, previous);
        rearm_due = t + 15;
        if (result == REARM_NEEDED || result == REARM_FAILED) printf("source-rearm %s previous=%s\n", rearm_name(result), previous);
        if (fallback.state == FALLBACK_REARMING) {
            if (t >= fallback.until) fallback_end("native-home-resume-expired");
            else if ((result == REARM_OK || result == REARM_NEEDED) && !viewer) {
                fallback.state = FALLBACK_RESUMING; home_requested = 1; home_until = t + 3; ng_stamp("native-home-resume");
            } else rearm_due = t + 1;
        }
        return;
    }
    if (kind == 'F' && fallback.state == FALLBACK_LAUNCHING) {
        if (!strcmp(line, "F 1")) { fallback.state = FALLBACK_REARMING; rearm_due = t; ng_stamp("native-home-fallback-launched"); }
        else fallback_end("native-home-fallback-failed");
    }
}
/* Called from the EFL watch timer; never blocks. */
static void launcher_poll(void) {
    if (!launcher_mode || failed || stopping || (!first_frame && !presentation_pending)) return;
    double t = now();
    if (first_frame) home_grab_start();
    if (fallback.state != FALLBACK_IDLE && t >= fallback.until) fallback_end("native-home-resume-expired");
    if (lifecycle.waiting && t >= lifecycle.deadline) { lifecycle.waiting = 0; ng_stamp("app-handoff-timeout"); }
    if (lw_fd >= 0 && lw_pending) {
        ssize_t n = read(lw_fd, lw_line + lw_used, sizeof lw_line - 1 - lw_used);
        if (n > 0) lw_used += (size_t)n;
        else if (n == 0 || (errno != EAGAIN && errno != EINTR)) { lw_close(); lw_due = t + 5; ng_stamp("platform-worker-disconnected"); return; }
        lw_line[lw_used] = 0;
        char *end = strchr(lw_line, '\n');
        if (end) {
            *end = 0;
            if (lw_line[0] != lw_pending) { lw_close(); lw_due = t + 5; return; }
            lw_pending = 0; lw_used = 0; lw_reply(lw_line);
        } else if (lw_used >= sizeof lw_line - 1 || t >= lw_deadline) {
            lw_close(); lw_due = t + 5; ng_stamp("platform-worker-timeout"); return;
        }
    }
    if (lw_pending || t < lw_due) return;
    char kind = 0;
    if (presentation_pending) kind = 'P';
    else if (home_requested) { kind = 'H'; home_requested = 0; home_checking = 1; }
    else if (fallback.state == FALLBACK_LAUNCHING && !fallback_sent) { kind = 'F'; fallback_sent = 1; }
    else if ((launcher_rearm || fallback.state == FALLBACK_REARMING) && t >= rearm_due) kind = 'R';
    else if ((lifecycle.waiting || lifecycle.away) && t >= snapshot_due) { kind = 'S'; snapshot_due = t + 1; }
    if (!kind) return;
    if (lw_fd < 0 && !lw_start()) { lw_due = t + 5; if (kind == 'H') home_checking = 0; return; }
    if (send(lw_fd, &kind, 1, MSG_NOSIGNAL) != 1) { lw_close(); lw_due = t + 5; return; }
    lw_pending = kind; lw_used = 0; lw_deadline = t + (kind == 'F' ? 13 : 6);
}
static int launcher_input(Obj *grab_target) {
    if (!launcher_mode) return 1;
    *(void **)(&evas_object_key_grab) = dlsym(elm_library, "evas_object_key_grab");
    *(void **)(&evas_object_event_callback_add) = dlsym(elm_library, "evas_object_event_callback_add");
    *(void **)(&ecore_evas_raise) = dlsym(elm_library, "ecore_evas_raise");
    *(void **)(&ecore_evas_activate) = dlsym(elm_library, "ecore_evas_activate");
    if (!evas_object_key_grab || !evas_object_event_callback_add || !ecore_evas_raise || !ecore_evas_activate) return 0;
    if (launcher_home) {
        /* Evas delivers grabbed keys to the grabbing object even while Chromium's
         * internal object holds canvas focus. data NULL = down, non-NULL = up. */
        printf("local-key-grab XF86Home %d\n", evas_object_key_grab(grab_target, "XF86Home", 0, 0, 0));
        evas_object_event_callback_add(grab_target, EVAS_KEY_DOWN, home_key, NULL);
        evas_object_event_callback_add(grab_target, EVAS_KEY_UP, home_key, (void *)1);
    }
    rearm_due = now() + 2;
    return 1;
}
static void launcher_shutdown(void) { if (launcher_mode) lw_close(); }
/* Page failures in the boot role end the process so the supervisor restarts it. */
static double failed_at;

/* ---- One-time preference import: native file -> page fragment ----
 * The page applies it only when it has no saved shortcuts (native-shim.js). */
static char *launcher_import_fragment(void) {
    const char *path = getenv("COUCHROOT_NATIVE_STATE");
    if (!path || !*path) return NULL;
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return NULL;
    static char raw[50001]; struct stat st; ssize_t n = -1;
    if (!fstat(fd, &st) && S_ISREG(st.st_mode) && st.st_size < (off_t)sizeof raw) n = read(fd, raw, sizeof raw - 1);
    close(fd);
    if (n <= 0) { puts("preferences-import skipped=unreadable"); return NULL; }
    raw[n] = 0;
    int compact, clock, first, selected, used = 0;
    if (sscanf(raw, "COUCHROOT1 %d %d %d %d%n", &compact, &clock, &first, &selected, &used) != 4 || raw[used] != '\n' ||
        compact < 0 || compact > 1 || clock < 0 || clock > 2 || first < 0 || first > 1 || selected < 0) {
        puts("preferences-import skipped=format"); return NULL;
    }
    static char json[BRIDGE_OUTPUT_MAX];
    Text t = { json, 0, sizeof json, 0 }; json[0] = 0;
    char selection[257] = "";
    int count = 0;
    text_put(&t, "{\"shortcuts\":{\"version\":1,\"apps\":[");
    for (char *line = raw + used + 1, *next; *line; line = next) {
        next = strchr(line, '\n');
        if (!next) { puts("preferences-import skipped=format"); return NULL; }
        *next++ = 0;
        char *tab = strchr(line, '\t');
        if (!tab) { puts("preferences-import skipped=format"); return NULL; }
        *tab = 0;
        const char *name = tab + 1;
        size_t length = strlen(name);
        int clean = length && length <= 120;
        for (const char *p = name; *p; p++) if ((unsigned char)*p < 0x20 || *p == 0x7f) clean = 0;
        if (!bridge_app_id(line) || !clean || count >= 128) { puts("preferences-import skipped=entry"); return NULL; }
        if (count == selected) snprintf(selection, sizeof selection, "%s", line);
        text_put(&t, count++ ? ",{\"id\":" : "{\"id\":"); text_json(&t, line);
        text_put(&t, ",\"name\":"); text_json(&t, name); text_put(&t, "}");
    }
    text_put(&t, "]},\"layout\":"); text_json(&t, compact ? "compact" : "comfortable");
    text_put(&t, ",\"clock\":"); text_json(&t, clock == 2 ? "24h" : clock == 1 ? "12h" : "off");
    text_put(&t, ",\"start\":"); text_json(&t, first ? "first" : "last");
    if (selection[0]) { text_put(&t, ",\"selection\":"); text_json(&t, selection); }
    text_put(&t, "}");
    if (t.overflow) { puts("preferences-import skipped=size"); return NULL; }
    /* Percent-encode for the URL fragment. */
    static char fragment[sizeof json * 3 + 16];
    char *out = fragment + sprintf(fragment, "#import=");
    for (const unsigned char *p = (const unsigned char *)json; *p; p++) {
        if ((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') || strchr("-._~", *p)) *out++ = (char)*p;
        else out += sprintf(out, "%%%02X", *p);
    }
    *out = 0;
    printf("preferences-import offered apps=%d\n", count);
    return fragment;
}
