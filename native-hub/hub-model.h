/* Bounded native state. No EFL, platform APIs, networking or web storage writes. */
#ifndef HUB_MODEL_H
#define HUB_MODEL_H
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#define HUB_MAX 128
#define HUB_HOME "com.samsung.tv.csfs"
#define HUB_WEB "MiniHub001.Hub"
typedef struct { char id[257], name[121]; } HubApp;
typedef struct {
 HubApp apps[HUB_MAX]; int count, selected, compact, clock, first;
} HubSaved;
typedef enum { HOME, EDIT, PICK, ACTIONS, MOVING, SETTINGS, RESET, ERROR_PAGE } HubPage;
typedef struct {
 HubSaved saved, draft; HubApp catalog[HUB_MAX], removed;
 int catalog_count, undo_at, focus, home_focus, move_at, target, dirty;
 HubPage page; char notice[180];
} Hub;
static void hub_defaults(HubSaved *s) {
 memset(s,0,sizeof(*s)); s->count=2;
 strcpy(s->apps[0].id,"kIciSQlYEM.plex");strcpy(s->apps[0].name,"Plex");
 strcpy(s->apps[1].id,"9Ur5IzDKqV.TizenYouTube");strcpy(s->apps[1].name,"YouTube");
}
static int hub_valid(const HubApp *a) {
 size_t n=strlen(a->id); if(!n||n>256||!a->name[0]||!strcmp(a->id,HUB_HOME)||!strcmp(a->id,HUB_WEB))return 0;
 for(size_t i=0;i<n;i++)if(!((a->id[i]>='a'&&a->id[i]<='z')||(a->id[i]>='A'&&a->id[i]<='Z')||(a->id[i]>='0'&&a->id[i]<='9')||strchr("_.-",a->id[i])))return 0;
 for(const unsigned char *p=(const unsigned char*)a->name;*p;p++)if(*p<32||*p==127)return 0;
 return 1;
}
static int hub_has(const HubSaved *s,const char *id){for(int i=0;i<s->count;i++)if(!strcmp(s->apps[i].id,id))return 1;return 0;}
static int hub_columns(const HubSaved *s){return s->compact?4:s->count>2?3:s->count>0?s->count:1;}
static int hub_step(int at,int count,int cols,int dx,int dy) {
 if(!count)return 0;int next=at;
 if(dx<0&&at%cols)next--;if(dx>0&&at%cols<cols-1&&at+1<count)next++;
 if(dy<0&&at>=cols)next-=cols;if(dy>0&&at+cols<count)next+=cols;
 else if(dy>0&&at/cols<(count-1)/cols)next=count-1;
 return next;
}
static void hub_move(HubSaved *s,int from,int to){HubApp a=s->apps[from];if(to>from)memmove(s->apps+from,s->apps+from+1,(size_t)(to-from)*sizeof(a));else memmove(s->apps+to+1,s->apps+to,(size_t)(from-to)*sizeof(a));s->apps[to]=a;}
/* Private native state is separate from the web application's localStorage.
 * O_NOFOLLOW, bounded parsing and same-directory atomic rename avoid partial saves. */
static int hub_read_apps(FILE *f,HubApp *apps,int *count) {
 char line[400];*count=0;
 while(fgets(line,sizeof(line),f)) {
  size_t n=strlen(line);if(!n||line[n-1]!='\n'||*count==HUB_MAX)return 0;
  line[--n]=0;char *tab=strchr(line,'\t');if(!tab)return 0;*tab++=0;
  if(strlen(line)>256||strlen(tab)>120)return 0;
  HubApp a={0};strcpy(a.id,line);strcpy(a.name,tab);if(!hub_valid(&a))return 0;
  for(int i=0;i<*count;i++)if(!strcmp(apps[i].id,a.id))return 0;
  apps[(*count)++]=a;
 }return !ferror(f);
}
static int hub_load(HubSaved *s,const char *path) {
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;
 struct stat st;if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size>50000){close(fd);return 0;}
 FILE *f=fdopen(fd,"r");if(!f){close(fd);return 0;}
 HubSaved n={0};char line[100],tail;int ok=fgets(line,sizeof(line),f)&&sscanf(line,"COUCHROOT1 %d %d %d %d %c",&n.compact,&n.clock,&n.first,&n.selected,&tail)==4;
 ok=ok&&n.compact>=0&&n.compact<=1&&n.clock>=0&&n.clock<=2&&n.first>=0&&n.first<=1&&hub_read_apps(f,n.apps,&n.count);
 fclose(f);if(!ok||n.selected<0||n.selected>=(n.count?n.count:1))return 0;
 *s=n;return 1;
}
static int hub_store(const HubSaved *s,const char *path) {
 if(!path||!path[0])return 0;char temp[1024];if(snprintf(temp,sizeof(temp),"%s.XXXXXX",path)>=(int)sizeof(temp))return 0;
 int fd=mkstemp(temp);if(fd<0)return 0;FILE *f=fdopen(fd,"w");if(!f){close(fd);unlink(temp);return 0;}
 int ok=fprintf(f,"COUCHROOT1 %d %d %d %d\n",s->compact,s->clock,s->first,s->selected)>=0;
 for(int i=0;i<s->count;i++)if(fprintf(f,"%s\t%s\n",s->apps[i].id,s->apps[i].name)<0)ok=0;
 if(fflush(f)||fsync(fd))ok=0;if(fclose(f))ok=0;
 if(ok&&rename(temp,path))ok=0;if(!ok)unlink(temp);return ok;
}
static void hub_init(Hub *h){memset(h,0,sizeof(*h));hub_defaults(&h->saved);h->undo_at=-1;h->catalog_count=2;memcpy(h->catalog,h->saved.apps,2*sizeof(HubApp));}
#endif
