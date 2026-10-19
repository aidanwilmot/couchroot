/* Bounded lifecycle probe: no network, no files, and a 45-second hard deadline. */
#define _POSIX_C_SOURCE 200809L
#include <signal.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopping;
static void stop(int signo) { (void)signo; stopping = 1; }
int main(void) {
    struct sigaction action = {0};
    action.sa_handler = stop;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, 0) || sigaction(SIGINT, &action, 0)) return 70;
    struct timespec started, now, delay = {0, 100000000};
    if (clock_gettime(CLOCK_MONOTONIC, &started)) return 71;
    printf("native lifecycle probe pid=%lu uid=%lu\n", (unsigned long)getpid(), (unsigned long)getuid());
    fflush(stdout);
    while (!stopping) {
        if (clock_gettime(CLOCK_MONOTONIC, &now)) return 71;
        if (now.tv_sec - started.tv_sec >= 45) return 0;
        nanosleep(&delay, 0);
    }
    return 0;
}
