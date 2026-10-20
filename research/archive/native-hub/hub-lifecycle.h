/* Lifecycle decisions require observed foreground changes, never launch success
 * alone. Only safe, consecutive empty observations can reclaim the native window. */
typedef struct { int away, empty, waiting; double deadline; } HubLifecycle;
static HubLifecycle lifecycle;
static int lifecycle_observe(HubLifecycle *l,const PlatformSnapshot *s,int valid){
 if(!valid){l->empty=0;return 0;}
 if(s->foreground[0]){l->away=1;l->empty=0;l->waiting=0;return 0;}
 if(!s->safe){l->empty=0;return 0;}
 if(l->away&&++l->empty>=2){l->away=0;l->empty=0;l->waiting=0;return 1;}
 return 0;
}
static Obj *native_window,*native_input;
static pid_t platform_pid=-1;static int platform_fd=-1,platform_pending;
static double platform_due,platform_deadline,discovery_due;
static unsigned char platform_bytes[sizeof(PlatformHeader)+sizeof(HubApp)*HUB_MAX];
static size_t platform_used;static char self_path[1024];static int platform_started,catalog_live;
static int native_focused, native_lost_focus;
static int home_enabled,home_grabbed,home_requested,home_checking;
static double home_pressed=-1,home_until;
static int rearm_enabled,rearm_last=-1;static double rearm_due;
static int (*home_display)(void)=ng_display;
/* Home over Live TV leaves through the web Hub route, re-arms, then finishes the press.
 * One attempt at a time: LAUNCHING until app_launcher reports, REARMING until a re-arm
 * reply no longer names the viewer, RESUMING while the final H request is in flight.
 * `until` is fixed when the attempt starts; nothing extends it. Times are checked on
 * the 0.1 s UI tick, so they are nominal bounds, not real-time guarantees. */
enum {FALLBACK_IDLE,FALLBACK_LAUNCHING,FALLBACK_REARMING,FALLBACK_RESUMING};
#define FALLBACK_LAUNCH_SECONDS 10
#define FALLBACK_SECONDS 20
static struct { int state,fd; pid_t child,reap; double launch_deadline,until; } fallback={FALLBACK_IDLE,-1,-1,-1,0,0};
static void fallback_end(const char *event){
 /* Killing the launcher's group stops the client; it cannot retract a launch request
  * app_launcher already handed to the platform before the deadline. */
 if(fallback.child>0){kill(-fallback.child,SIGKILL);fallback.reap=fallback.child;fallback.child=-1;}
 if(fallback.fd>=0)close(fallback.fd);fallback.fd=-1;
 /* An in-flight resume reply must not later count as a fresh Home press. */
 if(fallback.state==FALLBACK_RESUMING){home_requested=0;home_until=0;}
 fallback.state=FALLBACK_IDLE;stamp(event);
}
static int fallback_start(double now){
 child_reap(&fallback.reap);
 if(fallback.state!=FALLBACK_IDLE||fallback.reap>0)return 0;
 pid_t child=launcher_spawn(HUB_WEB,&fallback.fd);if(child<0){stamp("native-home-fallback-failed");return 0;}
 fallback.child=child;fallback.state=FALLBACK_LAUNCHING;fallback.launch_deadline=now+FALLBACK_LAUNCH_SECONDS;fallback.until=now+FALLBACK_SECONDS;
 stamp("native-home-source-fallback");return 1;
}
static void fallback_poll(double now){
 child_reap(&fallback.reap);
 if(fallback.state==FALLBACK_IDLE)return;
 if(fallback.state==FALLBACK_LAUNCHING){
  unsigned char ok=0;ssize_t n=read(fallback.fd,&ok,1);
  if(n==1&&ok==1){close(fallback.fd);fallback.fd=-1;fallback.reap=fallback.child;fallback.child=-1;fallback.state=FALLBACK_REARMING;rearm_due=now;stamp("native-home-fallback-launched");}
  else if(n==1||n==0||(n<0&&errno!=EAGAIN&&errno!=EINTR)){fallback_end("native-home-fallback-failed");return;}
  else if(now>=fallback.launch_deadline){fallback_end("native-home-fallback-timeout");return;}
 }
 if(now>=fallback.until)fallback_end("native-home-resume-expired");
}
static void home_key_down(void){if(home_grabbed&&home_pressed<0)home_pressed=now_seconds();}
static void home_key_up(void){
 if(!home_grabbed||home_pressed<0)return;
 double now=now_seconds(),held=now-home_pressed;home_pressed=-1;
 if(held<0||held>1.5||home_requested||home_checking)return;
 if(fallback.state!=FALLBACK_IDLE){stamp("native-home-busy");return;}
 home_requested=1;home_until=now+3;platform_due=now;
 if(!platform_started){platform_started=1;discovery_due=now+1.7;stamp("platform-start-home");}
 stamp("native-home-request");
}
static void home_grab_start(void){
 if(!home_enabled||home_grabbed)return;
 Obj *(*get_window)(Obj*)=0;Bool (*grab)(Obj*,const char*,int,int,int,int)=0;
 *(void**)(&get_window)=dlsym(RTLD_DEFAULT,"ecore_evas_wayland2_window_get");
 *(void**)(&grab)=dlsym(RTLD_DEFAULT,"ecore_wl2_window_keygrab_set");
 Obj *win=get_window?get_window(native_window):0;
 /* QN90A 1.25.1: mode 3 confirmed as overridable exclusive by compositor.
  * Lifetime belongs to this Wayland connection; exit restores the old route. */
 home_grabbed=win&&grab&&grab(win,"XF86Home",0,0,0,3);
 stamp(home_grabbed?"native-home-grab-ready":"native-home-grab-unavailable");
}
static void home_grab_release(void){
 if(!home_grabbed)return;
 Obj *(*get_window)(Obj*)=0;Bool (*ungrab)(Obj*,const char*,int,int)=0;
 *(void**)(&get_window)=dlsym(RTLD_DEFAULT,"ecore_evas_wayland2_window_get");
 *(void**)(&ungrab)=dlsym(RTLD_DEFAULT,"ecore_wl2_window_keygrab_unset");
 Obj *win=get_window?get_window(native_window):0;
 if(win&&ungrab)ungrab(win,"XF86Home",0,0);
 home_grabbed=0;home_pressed=-1;stamp("native-home-grab-released");
}
static void native_focus_out(Obj *ee){(void)ee;native_focused=0;native_lost_focus=1;stamp("native-focus-out");}
static void native_focus_in(Obj *ee){
 (void)ee;native_focused=1;stamp("native-focus-in");
 if(native_lost_focus&&(lifecycle.away||lifecycle.waiting)){
  lifecycle=(HubLifecycle){0};hub.notice[0]=0;redraw();discovery_due=now_seconds()+1.5;stamp("native-return-focused");
 }
 native_lost_focus=0;
}
static void platform_close(void){
 /* A lost worker loses the in-flight resume request; re-arming survives a restart. */
 if(fallback.state==FALLBACK_RESUMING)fallback_end("native-home-resume-cancelled");
 home_grab_release();
 if(platform_fd>=0)close(platform_fd);platform_fd=-1;
 if(platform_pid>0){kill(platform_pid,SIGKILL);waitpid(platform_pid,0,WNOHANG);}platform_pid=-1;
 platform_pending=0;platform_used=0;lifecycle.empty=0;home_checking=0;home_requested=0;
}
static int platform_start(void){
 int pair[2];if(platform_socketpair(pair))return 0;
 fcntl(pair[0],F_SETFD,FD_CLOEXEC);fcntl(pair[1],F_SETFD,FD_CLOEXEC);
 platform_pid=fork();
 if(platform_pid==0){
  close(pair[0]);if(pair[1]!=3){if(dup2(pair[1],3)<0)_exit(126);close(pair[1]);}fcntl(3,F_SETFD,0);
  int null=open("/dev/null",O_WRONLY);if(null>=0){dup2(null,1);dup2(null,2);if(null!=3)close(null);}
  signal(SIGCHLD,SIG_DFL);sigset_t empty;sigemptyset(&empty);sigprocmask(SIG_SETMASK,&empty,0);
  execl(self_path,self_path,"--platform-worker",(char*)0);_exit(127);
 }
 close(pair[1]);if(platform_pid<0){close(pair[0]);return 0;}
 platform_fd=pair[0];fcntl(platform_fd,F_SETFL,O_NONBLOCK);return 1;
}
static void apply_catalog(const HubApp *apps,int count){
 char focus_id[257]={0};if(hub.page==PICK&&hub.focus<hub.catalog_count)strcpy(focus_id,hub.catalog[hub.focus].id);
 memcpy(hub.catalog,apps,(size_t)count*sizeof(HubApp));hub.catalog_count=count;catalog_loaded=1;catalog_live=1;
 if(hub.page==PICK){int found=-1;for(int i=0;i<count;i++)if(!strcmp(focus_id,apps[i].id))found=i;hub.focus=found>=0?found:0;redraw();}
 stamp("catalog-discovered");printf("catalog-count %d\n",count);
}
static void platform_reply(PlatformHeader *h,const unsigned char *payload){
 if(h->kind=='D'){
  if(!h->status&&h->size%sizeof(HubApp)==0){int count=(int)(h->size/sizeof(HubApp));HubApp apps[HUB_MAX];memcpy(apps,payload,h->size);
   for(int i=0;i<count;i++){if(!memchr(apps[i].id,0,sizeof(apps[i].id))||!memchr(apps[i].name,0,sizeof(apps[i].name))||!hub_valid(&apps[i]))return;}
   apply_catalog(apps,count);
  }else{stamp("catalog-discovery-failed");if(hub.page==PICK){snprintf(hub.notice,sizeof(hub.notice),"Could not refresh apps. Your saved shortcuts are unchanged.");redraw();}}
  discovery_due=now_seconds()+60;return;
 }
 if(h->kind=='H'){
  home_checking=0;int resuming=fallback.state==FALLBACK_RESUMING;
  if(h->size!=sizeof(PlatformSnapshot)||h->status||now_seconds()>home_until){stamp("native-home-denied");if(resuming)fallback_end("native-home-resume-cancelled");return;}
  PlatformSnapshot snap;memcpy(&snap,payload,sizeof(snap));
  int named=memchr(snap.foreground,0,sizeof(snap.foreground))!=0,viewer=named&&!strcmp(snap.foreground,TV_VIEWER);
  if(resuming){
   /* Finish only over the web Hub this attempt opened (or nothing). Another foreground
    * means the owner moved on; never start a second fallback from a resume. Foreground
    * is a separate read from the safety snapshot and does not prove playback stopped. */
   if(!snap.safe||!named||(snap.foreground[0]&&strcmp(snap.foreground,HUB_WEB))||!home_display()){fallback_end("native-home-resume-cancelled");return;}
   fallback.state=FALLBACK_IDLE;
  }else if(fallback.state!=FALLBACK_IDLE){stamp("native-home-busy");return;}
  else if(rearm_enabled&&((!snap.safe&&snap.source_rearm)||(snap.safe&&viewer))&&named&&home_display()){
   /* Live TV in front, or a non-ISP saved source: request the web Hub through
    * app_launcher, re-arm, then finish this Home press if nothing else took over. */
   if(!fallback_start(now_seconds()))stamp("native-home-denied");
   return;
  }
  if(!snap.safe||!named||!home_display()){stamp("native-home-denied");return;}
  lifecycle=(HubLifecycle){0};home();
  ecore_evas_show(native_window);ecore_evas_raise(native_window);ecore_evas_activate(native_window);evas_object_focus_set(native_input,1);
  discovery_due=now_seconds()+1.5;stamp("native-home-activate");return;
 }
 if(h->kind=='R'){
  rearm_due=now_seconds()+15;if(h->size!=sizeof(RearmReport))return;
  RearmReport r;memcpy(&r,payload,sizeof(r));r.previous[sizeof(r.previous)-1]=0;
  if(r.result!=rearm_last||r.result==REARM_NEEDED||r.result==REARM_FAILED){stamp("source-rearm");printf("source-rearm %s previous=%s\n",rearm_name(r.result),r.previous);}
  rearm_last=r.result;
  if(fallback.state==FALLBACK_REARMING){
   double now=now_seconds();
   if(now>=fallback.until)fallback_end("native-home-resume-expired");
   else if((r.result==REARM_OK||r.result==REARM_NEEDED)&&!r.viewer){fallback.state=FALLBACK_RESUMING;home_requested=1;home_until=now+3;platform_due=now;stamp("native-home-resume");}
   else rearm_due=now+1;
  }
  return;
 }
 if(h->kind=='S'&&h->size==sizeof(PlatformSnapshot)){
  PlatformSnapshot snap;memcpy(&snap,payload,sizeof(snap));int valid=!h->status&&memchr(snap.foreground,0,sizeof(snap.foreground));
  if(valid)home_grab_start();
  /* Actual compositor focus can return before Samsung clears its app key.
   * A focus-in acknowledges an existing return; it does not raise a window. */
  if(native_focused){lifecycle.empty=0;return;}
  int was_away=lifecycle.away;
  if(lifecycle_observe(&lifecycle,&snap,valid)){
   stamp("native-return-safe");hub.notice[0]=0;redraw();ecore_evas_show(native_window);ecore_evas_raise(native_window);ecore_evas_activate(native_window);evas_object_focus_set(native_input,1);discovery_due=now_seconds()+1.5;
  }else if(!was_away&&lifecycle.away){stamp("app-foreground-observed");hub.notice[0]=0;}
 }
}
static void platform_poll(double now){
 if(!platform_started)return;
 if(platform_fd>=0&&platform_pending){
  ssize_t n=read(platform_fd,platform_bytes+platform_used,sizeof(platform_bytes)-platform_used);
  if(n>0)platform_used+=(size_t)n;
  else if(n==0||(n<0&&errno!=EAGAIN&&errno!=EINTR)){platform_close();platform_due=now+5;stamp("platform-worker-disconnected");return;}
  if(platform_used>=sizeof(PlatformHeader)){
   PlatformHeader h;memcpy(&h,platform_bytes,sizeof(h));
   if(h.magic!=PLATFORM_MAGIC||h.kind!=(uint32_t)platform_pending||h.size>sizeof(platform_bytes)-sizeof(h)){platform_close();platform_due=now+5;return;}
   if(platform_used==sizeof(h)+h.size){platform_pending=0;platform_reply(&h,platform_bytes+sizeof(h));platform_used=0;platform_due=home_requested?now:now+1;}
  }
  if(platform_pending&&now>=platform_deadline){platform_close();platform_due=now+5;stamp("platform-worker-timeout");}
 }
 if(!platform_pending&&now>=platform_due){
  if(platform_fd<0&&!platform_start()){platform_due=now+5;return;}
  char kind=home_requested?'H':rearm_enabled&&now>=rearm_due?'R':now>=discovery_due&&!lifecycle.waiting&&!lifecycle.away?'D':'S';
  if(kind=='H'){home_requested=0;home_checking=1;}
  if(send(platform_fd,&kind,1,0)!=1){platform_close();platform_due=now+5;return;}
  platform_pending=kind;platform_deadline=now+6;platform_used=0;
 }
 if(lifecycle.waiting&&now>=lifecycle.deadline){lifecycle.waiting=0;stamp("app-handoff-timeout");if(!launch_feedback_dismissed&&hub.page==launch_page)go(ERROR_PAGE,0);}
}
static Bool platform_begin(void *unused){(void)unused;if(!painted)return 1;if(platform_started)return 0;platform_started=1;platform_due=now_seconds();discovery_due=platform_due;stamp("platform-start-deferred");home_grab_start();return 0;}
