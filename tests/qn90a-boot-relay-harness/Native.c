#include <stddef.h>
#include <string.h>
#include <stdint.h>

static int ready_value, power_value, fg_null, reject_remaining;
static int sends, exits, controls_created, controls_destroyed;
static int fail_stage, fail_result;
static void (*send_hook)(void);
static char foreground[256];

void test_reset(int ready, int power, const char *fg, int rejects) {
    ready_value = ready; power_value = power; fg_null = fg == NULL;
    foreground[0] = 0;
    if (fg) strncpy(foreground, fg, sizeof(foreground) - 1);
    reject_remaining = rejects;
    sends = exits = controls_created = controls_destroyed = 0;
    fail_stage = fail_result = 0;
}
void test_fail_stage(int stage, int result) { fail_stage=stage; fail_result=result; }
void test_on_send(void (*hook)(void)) { send_hook=hook; }
void test_ready(int value) { ready_value = value; }
void test_power(int value) { power_value = value; }
void test_foreground(const char *value) {
    fg_null = value == NULL;
    if (value) { strncpy(foreground, value, sizeof(foreground)-1); foreground[255]=0; }
}
int test_sends(void) { return sends; }
int test_exits(void) { return exits; }
int test_outstanding_controls(void) { return controls_created - controls_destroyed; }

int device_power_get_state(void) { return power_value; }
int vconf_get_int(const char *key, int *value) { (void)key; *value=ready_value; return 0; }
const char *vconf_get_str(const char *key) { (void)key; return fg_null ? NULL : foreground; }
void free(void *pointer) { (void)pointer; } /* foreground is static test storage */
int chmod(const char *path, unsigned int mode) { (void)path; (void)mode; return 0; }
void ui_app_exit(void) { exits++; }
unsigned int g_timeout_add(unsigned int interval, void *callback, void *data) {
    (void)interval; (void)callback; (void)data; return 1;
}
int app_control_create(void **control) {
    if (fail_stage==1) { *control=NULL; return fail_result; }
    controls_created++; *control=(void *)(uintptr_t)1; return 0;
}
int app_control_destroy(void *control) { (void)control; controls_destroyed++; return 0; }
int app_control_set_app_id(void *control, const char *id) {
    (void)control; return fail_stage==2 ? fail_result : strcmp(id,"MiniHub001.Hub") == 0 ? 0 : -123;
}
int app_control_set_operation(void *control, const char *operation) {
    (void)control; return fail_stage==3 ? fail_result : strcmp(operation,"http://tizen.org/appcontrol/operation/default") == 0 ? 0 : -124;
}
int app_control_send_launch_request(void *control, void *callback, void *data) {
    (void)control; (void)callback; (void)data; sends++;
    if (send_hook) send_hook();
    if (reject_remaining > 0) { reject_remaining--; return -5; }
    return 0;
}
