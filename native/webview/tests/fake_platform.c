/* Fake libvconf + libsystemd for launcher tests: values come from files in
 * $FAKE_STATE (source, isp, fg, power); writes are logged. Not firmware evidence. */
#define _POSIX_C_SOURCE 200809L
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static char *state(const char *name) {
    const char *dir = getenv("FAKE_STATE"); char path[1024], value[512];
    if (!dir) return NULL;
    snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE *f = fopen(path, "r");
    if (!f) return NULL;
    size_t n = fread(value, 1, sizeof value - 1, f); fclose(f);
    value[n] = 0; value[strcspn(value, "\n")] = 0;
    return strdup(value);
}
static const char *file_for(const char *key) {
    if (!strcmp(key, "db/boot/last_service")) return "source";
    if (!strcmp(key, "db/was/isp_app_id")) return "isp";
    if (!strcmp(key, "memory/appfw/current_fullscreen_appid")) return "fg";
    return NULL;
}
char *vconf_get_str(const char *key) { const char *name = file_for(key); return name ? state(name) : NULL; }
int vconf_get_int(const char *key, int *out) {
    if (strcmp(key, "memory/pm/state")) return -1;
    char *value = state("pm");
    if (!value) return -1;
    *out = atoi(value); free(value); return 0;
}
int vconf_set_str(const char *key, const char *value) {
    const char *dir = getenv("FAKE_STATE"); char path[1024];
    if (!dir || strcmp(key, "db/boot/last_service")) return -1;
    snprintf(path, sizeof path, "%s/source", dir);
    FILE *f = fopen(path, "w"); if (!f) return -1; fputs(value, f); fclose(f);
    snprintf(path, sizeof path, "%s/log", dir);
    f = fopen(path, "a"); if (f) { fprintf(f, "set %s %s\n", key, value); fclose(f); }
    return 0;
}
int sd_bus_open_system(void **bus) { *bus = (void *)1; return 0; }
int sd_bus_set_method_call_timeout(void *bus, uint64_t usec) { (void)bus; (void)usec; return 0; }
int sd_bus_call_method(void *bus, const char *d, const char *p, const char *i, const char *m, void *e, void **reply, const char *t, ...) {
    (void)bus; (void)d; (void)p; (void)i; (void)m; (void)e; (void)t; *reply = (void *)1; return 1;
}
int sd_bus_message_read(void *message, const char *types, ...) {
    static char power[64]; char *value = state("power");
    (void)message; (void)types;
    if (!value) return -1;
    snprintf(power, sizeof power, "%s", value); free(value);
    if (getenv("FAKE_STANDBY_ONCE") && !strcmp(power, "standby")) {
        char path[1024]; snprintf(path, sizeof path, "%s/power", getenv("FAKE_STATE"));
        FILE *f = fopen(path, "w"); if (f) { fputs("lcdon", f); fclose(f); }
    }
    va_list args; va_start(args, types); *va_arg(args, const char **) = power; va_end(args);
    return 1;
}
void *sd_bus_unref(void *bus) { (void)bus; return NULL; }
void *sd_bus_message_unref(void *message) { (void)message; return NULL; }
