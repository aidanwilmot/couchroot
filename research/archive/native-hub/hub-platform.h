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
/* Preserve this launcher's no-Live-TV policy pending owner review. */
static int consumer_app(const char *id,const char *pkg){return platform_consumer(id,pkg,0);}
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
