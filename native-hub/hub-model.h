#ifndef HUB_MODEL_H
#define HUB_MODEL_H
#include "../native/common/preferences.h"
typedef enum { HOME, EDIT, PICK, ACTIONS, MOVING, SETTINGS, RESET, ERROR_PAGE } HubPage;
typedef struct {
 HubSaved saved, draft; HubApp catalog[HUB_MAX], removed;
 int catalog_count, undo_at, focus, home_focus, move_at, target, dirty;
 HubPage page; char notice[180];
} Hub;
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
static void hub_init(Hub *h){memset(h,0,sizeof(*h));hub_defaults(&h->saved);h->undo_at=-1;h->catalog_count=2;memcpy(h->catalog,h->saved.apps,2*sizeof(HubApp));}
#endif
