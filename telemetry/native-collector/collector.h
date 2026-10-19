#ifndef MINIMAL_COLLECTOR_H
#define MINIMAL_COLLECTOR_H
#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <signal.h>
#include <json-c/json.h>
#include <curl/curl.h>

#define CONFIG_LIMIT 4096
#define COUNTER_LIMIT 16384
#define BODY_LIMIT 65536

struct config {
    char device[49], endpoint[513], preferences[1024], firmware[128], token[513];
    unsigned char pin[32];
};
struct sender {
    CURL *curl;
    struct curl_slist *headers;
    const struct config *config;
    size_t response_bytes;
};
extern volatile sig_atomic_t stopping;
char *read_bounded(const char *path, size_t limit);
char *read_at(int directory, const char *name, size_t limit, bool private_file);
struct json_object *parse_object(const char *text);
const char *json_string(struct json_object *obj, const char *key, size_t max);
bool valid_endpoint(const char *endpoint, const char *device);
bool load_config(int directory, struct config *config);
bool load_preferences(const struct config *config, bool *enabled, char endpoint[513]);
double uptime_seconds(void);
struct json_object *sample(uint64_t sequence, const char *boot, const char *session, const char *device);
bool sender_init(struct sender *sender, const struct config *config);
bool sender_post(struct sender *sender, const char *endpoint, const char *body, int *error);
void sender_destroy(struct sender *sender);
#endif
