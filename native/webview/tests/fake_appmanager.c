/* Fake Tizen app-manager for bridge worker tests. Mirrors the documented
 * callback/getter shapes only; it is not evidence of firmware behavior. */
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
typedef struct { const char *id, *package, *label, *icon; bool hidden; int component; } App;
static const App apps[] = {
    { "kIciSQlYEM.plex", "kIciSQlYEM", "Plex", "/opt/usr/apps/kIciSQlYEM/shared/res/plex.png", false, 0 },
    { "9Ur5IzDKqV.TizenYouTube", "9Ur5IzDKqV", "YouTube \"TV\"\n line", "http://example.invalid/remote.png", false, 0 },
    { "org.tizen.netflix-app", "org.tizen.netflix-app", "Netflix", "/usr/share/icons/netflix.png", false, 0 },
    { "org.tizen.factory-tool", "org.tizen.factory-tool", "Factory tool", "", false, 0 }, /* Internal: not 10-char package. */
    { "AbCdEfGhIj.hidden", "AbCdEfGhIj", "Hidden", "", true, 0 },                       /* nodisplay. */
    { "AbCdEfGhIj.service", "AbCdEfGhIj", "Service", "", false, 1 },                     /* Not a UI app. */
    { "com.samsung.tv.csfs", "com.samsung.tv.csfs", "Samsung Home", "", false, 0 },      /* Explicit Home only. */
    { "MiniHub001.Hub", "MiniHub001", "Minimal Hub", "", false, 0 },                     /* Hub itself. */
    { "bad id!", "AbCdEfGhIj", "Bad", "", false, 0 },
};
static char *copy(const char *s) { return s ? strdup(s) : NULL; }
int app_manager_foreach_app_info(bool (*callback)(void *, void *), void *data) {
    if (getenv("FAKE_DISCOVERY_FAIL")) return -1;
    for (size_t i = 0; i < sizeof apps / sizeof *apps; i++)
        if (!callback((void *)&apps[i], data)) break;
    return 0;
}
int app_info_get_app_id(void *app, char **out) { *out = copy(((App *)app)->id); return 0; }
int app_info_get_package(void *app, char **out) { *out = copy(((App *)app)->package); return 0; }
int app_info_get_label(void *app, char **out) { *out = copy(((App *)app)->label); return 0; }
int app_info_get_icon(void *app, char **out) { *out = copy(((App *)app)->icon); return 0; }
int app_info_is_nodisplay(void *app, bool *out) { *out = ((App *)app)->hidden; return 0; }
int app_info_get_app_component_type(void *app, int *out) { *out = ((App *)app)->component; return 0; }
