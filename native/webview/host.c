/* Standalone EFL/EWK host. Native app bridge and optional boot-launcher role; no provisioning.
 * Legacy EFL ABI matches the existing native launcher. EWK declarations:
 * https://ewebkit.github.io/ewebkit-doc/ewebkit2/html/d6/daf/ewk__view_8h.html
 * Firmware compatibility must still be verified on the target TV.
 *
 * ewk_set_version_policy is not publicly documented. Its int(int) shape and
 * flag semantics come from disassembly of QN90A T-NKM2AKUC-2301.1
 * /usr/lib/libchromium-ewk.so (sha256 8fb23fa7...a0ed, see README). The
 * wrapper silently falls back to the default engine when the upgrade library
 * is absent, so the loaded engine is always checked in /proc/self/maps.
 *
 * Chromium-EFL is an Elementary client. On QN90A, ewk_view_add without
 * elm_init crashed in elm_config_longpress_timeout_get (NULL config), and with
 * a bare Ecore_Evas parent Chromium 120 received no keys. A normal elm_win
 * rendered but was never mapped by the compositor. The host therefore keeps
 * its plain wayland_egl window and wraps it with elm_win_fake_add. */
#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

typedef void Obj;
typedef unsigned char Bool;
#define FN(ret, name, args) static ret (*name) args
FN(int, elm_init, (int, char **));
FN(int, elm_shutdown, (void));
FN(Obj *, elm_win_fake_add, (Obj *));
FN(void, elm_win_resize_object_add, (Obj *, Obj *));
FN(void, elm_object_focus_set, (Obj *, Bool));
FN(Obj *, ecore_evas_new, (const char *, int, int, int, int, const char *));
FN(Obj *, ecore_evas_get, (Obj *));
FN(void, ecore_evas_show, (Obj *));
FN(void, ecore_evas_free, (Obj *));
FN(void, ecore_evas_title_set, (Obj *, const char *));
FN(void, ecore_evas_callback_post_render_set, (Obj *, void (*)(Obj *)));
FN(Bool, ecore_evas_focus_get, (const Obj *));
FN(void, ecore_main_loop_begin, (void));
FN(void, ecore_main_loop_quit, (void));
FN(Obj *, ecore_timer_add, (double, Bool (*)(void *), const void *));
FN(void *, ecore_timer_del, (Obj *));
FN(Obj *, evas_object_rectangle_add, (Obj *));
FN(Obj *, evas_object_text_add, (Obj *));
FN(void, evas_object_color_set, (Obj *, int, int, int, int));
FN(void, evas_object_move, (Obj *, int, int));
FN(void, evas_object_resize, (Obj *, int, int));
FN(void, evas_object_show, (Obj *));
FN(void, evas_object_hide, (Obj *));
FN(void, evas_object_del, (Obj *));
FN(void, evas_object_focus_set, (Obj *, Bool));
FN(Obj *, evas_focus_get, (const Obj *));
FN(const char *, evas_object_type_get, (const Obj *));
FN(void, evas_object_text_font_set, (Obj *, const char *, int));
FN(void, evas_object_text_text_set, (Obj *, const char *));
FN(void, evas_object_smart_callback_add, (Obj *, const char *, void (*)(void *, Obj *, void *), const void *));
FN(int, ewk_init, (void));
FN(int, ewk_shutdown, (void));
FN(Obj *, ewk_view_add, (Obj *));
FN(Bool, ewk_view_url_set, (Obj *, const char *));
FN(int, ewk_set_version_policy, (int));           /* Optional; upgrade only. */
FN(const char *, ewk_view_title_get, (const Obj *)); /* Optional diagnostics. */
FN(Bool, ewk_view_focus_set, (const Obj *, Bool)); /* Optional; Tizen ewk_view.h. */
FN(Bool, ewk_view_focus_get, (const Obj *));

#define DEFAULT_ENGINE "/usr/share/chromium-efl/lib/libchromium-impl.so"
#define UPGRADE_ENGINE "/usr/share/chromium-efl/upgrade/lib/libchromium-impl.so"
#ifndef MAPS_PATH
#define MAPS_PATH "/proc/self/maps"
#endif
enum { ENGINE_DEFAULT, ENGINE_UPGRADE };
static int engine_request = ENGINE_DEFAULT;

static Obj *window, *elm_window, *canvas, *view, *background, *label, *defer_timer, *watch_timer;
static void *elm_library, *ewk_library;
static int ewk_started, failed, loaded, first_frame, focused;
static int lifetime = 60;
static double start, load_start;
static char *url;
static volatile sig_atomic_t stopping, stop_signals;

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + t.tv_nsec / 1e9;
}
static void stamp(const char *event) {
    printf("webview event=%s elapsed_ms=%.3f\n", event, (now() - start) * 1000);
}
/* Chromium 120 routes keys through Elementary's focus manager; Chromium 76
 * accepted plain Evas focus. Set both, as the firmware's reference WebView
 * app does. */
#include "bridge.h"
static void view_focus(Bool on) {
    /* Evas first: for an Elementary-based view the widget then moves canvas
     * focus to the internal object that actually receives keys. */
    evas_object_focus_set(view, on);
    elm_object_focus_set(view, on);
    /* Chromium's own page focus. Evas and Elementary focus alone left the
     * Chromium 120 page unfocused (no focus ring, keys dropped) on QN90A. */
    if (ewk_view_focus_set) ewk_view_focus_set(view, on);
    Obj *holder = evas_focus_get(canvas);
    printf("webview view-focus=%d canvas-focus=%s ewk-focus=%d\n", on,
           !holder ? "none" : holder == view ? "view" : evas_object_type_get(holder),
           ewk_view_focus_get ? (int)ewk_view_focus_get(view) : -1);
}
static void failure(const char *reason) {
    if (failed) return;
    failed = 1;
    fprintf(stderr, "webview failure=%s\n", reason);
    if (view) { view_focus(0); evas_object_hide(view); }
    evas_object_text_text_set(label, "WebView unavailable. Close this test window to return.");
    evas_object_show(label);
    stamp("fallback");
}
#include "launcher.h"
/* Window events come from the Elementary wrapper, which keeps its own
 * Ecore_Evas focus, resize and delete callbacks installed. */
static void close_window(void *data, Obj *obj, void *info) {
    (void)data; (void)obj; (void)info; stopping = 1; ecore_main_loop_quit();
}
static void focus_in(void *data, Obj *obj, void *info) {
    (void)data; (void)obj; (void)info; focused = 1;
    puts("webview window-focus=in");
    if (view && loaded && !failed) view_focus(1);
    bridge_visibility(1);
    launcher_focus_in();
}
static void focus_out(void *data, Obj *obj, void *info) {
    (void)data; (void)obj; (void)info; focused = 0;
    puts("webview window-focus=out");
    if (view) view_focus(0);
    bridge_visibility(0);
}
static void load_finished(void *data, Obj *obj, void *info) {
    (void)data; (void)obj; (void)info;
    if (failed || loaded) return;
    loaded = 1;
    evas_object_hide(label);
    if (!focused && ecore_evas_focus_get(window)) focused = 1; /* Focus arrived before the signal hookup. */
    view_focus((Bool)focused);
    stamp("load-finished"); /* Not a paint or interaction-ready measurement. */
}
static void load_error(void *data, Obj *obj, void *info) {
    (void)data; (void)obj; (void)info; failure("load-error");
}
static void crashed(void *data, Obj *obj, void *info) {
    (void)data; (void)obj; (void)info; failure("webprocess-crashed");
}
/* Page diagnostics reach the log through the document title only: no script
 * bridge is exposed. Output is truncated and limited to printable ASCII. */
static void title_changed(void *data, Obj *obj, void *info) {
    (void)data; (void)info;
    const char *title = ewk_view_title_get ? ewk_view_title_get(obj) : NULL;
    if (title && bridge_message(title)) return;
    char clean[241]; size_t n = 0;
    for (; title && title[n] && n < sizeof clean - 1; n++)
        clean[n] = (title[n] >= 0x20 && title[n] < 0x7f) ? title[n] : '?';
    clean[n] = 0;
    printf("webview page-title=%s\n", clean);
}
/* Which implementation library is mapped. Unknown means neither path was
 * found, for example before the wrapper's lazy loader has run. */
static const char *observed_engine(void) {
    FILE *maps = fopen(MAPS_PATH, "r");
    char line[512]; int found_default = 0, found_upgrade = 0;
    if (!maps) return "unreadable";
    while (fgets(line, sizeof line, maps)) {
        if (strstr(line, UPGRADE_ENGINE)) found_upgrade = 1;
        else if (strstr(line, DEFAULT_ENGINE)) found_default = 1;
    }
    fclose(maps);
    if (found_upgrade && found_default) return "both";
    return found_upgrade ? "upgrade" : found_default ? "default" : "unknown";
}

/* Resolve only documented entry points. Missing APIs fail closed to the shell.
 * Ecore/Evas symbols resolve through Elementary's dependencies. */
#define RESOLVE(handle, name) do { \
    *(void **)(&name) = dlsym(handle, #name); \
    if (!name) { fprintf(stderr, "Missing API: %s\n", #name); return 0; } \
} while (0)
static int efl_api(void) {
    elm_library = dlopen("libelementary.so.1", RTLD_NOW | RTLD_GLOBAL);
    if (!elm_library) { fprintf(stderr, "%s\n", dlerror()); return 0; }
#define E(name) RESOLVE(elm_library, name)
    E(elm_init); E(elm_shutdown); E(elm_win_fake_add); E(elm_win_resize_object_add);
    E(elm_object_focus_set);
    E(ecore_evas_new); E(ecore_evas_get); E(ecore_evas_show); E(ecore_evas_free);
    E(ecore_evas_title_set); E(ecore_evas_callback_post_render_set); E(ecore_evas_focus_get);
    E(ecore_main_loop_begin); E(ecore_main_loop_quit); E(ecore_timer_add); E(ecore_timer_del);
    E(evas_object_rectangle_add); E(evas_object_text_add); E(evas_object_color_set);
    E(evas_object_move); E(evas_object_resize); E(evas_object_show); E(evas_object_hide);
    E(evas_object_del); E(evas_object_focus_set); E(evas_focus_get); E(evas_object_type_get);
    E(evas_object_text_font_set);
    E(evas_object_text_text_set); E(evas_object_smart_callback_add);
#undef E
    return 1;
}
static int ewk_api(void) {
    ewk_library = dlopen("libchromium-ewk.so", RTLD_NOW | RTLD_GLOBAL);
    if (!ewk_library) { fprintf(stderr, "%s\n", dlerror()); return 0; }
    RESOLVE(ewk_library, ewk_init); RESOLVE(ewk_library, ewk_shutdown);
    RESOLVE(ewk_library, ewk_view_add); RESOLVE(ewk_library, ewk_view_url_set);
    *(void **)(&ewk_set_version_policy) = dlsym(ewk_library, "ewk_set_version_policy");
    *(void **)(&ewk_view_title_get) = dlsym(ewk_library, "ewk_view_title_get");
    *(void **)(&ewk_view_focus_set) = dlsym(ewk_library, "ewk_view_focus_set");
    *(void **)(&ewk_view_focus_get) = dlsym(ewk_library, "ewk_view_focus_get");
    *(void **)(&ewk_view_script_execute) = dlsym(ewk_library, "ewk_view_script_execute");
    *(void **)(&ewk_view_url_get) = dlsym(ewk_library, "ewk_view_url_get");
    *(void **)(&ewk_view_visibility_set) = dlsym(ewk_library, "ewk_view_visibility_set");
    if (bridge_enabled && (!ewk_view_script_execute || !ewk_view_url_get || !ewk_view_title_get)) {
        fputs("webview bridge-unavailable\n", stderr); bridge_enabled = 0;
    }
    return 1;
}
static Bool create_view(void *unused) {
    (void)unused; defer_timer = NULL;
    if (failed || stopping) return 0;
    stamp("ewk-init-start");
    if (!ewk_api()) { failure("ewk-api-unavailable"); return 0; }
    if (engine_request == ENGINE_UPGRADE) {
        /* Must precede every other EWK call: the wrapper selects and caches
         * the implementation library on its first lazy resolution. */
        if (!ewk_set_version_policy) { failure("engine-upgrade-api-unavailable"); return 0; }
        int accepted = ewk_set_version_policy(1);
        printf("webview engine-policy requested=1 returned=%d\n", accepted);
    }
    if (ewk_init() <= 0) { failure("ewk-init"); return 0; }
    ewk_started = 1;
    const char *engine = observed_engine();
    printf("webview engine requested=%s observed=%s\n",
           engine_request == ENGINE_UPGRADE ? "upgrade" : "default", engine);
    /* Never present the default engine as an upgrade. */
    if (engine_request == ENGINE_UPGRADE && strcmp(engine, "upgrade")) {
        failure("engine-upgrade-not-loaded"); return 0;
    }
    if (stopping) return 0; /* Stop requested during the blocking init call. */
    view = ewk_view_add(canvas);
    if (!view) { failure("view-create"); return 0; }
    if (stopping) return 0;
    stamp("view-created");
    evas_object_smart_callback_add(view, "load,finished", load_finished, NULL);
    evas_object_smart_callback_add(view, "load,error", load_error, NULL);
    evas_object_smart_callback_add(view, "webprocess,crashed", crashed, NULL);
    if (ewk_view_title_get) evas_object_smart_callback_add(view, "title,changed", title_changed, NULL);
    elm_win_resize_object_add(elm_window, view); /* Elementary parent; follows window size. */
    evas_object_show(view);
    load_start = now();
    stamp("navigation-start");
    if (!ewk_view_url_set(view, url)) failure("navigation-rejected");
    return 0;
}
static void rendered(Obj *win) {
    if (first_frame) return;
    first_frame = 1;
    stamp("native-first-render");
    if (launcher_mode) ng_stamp("first-render-complete"); /* The hook's casting monitor waits for it. */
    ecore_evas_callback_post_render_set(win, NULL);
    /* Next event-loop turn; EWK stays on the EFL thread. This does not make
     * synchronous EWK initialization nonblocking. */
    defer_timer = ecore_timer_add(0, create_view, NULL);
    if (!defer_timer) failure("defer-timer");
}
static Bool watch(void *unused) {
    (void)unused;
    if (stopping || (lifetime && now() - start >= lifetime)) { ecore_main_loop_quit(); return 1; }
    if (launcher_mode && failed) {
        if (!failed_at) failed_at = now();
        else if (now() - failed_at > 3) { ecore_main_loop_quit(); return 1; } /* Supervisor restarts. */
    }
    bridge_poll();
    launcher_poll();
    if (!first_frame && now() - start > 10) failure("native-render-timeout");
    if (view && !loaded && now() - load_start > 20) failure("page-load-timeout");
    return 1;
}
/* The first signal is observed by the watch timer. A second one means the
 * process is stuck in a blocking vendor call: leave immediately. */
static double first_signal;
static void stop_signal(int sig) {
    (void)sig;
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); /* Async-signal-safe. */
    double at = (double)t.tv_sec + t.tv_nsec / 1e9;
    stopping = 1;
    /* systemd and the supervisor may both deliver the stop request; only a
     * repeat after two seconds means a blocking vendor call is stuck. */
    if (++stop_signals == 1) first_signal = at;
    else if (at - first_signal > 2) _exit(7);
}

/* Only a canonical existing local file is accepted. Percent-encode path bytes
 * so #, ?, percent signs, spaces and non-ASCII names cannot alter the URL. */
static char *file_url(const char *input, const char *query) {
    char *path = realpath(input, NULL);
    struct stat st;
    if (!path || stat(path, &st) || !S_ISREG(st.st_mode) || access(path, R_OK)) {
        free(path); return NULL;
    }
    size_t n = strlen(path);
    char *result = malloc(n * 3 + 8 + strlen(query));
    if (!result) { free(path); return NULL; }
    memcpy(result, "file://", 7);
    char *out = result + 7;
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)path[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || strchr("/-._~", c)) *out++ = (char)c;
        else { snprintf(out, 4, "%%%02X", c); out += 3; }
    }
    strcpy(out, query); /* Fixed, host-chosen query only. */
    free(path); return result;
}
/* Boot role: the Hub bundle beside this executable, the bridge, no lifetime
 * limit, Home/re-arm from the hook environment, and a one-time import. */
static int launcher_child_setup(void) {
    char *self = realpath(SELF_EXE, NULL);
    char *slash = self ? strrchr(self, '/') : NULL;
    if (!slash) { free(self); return 0; }
    *slash = 0;
    char page[4096];
    if (snprintf(page, sizeof page, "%s/hub/index.html", self) >= (int)sizeof page) { free(self); return 0; }
    free(self);
    const char *engine = getenv("COUCHROOT_WEBVIEW_ENGINE");
    engine_request = engine && !strcmp(engine, "default") ? ENGINE_DEFAULT : ENGINE_UPGRADE;
    const char *home = getenv("COUCHROOT_NATIVE_HOME"), *rearm = getenv("COUCHROOT_NATIVE_SOURCE_REARM");
    launcher_mode = 1; bridge_enabled = 1; lifetime = 0;
    launcher_home = home && !strcmp(home, "1"); launcher_rearm = rearm && !strcmp(rearm, "1");
    char *base = file_url(page, "?host=native-webview");
    if (!base) return 0;
    const char *fragment = launcher_import_fragment();
    url = malloc(strlen(base) + (fragment ? strlen(fragment) : 0) + 1);
    if (!url) { free(base); return 0; }
    strcpy(url, base); if (fragment) strcat(url, fragment);
    free(base);
    printf("launcher engine=%s home=%d rearm=%d\n", engine_request == ENGINE_UPGRADE ? "upgrade" : "default", launcher_home, launcher_rearm);
    return 1;
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--bridge-discover")) return worker_discover();
    if (argc == 3 && !strcmp(argv[1], "--bridge-launch")) return worker_launch(argv[2]);
    if (argc == 2 && !strcmp(argv[1], "--launcher-worker")) return launcher_worker();
    if (argc == 2 && !strcmp(argv[1], "--source-rearm-wait")) return source_rearm_wait();
    if (argc == 3 && !strcmp(argv[1], "--native-guard") && !strcmp(argv[2], "--stay")) return launcher_supervise();
    start = now(); setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGINT, stop_signal); signal(SIGTERM, stop_signal);
    signal(SIGPIPE, SIG_IGN);
    int first = 1;
    if (argc == 2 && !strcmp(argv[1], "--launcher-child")) {
        if (!launcher_child_setup()) { fputs("webview failure=launcher-setup\n", stderr); return 2; }
        first = argc; /* No page or lifetime arguments in this role. */
    }
    for (; !launcher_mode && first < argc && !strncmp(argv[first], "--", 2); first++) {
        if (!strcmp(argv[first], "--engine=upgrade")) engine_request = ENGINE_UPGRADE;
        else if (!strcmp(argv[first], "--engine=default")) engine_request = ENGINE_DEFAULT;
        else if (!strcmp(argv[first], "--native-bridge")) bridge_enabled = 1;
        else return 2;
    }
    if (!launcher_mode && (argc - first < 1 || argc - first > 2)) {
        fprintf(stderr, "Usage: %s [--engine=default|upgrade] [--native-bridge] LOCAL_HTML [LIFETIME_SECONDS:1..3600]\n", argv[0]); return 2;
    }
    if (!launcher_mode && argc - first == 2) {
        char *end; errno = 0; long value = strtol(argv[first + 1], &end, 10);
        if (errno || end == argv[first + 1] || *end || value < 1 || value > 3600) return 2;
        lifetime = (int)value;
    }
    if (!launcher_mode) url = file_url(argv[first], bridge_enabled ? "?host=native-webview" : "");
    if (!url) { fprintf(stderr, "Input must be a readable local file\n"); return 2; }
    stamp("main");
    if (!efl_api()) { free(url); return 3; }
    if (elm_init(argc, argv) <= 0) { free(url); return 3; } /* Also initializes Ecore_Evas. */
    window = ecore_evas_new("wayland_egl", 0, 0, 1920, 1080, NULL);
    canvas = window ? ecore_evas_get(window) : NULL;
    /* The fake window does not own the Ecore_Evas; freeing the Ecore_Evas
     * deletes it with the rest of the canvas. */
    elm_window = canvas ? elm_win_fake_add(window) : NULL;
    background = elm_window ? evas_object_rectangle_add(canvas) : NULL;
    label = background ? evas_object_text_add(canvas) : NULL;
    if (!label) { if (window) ecore_evas_free(window); elm_shutdown(); free(url); return 4; }
    ecore_evas_title_set(window, launcher_mode ? "Minimal Hub" : "Minimal Hub WebView experiment");
    if (!launcher_input(background)) { fputs("webview failure=launcher-input\n", stderr); ecore_evas_free(window); elm_shutdown(); free(url); return 3; }
    evas_object_color_set(background, 16, 20, 28, 255);
    evas_object_resize(background, 1920, 1080);
    elm_win_resize_object_add(elm_window, background);
    evas_object_show(background);
    evas_object_text_font_set(label, "Sans", 32);
    evas_object_text_text_set(label, "Loading Minimal Hub WebView…");
    evas_object_color_set(label, 230, 235, 245, 255);
    evas_object_move(label, 80, 80); evas_object_show(label);
    evas_object_smart_callback_add(elm_window, "delete,request", close_window, NULL);
    evas_object_smart_callback_add(elm_window, "focus,in", focus_in, NULL);
    evas_object_smart_callback_add(elm_window, "focus,out", focus_out, NULL);
    ecore_evas_callback_post_render_set(window, rendered); /* Unused by Elementary 1.25. */
    watch_timer = ecore_timer_add(0.1, watch, NULL);
    if (!watch_timer) failure("watch-timer");
    ecore_evas_show(window);
    if (watch_timer) ecore_main_loop_begin();
    else fputs("webview failure=watch-timer-no-loop\n", stderr);
    if (defer_timer) ecore_timer_del(defer_timer);
    if (watch_timer) ecore_timer_del(watch_timer);
    bridge_shutdown();
    launcher_shutdown();
    if (view) { evas_object_del(view); view = NULL; }
    if (ewk_started) ewk_shutdown();
    ecore_evas_free(window); window = NULL; /* Deletes the fake window and canvas objects. */
    elm_shutdown();
    /* Libraries remain mapped until process exit: vendor TLS/destructors may
     * still reference them after shutdown. */
    free(url); stamp("exit");
    if (failed) return 5;
    /* Stopped by signal or window close before the page finished: not a fault. */
    return loaded ? 0 : (stopping ? 6 : 5);
}
