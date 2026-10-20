#include "collector.h"
#include <openssl/ssl.h>
#include <openssl/crypto.h>
#include <string.h>

static int verify_pin(X509_STORE_CTX *store, void *data) {
    const struct config *cfg = data;
    unsigned char digest[EVP_MAX_MD_SIZE]; unsigned int length = 0;
    X509 *cert = X509_STORE_CTX_get0_cert(store);
    // Match the managed collector: the entire DER certificate is the identity.
    // This also works before the TV clock is synchronized after boot.
    return cert && X509_digest(cert, EVP_sha256(), digest, &length) == 1 &&
        length == 32 && CRYPTO_memcmp(digest, cfg->pin, 32) == 0;
}

static CURLcode tls_context(CURL *curl, void *context, void *data) {
    (void)curl;
    SSL_CTX_set_cert_verify_callback(context, verify_pin, data);
    return CURLE_OK;
}

static size_t discard(char *data, size_t size, size_t count, void *user) {
    (void)data;
    struct sender *sender = user;
    if (count && size > 1024 / count) return 0;
    size_t n = size * count;
    if (n > 1024 - sender->response_bytes) return 0;
    sender->response_bytes += n; return n;
}

static int progress(void *unused, curl_off_t a, curl_off_t b, curl_off_t c, curl_off_t d) {
    (void)unused; (void)a; (void)b; (void)c; (void)d;
    return stopping != 0;
}

bool sender_init(struct sender *sender, const struct config *cfg) {
    memset(sender, 0, sizeof *sender); sender->config = cfg;
    const curl_version_info_data *version = curl_version_info(CURLVERSION_NOW);
    // SSL_CTX is OpenSSL-specific. Fail closed on a different backend or blocking DNS.
    if (!version || version->version_num < 0x074400 || !version->ssl_version ||
        strncmp(version->ssl_version, "OpenSSL/1.1.1", 13) || !(version->features & CURL_VERSION_ASYNCHDNS)) return false;
    sender->curl = curl_easy_init();
    if (!sender->curl) return false;
    char auth[544]; snprintf(auth, sizeof auth, "Authorization: Bearer %s", cfg->token);
    const char *headers[] = {auth, "Content-Type: application/json", "Expect:"};
    for (int i = 0; i < 3; ++i) {
        struct curl_slist *next = curl_slist_append(sender->headers, headers[i]);
        if (!next) { sender_destroy(sender); return false; }
        sender->headers = next;
    }
#define SET(option, value) do { if (curl_easy_setopt(sender->curl, option, value) != CURLE_OK) goto fail; } while (0)
    SET(CURLOPT_HTTPHEADER, sender->headers);
    SET(CURLOPT_PROXY, ""); SET(CURLOPT_NOPROXY, "*");
    SET(CURLOPT_FOLLOWLOCATION, 0L); SET(CURLOPT_PROTOCOLS, (long)CURLPROTO_HTTPS);
    SET(CURLOPT_REDIR_PROTOCOLS, (long)CURLPROTO_HTTPS);
    SET(CURLOPT_TIMEOUT_MS, 3000L); SET(CURLOPT_CONNECTTIMEOUT_MS, 3000L);
    SET(CURLOPT_NOSIGNAL, 1L); SET(CURLOPT_HTTP_VERSION, (long)CURL_HTTP_VERSION_1_1);
    SET(CURLOPT_SSLVERSION, (long)CURL_SSLVERSION_TLSv1_2);
    SET(CURLOPT_SSL_VERIFYPEER, 1L); SET(CURLOPT_SSL_VERIFYHOST, 0L);
    SET(CURLOPT_SSL_SESSIONID_CACHE, 0L);
    SET(CURLOPT_SSL_CTX_FUNCTION, tls_context); SET(CURLOPT_SSL_CTX_DATA, (void *)cfg);
    SET(CURLOPT_WRITEFUNCTION, discard); SET(CURLOPT_WRITEDATA, sender);
    SET(CURLOPT_XFERINFOFUNCTION, progress); SET(CURLOPT_NOPROGRESS, 0L);
    return true;
fail:
    sender_destroy(sender); return false;
#undef SET
}

bool sender_post(struct sender *sender, const char *endpoint, const char *body, int *error) {
    size_t length = strlen(body);
    if (!length || length > BODY_LIMIT || !valid_endpoint(endpoint, sender->config->device)) { *error = -1; return false; }
    sender->response_bytes = 0;
    CURLcode rc = curl_easy_setopt(sender->curl, CURLOPT_URL, endpoint);
    if (rc == CURLE_OK) rc = curl_easy_setopt(sender->curl, CURLOPT_POSTFIELDS, body);
    if (rc == CURLE_OK) rc = curl_easy_setopt(sender->curl, CURLOPT_POSTFIELDSIZE, (long)length);
    if (rc == CURLE_OK) rc = curl_easy_perform(sender->curl);
    long status = 0;
    if (rc == CURLE_OK) rc = curl_easy_getinfo(sender->curl, CURLINFO_RESPONSE_CODE, &status);
    *error = rc != CURLE_OK ? (int)rc : status == 204 ? 0 : -(int)status;
    return *error == 0;
}

void sender_destroy(struct sender *sender) {
    if (sender->curl) curl_easy_cleanup(sender->curl);
    curl_slist_free_all(sender->headers);
    sender->curl = NULL; sender->headers = NULL;
}
