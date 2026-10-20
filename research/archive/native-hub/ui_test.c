/* Headless Evas contract harness: behavior tests and scene snapshots, not a TV emulator. */
#define HUB_LAUNCHER "/usr/bin/false"
#define main native_main
#include "prototype.c"
#undef main
#include <assert.h>
/* Mock vconf for the saved-source re-arm. */
static char mock_isp[64],mock_last[64],mock_fg[64];static int mock_sets,mock_set_fail,mock_set_ignored;
static char *mock_vget(const char *k){const char *v=!strcmp(k,"db/was/isp_app_id")?mock_isp:!strcmp(k,"db/boot/last_service")?mock_last:!strcmp(k,"memory/appfw/current_fullscreen_appid")?mock_fg:0;return v&&strcmp(v,"<null>")?strdup(v):0;}
static int mock_vset(const char *k,const char *v){mock_sets++;if(mock_set_fail)return -1;if(!mock_set_ignored&&!strcmp(k,"db/boot/last_service"))snprintf(mock_last,sizeof(mock_last),"%s",v);return 0;}
static void mock_source(const char *isp,const char *last,const char *fg){snprintf(mock_isp,64,"%s",isp);snprintf(mock_last,64,"%s",last);snprintf(mock_fg,64,"%s",fg);mock_sets=mock_set_fail=mock_set_ignored=0;}
typedef struct {int live,visible,x,y,w,h,r,g,b,a,size,n,bold;long seq;int points[160][2];char value[512];} Mock;
static Mock objects[1024];static int quits;static long mock_seq;
static Obj *mock_add(Obj *unused){(void)unused;for(int i=0;i<1024;i++)if(!objects[i].live){memset(&objects[i],0,sizeof(Mock));objects[i].live=1;objects[i].a=255;objects[i].seq=++mock_seq;return &objects[i];}abort();}
static void mock_del(Obj *o){((Mock*)o)->live=0;}
static void mock_show(Obj *o){((Mock*)o)->visible=1;}
static void mock_move(Obj *o,int x,int y){((Mock*)o)->x=x;((Mock*)o)->y=y;}
static void mock_resize(Obj *o,int w,int h){((Mock*)o)->w=w;((Mock*)o)->h=h;}
static void mock_color(Obj *o,int r,int g,int b,int a){assert(r<=a&&g<=a&&b<=a);((Mock*)o)->r=r;((Mock*)o)->g=g;((Mock*)o)->b=b;((Mock*)o)->a=a;}
static void mock_font(Obj *o,const char *font,int size){((Mock*)o)->bold=strstr(font,"Bold")!=0;((Mock*)o)->size=size;}
static void mock_text(Obj *o,const char *s){snprintf(((Mock*)o)->value,512,"%s",s);}
static void mock_geometry(Obj *o,int *x,int *y,int *w,int *h){
 Mock *m=o;double units=0;
 for(const unsigned char *p=(unsigned char*)m->value;*p;p++){
  if((*p&0xc0)==0x80)continue;
  units+=*p>=128?.85:strchr("ilIjt ",*p)?.278:strchr("MWmw",*p)?.82:(m->bold&&strchr("pbd",*p))?.611:(*p>='A'&&*p<='Z')?(m->bold?.69:.66):strchr("+=<>",*p)?.584:.556;
 }
 if(x)*x=m->x;if(y)*y=m->y;if(w)*w=(int)(units*m->size);if(h)*h=m->size*12/10;
}
static void mock_point(Obj *o,int x,int y){Mock *m=o;assert(m->n<160);m->points[m->n][0]=x;m->points[m->n++][1]=y;}
static void mock_quit(void){quits++;}
/* Mock window activation and Home fallback replies; the launcher is a local stand-in. */
static int activations;
static void mock_window(Obj *o){(void)o;}
static void mock_activate(Obj *o){(void)o;activations++;}
static void mock_focus(Obj *o,Bool on){(void)o;(void)on;}
static int mock_display(void){return 1;}
static void home_reply(const char *fg,int safe){PlatformHeader h={PLATFORM_MAGIC,'H',sizeof(PlatformSnapshot),0};PlatformSnapshot s={.safe=safe};snprintf(s.foreground,sizeof(s.foreground),"%s",fg);home_checking=1;home_requested=0;platform_reply(&h,(const unsigned char*)&s);}
static void rearm_reply(int result,int viewer){PlatformHeader h={PLATFORM_MAGIC,'R',sizeof(RearmReport),0};RearmReport r={result,viewer,"vc-service"};platform_reply(&h,(const unsigned char*)&r);}
static void fallback_settle(void){for(int i=0;i<300&&(fallback.state==FALLBACK_LAUNCHING||fallback.reap>0);i++){struct timespec pause={0,10000000};nanosleep(&pause,0);fallback_poll(now_seconds());}}
static pid_t fallback_begin(void){home_until=now_seconds()+3;home_reply(TV_VIEWER,1);assert(fallback.state==FALLBACK_LAUNCHING&&fallback.child>0);return fallback.child;}
static void escape(FILE *f,const char *s){for(;*s;s++){if(*s=='&')fputs("&amp;",f);else if(*s=='<')fputs("&lt;",f);else if(*s=='>')fputs("&gt;",f);else fputc(*s,f);}}
static void snapshot(const char *dir,const char *name){if(!dir)return;printf("scene %s: %d objects\n",name,scene_count);char path[1024];snprintf(path,sizeof(path),"%s/%s.svg",dir,name);FILE *f=fopen(path,"w");assert(f);fputs("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1920\" height=\"1080\" viewBox=\"0 0 1920 1080\"><rect width=\"1920\" height=\"1080\" fill=\"#111212\"/>",f);
 Mock *order[1024];int count=0;for(int i=0;i<1024;i++)if(objects[i].live&&objects[i].visible){int j=count++;while(j&&order[j-1]->seq>objects[i].seq){order[j]=order[j-1];j--;}order[j]=objects+i;}
 for(int i=0;i<count;i++){Mock *m=order[i];int a=m->a?m->a:1;
 if(m->n){fprintf(f,"<polygon fill=\"rgb(%d,%d,%d)\" fill-opacity=\"%.3f\" points=\"",m->r*255/a,m->g*255/a,m->b*255/a,m->a/255.0);for(int j=0;j<m->n;j++)fprintf(f,"%d,%d ",m->points[j][0],m->points[j][1]);fputs("\"/>",f);}
 else if(m->value[0]){fprintf(f,"<text x=\"%d\" y=\"%d\" font-size=\"%d\" font-family=\"Arial, sans-serif\" font-weight=\"%s\" fill=\"rgb(%d,%d,%d)\">",m->x,m->y+m->size,m->size,m->bold?"bold":"normal",m->r,m->g,m->b);escape(f,m->value);fputs("</text>",f);}}
 fputs("</svg>",f);fclose(f);
}
int main(int argc,char **argv){
 evas_object_polygon_add=mock_add;evas_object_polygon_point_add=mock_point;evas_object_del=mock_del;evas_object_show=mock_show;evas_object_move=mock_move;evas_object_resize=mock_resize;evas_object_color_set=mock_color;evas_object_text_add=mock_add;evas_object_text_font_set=mock_font;evas_object_text_text_set=mock_text;evas_object_geometry_get=mock_geometry;ecore_main_loop_quit=mock_quit;
 char dir[]="/tmp/couchroot-native-test-XXXXXX";assert(mkdtemp(dir));snprintf(state_path,sizeof(state_path),"%s/state",dir);
 hub_init(&hub);redraw();const char *out=argc>1?argv[1]:0;snapshot(out,"home");
 /* Back stays home, grid boundaries do not wrap, focus-only movement reuses all scene objects. */
 ui_key("Escape");assert(hub.page==HOME);int count=scene_count;Obj *first=scene[0];ui_key("Right");assert(hub.focus==1&&scene_count==count&&scene[0]==first);ui_key("Right");assert(hub.focus==1);
 ui_key("Down");assert(hub.focus==2);ui_key("Return");assert(hub.page==EDIT);
 ui_key("Down");ui_key("Return");assert(hub.page==ACTIONS);ui_key("Return");assert(hub.page==MOVING);
 ui_key("Right");assert(!strcmp(hub.draft.apps[1].name,"Plex"));snapshot(out,"moving");ui_key("Escape");assert(!strcmp(hub.saved.apps[0].name,"Plex"));
 go(EDIT,1);activate();activate();ui_key("Right");activate();assert(!strcmp(hub.saved.apps[1].name,"Plex"));
 /* Remove, intervening settings save, undo restore exact position. */
 go(EDIT,2);activate();go(ACTIONS,1);activate();assert(hub.saved.count==1&&hub.undo_at==1);
 go(SETTINGS,0);activate();assert(hub.saved.compact);snapshot(out,"settings");undo_remove();assert(hub.saved.count==2&&!strcmp(hub.saved.apps[1].name,"Plex"));
 /* Utility focus changes preserve the list objects and refresh only preview.
  * Back restores the invoking footer even after favorite count changes. */
 home();hub.focus=hub.saved.count+2;activate();assert(hub.page==SETTINGS);Obj *row_obj=scene[1];ui_key("Down");assert(scene[1]==row_obj);activate();assert(hub.saved.clock==1);activate();assert(hub.saved.clock==2);snapshot(out,"clock-24");HubSaved clock_saved;assert(hub_load(&clock_saved,state_path)&&clock_saved.clock==2);ui_key("Escape");assert(hub.focus==hub.saved.count+2);
 go(EDIT,1);snapshot(out,"edit-preview");
 /* Failed mutations leave saved data intact and do not consume undo. */
 char saved_path[1024];strcpy(saved_path,state_path);strcpy(state_path,"/no/such/couchroot/state");go(EDIT,1);activate();go(ACTIONS,1);activate();assert(hub.saved.count==2);strcpy(state_path,saved_path);
 HubSaved loaded;assert(hub_load(&loaded,state_path));assert(loaded.count==2&&loaded.compact);
 /* Reset cancellation and reset preserve independent preferences. */
 go(RESET,0);activate();assert(hub.saved.compact);go(RESET,1);activate();assert(hub.saved.compact&&hub.saved.count==2&&!strcmp(hub.saved.apps[0].name,"Plex"));
 /* Last partial grid row, long catalog scrolling and empty state. */
 hub.saved.count=HUB_MAX;for(int i=0;i<HUB_MAX;i++){snprintf(hub.saved.apps[i].id,257,"test.%d",i);snprintf(hub.saved.apps[i].name,121,"Application %d",i);hub.catalog[i]=hub.saved.apps[i];}hub.catalog_count=HUB_MAX;catalog_loaded=1;
 go(HOME,127);ui_key("Down");assert(hub.focus==128);ui_key("Up");assert(hub.focus==127);snapshot(out,"many");
 go(PICK,0);for(int i=0;i<127;i++)ui_key("Down");assert(hub.focus==127);snapshot(out,"picker");
 hub.saved.count=0;hub.saved.selected=0;go(HOME,0);snapshot(out,"empty");activate();assert(hub.page==PICK);
 go(ERROR_PAGE,0);snapshot(out,"error");ui_key("Escape");assert(hub.page==HOME);
 hub_init(&hub);hub.saved.count=1;home();assert(bh[0]<720);snapshot(out,"single");
 /* Corrupt preferences survive selection movement; only an explicit edit replaces them. */
 preferences_invalid=1;hub.dirty=0;hub.saved.count=2;home();ui_key("Right");assert(!hub.dirty);preferences_invalid=0;
 /* A real child failure returns through the timer, duplicate submission is
  * rejected, and a stalled pipe is bounded. No firmware launcher runs here. */
 hub_init(&hub);home();launch_app(hub.saved.apps[0].id);assert(pending_launch);pid_t active=launch_child;launch_app(HUB_WEB);assert(launch_child==active);
 for(int i=0;i<100&&pending_launch;i++){struct timespec pause={0,10000000};nanosleep(&pause,0);tick(0);}assert(!pending_launch&&hub.page==ERROR_PAGE&&quits==0);
 home();launch_app(HUB_WEB);ui_key("Right");assert(hub.focus==1);ui_key("Escape");for(int i=0;i<100&&pending_launch;i++){struct timespec pause={0,10000000};nanosleep(&pause,0);tick(0);}assert(!pending_launch&&hub.page==HOME);launch_feedback_dismissed=0;launch_page=HOME;
 int stalled[2];assert(pipe(stalled)==0);fcntl(stalled[0],F_SETFL,O_NONBLOCK);launch_fd=stalled[0];pending_launch=1;launch_child=-1;launch_deadline=0;tick(0);close(stalled[1]);assert(!pending_launch&&hub.page==ERROR_PAGE);
 /* Bounded/strict state parser: malformed/truncated/duplicate data stays rejected. */
 FILE *f=fopen(state_path,"w");assert(f);fputs("COUCHROOT1 0 0 0 0\ntest.a\tA\ntest.a\tB\n",f);fclose(f);assert(!hub_load(&loaded,state_path));
 unlink(state_path);assert(symlink("/dev/null",state_path)==0);assert(!hub_load(&loaded,state_path));unlink(state_path);rmdir(dir);
 assert(hub_step(5,7,3,0,1)==6);assert(hub_step(6,7,3,1,0)==6);
 /* Return requires a real away transition and two fresh, safe empty states. */
 HubLifecycle life={0};PlatformSnapshot snap={0};snap.safe=1;
 assert(!lifecycle_observe(&life,&snap,1));assert(!lifecycle_observe(&life,&snap,1));
 strcpy(snap.foreground,"test.video");assert(!lifecycle_observe(&life,&snap,1)&&life.away);
 snap.foreground[0]=0;snap.safe=0;assert(!lifecycle_observe(&life,&snap,1));snap.safe=1;
 assert(!lifecycle_observe(&life,&snap,1));assert(!lifecycle_observe(&life,&snap,0));
 assert(!lifecycle_observe(&life,&snap,1));assert(lifecycle_observe(&life,&snap,1));assert(!life.away);
 assert(consumer_app("org.tizen.netflix-app","org.tizen.netflix-app"));
 assert(consumer_app("kIciSQlYEM.plex","kIciSQlYEM"));
 assert(!consumer_app("com.samsung.tv.tvplus","com.samsung.tv.tvplus"));
 assert(!consumer_app("org.tizen.factory","org.tizen.factory"));
 /* Live discovery retains the focused catalog identity and Home toolbar. */
 hub_init(&hub);go(PICK,1);HubApp reordered[]={hub.catalog[1],hub.catalog[0]};apply_catalog(reordered,2);assert(hub.focus==0&&!strcmp(hub.catalog[0].name,"YouTube"));
 home();hub.focus=hub.saved.count+2;apply_catalog(reordered,2);assert(hub.page==HOME&&hub.focus==hub.saved.count+2);
 /* Compositor return does not require stale framework data to become empty.
  * This path acknowledges focus already granted; it never raises the window. */
 lifecycle=(HubLifecycle){.away=1,.waiting=1};native_lost_focus=1;native_focus_in(0);assert(native_focused&&!lifecycle.away&&!lifecycle.waiting);
 native_focus_out(0);assert(!native_focused&&native_lost_focus);
 /* Stale framework foreground must not re-lock a compositor-focused Hub. */
 PlatformHeader reply={PLATFORM_MAGIC,'S',sizeof(PlatformSnapshot),0};
 PlatformSnapshot stale={0};strcpy(stale.foreground,"test.exited-app");
 native_focused=1;lifecycle=(HubLifecycle){0};
 platform_reply(&reply,(const unsigned char*)&stale);assert(!lifecycle.away&&!lifecycle.waiting);
 /* Failed discovery keeps the last valid catalog and all saved favorites. */
 HubSaved kept=hub.saved;int kept_count=hub.catalog_count;
 PlatformHeader failed={PLATFORM_MAGIC,'D',0,1};
 platform_reply(&failed,0);assert(hub.catalog_count==kept_count&&!memcmp(&kept,&hub.saved,sizeof(kept)));

 /* Home is explicit, opt-in, debounced and never admits Live TV/off/missing state. */
 assert(home_settings_match("isp-service",HUB_WEB,"lcdon","test.video"));
 assert(!home_settings_match("tv",HUB_WEB,"lcdon","test.video"));
 assert(!home_settings_match("isp-service",HUB_WEB,"lcdoff","test.video"));
 assert(!home_settings_match("isp-service",HUB_WEB,"lcdon",0));
 assert(!native_settings_match("isp-service",HUB_WEB,"lcdon","test.video"));
 home_grabbed=0;home_requested=0;home_pressed=-1;home_key_down();home_key_up();assert(!home_requested);
 home_grabbed=1;home_key_up();assert(!home_requested);home_key_down();double pressed=home_pressed;home_key_down();assert(home_pressed==pressed);home_key_up();assert(home_requested);
 home_requested=0;home_checking=0;home_pressed=now_seconds()-2;home_key_up();assert(!home_requested);
 home_grabbed=0;home_pressed=-1;
 /* Late/failed Home replies must not activate a window or clear away state. */
 lifecycle=(HubLifecycle){.away=1};home_until=0;
 PlatformHeader late={PLATFORM_MAGIC,'H',sizeof(PlatformSnapshot),0};PlatformSnapshot ready={.safe=1};
 platform_reply(&late,(const unsigned char*)&ready);assert(lifecycle.away);
 home_until=now_seconds()+3;late.status=1;
 platform_reply(&late,(const unsigned char*)&ready);assert(lifecycle.away);
 lifecycle=(HubLifecycle){0};
 /* Home over Live TV: one bounded, cancellable web fallback at a time. */
 ecore_evas_show=mock_window;ecore_evas_raise=mock_window;ecore_evas_activate=mock_activate;evas_object_focus_set=mock_focus;home_display=mock_display;rearm_enabled=1;
 char tools[]="/tmp/couchroot-native-launcher-XXXXXX";assert(mkdtemp(tools));char launcher_ok[1100],launcher_fail[1100],stall[1100];
 const char *stand_ins[][2]={{"ok","exit 0"},{"fail","exit 1"},{"stall","exec sleep 30"}};char *paths[]={launcher_ok,launcher_fail,stall};
 for(int i=0;i<3;i++){snprintf(paths[i],1100,"%s/%s",tools,stand_ins[i][0]);FILE *sf=fopen(paths[i],"w");assert(sf);fprintf(sf,"#!/bin/sh\n%s\n",stand_ins[i][1]);fclose(sf);assert(chmod(paths[i],0700)==0);}
 /* Launcher failure ends the attempt; a later re-arm does not resume it. */
 hub_launcher=launcher_fail;activations=0;fallback_begin();fallback_settle();
 assert(fallback.state==FALLBACK_IDLE&&fallback.child<0&&fallback.reap<0&&fallback.fd<0);
 rearm_reply(REARM_NEEDED,0);assert(!home_requested&&!activations);
 /* A stalled launcher is killed with its process group at the launch deadline.
  * An inherited pipe proves both supervisor and launcher have exited, without
  * depending on when the OS reaps an orphan zombie/process-group record. */
 int live[2];assert(pipe(live)==0);assert(fcntl(live[0],F_SETFL,O_NONBLOCK)==0);
 char ready_path[1100];snprintf(ready_path,sizeof(ready_path),"%s/ready",tools);
 FILE *sf=fopen(stall,"w");assert(sf);fprintf(sf,"#!/bin/sh\nprintf ready > '%s'\nexec sleep 30\n",ready_path);fclose(sf);
 hub_launcher=stall;pid_t group=fallback_begin();close(live[1]);fallback_poll(now_seconds());assert(fallback.state==FALLBACK_LAUNCHING);
 for(int i=0;i<500&&access(ready_path,F_OK);i++){struct timespec pause={0,10000000};nanosleep(&pause,0);}
 assert(access(ready_path,F_OK)==0);assert(getpgid(group)==group);
 char byte;assert(read(live[0],&byte,1)<0&&errno==EAGAIN);
 fallback_poll(fallback.launch_deadline);assert(fallback.state==FALLBACK_IDLE&&fallback.child<0&&fallback.reap==group);fallback_settle();assert(fallback.reap<0);
 ssize_t remaining=-1;
 for(int i=0;i<500;i++){remaining=read(live[0],&byte,1);if(remaining==0)break;assert(remaining<0&&errno==EAGAIN);struct timespec pause={0,10000000};nanosleep(&pause,0);}
 assert(remaining==0);close(live[0]);unlink(ready_path);
 rearm_reply(REARM_OK,0);assert(!home_requested&&!activations);
 /* Repeated Home neither overlaps attempts nor extends the fixed deadline; the
  * resume waits for a re-arm without the viewer, then finishes over the web Hub. */
 hub_launcher=launcher_ok;pid_t attempt=fallback_begin();double until=fallback.until;
 home_grabbed=1;home_pressed=-1;home_key_down();home_key_up();assert(!home_requested);
 home_until=now_seconds()+3;home_reply(TV_VIEWER,1);assert(fallback.child==attempt&&fallback.until==until);
 home_until=now_seconds()+3;home_reply(HUB_WEB,1);assert(!activations&&fallback.state==FALLBACK_LAUNCHING);home_grabbed=0;
 fallback_settle();assert(fallback.state==FALLBACK_REARMING&&fallback.until==until);
 rearm_reply(REARM_NEEDED,1);assert(fallback.state==FALLBACK_REARMING&&!home_requested);
 rearm_reply(REARM_OK,0);assert(fallback.state==FALLBACK_RESUMING&&home_requested&&fallback.until==until);
 home_reply(HUB_WEB,1);assert(activations==1&&fallback.state==FALLBACK_IDLE);
 /* A newly selected app, or the viewer again, cancels the resume without a second attempt. */
 activations=0;fallback_begin();fallback_settle();rearm_reply(REARM_OK,0);home_reply("test.video",1);assert(!activations&&fallback.state==FALLBACK_IDLE);
 fallback_begin();fallback_settle();rearm_reply(REARM_OK,0);home_reply(TV_VIEWER,1);assert(!activations&&fallback.state==FALLBACK_IDLE&&fallback.child<0);
 /* Worker restart: re-arming survives it; a lost resume request is cancelled and its late reply ignored. */
 fallback_begin();fallback_settle();platform_close();assert(fallback.state==FALLBACK_REARMING);
 rearm_reply(REARM_OK,0);assert(fallback.state==FALLBACK_RESUMING);platform_close();assert(fallback.state==FALLBACK_IDLE&&!home_requested);
 home_reply(HUB_WEB,1);assert(!activations&&fallback.state==FALLBACK_IDLE&&fallback.child<0);
 /* Expiry while re-arming or resuming is final, including for an in-flight resume reply. */
 fallback_begin();fallback_settle();fallback_poll(fallback.until);assert(fallback.state==FALLBACK_IDLE);rearm_reply(REARM_OK,0);assert(!home_requested);
 fallback_begin();fallback_settle();rearm_reply(REARM_OK,0);fallback_poll(fallback.until);assert(fallback.state==FALLBACK_IDLE&&!home_requested);
 home_reply(HUB_WEB,1);assert(!activations&&fallback.state==FALLBACK_IDLE);
 for(int i=0;i<3;i++)unlink(paths[i]);rmdir(tools);hub_launcher=HUB_LAUNCHER;rearm_enabled=0;home_display=ng_display;
 puts("native Home fallback: failure, timeout, repeated Home, worker restart, expiry and foreground change passed");
 /* Worst visible case: twelve branded cards. Repeated navigation must not
  * allocate new card objects, grow the scene, or cross its fixed capacity. */
 hub_init(&hub);hub.saved.compact=1;hub.saved.count=12;
 /* Card styles match exact ids only; unknown and near-miss ids use the fallback. */
 assert(card_style("9Ur5IzDKqV.TizenYouTube")!=card_style("9Ur5IzDKqV.TizenYouTube.extra")&&card_style("x.unknown")==card_style("y.unknown"));
 for(int i=0;i<CARD_STYLE_COUNT;i++){const CardStyle *c=card_style(card_styles[i].id);assert(c==&card_styles[i]&&c->shapes<=CARD_MAX_SHAPES&&c->split<4&&!(c->split&&c->play));for(int j=0;j<c->shapes;j++)assert(c->shape[j].n>=3&&c->shape[j].n<=CARD_MAX_POINTS);
  int before=scene_count;card_art(0,0,393,221,c->id);wordmark(0,0,393,221,36,"Any app",c->id);assert(scene_count-before<=CARD_MAX_OBJECTS);while(scene_count>before)evas_object_del(scene[--scene_count]);}
 for(int i=0;i<12;i++){const CardStyle *c=&card_styles[i%CARD_STYLE_COUNT];snprintf(hub.saved.apps[i].id,257,"%s",c->id);snprintf(hub.saved.apps[i].name,121,"%s",c->word[0]?c->word:"Any app");}
 home();int scene_bound=scene_count;assert(scene_bound<450);Obj *retained_card=scene[0];
 for(int i=0;i<10000;i++){ui_key(i%2?"Left":"Right");assert(scene_count==scene_bound&&scene[0]==retained_card);}
 snapshot(out,"compact-brands");
 printf("native scene: %d objects for twelve branded cards; 10000 focus moves retained the cards\n",scene_bound);
 /* Design snapshots only (no assertions): the owner's six-shortcut Home with the clock,
  * footer focus with Undo and a notice, and the picker over a real catalog. */
 if(out){hub_init(&hub);hub.saved.count=6;hub.saved.clock=1;hub.saved.selected=1;
  const char *six[][2]={{"kIciSQlYEM.plex","Plex"},{"9Ur5IzDKqV.TizenYouTube","YouTube"},{"MCmYXNxgcu.DisneyPlus","Disney+"},{"S9nU6P0m8Q.APM","Amazon Music"},{"OGLLvqej7u.CrunchyrollWebApp","Crunchyroll"},{"org.tizen.primevideo","Prime Video"}};
  for(int i=0;i<6;i++){snprintf(hub.saved.apps[i].id,257,"%s",six[i][0]);snprintf(hub.saved.apps[i].name,121,"%s",six[i][1]);}
  home();snapshot(out,"home-six");
  hub.undo_at=2;snprintf(hub.notice,sizeof(hub.notice),"Opening app…");redraw();hub.focus=7;focus_ring();snapshot(out,"home-footer");hub.undo_at=-1;
  /* Names come from the same style entry as each id, so preview art always matches its row. */
  for(int i=0;i<CARD_STYLE_COUNT&&i<HUB_MAX;i++){snprintf(hub.catalog[i].id,257,"%s",card_styles[i].id);snprintf(hub.catalog[i].name,121,"%s",card_styles[i].word[0]?card_styles[i].word:"Any app");}
  hub.catalog_count=CARD_STYLE_COUNT;catalog_loaded=1;go(PICK,2);snprintf(hub.notice,sizeof(hub.notice),"Added to Home");redraw();snapshot(out,"picker-real");go(ACTIONS,0);snapshot(out,"actions");go(RESET,1);snapshot(out,"reset");go(SETTINGS,1);snapshot(out,"settings-clock");}
 /* Optional profiler: off by default; parsers classify state, syscall and wait channel. */
 assert(!prof_enabled);pstamp("must-not-print");
 assert(prof_state("123 (native hub) S 1 2")=='S'&&prof_state("9 (a) b) R 1")=='R'&&prof_state("bad")=='?');
 assert(prof_syscall_nr("168 0x1 0x2")==168&&prof_syscall_nr("running")==-2&&prof_syscall_nr("-1 0xbe")==-1&&prof_syscall_nr("")==-3);
 ProfBucket pb;memset(&pb,0,sizeof(pb));prof_count(&pb,'R',-1,"");prof_count(&pb,'S',168,"poll_schedule_timeout");prof_count(&pb,'S',168,"poll_schedule_timeout");prof_count(&pb,'D',54,"kbase_ioctl");
 for(int i=0;i<40;i++)prof_count(&pb,'S',1000+i,"w");
 assert(pb.n==44&&pb.r==1&&pb.s==42&&pb.d==1&&pb.sys_nr[0]==168&&pb.sys_n[0]==2&&pb.sys_nr[1]==54&&pb.wchan_n[0]==2&&!strcmp(pb.wchan[1],"kbase_ioctl"));
 FILE *pf=tmpfile();assert(pf);prof_print_bucket(pf,"phase",&pb);rewind(pf);char pline[512];assert(fgets(pline,sizeof(pline),pf));fclose(pf);
 assert(!strncmp(pline,"samp phase n=44 R=1 D=1 S=42 other=0 sys168=2 sys54=1",52)&&strstr(pline," w:poll_schedule_timeout=2 w:kbase_ioctl=1"));
 /* Saved-source re-arm: only when Hub owns ISP; deliberately regardless of the foreground app, including the viewer. */
 assert(rearm_decision("MiniHub001.Hub","vc-service","")==REARM_NEEDED&&rearm_decision("MiniHub001.Hub","vc-service","MiniHub001.Hub")==REARM_NEEDED);
 assert(rearm_decision("MiniHub001.Hub","vc-service","org.tizen.tv-viewer")==REARM_NEEDED&&rearm_decision("MiniHub001.Hub","tv-service","9Ur5IzDKqV.TizenYouTube")==REARM_NEEDED);
 assert(rearm_decision("MiniHub001.Hub","isp-service","org.tizen.tv-viewer")==REARM_OK&&rearm_decision("","vc-service","")==REARM_NOT_ISP&&rearm_decision("Other.App","vc-service","")==REARM_NOT_ISP);
 assert(rearm_decision(0,"vc-service","")==REARM_UNREADABLE&&rearm_decision("MiniHub001.Hub",0,"")==REARM_UNREADABLE&&rearm_decision("MiniHub001.Hub","vc-service",0)==REARM_UNREADABLE);
 mock_source("MiniHub001.Hub","vc-service","");RearmReport rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_NEEDED&&mock_sets==1&&!strcmp(mock_last,"isp-service")&&!strcmp(rr.previous,"vc-service"));
 mock_source("MiniHub001.Hub","vc-service","org.tizen.tv-viewer");rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_NEEDED&&rr.viewer&&mock_sets==1&&!strcmp(mock_last,"isp-service"));
 mock_source("MiniHub001.Hub","vc-service","MiniHub001.Hub");rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_NEEDED&&!rr.viewer);
 mock_source("MiniHub001.Hub","isp-service","");rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_OK&&!mock_sets);
 mock_source("MiniHub001.Hub","vc-service","");mock_set_fail=1;rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_FAILED);
 mock_source("MiniHub001.Hub","vc-service","");mock_set_ignored=1;rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_FAILED);
 mock_source("MiniHub001.Hub","isp-service","");rr=source_rearm(mock_vget,mock_vset,1);assert(rr.result==REARM_OK&&mock_sets==1&&!strcmp(mock_last,"isp-service"));
 mock_source("MiniHub001.Hub","vc-service","");rr=source_rearm(mock_vget,mock_vset,1);assert(rr.result==REARM_NEEDED&&!mock_sets&&!strcmp(mock_last,"vc-service"));
 mock_source("<null>","vc-service","");rr=source_rearm(mock_vget,mock_vset,0);assert(rr.result==REARM_UNREADABLE&&!mock_sets);
 assert(source_rearm(0,mock_vset,0).result==REARM_UNREADABLE);
 /* Home source fallback flag: only a non-ISP source with the Hub ISP slot and LCD on. */
 assert(!home_settings_note("vc-service","MiniHub001.Hub","lcdon","org.tizen.tv-viewer")&&home_source_rearm);
 assert(home_settings_note("isp-service","MiniHub001.Hub","lcdon","x")&&!home_source_rearm);
 assert(!home_settings_note("vc-service","MiniHub001.Hub","lcdoff","")&&!home_source_rearm);
 assert(!home_settings_note("vc-service","","lcdon","")&&!home_source_rearm&&!home_settings_note(0,"MiniHub001.Hub","lcdon","")&&!home_source_rearm);
 /* Review snapshots: the owner's six-tile Home and every card style at the compact size. */
 hub_init(&hub);const char *owner[][2]={{"kIciSQlYEM.plex","Plex"},{"9Ur5IzDKqV.TizenYouTube","YouTube"},{"MCmYXNxgcu.DisneyPlus","Disney+"},{"S9nU6P0m8Q.APM","Amazon Music"},{"OGLLvqej7u.CrunchyrollWebApp","Crunchyroll"},{"org.tizen.primevideo","Prime Video"}};
 hub.saved.count=6;for(int i=0;i<6;i++){snprintf(hub.saved.apps[i].id,257,"%s",owner[i][0]);snprintf(hub.saved.apps[i].name,121,"%s",owner[i][1]);}
 go(HOME,1);printf("owner home: %d scene objects for six branded cards (+3 focus objects)\n",scene_count);snapshot(out,"owner-home");ui_key("Down");ui_key("Right");snapshot(out,"owner-home-focus");
 for(int sheet=0;sheet*16<CARD_STYLE_COUNT;sheet++){
  if(ring){evas_object_del(ring);ring=0;}for(int k=0;k<2;k++)if(ring_extra[k]){evas_object_del(ring_extra[k]);ring_extra[k]=0;}
  for(int i=0;i<scene_count;i++)evas_object_del(scene[i]);scene_count=0;buttons=0;clock_label=0;hub.page=HOME;hub.saved.count=16;
  for(int i=0;i<16&&sheet*16+i<CARD_STYLE_COUNT;i++){const CardStyle *c=&card_styles[sheet*16+i];int x=116+(i%4)*(393+38),y=40+(i/4)*(221+30);
   snprintf(hub.saved.apps[i].id,257,"%s",c->id);bx[i]=x;by[i]=y;bw[i]=393;bh[i]=221;buttons=i+1;card_art(x,y,393,221,c->id);wordmark(x,y,393,221,36,!strcmp(c->id,"*default*")?"Unknown Application Name":c->word,c->id);}
  hub.focus=5;focus_ring();char name[32];snprintf(name,sizeof(name),"tiles-%d",sheet+1);snapshot(out,name);}
 puts("native source re-arm: decision matrix, write readback, probe and failure handling passed");
 puts("native profiler: disabled by default; state, syscall and wait-channel accounting passed");
 puts("native UI: navigation, persistence, failure, edit, undo, paging and scene checks passed");return 0;
}
