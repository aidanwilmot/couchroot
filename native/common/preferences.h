/* Shared bounded native preference format; web/model.js is the entry-rule reference. */
#ifndef COUCHROOT_PREFERENCES_H
#define COUCHROOT_PREFERENCES_H
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
static inline void hub_defaults(HubSaved *s) {
 memset(s,0,sizeof(*s)); s->count=2;
 strcpy(s->apps[0].id,"kIciSQlYEM.plex");strcpy(s->apps[0].name,"Plex");
 strcpy(s->apps[1].id,"9Ur5IzDKqV.TizenYouTube");strcpy(s->apps[1].name,"YouTube");
}
static inline int hub_valid(const HubApp *a) {
 size_t n=strlen(a->id); if(!n||n>256||!a->name[0]||!strcmp(a->id,HUB_HOME)||!strcmp(a->id,HUB_WEB))return 0;
 for(size_t i=0;i<n;i++)if(!((a->id[i]>='a'&&a->id[i]<='z')||(a->id[i]>='A'&&a->id[i]<='Z')||(a->id[i]>='0'&&a->id[i]<='9')||strchr("_.-",a->id[i])))return 0;
 if(strlen(a->name)>120)return 0;
 int text=0;
 for(const unsigned char *p=(const unsigned char*)a->name;*p;) {
  if(*p<32||*p==127)return 0;
  if(*p==' '){p++;continue;}
  if(p[0]==0xc2&&p[1]==0xa0){p+=2;continue;}
  if(p[0]==0xe1&&p[1]==0x9a&&p[2]==0x80){p+=3;continue;}
  if(p[0]==0xe2&&p[1]==0x80&&((p[2]>=0x80&&p[2]<=0x8a)||p[2]==0xa8||p[2]==0xa9||p[2]==0xaf)){p+=3;continue;}
  if(p[0]==0xe2&&p[1]==0x81&&p[2]==0x9f){p+=3;continue;}
  if(p[0]==0xe3&&p[1]==0x80&&p[2]==0x80){p+=3;continue;}
  if(p[0]==0xef&&p[1]==0xbb&&p[2]==0xbf){p+=3;continue;}
  text=1;p++;
 }
 if(!text)return 0;
 return 1;
}
/* Private native state is separate from the web application's localStorage.
 * O_NOFOLLOW, bounded parsing and same-directory atomic rename avoid partial saves. */
static inline int hub_read_apps(FILE *f,HubApp *apps,int *count) {
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
static inline int hub_load(HubSaved *s,const char *path) {
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;
 struct stat st;if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size>50000){close(fd);return 0;}
 FILE *f=fdopen(fd,"r");if(!f){close(fd);return 0;}
 HubSaved n={0};char line[100],tail;int ok=fgets(line,sizeof(line),f)&&sscanf(line,"COUCHROOT1 %d %d %d %d %c",&n.compact,&n.clock,&n.first,&n.selected,&tail)==4;
 ok=ok&&n.compact>=0&&n.compact<=1&&n.clock>=0&&n.clock<=2&&n.first>=0&&n.first<=1&&hub_read_apps(f,n.apps,&n.count);
 fclose(f);if(!ok||n.selected<0||n.selected>=(n.count?n.count:1))return 0;
 *s=n;return 1;
}
static inline int hub_store(const HubSaved *s,const char *path) {
 if(!path||!path[0])return 0;
 char temp[1024];
 if(snprintf(temp,sizeof(temp),"%s.XXXXXX",path)>=(int)sizeof(temp))return 0;
 int fd=mkstemp(temp);if(fd<0)return 0;FILE *f=fdopen(fd,"w");if(!f){close(fd);unlink(temp);return 0;}
 int ok=fprintf(f,"COUCHROOT1 %d %d %d %d\n",s->compact,s->clock,s->first,s->selected)>=0;
 for(int i=0;i<s->count;i++)if(fprintf(f,"%s\t%s\n",s->apps[i].id,s->apps[i].name)<0)ok=0;
 if(fflush(f)||fsync(fd))ok=0;
 if(fclose(f))ok=0;
 if(ok&&rename(temp,path))ok=0;
 if(!ok)unlink(temp);
 return ok;
}

#endif
