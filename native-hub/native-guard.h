#ifndef NATIVE_GUARD_INCLUDED
#define NATIVE_GUARD_INCLUDED
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <signal.h>
#include <sys/stat.h>
#include <time.h>

/* Same predicates as the private boot wrapper. NULL is never empty foreground. */
static int native_settings_match(const char *source, const char *isp,
                                 const char *power, const char *foreground) {
    return source && isp && power && foreground &&
        !strcmp(source, "isp-service") && !strcmp(isp, "MiniHub001.Hub") &&
        !strcmp(power, "lcdon") && !strcmp(foreground, "");
}
static void ng_stamp(const char *event) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    printf("%s %.3f\n", event, t.tv_sec + t.tv_nsec / 1e9); fflush(stdout);
}
static double ng_uptime(void) {
    double value=-1; FILE *f=fopen("/proc/uptime", "r");
    if(f) { if(fscanf(f,"%lf",&value)!=1)value=-1; fclose(f); }
    return value;
}
static int ng_marker(void) {
    return access("/tmp/couchroot-early-hub-enabled", F_OK)==0;
}
static int ng_display(void) {
    struct stat s;
    return access("/run/.wm_ready", F_OK)==0 &&
        stat("/run/user/5001/wayland-0", &s)==0 && S_ISSOCK(s.st_mode);
}
/* Dynamic ABI declarations match libvconf and libsystemd's public C APIs. */
static int native_settings_read_checked(int (*match)(const char*,const char*,const char*,const char*)) {
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
    char *source=get_str("db/boot/last_service"); ng_stamp("native-source-read");
    char *isp=get_str("db/was/isp_app_id"); ng_stamp("native-isp-read");
    void *bus=NULL,*reply=NULL; const char *power=NULL;
    int rc=open_system(&bus);
    if(rc>=0)rc=set_timeout(bus,2000000);
    if(rc>=0)rc=call(bus,"org.tizen.system.deviced","/Org/Tizen/System/DeviceD/Display",
        "org.tizen.system.deviced.display","GetState",NULL,&reply,"");
    if(rc>=0)rc=read_reply(reply,"s",&power);
    if(rc<=0)power=NULL;
    ng_stamp("native-power-read");
    char *foreground=get_str("memory/appfw/current_fullscreen_appid");
    ng_stamp("native-foreground-read");
    printf("native-values source=%s isp=%s power=%s foreground=[%s]\n",
        source?source:"<missing>",isp?isp:"<missing>",power?power:"<missing>",foreground?foreground:"<missing>");
    int ok=match(source,isp,power,foreground);
    free(source); free(isp); free(foreground);
    if(reply)unref_message(reply); if(bus)unref_bus(bus);
    dlclose(sd); dlclose(vc); return ok;
missing:
    dlclose(sd); dlclose(vc); return 0;
}
static int native_settings_read(void) { return native_settings_read_checked(native_settings_match); }
static int native_boot_guard(void) {
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
#endif
