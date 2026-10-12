/* Native offline UI. Bounded scene, no animations, one moving focus ring. */
#include "hub-model.h"
#include <math.h>
static Hub hub;
static Obj *scene[512], *canvas, *ring; static int scene_count;
static int preview_start, home_return_focus, home_return_action=-1;
static void hints(void);
static int bx[140],by[140],bw[140],bh[140], buttons;
static char state_path[1024], catalog_path[1024];
static Obj *clock_label; static int clock_minute=-1;
static int preferences_invalid, catalog_loaded, launch_feedback_dismissed;
static HubPage launch_page;
static double selection_due;static int pending_launch;static char launch_id[257];
static void launch_app(const char *id);
static double now_seconds(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static Obj *remember(Obj *o){if(!o||scene_count>=512)exit(4);scene[scene_count++]=o;return o;}
static Obj *round_box(int x,int y,int w,int h,int radius,int r,int g,int b){
 Obj *o=remember(evas_object_polygon_add(canvas));
 for(int corner=0;corner<4;corner++)for(int step=0;step<=6;step++){
  double a=(-90+corner*90+step*15)*3.141592653589793/180;
  int cx=(corner==0||corner==1)?w-radius:radius,cy=corner<2?(corner==0?radius:h-radius):(corner==2?h-radius:radius);
  evas_object_polygon_point_add(o,x+cx+(int)(radius*cos(a)),y+cy+(int)(radius*sin(a)));
 }
 evas_object_color_set(o,r,g,b,255);evas_object_show(o);return o;
}
static Obj *label(int x,int y,int size,const char *s,int maxw,int muted){
 Obj *o=remember(evas_object_text_add(canvas));evas_object_text_font_set(o,"Sans",size);evas_object_text_text_set(o,s);
 int w,h;evas_object_geometry_get(o,0,0,&w,&h);while(w>maxw&&size>18){size--;evas_object_text_font_set(o,"Sans",size);evas_object_geometry_get(o,0,0,&w,&h);}
 if(w>maxw){char clipped[512];snprintf(clipped,sizeof(clipped),"%s",s);size_t n=strlen(clipped);while(w>maxw&&n){n--;while(n&&((unsigned char)clipped[n]&0xc0)==0x80)n--;clipped[n]=0;char shown[516];snprintf(shown,sizeof(shown),"%s…",clipped);evas_object_text_text_set(o,shown);evas_object_geometry_get(o,0,0,&w,&h);}}
 evas_object_move(o,x,y);evas_object_color_set(o,muted?168:240,muted?170:239,muted?158:229,255);evas_object_show(o);return o;
}
static void centered(int x,int y,int w,int h,int size,const char *s){
 Obj *o=label(0,0,size,s,w-(w<150?10:34),0);int tw,th;evas_object_geometry_get(o,0,0,&tw,&th);evas_object_move(o,x+(w-tw)/2,y+(h-th)/2);
}
static void button(int index,int x,int y,int w,int h,const char *s){
 bx[index]=x;by[index]=y;bw[index]=w;bh[index]=h;if(index>=buttons)buttons=index+1;
 round_box(x,y,w,h,h<70?h/2:16,31,33,29);if(w>=800)label(x+28,y+20,29,s,w-56,0);else centered(x,y,w,h,24,s);
}
static void contour(Obj *o,int x,int y,int w,int h,int radius,int reverse){
 for(int n=0;n<=28;n++){int j=reverse?28-n:n,corner=(j%28)/7,step=(j%28)%7;
  double a=(-90+corner*90+step*15)*3.141592653589793/180;
  int cx=corner<2?w-radius:radius,cy=(corner==1||corner==2)?h-radius:radius;
  evas_object_polygon_point_add(o,x+cx+(int)(radius*cos(a)),y+cy+(int)(radius*sin(a)));
 }
}
static void focus_ring(void){
 if(ring){evas_object_del(ring);ring=0;}int i=hub.focus;if(i<0||i>=buttons||!bw[i])return;
 ring=evas_object_polygon_add(canvas);int x=bx[i]-9,y=by[i]-9,w=bw[i]+18,h=bh[i]+18;
 contour(ring,x,y,w,h,30,0);contour(ring,x+4,y+4,w-8,h-8,26,1);
 evas_object_color_set(ring,240,229,205,255);evas_object_show(ring);
}
static void clock_update(void){if(!clock_label)return;time_t t=time(0);struct tm *tm=localtime(&t);if(!tm||clock_minute==tm->tm_min)return;clock_minute=tm->tm_min;char value[40];strftime(value,sizeof(value),hub.saved.clock==2?"%H:%M":"%I:%M %p",tm);evas_object_text_text_set(clock_label,value);}
#include "hub-art.h"
static void preview_panel(void);
static void redraw(void){
 if(ring){evas_object_del(ring);ring=0;}for(int i=0;i<scene_count;i++)evas_object_del(scene[i]);scene_count=0;clock_label=0;clock_minute=-1;buttons=0;memset(bw,0,sizeof(bw));
 HubSaved *s=hub.page==MOVING?&hub.draft:&hub.saved;
 if(hub.page==HOME||hub.page==MOVING){
  if(s->clock){clock_label=label(1630,65,26,"",220,1);clock_update();}
  if(hub.page==MOVING){char moving[180];snprintf(moving,sizeof(moving),"Move %s",s->apps[hub.move_at].name);label(120,65,34,moving,1300,0);snprintf(moving,sizeof(moving),"Position %d of %d",hub.move_at+1,s->count);label(1500,70,26,moving,300,1);}
  int cols=hub_columns(s),rows=s->compact?3:2,w=(1688-(cols-1)*38)/cols,h=w*9/16;
  if(cols==1) {w=820;h=w*9/16;}
  int row=hub.focus<s->count?hub.focus/cols:(hub.home_focus<s->count?hub.home_focus:0)/cols,top=row>=rows?row-rows+1:0;
  int visible=(s->count+cols-1)/cols;if(visible>rows)visible=rows;
  int y0=140+(720-(visible*h+(visible-1)*30))/2;if(y0<125)y0=125;
  for(int i=top*cols;i<s->count&&i<(top+rows)*cols;i++){
   int x=(cols==1?(1920-w)/2:116)+(i%cols)*(w+38),y=y0+(i/cols-top)*(h+30);
   bx[i]=x;by[i]=y;bw[i]=w;bh[i]=h;buttons=i+1;
   card_art(x,y,w,h,s->apps[i].id);
   wordmark(x,y,w,h,cols<3?76:cols==3?52:36,s->apps[i].name,s->apps[i].id);
  }
  if(!s->count){button(0,640,320,640,260,"+ Add apps");label(750,630,28,"Nothing on Home yet",600,1);}
  int base=s->count?s->count:1;
  if(hub.page==MOVING){button(base,116,940,230,65,"Cancel");button(base+1,374,940,280,65,"Save position");}
  else {button(base,120,973,156,58,"Edit apps");button(base+1,298,973,256,58,"Samsung Home");button(base+2,576,973,160,58,"Settings");button(base+3,758,973,166,58,"Web Hub");if(hub.undo_at>=0)button(base+4,946,973,202,58,"Undo remove");}
  if(top>0)label(1840,180,32,"↑",60,1);if((top+rows)*cols<s->count)label(1840,780,32,"↓",60,1);
 }else{
  const char *titles[]={"","Edit apps","Add apps","App actions","","Settings","Reset shortcuts?","Could not open app"};
  label(116,95,48,titles[hub.page],1660,0);
  char rows[132][160];int count=0;
  if(hub.page==EDIT){strcpy(rows[count++],"Add apps");for(int i=0;i<s->count;i++)snprintf(rows[count++],160,"%s",s->apps[i].name);}
  if(hub.page==PICK){for(int i=0;i<hub.catalog_count;i++)snprintf(rows[count++],160,"%s%s",hub_has(s,hub.catalog[i].id)?"Added · ":"+ ",hub.catalog[i].name);}
  if(hub.page==ACTIONS){strcpy(rows[count++],"Move");strcpy(rows[count++],"Remove from Home");strcpy(rows[count++],"Cancel");}
  if(hub.page==SETTINGS){snprintf(rows[count++],160,"Tile layout · %s",s->compact?"Compact":"Comfortable");snprintf(rows[count++],160,"Clock · %s",s->clock==2?"24 hour":s->clock==1?"12 hour":"Off");snprintf(rows[count++],160,"Start on · %s",s->first?"First favorite":"Last selected");strcpy(rows[count++],"Reset shortcuts");strcpy(rows[count++],"Advanced settings in Web Hub");}
  if(hub.page==RESET){strcpy(rows[count++],"Keep my shortcuts");strcpy(rows[count++],"Reset to Plex and YouTube");}
  if(hub.page==ERROR_PAGE){strcpy(rows[count++],"Back to apps");strcpy(rows[count++],"Retry");strcpy(rows[count++],"Samsung Home");}
  int top=hub.focus>=7?hub.focus-6:0;for(int i=top;i<count&&i<top+7;i++)button(i,116,215+(i-top)*94,900,76,rows[i]);
  buttons=count;
  if(top)label(1040,240,30,"↑",60,1);if(top+7<count)label(1040,795,30,"↓",60,1);
  preview_start=scene_count;
  preview_panel();
 }
 hints();focus_ring();
}
static void hints(void){
 if(hub.notice[0])label(120,905,24,hub.notice,1680,1);
 else {
  round_box(1210,982,142,40,10,31,33,29);centered(1210,982,142,40,22,"↑ ↓ ← →");
  label(1368,987,23,hub.page==MOVING?"Move":"Choose",135,1);
  round_box(1495,982,55,40,10,31,33,29);centered(1495,982,55,40,20,"OK");
  label(1565,987,23,hub.page==HOME?"Open":"Select",100,1);
  if(hub.page!=HOME){round_box(1670,982,80,40,10,31,33,29);centered(1670,982,80,40,20,"Back");label(1762,987,22,"Return",100,1);}
 }
}
static void preview_panel(void){
 const HubApp *app=0;
 if(hub.page==EDIT&&hub.focus>0&&hub.focus<=hub.saved.count)app=&hub.saved.apps[hub.focus-1];
 if(hub.page==PICK&&hub.focus<hub.catalog_count)app=&hub.catalog[hub.focus];
 if(hub.page==ACTIONS)app=&hub.saved.apps[hub.target];
 round_box(1110,215,690,590,22,25,28,24);
 if(app){card_art(1140,245,630,354,app->id);wordmark(1140,245,630,354,58,app->name,app->id);label(1140,646,30,app->name,620,0);label(1140,700,24,hub.page==PICK?(hub_has(&hub.saved,app->id)?"Already on Home":"OK adds this app to Home"):"Move it or remove its shortcut",620,1);return;}
 const char *title="Your apps, your order",*detail="Choose an app to preview it.";
 if(hub.page==RESET){title="Reset your Home shortcuts?";detail="Your other settings stay as they are.";}
 if(hub.page==ERROR_PAGE){title="The TV did not open this app";detail="Your shortcuts and settings are unchanged.";}
 if(hub.page==PICK){title="Add your favorites";detail=catalog_loaded?"Choose an app to add to your Home screen.":"Only default apps are available in this preview.";}
 if(hub.page==EDIT){title="Make room for your favorites";detail="Add apps without changing installed applications.";}
 if(hub.page==SETTINGS){const char *titles[]={"Space to settle in","A quiet clock","Pick up where you left off","Start fresh","More settings"};const char *details[]={"Comfortable: six tiles. Compact: twelve.","Show the time on your Home screen.","Remember your selection or start at the first app.","Reset shortcuts. Keep your other settings.","Open the installed web Hub for advanced settings."};title=titles[hub.focus];detail=details[hub.focus];
  if(hub.focus==0){int cols=hub.saved.compact?4:3,rows=hub.saved.compact?3:2;for(int i=0;i<cols*rows;i++)round_box(1170+(i%cols)*(550/cols),265+(i/cols)*95,500/cols,78,10,52,49,38);}
  else if(hub.focus==1)centered(1140,270,630,250,70,hub.saved.clock==2?"21:41":hub.saved.clock==1?"9:41 PM":"Clock off");
  else if(hub.focus==2)centered(1140,270,630,250,48,hub.saved.first?"First favorite":"Last selected");
  else centered(1140,270,630,250,64,hub.focus==3?"↺":"Web Hub");
 }else {centered(1140,285,630,200,70,hub.page==ERROR_PAGE?"!":hub.page==RESET?"↺":"+");}
 label(1140,605,32,title,620,0);label(1140,665,24,detail,620,1);
 if(hub.page==RESET){label(1140,718,24,"Plex and YouTube will replace your shortcuts.",620,1);label(1140,755,24,"No apps will be uninstalled.",620,1);}
 if(hub.page==ERROR_PAGE){label(1140,718,24,"Retry, or return to your apps with Back.",620,1);}
}
static void go(HubPage page,int focus){if(hub.page==HOME&&page!=HOME){home_return_focus=hub.focus;int base=hub.saved.count?hub.saved.count:1;home_return_action=hub.focus>=base?hub.focus-base:-1;}hub.page=page;hub.focus=focus;hub.notice[0]=0;redraw();}
static int commit(HubSaved *next){
 if(!hub_store(next,state_path)){snprintf(hub.notice,sizeof(hub.notice),"Could not save. Your previous shortcuts and settings are intact.");redraw();return 0;}
 hub.saved=*next;hub.dirty=0;preferences_invalid=0;return 1;
}
static void back_home(void){int base=hub.saved.count?hub.saved.count:1;int at=home_return_action>=0?base+(home_return_action>3&&hub.undo_at<0?0:home_return_action):home_return_focus<hub.saved.count?home_return_focus:0;go(HOME,at);}
static void home(void){go(HOME,hub.saved.count?hub.saved.selected:0);}
static void undo_remove(void){if(hub.undo_at<0||hub.saved.count>=HUB_MAX)return;HubSaved s=hub.saved;int at=hub.undo_at<s.count?hub.undo_at:s.count;memmove(s.apps+at+1,s.apps+at,(size_t)(s.count-at)*sizeof(HubApp));s.apps[at]=hub.removed;s.count++;s.selected=at;if(commit(&s)){hub.undo_at=-1;home();}}
static void activate(void){
 int i=hub.focus,base=hub.saved.count?hub.saved.count:1;HubSaved s=hub.saved;
 if(hub.page==HOME){if(i<hub.saved.count){launch_app(s.apps[i].id);return;}if(!s.count&&!i){go(PICK,0);return;}i-=base;if(i==0)go(EDIT,0);if(i==1)launch_app(HUB_HOME);if(i==2)go(SETTINGS,0);if(i==3)launch_app(HUB_WEB);if(i==4)undo_remove();}
 else if(hub.page==EDIT){if(!i)go(PICK,0);else{hub.target=i-1;go(ACTIONS,0);}}
 else if(hub.page==PICK){if(i>=hub.catalog_count)return;if(hub_has(&s,hub.catalog[i].id)){snprintf(hub.notice,sizeof(hub.notice),"Already on Home");redraw();return;}if(s.count>=HUB_MAX)return;s.apps[s.count++]=hub.catalog[i];if(commit(&s)){snprintf(hub.notice,sizeof(hub.notice),"Added to Home");redraw();}}
 else if(hub.page==ACTIONS){if(i==0){hub.draft=s;hub.move_at=hub.target;go(MOVING,hub.target);}else if(i==1){HubApp removed=s.apps[hub.target];memmove(s.apps+hub.target,s.apps+hub.target+1,(size_t)(s.count-hub.target-1)*sizeof(HubApp));s.count--;s.selected=hub.target<s.count?hub.target:s.count?s.count-1:0;if(commit(&s)){hub.removed=removed;hub.undo_at=hub.target;go(EDIT,0);}}else go(EDIT,hub.target+1);}
 else if(hub.page==MOVING){if(i==s.count)home();else{hub.draft.selected=hub.move_at;if(commit(&hub.draft))home();}}
 else if(hub.page==SETTINGS){if(i==0)s.compact=!s.compact;if(i==1)s.clock=(s.clock+1)%3;if(i==2)s.first=!s.first;if(i<3){if(commit(&s))redraw();}if(i==3)go(RESET,0);if(i==4)launch_app(HUB_WEB);}
 else if(hub.page==RESET){if(!i)go(SETTINGS,3);else{HubSaved defaults;hub_defaults(&defaults);memcpy(s.apps,defaults.apps,2*sizeof(HubApp));s.count=2;s.selected=0;if(commit(&s)){hub.undo_at=-1;home();}}}
 else if(hub.page==ERROR_PAGE){if(!i)home();if(i==1)launch_app(launch_id);if(i==2)launch_app(HUB_HOME);}
}
static void ui_key(const char *k){
 int back=!strcmp(k,"Escape")||!strcmp(k,"XF86Back");
 if(pending_launch&&back){launch_feedback_dismissed=1;home();return;}
 if(back){if(hub.page==HOME)return;if(hub.page==PICK)go(EDIT,0);else if(hub.page==ACTIONS)go(EDIT,hub.target+1);else if(hub.page==RESET)go(SETTINGS,3);else if(hub.page==MOVING||hub.page==ERROR_PAGE)home();else back_home();return;}
 if(!strcmp(k,"Return")||!strcmp(k,"KP_Enter")){activate();return;}
 int dx=!strcmp(k,"Right")?1:!strcmp(k,"Left")?-1:0,dy=!strcmp(k,"Down")?1:!strcmp(k,"Up")?-1:0;if(!dx&&!dy)return;
 int old=hub.focus;
 if(hub.page==HOME||hub.page==MOVING){HubSaved *s=hub.page==MOVING?&hub.draft:&hub.saved;int n=s->count,base=n?n:1,cols=hub_columns(s);
  if(hub.focus<base){int next=hub_step(hub.focus,n,cols,dx,dy);if(dy>0&&next==hub.focus){hub.home_focus=hub.focus;hub.focus=base;}else if(hub.page==MOVING){hub_move(s,hub.move_at,next);hub.move_at=next;hub.focus=next;redraw();return;}else hub.focus=next;}
  else {if(dy<0)hub.focus=hub.page==MOVING?hub.move_at:hub.home_focus<n?hub.home_focus:0;else if(dx<0&&hub.focus>base)hub.focus--;else if(dx>0&&hub.focus<buttons-1)hub.focus++;}
  if(hub.page==HOME&&hub.focus<n){hub.saved.selected=hub.focus;hub.home_focus=hub.focus;if(!preferences_invalid&&state_path[0])hub.dirty=1;selection_due=now_seconds()+0.3;}
  int rows=s->compact?3:2;if(hub.focus<base&&((old>=base&&hub.focus/cols>=rows)||(old<base&&(old/cols>=rows-1||hub.focus/cols>=rows-1)&&old/cols!=hub.focus/cols))){redraw();return;}
 }else{if((dy>0||dx>0)&&hub.focus<buttons-1)hub.focus++;if((dy<0||dx<0)&&hub.focus>0)hub.focus--;if(hub.focus>=7||old>=7){redraw();return;}}
 if(old!=hub.focus){
  if(hub.page!=HOME&&hub.page!=MOVING){
   if(ring){evas_object_del(ring);ring=0;}
   while(scene_count>preview_start)evas_object_del(scene[--scene_count]);
   preview_panel();hints();
  }
  focus_ring();
 }
}
