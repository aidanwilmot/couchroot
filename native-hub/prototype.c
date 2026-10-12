/* Bounded QN90A experiment. EFL legacy ABI: ecore_evas/evas/ecore 1.25.
 * Uses the TV's libraries through dlopen; no firmware libraries redistributed.
 * Optional Home-only grab after first render; no source/package changes or network access.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <stdint.h>
#include <signal.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/wait.h>
/* Bullseye's ARM fcntl default symbol is GLIBC_2.28. QN90A needs the
 * legacy interface; our commands only use integer flags, never flock64. */
#if defined(__linux__) && defined(__arm__) && defined(__GLIBC__)
__asm__(".symver fcntl, fcntl@GLIBC_2.4");
#endif
#ifndef NATIVE_GUARD_INCLUDED
#include "native-guard.h"
#endif
#include "hub-profile.h"
typedef void Obj;
typedef unsigned char Bool;
typedef struct { char *keyname; } KeyPrefix; /* Only the documented first field is read. */
#define FN(ret,name,args) static ret (*name) args
FN(int,ecore_evas_init,(void)); FN(int,ecore_evas_shutdown,(void));
FN(void,ecore_main_loop_begin,(void)); FN(void,ecore_main_loop_quit,(void));
FN(Obj*,ecore_evas_new,(const char*,int,int,int,int,const char*));
FN(Obj*,ecore_evas_get,(Obj*)); FN(void,ecore_evas_show,(Obj*)); FN(void,ecore_evas_free,(Obj*));
FN(void,ecore_evas_title_set,(Obj*,const char*)); FN(void,ecore_evas_name_class_set,(Obj*,const char*,const char*)); FN(void,ecore_evas_fullscreen_set,(Obj*,Bool));
FN(Obj*,evas_object_rectangle_add,(Obj*)); FN(Obj*,evas_object_text_add,(Obj*));
FN(void,evas_object_color_set,(Obj*,int,int,int,int)); FN(void,evas_object_move,(Obj*,int,int)); FN(void,evas_object_resize,(Obj*,int,int));
FN(void,evas_object_show,(Obj*)); FN(void,evas_object_focus_set,(Obj*,Bool)); FN(void,evas_object_text_font_set,(Obj*,const char*,int)); FN(void,evas_object_text_text_set,(Obj*,const char*));
FN(void,evas_object_event_callback_add,(Obj*,int,void(*)(void*,Obj*,Obj*,void*),const void*));
FN(Bool,evas_object_key_grab,(Obj*,const char*,uint64_t,uint64_t,Bool));
FN(void*,ecore_timer_add,(double,Bool(*)(void*),const void*));
FN(void,ecore_evas_callback_focus_in_set,(Obj*,void(*)(Obj*)));
FN(void,ecore_evas_callback_focus_out_set,(Obj*,void(*)(Obj*)));
FN(void,ecore_evas_raise,(Obj*)); FN(void,ecore_evas_activate,(Obj*));
FN(void,ecore_evas_callback_post_render_set,(Obj*,void(*)(Obj*)));
FN(Obj*,evas_object_polygon_add,(Obj*));
FN(void,ecore_evas_callback_pre_render_set,(Obj*,void(*)(Obj*)));
FN(void,evas_object_polygon_point_add,(Obj*,int,int));
FN(void,evas_object_del,(Obj*));
FN(void,evas_object_geometry_get,(Obj*,int*,int*,int*,int*));
static int painted;
static void stamp(const char *event){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);printf("%s %.3f\n",event,t.tv_sec+t.tv_nsec/1e9);fflush(stdout);prof_milestone(event);}
/* Extra milestones only when COUCHROOT_NATIVE_PROFILE=1; default output is unchanged. */
static void pstamp(const char *event){if(prof_enabled)stamp(event);}
#ifndef HUB_LAUNCHER
#define HUB_LAUNCHER "/usr/bin/app_launcher"
#endif
#include "hub-ui.h"
static void home_grab_start(void);
static int pre_painted;static void pre_paint(Obj *ee){(void)ee;if(!pre_painted++)pstamp("first-pre-render");}
static void paint(Obj *ee){(void)ee;if(!painted++){stamp("first-render-complete");home_grab_start();prof_finish();}}
/* A child supervisor owns waitpid; Ecore can reap our supervisor without losing
 * app_launcher status. It reports one byte (1 accepted, 2 failed) on a nonblocking
 * pipe, and its own process group lets a deadline kill supervisor and launcher together. */
static const char *hub_launcher=HUB_LAUNCHER;
static pid_t launcher_spawn(const char *id,int *fd){
 int fds[2];if(pipe(fds))return -1;
 fcntl(fds[0],F_SETFL,O_NONBLOCK);fcntl(fds[0],F_SETFD,FD_CLOEXEC);fcntl(fds[1],F_SETFD,FD_CLOEXEC);
 pid_t child=fork();
 if(child==0){
  close(fds[0]);setpgid(0,0);signal(SIGCHLD,SIG_DFL);
  sigset_t empty;sigemptyset(&empty);sigprocmask(SIG_SETMASK,&empty,0);
  pid_t app=fork();if(app==0){close(fds[1]);execl(hub_launcher,"app_launcher","-s",id,"-u","5001","__NO_LOADING_LAUNCH","enable",(char*)0);_exit(127);}
  int status=0;pid_t r=-1;if(app>0)do{r=waitpid(app,&status,0);}while(r<0&&errno==EINTR);
  unsigned char ok=(r==app&&r>0&&WIFEXITED(status)&&WEXITSTATUS(status)==0)?1:2;
  if(write(fds[1],&ok,1)<0)_exit(3);close(fds[1]);_exit(0);
 }
 close(fds[1]);if(child<0){close(fds[0]);return -1;}
 setpgid(child,child);*fd=fds[0];return child;
}
/* Nonblocking reap of a finished or killed supervisor; Ecore may already have reaped it. */
static void child_reap(pid_t *pid){
 if(*pid<=0)return;pid_t r=waitpid(*pid,0,WNOHANG);
 if(r==*pid||(r<0&&errno!=EINTR))*pid=-1;
}
#include "hub-platform.h"
#include "hub-lifecycle.h"
static pid_t launch_child=-1;static int launch_fd=-1;static double launch_deadline;
static void launch_app(const char *id){
 if(pending_launch||lifecycle.waiting||lifecycle.away)return;
 if(id!=launch_id)snprintf(launch_id,sizeof(launch_id),"%s",id);
 launch_child=launcher_spawn(launch_id,&launch_fd);if(launch_child<0){go(ERROR_PAGE,0);return;}
 pending_launch=1;launch_page=hub.page;launch_feedback_dismissed=0;launch_deadline=now_seconds()+10;
 stamp("remote-launch-request");snprintf(hub.notice,sizeof(hub.notice),"Opening app…");redraw();
}
static Bool tick(void *unused){
 (void)unused;double now=now_seconds();clock_update();fallback_poll(now);platform_poll(now);
 if(pending_launch){unsigned char ok=0;ssize_t n=read(launch_fd,&ok,1);int failed=n==0||(n<0&&errno!=EAGAIN&&errno!=EINTR);
  if(n==1||failed||now>=launch_deadline){
   if(n!=1&&launch_child>0)kill(-launch_child,SIGKILL);
   close(launch_fd);launch_fd=-1;pending_launch=0;waitpid(launch_child,0,WNOHANG);launch_child=-1;
   if(n==1&&ok==1){stamp("app-launch-accepted");if(hub.dirty)hub_store(&hub.saved,state_path);lifecycle.waiting=strcmp(launch_id,HUB_HOME)!=0;lifecycle.deadline=now+10;platform_due=now;}
   else{stamp("app-launch-failed");if(!launch_feedback_dismissed&&hub.page==launch_page)go(ERROR_PAGE,0);}
  }
 }
 if(hub.dirty&&now>=selection_due){hub.dirty=0;if(!hub_store(&hub.saved,state_path)){snprintf(hub.notice,sizeof(hub.notice),"Selection could not be saved");redraw();}}
 return 1;
}
static Bool load_catalog(void *unused){
 (void)unused;if(!catalog_path[0])return 0;
 int fd=open(catalog_path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;struct stat st;
 if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size>50000){close(fd);return 0;}
 FILE *f=fdopen(fd,"r");if(!f){close(fd);return 0;}HubApp apps[HUB_MAX];int count=0;
 if(hub_read_apps(f,apps,&count)&&count){memcpy(hub.catalog,apps,(size_t)count*sizeof(HubApp));hub.catalog_count=count;catalog_loaded=1;}
 fclose(f);if(hub.page==PICK){if(hub.focus>=hub.catalog_count)hub.focus=0;redraw();}return 0;
}
static void key(void *data,Obj *c,Obj *obj,void *info){(void)data;(void)c;(void)obj;KeyPrefix *e=info;if(e&&e->keyname){if(!strcmp(e->keyname,"XF86Home"))home_key_down();else ui_key(e->keyname);}}
static void key_up(void *data,Obj *c,Obj *obj,void *info){(void)data;(void)c;(void)obj;KeyPrefix *e=info;if(e&&e->keyname&&!strcmp(e->keyname,"XF86Home"))home_key_up();}
static Bool deadline(void *unused){(void)unused;stamp("deadline-exit");ecore_main_loop_quit();return 0;}
#define LOAD(name) do{*(void**)(&name)=dlsym(RTLD_DEFAULT,#name);if(!name){fprintf(stderr,"missing %s\n",#name);return 3;}}while(0)
int main(int argc,char **argv){
if(argc==2&&!strcmp(argv[1],"--platform-worker"))return platform_worker();
if(argc==2&&!strcmp(argv[1],"--source-rearm-wait"))return source_rearm_wait();
if(argc==2&&!strcmp(argv[1],"--source-rearm-probe")){char *(*get)(const char*)=0;int (*set)(const char*,const char*)=0;if(!vconf_api(&get,&set))return 10;alarm(10);RearmReport r=source_rearm(get,set,1);printf("source-rearm-probe %s previous=%s\n",rearm_name(r.result),r.previous);return r.result==REARM_OK?0:11;}
if(argc==2&&!strcmp(argv[1],"--platform-diagnostics")){alarm(8);int ok=discover_apps();printf("discovery %d count %d\n",ok,discovered_count);for(int i=0;i<discovered_count;i++)printf("%s\t%s\n",discovered[i].id,discovered[i].name);return ok?0:10;}
if(strlen(argv[0])>=sizeof(self_path)||argv[0][0]!='/')return 11;strcpy(self_path,argv[0]);signal(SIGPIPE,SIG_IGN);stamp("main-entered");
if(argc==2&&!strcmp(argv[1],"--settings-check")){alarm(10);return native_settings_read()?0:8;}
setvbuf(stdout,0,_IOLBF,0);prof_start();if(!dlopen("libecore_evas.so.1",RTLD_NOW|RTLD_GLOBAL)){fprintf(stderr,"%s\n",dlerror());return 2;}
stamp("libraries-loaded");
LOAD(ecore_evas_callback_focus_in_set);LOAD(ecore_evas_callback_focus_out_set);LOAD(ecore_evas_raise);LOAD(ecore_evas_activate);LOAD(evas_object_polygon_add);LOAD(evas_object_polygon_point_add);LOAD(evas_object_del);LOAD(evas_object_geometry_get);LOAD(ecore_evas_init);LOAD(ecore_evas_shutdown);LOAD(ecore_main_loop_begin);LOAD(ecore_main_loop_quit);LOAD(ecore_evas_new);LOAD(ecore_evas_get);LOAD(ecore_evas_show);LOAD(ecore_evas_free);LOAD(ecore_evas_title_set);LOAD(ecore_evas_name_class_set);LOAD(ecore_evas_fullscreen_set);LOAD(evas_object_rectangle_add);LOAD(evas_object_text_add);LOAD(evas_object_color_set);LOAD(evas_object_move);LOAD(evas_object_resize);LOAD(evas_object_show);LOAD(evas_object_focus_set);LOAD(evas_object_text_font_set);LOAD(evas_object_text_text_set);LOAD(evas_object_event_callback_add);LOAD(evas_object_key_grab);LOAD(ecore_timer_add);LOAD(ecore_evas_callback_post_render_set);
if(argc>1&&!strcmp(argv[1],"--check")){stamp("symbols-ready");return 0;}
stamp("symbols-ready");
/* Trial-controlled final admission runs after library loading, before any window. */
if(argc>=2&&!strcmp(argv[1],"--warm-guard")){
 alarm(10);if(!ng_display()||!native_settings_read()||!ng_display())return 8;alarm(0);stamp("warm-admission-passed");
}
if(argc>=2&&!strcmp(argv[1],"--native-guard")){
 if(!native_boot_guard()){stamp("admission-denied");return 8;}
 stamp("admission-passed");
}
if(argc>=3&&!strcmp(argv[1],"--guard")){
 sigset_t blocked,previous;sigemptyset(&blocked);sigaddset(&blocked,SIGCHLD);
 if(sigprocmask(SIG_BLOCK,&blocked,&previous)!=0)return 8;
 pid_t guard=fork();
 if(guard==0){sigprocmask(SIG_SETMASK,&previous,0);execl("/bin/sh","sh","-c",argv[2],(char*)0);_exit(127);}
 int status=0;pid_t result=-1;
 if(guard>0){do{result=waitpid(guard,&status,0);}while(result<0&&errno==EINTR);}
 sigprocmask(SIG_SETMASK,&previous,0);
 if(result!=guard||result<=0||!WIFEXITED(status)||WEXITSTATUS(status)!=0){stamp("admission-denied");return 8;}
 stamp("admission-passed");
}
if(ecore_evas_init()<1)return 5;stamp("canvas-initialized");
const char *engine=getenv("ECORE_EVAS_ENGINE");if(!engine)engine="wayland_egl";
if(strcmp(engine,"wayland_egl")&&strcmp(engine,"wayland_shm"))return 9;
printf("render-engine %s\n",engine);
Obj *ee=ecore_evas_new(engine,0,0,1920,1080,0);if(!ee)return 6;stamp("window-created");
ecore_evas_title_set(ee,"Couchroot Native Trial");ecore_evas_name_class_set(ee,"couchroot-native-trial","Couchroot");ecore_evas_fullscreen_set(ee,1);pstamp("window-configured");
Obj *e=ecore_evas_get(ee);if(!e)return 7;
Obj *bg=evas_object_rectangle_add(e);evas_object_color_set(bg,17,18,18,255);evas_object_resize(bg,1920,1080);evas_object_show(bg);
native_window=ee;native_input=bg;canvas=e;hub_init(&hub);
const char *prefs=getenv("COUCHROOT_NATIVE_STATE"),*catalog=getenv("COUCHROOT_NATIVE_CATALOG");
if(prefs&&strlen(prefs)<sizeof(state_path))strcpy(state_path,prefs);
if(catalog&&strlen(catalog)<sizeof(catalog_path))strcpy(catalog_path,catalog);
if(state_path[0]){if(access(state_path,F_OK)==0&&!hub_load(&hub.saved,state_path)){preferences_invalid=1;snprintf(hub.notice,sizeof(hub.notice),"Saved native preferences could not be read; edits replace them, navigation does not");}}
else snprintf(hub.notice,sizeof(hub.notice),"Preview mode · saving is unavailable until native storage is configured");
hub.focus=hub.saved.first?0:hub.saved.selected;hub.home_focus=hub.focus;redraw();pstamp("scene-built");
/* Evas 1.25 legacy enum: EVAS_CALLBACK_KEY_DOWN = 10. */
evas_object_event_callback_add(bg,10,key,0);evas_object_event_callback_add(bg,11,key_up,0);
const char *home_flag=getenv("COUCHROOT_NATIVE_HOME");home_enabled=home_flag&&!strcmp(home_flag,"1");
const char *rearm_flag=getenv("COUCHROOT_NATIVE_SOURCE_REARM");rearm_enabled=rearm_flag&&!strcmp(rearm_flag,"1");
const char *keys[]={"Left","Right","Up","Down","Return","KP_Enter","Escape","XF86Back"};for(int i=0;i<8;i++)printf("local-key-grab %s %d\n",keys[i],evas_object_key_grab(bg,keys[i],0,0,0));
if(home_enabled)evas_object_key_grab(bg,"XF86Home",0,0,0);
pstamp("keys-grabbed");
evas_object_focus_set(bg,1);
ecore_evas_callback_post_render_set(ee,paint);
if(prof_enabled){*(void**)(&ecore_evas_callback_pre_render_set)=dlsym(RTLD_DEFAULT,"ecore_evas_callback_pre_render_set");if(ecore_evas_callback_pre_render_set)ecore_evas_callback_pre_render_set(ee,pre_paint);}
ecore_evas_callback_focus_in_set(ee,native_focus_in);ecore_evas_callback_focus_out_set(ee,native_focus_out);
if(!((argc==4&&!strcmp(argv[3],"--stay"))||(argc==3&&(!strcmp(argv[1],"--native-guard")||!strcmp(argv[1],"--warm-guard"))&&!strcmp(argv[2],"--stay"))))ecore_timer_add(45,deadline,0);
ecore_timer_add(0.1,tick,0);ecore_timer_add(1.5,load_catalog,0);ecore_timer_add(1.7,platform_begin,0);
ecore_evas_show(ee);stamp("window-show-requested");ecore_main_loop_begin();stamp("loop-exited");platform_close();if(fallback.state!=FALLBACK_IDLE)fallback_end("native-home-fallback-cancelled");if(pending_launch&&launch_child>0)kill(-launch_child,SIGKILL);if(launch_fd>=0)close(launch_fd);if(hub.dirty)hub_store(&hub.saved,state_path);ecore_evas_free(ee);ecore_evas_shutdown();return 0;}
