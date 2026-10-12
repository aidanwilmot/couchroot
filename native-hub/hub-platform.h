/* TV API calls run in a separate exec'd worker, never in the Evas thread.
 * ABI: Tizen app-manager app_info callbacks, vconf and systemd (see README).
 * This channel is private to the parent/child; it is not a network listener. */
#include <stdbool.h>
#include <sys/socket.h>
#include <poll.h>
#define PLATFORM_MAGIC 0x43524832u
typedef struct { uint32_t magic, kind, size, status; } PlatformHeader;
typedef struct { int safe, source_rearm; char foreground[257]; } PlatformSnapshot;
static int (*platform_id)(void*,char**),(*platform_label)(void*,char**),(*platform_package)(void*,char**),(*platform_hidden)(void*,bool*),(*platform_component)(void*,int*);
static int consumer_app(const char *id,const char *pkg){
 /* Same consumer boundary as web/bridge.js, with TV Plus omitted for this
  * no-Live-TV trial. Samsung marks many internal tools nodisplay=false. */
 if(!strcmp(id,"org.tizen.netflix-app")||!strcmp(id,"org.tizen.primevideo")||!strcmp(id,"org.tizen.browser"))return 1;
 if(!pkg||strlen(pkg)!=10)return 0;
 for(const char *p=pkg;*p;p++)if(!((*p>='0'&&*p<='9')||(*p>='A'&&*p<='Z')||(*p>='a'&&*p<='z')))return 0;
 return 1;
}
static HubApp discovered[HUB_MAX];static int discovered_count,discovered_overflow;
static bool discover_app(void *app,void *unused){
 (void)unused;bool hidden=true;int component=-1;char *id=0,*name=0;
 if(platform_hidden(app,&hidden)||hidden||platform_component(app,&component)||component!=0)return true;
 if(platform_id(app,&id)||!id)return true;
 char *pkg=0;if(platform_package(app,&pkg)||!consumer_app(id,pkg)){free(pkg);free(id);return true;}free(pkg);
 if(platform_label(app,&name)||!name){free(id);return true;}
 HubApp value={0};
 if(strlen(id)<=256&&strlen(name)<=120){strcpy(value.id,id);strcpy(value.name,name);
  if(hub_valid(&value)){
   int duplicate=0;for(int i=0;i<discovered_count;i++)if(!strcmp(discovered[i].id,id))duplicate=1;
   if(!duplicate){if(discovered_count==HUB_MAX)discovered_overflow=1;else discovered[discovered_count++]=value;}
  }
 }
 free(id);free(name);return true;
}
static int compare_apps(const void *a,const void *b){const HubApp *x=a,*y=b;int c=strcmp(x->name,y->name);return c?c:strcmp(x->id,y->id);}
static int discover_apps(void){
 void *lib=dlopen("libcapi-appfw-app-manager.so.0",RTLD_NOW|RTLD_LOCAL);if(!lib)return 0;
 int (*foreach_app)(bool(*)(void*,void*),void*)=0;
 *(void**)(&foreach_app)=dlsym(lib,"app_manager_foreach_app_info");
 *(void**)(&platform_id)=dlsym(lib,"app_info_get_app_id");
 *(void**)(&platform_package)=dlsym(lib,"app_info_get_package");
 *(void**)(&platform_label)=dlsym(lib,"app_info_get_label");
 *(void**)(&platform_hidden)=dlsym(lib,"app_info_is_nodisplay");
 *(void**)(&platform_component)=dlsym(lib,"app_info_get_app_component_type");
 discovered_count=0;discovered_overflow=0;
 int ok=foreach_app&&platform_id&&platform_package&&platform_label&&platform_hidden&&platform_component&&foreach_app(discover_app,0)==0&&!discovered_overflow;
 if(ok)qsort(discovered,(size_t)discovered_count,sizeof(HubApp),compare_apps);
 dlclose(lib);return ok;
}
static int platform_write(int fd,const void *data,size_t size){
 const char *p=data;while(size){ssize_t n=write(fd,p,size);if(n<0&&errno==EINTR)continue;if(n<=0)return 0;p+=n;size-=(size_t)n;}return 1;
}
/* Explicit Home is allowed to leave an occupied app. Boot/automatic return
 * continue to require empty foreground through native_settings_match. */
static int home_settings_match(const char *source,const char *isp,const char *power,const char *foreground){
 return source&&isp&&power&&foreground&&!strcmp(source,"isp-service")&&!strcmp(isp,HUB_WEB)&&!strcmp(power,"lcdon");
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
static int rearm_decision(const char *isp,const char *last,const char *foreground){
 if(!isp||!last||!foreground)return REARM_UNREADABLE;
 if(strcmp(isp,HUB_WEB))return REARM_NOT_ISP;
 return strcmp(last,REARM_SOURCE)?REARM_NEEDED:REARM_OK;
}
/* probe: rewrite only an already-correct value, proving write access without change. */
static RearmReport source_rearm(char *(*get)(const char*),int (*set)(const char*,const char*),int probe){
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
static int vconf_api(char *(**get)(const char*),int (**set)(const char*,const char*)){
 void *vc=dlopen("libvconf.so.0",RTLD_NOW|RTLD_LOCAL);if(!vc)return 0;
 *(void**)get=dlsym(vc,"vconf_get_str");*(void**)set=dlsym(vc,"vconf_set_str");return *get&&*set;
}
/* Bounded helper for boots where native never started (normal init): poll every 15 s
 * for at most 15 minutes, stop after a re-arm or when nothing is needed. */
static int source_rearm_wait(void){
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
static int home_source_rearm;
static int home_settings_note(const char *source,const char *isp,const char *power,const char *foreground){
 home_source_rearm=source&&isp&&power&&foreground&&strcmp(source,REARM_SOURCE)&&!strcmp(isp,HUB_WEB)&&!strcmp(power,"lcdon");
 return home_settings_match(source,isp,power,foreground);
}
static int platform_worker(void){
 signal(SIGPIPE,SIG_IGN);
 char *(*get)(const char*)=0;int (*set)(const char*,const char*)=0;vconf_api(&get,&set);
 /* Keep these mappings warm for subsequent snapshots. */
 void *sd=dlopen("libsystemd.so.0",RTLD_NOW|RTLD_LOCAL);(void)sd;
 char command;while(read(3,&command,1)==1){
  alarm(5);PlatformHeader header={PLATFORM_MAGIC,(uint32_t)command,0,0};
  PlatformSnapshot snap={0};const void *payload=&snap;
  if(command=='D'){header.status=discover_apps()?0:1;header.size=header.status?0:(uint32_t)(discovered_count*sizeof(HubApp));payload=discovered;}
  else if(command=='S'||command=='H'){
   home_source_rearm=0;snap.safe=command=='H'?native_settings_read_checked(home_settings_note):native_settings_read();snap.source_rearm=command=='H'&&home_source_rearm;char *fg=get?get("memory/appfw/current_fullscreen_appid"):0;
   if(fg&&strlen(fg)<=256){strcpy(snap.foreground,fg);header.status=0;}else header.status=1;
   free(fg);header.size=sizeof(snap);
  }else if(command=='R'){static RearmReport report;report=source_rearm(get,set,0);header.status=0;header.size=sizeof(report);payload=&report;
  }else return 2;
  if(!platform_write(3,&header,sizeof(header))||!platform_write(3,payload,header.size))return 3;
  alarm(0);
 }return 0;
}
