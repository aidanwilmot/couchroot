/* Deterministic lifecycle fixture, not an EFL renderer or firmware emulator. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
typedef void Obj;
typedef unsigned char Bool;
static int win, canvas, fake_win, rectangle, text, web;
static int shown, rendered, web_deleted, win_freed, initialized, focus, elm_focus, quit, elm, view_parented;
static void (*post_render)(Obj *);
typedef void (*Smart)(void *, Obj *, void *);
static Smart close_request, focus_in, focus_out, loaded, error, crash, title, frame;
static int window_focused; /* What ecore_evas_focus_get reports. */
typedef struct { Bool (*callback)(void *); int active; } Timer;
static Timer watch_timer, deferred;
static char loaded_url[4096]; static int replied;
static int mode(const char *value) { const char *m = getenv("FAKE_MODE"); return m && !strcmp(m, value); }

int elm_init(int argc, char **argv) {
    assert(argc >= 2 && argv && argv[0]); puts("mock elm-init");
    if (mode("elm-fail")) return 0;
    return ++elm;
}
int elm_shutdown(void) { assert(elm && !initialized && (win_freed || mode("window-fail"))); puts("mock elm-shutdown"); return --elm; }
Obj *elm_win_fake_add(Obj *ee) { assert(elm && ee == &win); return mode("fake-fail") ? NULL : &fake_win; }
void elm_win_resize_object_add(Obj *w, Obj *o) {
    assert(w == &fake_win && (o == &web || o == &rectangle));
    if (o == &web) view_parented = 1;
}
void elm_object_focus_set(Obj *o, Bool value) { assert(o == &web); elm_focus = value; }
Obj *ecore_evas_new(const char *engine, int x, int y, int w, int h, const char *options) {
    (void)x; (void)y; (void)options;
    assert(elm && !strcmp(engine, "wayland_egl") && w == 1920 && h == 1080);
    return mode("window-fail") ? NULL : &win;
}
Obj *ecore_evas_get(Obj *w) { assert(w == &win); return &canvas; }
void ecore_evas_show(Obj *w) { assert(w == &win); shown = 1; puts("mock window-show"); }
void ecore_evas_free(Obj *w) { assert(w == &win && !initialized && elm); win_freed = 1; puts("mock window-free"); }
void ecore_evas_title_set(Obj *w, const char *s) { (void)w; (void)s; }
void ecore_evas_callback_post_render_set(Obj *w, void (*f)(Obj *)) { (void)w; post_render = f; }
Bool ecore_evas_focus_get(const Obj *w) { assert(w == &win); return (Bool)window_focused; }
Obj *ecore_timer_add(double seconds, Bool (*f)(void *), const void *data) {
    (void)data;
    Timer *t = seconds == 0 ? &deferred : &watch_timer;
    t->callback = f; t->active = 1; return t;
}
void *ecore_timer_del(Obj *o) { Timer *t = o; assert(t->active); t->active = 0; return NULL; }
void ecore_main_loop_quit(void) { quit = 1; }
/* Launcher-role hooks: Home key grab/callbacks and window raise. */
typedef struct { const char *keyname; } KeyPrefix;
static void (*key_down)(void *, Obj *, Obj *, void *), (*key_up)(void *, Obj *, Obj *, void *);
static void *key_down_data, *key_up_data;
static int raised;
Bool evas_object_key_grab(Obj *o, const char *key, uint64_t m, uint64_t n, Bool exclusive) {
    assert(o == &rectangle && !strcmp(key, "XF86Home") && !m && !n && !exclusive); return 1;
}
void evas_object_event_callback_add(Obj *o, int type, void (*f)(void *, Obj *, Obj *, void *), const void *data) {
    assert(o == &rectangle);
    if (type == 10) { key_down = f; key_down_data = (void *)data; } else { assert(type == 11); key_up = f; key_up_data = (void *)data; }
}
void ecore_evas_raise(Obj *w) { assert(w == &win); puts("mock raise"); raised++; }
void ecore_evas_activate(Obj *w) { assert(w == &win); }
static int wl_window;
Obj *ecore_evas_wayland2_window_get(Obj *w) { assert(w == &win); return &wl_window; }
Bool ecore_wl2_window_keygrab_set(Obj *w, const char *key, int mod, int not_mod, int priority, int type) {
    assert(w == &wl_window && !strcmp(key, "XF86Home") && !mod && !not_mod && !priority && type == 3);
    puts("mock keygrab XF86Home"); return 1;
}
static void write_state(const char *name, const char *value);
static void drive(int (*done)(void)) {
    const char *wait = getenv("FAKE_WAIT_MS"), *wake = getenv("FAKE_WAKE_AT_MS");
    int rounds = wait ? atoi(wait) / 10 : 300, wake_round = wake ? atoi(wake) / 10 : -1;
    for (int i = 0; i < rounds && !done() && watch_timer.active; i++) {
        if (i == wake_round) { /* Remote wake: screen on, Samsung brings Live TV forward. */
            write_state("pm", "1"); write_state("fg", "org.tizen.tv-viewer"); write_state("source", "vc-service");
        }
        watch_timer.callback(NULL);
        struct timespec pause = { 0, 10000000 }; nanosleep(&pause, NULL);
    }
}
static int has_replied(void) { return replied; }
static int has_shown(void) { return shown || quit; }
static int has_raised(void) { return raised > 0; }
static void write_state(const char *name, const char *value) {
    char path[1024]; snprintf(path, sizeof path, "%s/%s", getenv("FAKE_STATE"), name);
    FILE *f = fopen(path, "w"); assert(f); fputs(value, f); fclose(f);
}
static int ewk_focus_value(void);
static void both_focus(int expected) { assert(focus == expected && elm_focus == expected && ewk_focus_value() == expected); }
void ecore_main_loop_begin(void) {
    assert(!initialized && post_render && close_request && focus_in && focus_out);
    int hidden_start = !shown;
    /* Launcher tests: TV state changes after boot admission. */
    if (getenv("FAKE_FG_AFTER_START")) write_state("fg", getenv("FAKE_FG_AFTER_START"));
    if (getenv("FAKE_SOURCE_AFTER_START")) write_state("source", getenv("FAKE_SOURCE_AFTER_START"));
    if (getenv("FAKE_ISP_AFTER_START")) write_state("isp", getenv("FAKE_ISP_AFTER_START"));
    if (!hidden_start) { rendered = 1; post_render(&win); }
    assert(deferred.active);
    if (mode("close-early")) { close_request(NULL, &fake_win, NULL); assert(quit); return; }
    if (!deferred.callback(NULL)) deferred.active = 0;
    if (loaded && !mode("url-fail")) {
        assert(view_parented);
        if (mode("load-error")) error(NULL, &web, NULL);
        else {
            if (title && !getenv("FAKE_TITLE")) title(NULL, &web, NULL);
            if (frame && mode("frame-before-load")) { frame(NULL, &web, NULL); assert(!shown); }
            /* Losing focus while loading must not steal it at load completion. */
            if (mode("focus-before-load")) {
                /* The window already had focus; no signal arrives after load. */
                window_focused = 1; loaded(NULL, &web, NULL); both_focus(1);
            } else {
                focus_out(NULL, &fake_win, NULL); loaded(NULL, &web, NULL); both_focus(0);
            }
            if (hidden_start && frame && !mode("no-page-frame")) {
                assert(!shown); frame(NULL, &web, NULL);
                if (getenv("COUCHROOT_WEBVIEW_DEFER_SHOW")) {
                    assert(!shown); /* A background paint is not UI readiness. */
                    if (!mode("no-ui-ready")) {
                        const char *saved = getenv("FAKE_TITLE");
                        char *copy = saved ? strdup(saved) : NULL;
                        setenv("FAKE_TITLE", "hubbridge:1:ready1:ready", 1);
                        title(NULL, &web, NULL);
                        assert(!shown);
                        frame(NULL, &web, NULL);
                        if (!mode("no-ui-painted")) {
                            assert(!shown); /* A frame after 'ready' alone may still be stale markup. */
                            setenv("FAKE_TITLE", "hubbridge:1:painted1:painted", 1);
                            title(NULL, &web, NULL);
                        }
                        if (copy) { setenv("FAKE_TITLE", copy, 1); free(copy); }
                        else unsetenv("FAKE_TITLE");
                    }
                }
                if (!shown) drive(has_shown);
                if (mode("no-ui-ready") || mode("no-ui-painted")) { assert(!shown); close_request(NULL, &fake_win, NULL); }
                if (quit) return;
                assert(shown); rendered = 1; post_render(&win);
            }
            focus_in(NULL, &fake_win, NULL); both_focus(1);
            focus_out(NULL, &fake_win, NULL); both_focus(0);
            focus_in(NULL, &fake_win, NULL); both_focus(1);
            if (mode("crash")) { crash(NULL, &web, NULL); both_focus(0); }
            const char *request = getenv("FAKE_TITLE");
            if (request && title) {
                /* Deliver one bridge request, then drive the host's watch timer
                 * until it replies or a bounded wait expires. */
                title(NULL, &web, NULL);
                drive(has_replied);
                if (getenv("FAKE_RETURN")) {
                    /* The launched app is in front (focus lost), then exits. */
                    focus_out(NULL, &fake_win, NULL);
                    struct timespec pause = { 1, 500000000 }; nanosleep(&pause, NULL);
                    for (int i = 0; i < 20; i++) { watch_timer.callback(NULL); nanosleep(&(struct timespec){ 0, 10000000 }, NULL); }
                    write_state("fg", "");
                    drive(has_raised);
                }
            }
            if (getenv("FAKE_HOME_PRESS")) {
                for (int i = 0; i < 3; i++) watch_timer.callback(NULL); /* Starts the Wayland grab. */
                assert(key_down && key_up);
                KeyPrefix home = { "XF86Home" };
                key_down(key_down_data, &canvas, &rectangle, &home);
                key_up(key_up_data, &canvas, &rectangle, &home);
                drive(has_raised);
            }
            if (getenv("FAKE_DRIVE")) drive(has_raised); /* Let periodic work (re-arm) run. */
        }
    }
    close_request(NULL, &fake_win, NULL); assert(quit);
}
Obj *evas_object_rectangle_add(Obj *c) { assert(c == &canvas); return &rectangle; }
Obj *evas_object_text_add(Obj *c) { assert(c == &canvas); return &text; }
void evas_object_color_set(Obj *o, int r, int g, int b, int a) { (void)o; (void)r; (void)g; (void)b; (void)a; }
void evas_object_move(Obj *o, int x, int y) { (void)o; (void)x; (void)y; }
void evas_object_resize(Obj *o, int w, int h) { assert((o == &rectangle || o == &web) && w == 1920 && h == 1080); }
void evas_object_show(Obj *o) { (void)o; }
void evas_object_hide(Obj *o) { (void)o; }
void evas_object_del(Obj *o) { assert(o == &web && !win_freed); web_deleted = 1; puts("mock view-delete"); }
void evas_object_focus_set(Obj *o, Bool value) { assert(o == &web); focus = value; }
Obj *evas_focus_get(const Obj *c) { assert(c == &canvas); return focus ? &web : NULL; }
const char *evas_object_type_get(const Obj *o) { (void)o; return "mock"; }
void evas_object_text_font_set(Obj *o, const char *s, int n) { (void)o; (void)s; (void)n; }
void evas_object_text_text_set(Obj *o, const char *s) { assert(o == &text); printf("mock label=%s\n", s); }
void evas_object_smart_callback_add(Obj *o, const char *name, Smart f, const void *data) {
    (void)data;
    if (o == &fake_win) {
        if (!strcmp(name, "delete,request")) close_request = f;
        else if (!strcmp(name, "focus,in")) focus_in = f;
        else if (!strcmp(name, "focus,out")) focus_out = f;
        else assert(0);
        return;
    }
    assert(o == &web);
    if (!strcmp(name, "load,finished")) loaded = f;
    else if (!strcmp(name, "load,error")) error = f;
    else if (!strcmp(name, "webprocess,crashed")) crash = f;
    else if (!strcmp(name, "title,changed")) title = f;
    else if (!strcmp(name, "frame,rendered")) frame = f;
    else assert(0);
}
#ifndef OMIT_VERSION_POLICY
int ewk_set_version_policy(int value) {
    assert(!initialized && elm); printf("mock version-policy=%d\n", value); return 1;
}
#endif
static int ewk_focus;
Bool ewk_view_focus_set(const Obj *o, Bool value) { assert(o == &web); ewk_focus = value; return 1; }
Bool ewk_view_focus_get(const Obj *o) { assert(o == &web); return (Bool)ewk_focus; }
static int ewk_focus_value(void) { return ewk_focus; }
const char *ewk_view_title_get(const Obj *o) {
    assert(o == &web);
    const char *request = getenv("FAKE_TITLE");
    return request ? request : "diag ready\x01ok";
}
const char *ewk_view_url_get(const Obj *o) {
    assert(o == &web);
    const char *other = getenv("FAKE_CURRENT_URL");
    return other ? other : loaded_url;
}
Bool ewk_view_script_execute(Obj *o, const char *script, void *callback, void *data) {
    assert(o == &web && !callback && !data);
    printf("mock script=%s\n", script); replied = 1; return 1;
}
Bool ewk_view_visibility_set(Obj *o, Bool visible) { assert(o == &web); printf("mock visibility=%d\n", visible); return 1; }
int ewk_init(void) {
    assert(elm); puts("mock ewk-init");
    if (mode("sigterm-in-init")) raise(SIGTERM);
    if (mode("init-fail")) return 0;
    initialized = 1; return 1;
}
int ewk_shutdown(void) {
    assert(initialized && (mode("view-fail") || mode("sigterm-in-init") || mode("engine-mismatch") || web_deleted));
    initialized = 0; puts("mock ewk-shutdown"); return 0;
}
Obj *ewk_view_add(Obj *c) { assert(initialized && c == &canvas); return mode("view-fail") ? NULL : &web; }
Bool ewk_view_url_set(Obj *o, const char *url) {
    assert(o == &web); printf("mock url=%s\n", url);
    snprintf(loaded_url, sizeof loaded_url, "%s", url);
    return !mode("url-fail");
}
