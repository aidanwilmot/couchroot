/* Bounded execution probe: no network or telemetry credentials. */
#include <stdio.h>
#include <unistd.h>
int main(void) {
    printf("minimal-native-probe uid=%lu gid=%lu\n",
           (unsigned long)getuid(), (unsigned long)getgid());
    FILE *marker = fopen("/opt/usr/home/owner/apps_rw/MiniNativeProbe/data/probe.txt", "w");
    if (marker) {
        fprintf(marker, "native-main pid=%lu uid=%lu gid=%lu\n",
                (unsigned long)getpid(), (unsigned long)getuid(), (unsigned long)getgid());
        fclose(marker);
    }
    return 42; /* Distinguishes actual execution from launcher submission. */
}
