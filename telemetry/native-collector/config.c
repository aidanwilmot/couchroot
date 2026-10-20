#include "collector.h"
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static char *read_fd(int fd, size_t limit) {
    if (fd < 0) return NULL;
    char *text = malloc(limit + 1);
    size_t count = 0;
    if (!text) { close(fd); return NULL; }
    while (count <= limit) {
        ssize_t n = read(fd, text + count, limit + 1 - count);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { free(text); close(fd); return NULL; }
        if (!n) break;
        count += (size_t)n;
        if (count > limit) { free(text); close(fd); return NULL; }
    }
    close(fd);
    if (memchr(text, 0, count)) { free(text); return NULL; }
    text[count] = 0;
    return text;
}

char *read_bounded(const char *path, size_t limit) {
    return read_fd(open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK), limit);
}

char *read_at(int directory, const char *name, size_t limit, bool private_file) {
    int fd = openat(directory, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    struct stat st;
    if (fd < 0) return NULL;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        (private_file && ((st.st_mode & 077) || (st.st_uid != getuid() && st.st_uid != 0)))) {
        close(fd); return NULL;
    }
    return read_fd(fd, limit);
}

struct json_object *parse_object(const char *text) {
    if (!text) return NULL;
    struct json_tokener *tok = json_tokener_new_ex(8);
    if (!tok) return NULL;
    json_tokener_set_flags(tok, JSON_TOKENER_STRICT | JSON_TOKENER_VALIDATE_UTF8);
    struct json_object *obj = json_tokener_parse_ex(tok, text, (int)strlen(text) + 1);
    if (json_tokener_get_error(tok) != json_tokener_success || !json_object_is_type(obj, json_type_object)) {
        json_object_put(obj); obj = NULL;
    }
    json_tokener_free(tok);
    return obj;
}

const char *json_string(struct json_object *obj, const char *key, size_t max) {
    struct json_object *value;
    if (!json_object_object_get_ex(obj, key, &value) || !json_object_is_type(value, json_type_string)) return NULL;
    const char *s = json_object_get_string(value);
    size_t n = (size_t)json_object_get_string_len(value);
    return n && n <= max && strlen(s) == n ? s : NULL;
}

bool valid_endpoint(const char *endpoint, const char *device) {
    if (!endpoint || strlen(endpoint) > 512 || strncmp(endpoint, "https://", 8) ||
        strpbrk(endpoint, "?#@\\")) return false;
    for (const unsigned char *c = (const unsigned char *)endpoint; *c; ++c)
        if (*c <= 32 || *c >= 127) return false;
    CURLU *url = curl_url();
    if (!url) return false;
    char *host = NULL, *path = NULL, *port = NULL;
    char expected[80]; snprintf(expected, sizeof expected, "/v1/devices/%s", device);
    bool valid = curl_url_set(url, CURLUPART_URL, endpoint, 0) == CURLUE_OK &&
        curl_url_get(url, CURLUPART_HOST, &host, 0) == CURLUE_OK && host[0] &&
        curl_url_get(url, CURLUPART_PATH, &path, 0) == CURLUE_OK &&
        (!strcmp(path, expected) || (!strcmp(device, "s90d") && !strcmp(path, "/v1/s90d")));
    if (curl_url_get(url, CURLUPART_PORT, &port, 0) == CURLUE_OK && !strcmp(port, "0")) valid = false;
    curl_free(host); curl_free(path); curl_free(port); curl_url_cleanup(url);
    return valid;
}

static bool copy_field(struct json_object *obj, const char *key, char *target, size_t capacity) {
    const char *s = json_string(obj, key, capacity - 1);
    if (!s) return false;
    strcpy(target, s); return true;
}

bool load_config(int directory, struct config *cfg) {
    char *text = read_at(directory, "config.json", CONFIG_LIMIT, true);
    struct json_object *obj = parse_object(text);
    free(text);
    if (!obj) return false;
    const char *pin = json_string(obj, "certificate_sha256", 64);
    bool valid = copy_field(obj, "device_id", cfg->device, sizeof cfg->device) &&
        copy_field(obj, "endpoint", cfg->endpoint, sizeof cfg->endpoint) &&
        copy_field(obj, "dashboard_config_path", cfg->preferences, sizeof cfg->preferences) &&
        copy_field(obj, "firmware", cfg->firmware, sizeof cfg->firmware) &&
        copy_field(obj, "token", cfg->token, sizeof cfg->token) && pin && strlen(pin) == 64;
    if (valid) {
        valid = (!strcmp(cfg->device, "s90d") || !strcmp(cfg->device, "qn90a")) &&
            valid_endpoint(cfg->endpoint, cfg->device) && strlen(cfg->token) >= 32 && cfg->preferences[0] == '/';
        for (const unsigned char *p = (const unsigned char *)cfg->token; *p; ++p)
            if (!isalnum(*p) && *p != '-' && *p != '_' && *p != '.') valid = false;
        for (int i = 0; i < 32; ++i) {
            unsigned int v;
            if (!isxdigit((unsigned char)pin[i*2]) || !isxdigit((unsigned char)pin[i*2+1]) ||
                sscanf(pin+i*2, "%2x", &v) != 1) { valid = false; break; }
            cfg->pin[i] = (unsigned char)v;
        }
#ifndef COLLECTOR_HOST_TEST
        const char *firmware = !strcmp(cfg->device, "qn90a") ? "T-NKM2AKUC-2301.1" : "T-PTMDAKUC-0090-2130.0";
        char expected[160]; snprintf(expected, sizeof expected, "Version=%s;", firmware);
        char *actual = read_bounded("/etc/prd_info.ini", CONFIG_LIMIT);
        valid = valid && sizeof(void *) == 4 && !strcmp(cfg->firmware, firmware) && actual && strstr(actual, expected);
        free(actual);
#endif
    }
    json_object_put(obj);
    if (!valid) memset(cfg, 0, sizeof *cfg);
    return valid;
}

bool load_preferences(const struct config *cfg, bool *enabled, char endpoint[513]) {
    *enabled = false;
    char *text = read_bounded(cfg->preferences, CONFIG_LIMIT);
    struct json_object *obj = parse_object(text), *schema, *on;
    free(text);
    if (!obj) return false;
    const char *url = json_string(obj, "endpoint", 512);
    bool valid = json_object_object_get_ex(obj, "schema", &schema) && json_object_is_type(schema, json_type_int) &&
        json_object_get_int64(schema) == 1 && json_object_object_get_ex(obj, "enabled", &on) &&
        json_object_is_type(on, json_type_boolean) && valid_endpoint(url, cfg->device);
    if (valid) { *enabled = json_object_get_boolean(on); strcpy(endpoint, url); }
    json_object_put(obj); return valid;
}
