/* Shared host platform primitives. SPDX-License-Identifier: 0BSD.
 * Normal-mode admission is shared; TV Plus remains an explicit caller policy. */
#ifndef COUCHROOT_PLATFORM_CORE_H
#define COUCHROOT_PLATFORM_CORE_H
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <fcntl.h>
#include <spawn.h>
#include <errno.h>
#include <time.h>
#include <sys/wait.h>
#if defined(__linux__) && !defined(_GNU_SOURCE)
extern int pipe2(int [2], int);
#endif
#ifndef UPTIME_PATH
#define UPTIME_PATH "/proc/uptime"
#endif
#ifndef MARKER_PATH
#define MARKER_PATH "/tmp/couchroot-early-hub-enabled"
#endif
#ifndef WM_READY_PATH
#define WM_READY_PATH "/run/.wm_ready"
#endif
#ifndef WAYLAND_SOCKET_PATH
#define WAYLAND_SOCKET_PATH "/run/user/5001/wayland-0"
#endif
#ifndef PLATFORM_TRACE_READS
#define PLATFORM_TRACE_READS 0
#endif
/* Same predicates as the private boot wrapper. NULL is never empty foreground. */
static inline int native_settings_match(const char *source, const char *isp,
                                 const char *power, const char *foreground) {
    return source && isp && power && foreground &&
        !strcmp(source, "isp-service") && !strcmp(isp, "MiniHub001.Hub") &&
        !strcmp(power, "lcdon") && !strcmp(foreground, "");
}
static inline void ng_stamp(const char *event) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    printf("%s %.3f\n", event, t.tv_sec + t.tv_nsec / 1e9); fflush(stdout);
}
static inline double ng_uptime(void) {
    double value=-1; FILE *f=fopen(UPTIME_PATH, "r");
    if(f) { if(fscanf(f,"%lf",&value)!=1)value=-1; fclose(f); }
    return value;
}
static inline int ng_marker(void) {
    return access(MARKER_PATH, F_OK)==0;
}
static inline int ng_display(void) {
    struct stat s;
    return access(WM_READY_PATH, F_OK)==0 &&
        stat(WAYLAND_SOCKET_PATH, &s)==0 && S_ISSOCK(s.st_mode);
}
/* Dynamic ABI declarations match libvconf and libsystemd's public C APIs. */
static inline int native_settings_read_checked(int (*match)(const char*,const char*,const char*,const char*)) {
    void *vc=dlopen("libvconf.so.0",RTLD_NOW|RTLD_LOCAL);
    void *sd=dlopen("libsystemd.so.0",RTLD_NOW|RTLD_LOCAL);
    if(!vc || !sd) { if(vc)dlclose(vc); if(sd)dlclose(sd); return 0; }
    char *(*get_str)(const char*)=NULL;
    int (*open_system)(void**)=NULL;
    int (*set_timeout)(void*,uint64_t)=NULL;
    int (*call)(void*,const char*,const char*,const char*,const char*,void*,void**,const char*,...)=NULL;
    int (*read_reply)(void*,const char*,...)=NULL;
    void *(*unref_bus)(void*)=NULL, *(*unref_message)(void*)=NULL;
#define NG_LOAD(handle, pointer, symbol) do { *(void**)(&pointer)=dlsym(handle,symbol); if(!pointer)goto missing; } while(0)
    NG_LOAD(vc,get_str,"vconf_get_str");
    NG_LOAD(sd,open_system,"sd_bus_open_system");
    NG_LOAD(sd,set_timeout,"sd_bus_set_method_call_timeout");
    NG_LOAD(sd,call,"sd_bus_call_method");
    NG_LOAD(sd,read_reply,"sd_bus_message_read");
    NG_LOAD(sd,unref_bus,"sd_bus_unref");
    NG_LOAD(sd,unref_message,"sd_bus_message_unref");
#undef NG_LOAD
    char *source=get_str("db/boot/last_service"); if (PLATFORM_TRACE_READS) ng_stamp("native-source-read");
    char *isp=get_str("db/was/isp_app_id"); if (PLATFORM_TRACE_READS) ng_stamp("native-isp-read");
    void *bus=NULL,*reply=NULL; const char *power=NULL;
    int rc=open_system(&bus);
    if(rc>=0)rc=set_timeout(bus,2000000);
    if(rc>=0)rc=call(bus,"org.tizen.system.deviced","/Org/Tizen/System/DeviceD/Display",
        "org.tizen.system.deviced.display","GetState",NULL,&reply,"");
    if(rc>=0)rc=read_reply(reply,"s",&power);
    if(rc<=0)power=NULL;
    if (PLATFORM_TRACE_READS) ng_stamp("native-power-read");
    char *foreground=get_str("memory/appfw/current_fullscreen_appid");
    if (PLATFORM_TRACE_READS) ng_stamp("native-foreground-read");
    printf("native-values source=%s isp=%s power=%s foreground=[%s]\n",
        source?source:"<missing>",isp?isp:"<missing>",power?power:"<missing>",foreground?foreground:"<missing>");
    int ok=match(source,isp,power,foreground);
    free(source); free(isp); free(foreground);
    if(reply)unref_message(reply);
    if(bus)unref_bus(bus);
    dlclose(sd); dlclose(vc); return ok;
missing:
    dlclose(sd); dlclose(vc); return 0;
}
static inline int native_settings_read(void) { return native_settings_read_checked(native_settings_match); }
static inline int platform_early_boot_guard(void) {
    double up=ng_uptime();
    if(up<0 || up>=46 || !ng_marker())return 0;
    /* Bound all admission, including library IPC. Original floor(uptime)<=45. */
    alarm((unsigned)(46-up)+1);
    while(!ng_display()) {
        up=ng_uptime(); if(up<0 || up>=46 || !ng_marker())return 0;
        struct timespec delay={0,200000000}; nanosleep(&delay,NULL);
    }
    ng_stamp("native-compositor-ready");
    if(!native_settings_read())return 0;
    up=ng_uptime();
    int ok=up>=0 && up<46 && ng_marker() && ng_display();
    alarm(0); return ok;
}
static inline int home_settings_match(const char *source,const char *isp,const char *power,const char *foreground){
 return source&&isp&&power&&foreground&&!strcmp(source,"isp-service")&&!strcmp(isp,"MiniHub001.Hub")&&!strcmp(power,"lcdon");
}
/* Saved-source re-arm. The firmware boots in background (no Live TV) mode only while
 * db/boot/last_service is isp-service. Switching to Live TV/TV Plus writes another value
 * at once; power-off does not rewrite it (QN90A-verified), so re-arming while the TV is
 * still on keeps the next boot quiet. Requires Hub to own the ISP slot. The key's write
 * privilege is public; the firmware setter keeps its metadata unchanged. */
#define TV_VIEWER "org.tizen.tv-viewer"
#define REARM_SOURCE "isp-service"
enum {REARM_OK=0,REARM_NEEDED=1,REARM_FOREGROUND=2,REARM_NOT_ISP=3,REARM_FAILED=4,REARM_UNREADABLE=5};
typedef struct { int result, viewer; char previous[64]; } RearmReport;
static inline int rearm_decision(const char *isp,const char *last,const char *foreground){
 if(!isp||!last||!foreground)return REARM_UNREADABLE;
 if(strcmp(isp,"MiniHub001.Hub"))return REARM_NOT_ISP;
 return strcmp(last,REARM_SOURCE)?REARM_NEEDED:REARM_OK;
}
/* probe: rewrite only an already-correct value, proving write access without change. */
static inline RearmReport source_rearm(char *(*get)(const char*),int (*set)(const char*,const char*),int probe){
 RearmReport r={REARM_UNREADABLE,0,""};if(!get||!set)return r;
 char *isp=get("db/was/isp_app_id"),*last=get("db/boot/last_service"),*fg=get("memory/appfw/current_fullscreen_appid");
 if(last)snprintf(r.previous,sizeof(r.previous),"%s",last);
 r.result=rearm_decision(isp,last,fg);r.viewer=fg&&!strcmp(fg,TV_VIEWER);
 if(probe&&r.result==REARM_OK)r.result=set("db/boot/last_service",REARM_SOURCE)==0?REARM_OK:REARM_FAILED;
 else if(!probe&&r.result==REARM_NEEDED){
  char *check=0;if(set("db/boot/last_service",REARM_SOURCE)!=0||!(check=get("db/boot/last_service"))||strcmp(check,REARM_SOURCE))r.result=REARM_FAILED;free(check);
 }
 free(isp);free(last);free(fg);return r;
}
static const char *rearm_name(int result){
 static const char *names[]={"ok","rearmed","skipped-foreground","not-isp","failed","unreadable"};
 return result>=0&&result<=5?names[result]:"unknown";
}
static inline int vconf_api(char *(**get)(const char*),int (**set)(const char*,const char*)){
 void *vc=dlopen("libvconf.so.0",RTLD_NOW|RTLD_LOCAL);if(!vc)return 0;
 *(void**)get=dlsym(vc,"vconf_get_str");*(void**)set=dlsym(vc,"vconf_set_str");return *get&&*set;
}
/* Bounded helper for boots where native never started (normal init): poll every 15 s
 * for at most 15 minutes, stop after a re-arm or when nothing is needed. */
static inline int source_rearm_wait(void){
 char *(*get)(const char*)=0;int (*set)(const char*,const char*)=0;if(!vconf_api(&get,&set))return 10;
 for(int i=0;i<60;i++){
  alarm(10);RearmReport r=source_rearm(get,set,0);alarm(0);
  if(r.result!=REARM_UNREADABLE){printf("source-rearm %s previous=%s\n",rearm_name(r.result),r.previous);fflush(stdout);return r.result==REARM_FAILED?11:0;}
  sleep(15);
 }
 printf("source-rearm gave-up\n");return 12;
}
/* Explicit Home denied only by a non-ISP saved source (Live TV/TV Plus was used): Hub
 * still owns the ISP slot and the screen is on, so the caller may fall back to the web Hub
 * route and re-arm. Any other failed predicate keeps the plain denial. */

static inline int platform_consumer(const char *id, const char *pkg, int tv_plus) {
 if (!id) return 0;
 if (!strcmp(id,"org.tizen.netflix-app") || !strcmp(id,"org.tizen.primevideo") || !strcmp(id,"org.tizen.browser") ||
     (tv_plus && !strcmp(id,"com.samsung.tv.tvplus"))) return 1;
 if (!pkg || strlen(pkg)!=10) return 0;
 for (const char *p=pkg;*p;p++) if (!((*p>='0'&&*p<='9')||(*p>='A'&&*p<='Z')||(*p>='a'&&*p<='z'))) return 0;
 return 1;
}
/* Atomic CLOEXEC creation on Linux (the shipped targets). macOS test fallback. */
static inline int platform_cloexec(int fd) { return fcntl(fd,F_SETFD,FD_CLOEXEC); }
static inline int platform_pipe(int pair[2]) {
#ifdef __linux__
 return pipe2(pair,O_CLOEXEC);
#else
 if (pipe(pair)) return -1;
 if (!platform_cloexec(pair[0]) && !platform_cloexec(pair[1])) return 0;
 close(pair[0]);close(pair[1]);return -1;
#endif
}
static inline int platform_socketpair(int pair[2]) {
#ifdef __linux__
 return socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,pair);
#else
 if (socketpair(AF_UNIX,SOCK_STREAM,0,pair)) return -1;
 if (!platform_cloexec(pair[0]) && !platform_cloexec(pair[1])) return 0;
 close(pair[0]);close(pair[1]);return -1;
#endif
}
static inline int platform_spawn_app(pid_t *pid, const char *path, const char *id, const char *uid, int quiet, int silence) {
 extern char **environ;
 char *args[]={"app_launcher","-s",(char*)id,"-u",(char*)uid,quiet?"__NO_LOADING_LAUNCH":NULL,quiet?"enable":NULL,NULL};
 posix_spawn_file_actions_t actions;
 int rc=posix_spawn_file_actions_init(&actions);
 if (rc) return rc;
 if (silence) {
  rc=posix_spawn_file_actions_addopen(&actions,1,"/dev/null",O_WRONLY,0);
  if (!rc) rc=posix_spawn_file_actions_addopen(&actions,2,"/dev/null",O_WRONLY,0);
 }
 if (!rc) rc=posix_spawn(pid,path,&actions,NULL,args,environ);
 posix_spawn_file_actions_destroy(&actions);return rc;
}
#ifndef NORMAL_MODE_PATH
#define NORMAL_MODE_PATH "/tmp/init_mode_normal"
#endif
#ifndef NORMAL_BOOT_WAIT_LIMIT
#define NORMAL_BOOT_WAIT_LIMIT 120
#endif
#ifndef PLATFORM_APP_LAUNCHER
#define PLATFORM_APP_LAUNCHER "/usr/bin/app_launcher"
#endif
#define HUB_WEB_APP "MiniHub001.Hub"
static inline double platform_now(void) {
 struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;
}
/* Remote power-button restarts can begin in normal mode with the display still
 * in standby. Do not draw over standby or the TV viewer. Wait for lcdon, ask the
 * signed Hub to retire the viewer through Samsung's app lifecycle, then admit
 * only over that Hub. A different source, ISP owner or foreground app cancels.
 * This runs before EFL/Chromium initialization, bounded by both uptime and wall
 * time; it is not a new rule for manual entry or the early background path. */
enum { NORMAL_WAIT, NORMAL_LAUNCH, NORMAL_READY, NORMAL_CANCEL };
static int normal_state;
static inline int normal_settings_note(const char *source, const char *isp, const char *power, const char *fg) {
    normal_state = NORMAL_WAIT;
    if ((source && strcmp(source, REARM_SOURCE)) || (isp && strcmp(isp, HUB_WEB_APP)) ||
        (fg && *fg && strcmp(fg, HUB_WEB_APP) && strcmp(fg, TV_VIEWER))) normal_state = NORMAL_CANCEL;
    else if (source && isp && power && fg && !strcmp(power, "lcdon"))
        normal_state = !strcmp(fg, HUB_WEB_APP) ? NORMAL_READY : NORMAL_LAUNCH;
    return normal_state == NORMAL_READY;
}
static inline int normal_launch_web(void) {
    char uid[16]; snprintf(uid, sizeof uid, "%u", (unsigned)getuid());
    pid_t pid;
    int result = platform_spawn_app(&pid, PLATFORM_APP_LAUNCHER, HUB_WEB_APP, uid, 1, 1);
    if (result) return 0;
    double until = platform_now() + 8;
    for (;;) {
        int status = 0; pid_t r = waitpid(pid, &status, WNOHANG);
        if (r == pid) return WIFEXITED(status) && !WEXITSTATUS(status);
        if ((r < 0 && errno != EINTR) || platform_now() >= until) {
            kill(pid, SIGKILL);
            while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
            return 0;
        }
        struct timespec delay = { 0, 100000000 }; nanosleep(&delay, NULL);
    }
}
static inline int normal_boot_guard(void) {
    double up = ng_uptime();
    if (up < 0 || up >= 120 || !ng_marker()) return 0;
    double until = platform_now() + (120 - up < NORMAL_BOOT_WAIT_LIMIT ? 120 - up : NORMAL_BOOT_WAIT_LIMIT);
    alarm((unsigned)(until - platform_now()) + 2); /* Grace for the last bounded sleep. */
    ng_stamp("normal-boot-wait");
    double launch_due = 0; int submitted = 0;
    while (platform_now() < until && ng_marker()) {
        up = ng_uptime(); if (up < 0 || up >= 120) break;
        if (ng_display()) {
            normal_state = NORMAL_WAIT;
            int ready = native_settings_read_checked(normal_settings_note);
            if (normal_state == NORMAL_CANCEL) { ng_stamp("normal-boot-cancelled"); break; }
            if (ready) {
                /* The IPC can span the deadline or a cancellation. */
                if (platform_now() >= until || !ng_marker() || !ng_display()) break;
                alarm(0); ng_stamp("normal-boot-handoff-ready"); return 1;
            }
            if (normal_state == NORMAL_LAUNCH && !submitted && platform_now() >= launch_due && platform_now() + 9 < until) {
                submitted = normal_launch_web();
                ng_stamp(submitted ? "normal-boot-web-submitted" : "normal-boot-web-retry");
                launch_due = platform_now() + 5;
            }
        }
        struct timespec delay = { 0, 200000000 }; nanosleep(&delay, NULL);
    }
    alarm(0); return 0;
}
static inline int platform_boot_guard(void) {
    if (access(NORMAL_MODE_PATH, F_OK) == 0) return normal_boot_guard();
    return platform_early_boot_guard();
}


#endif
