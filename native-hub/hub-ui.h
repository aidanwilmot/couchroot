/* Native offline UI. Bounded scene, no animations, one moving focus ring. */
#include "hub-model.h"
#include <math.h>
/* Design tokens (1920x1080, read from ~3 m). One margin, one header line, one footer row.
 * Colours are opaque warm neutrals over the #111212 window; text pairs are >= 4.5:1. */
enum{MX=120,MR=1800,HEAD_Y=64,FOOT_Y=956,FOOT_H=60,BODY_Y=168,
 GRID_GAP=40,GRID_GAP_C=32,ROW_H=80,ROW_STRIDE=92,ROW_W=920,PANEL_X=1104,
 R_PANEL=24,R_CTRL=14,R_CHIP=8,R_TILE=21,
 T_TITLE=44,T_HEAD=32,T_BODY=28,T_CTRL=26,T_DETAIL=24,T_HINT=22};
#define C_PANEL 24,26,25
#define C_ROW 30,32,31
#define C_WELL 35,38,36
#define C_CHIP 38,40,39
#define C_BADGE 50,53,50
static Hub hub;
static Obj *scene[512], *canvas, *ring; static int scene_count;
static int preview_start, home_return_focus, home_return_action=-1;
static void hints(void);
static int bx[140],by[140],bw[140],bh[140],br[140], buttons;
static char state_path[1024], catalog_path[1024];
static Obj *clock_label; static int clock_minute=-1, title_right;
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
/* Ink: 0 primary, 1 secondary, 2 quiet (hints, clock), 3 accent. */
static void ink(Obj *o,int tone){
 static const unsigned char c[4][3]={{240,239,229},{172,174,163},{146,148,139},{228,196,132}};
 evas_object_color_set(o,c[tone&3][0],c[tone&3][1],c[tone&3][2],255);
}
static Obj *label(int x,int y,int size,const char *s,int maxw,int muted){
 Obj *o=remember(evas_object_text_add(canvas));evas_object_text_font_set(o,"Sans",size);evas_object_text_text_set(o,s);
 int w,h;evas_object_geometry_get(o,0,0,&w,&h);while(w>maxw&&size>18){size--;evas_object_text_font_set(o,"Sans",size);evas_object_geometry_get(o,0,0,&w,&h);}
 if(w>maxw){char clipped[512];snprintf(clipped,sizeof(clipped),"%s",s);size_t n=strlen(clipped);while(w>maxw&&n){n--;while(n&&((unsigned char)clipped[n]&0xc0)==0x80)n--;clipped[n]=0;char shown[516];snprintf(shown,sizeof(shown),"%s…",clipped);evas_object_text_text_set(o,shown);evas_object_geometry_get(o,0,0,&w,&h);}}
 evas_object_move(o,x,y);ink(o,muted);evas_object_show(o);return o;
}
static int text_w(Obj *o){int w,h;evas_object_geometry_get(o,0,0,&w,&h);return w;}
static int text_h(Obj *o){int w,h;evas_object_geometry_get(o,0,0,&w,&h);return h;}
/* Width of a string before anything is drawn, so plates can be created beneath their text. */
static int measure(int size,const char *s){Obj *o=evas_object_text_add(canvas);evas_object_text_font_set(o,"Sans",size);evas_object_text_text_set(o,s);int w=text_w(o);evas_object_del(o);return w;}
static Obj *right_label(int right,int y,int size,const char *s,int maxw,int tone){Obj *o=label(0,y,size,s,maxw,tone);evas_object_move(o,right-text_w(o),y);return o;}
static Obj *centered_tone(int x,int y,int w,int h,int size,const char *s,int tone){
 Obj *o=label(0,0,size,s,w-(w<150?10:34),tone);int tw,th;evas_object_geometry_get(o,0,0,&tw,&th);evas_object_move(o,x+(w-tw)/2,y+(h-th)/2);return o;
}
static void centered(int x,int y,int w,int h,int size,const char *s){centered_tone(x,y,w,h,size,s,0);}
static void target(int index,int x,int y,int w,int h,int radius){bx[index]=x;by[index]=y;bw[index]=w;bh[index]=h;br[index]=radius;if(index>=buttons)buttons=index+1;}
/* List row: name on the left, optional value right-aligned in the secondary ink. */
static void row(int index,int x,int y,const char *s,const char *value,int value_tone){
 target(index,x,y,ROW_W,ROW_H,R_CTRL);round_box(x,y,ROW_W,ROW_H,R_CTRL,C_ROW);
 int vw=value&&value[0]?measure(T_BODY,value):0;
 Obj *o=label(x+32,y,T_BODY,s,ROW_W-64-(vw?vw+40:0),0);evas_object_move(o,x+32,y+(ROW_H-text_h(o))/2);
 if(vw){Obj *v=right_label(x+ROW_W-32,y,T_BODY,value,300,value_tone);evas_object_move(v,x+ROW_W-32-text_w(v),y+(ROW_H-text_h(v))/2);}
}
/* Footer actions: one plate, equal-width segments; the focus ring frames a segment. */
static int segments(int base,int n,const char *const *names,int accent_last){
 enum{SEG=240};int x=MX;
 round_box(x,FOOT_Y,SEG*n,FOOT_H,R_CTRL,C_ROW);
 for(int i=0;i<n;i++){target(base+i,x+SEG*i,FOOT_Y,SEG,FOOT_H,R_CTRL);centered_tone(x+SEG*i,FOOT_Y,SEG,FOOT_H,T_CTRL,names[i],accent_last&&i==n-1?3:0);}
 return x+SEG*n;
}
static void contour(Obj *o,int x,int y,int w,int h,int radius,int reverse){
 for(int n=0;n<=28;n++){int j=reverse?28-n:n,corner=(j%28)/7,step=(j%28)%7;
  double a=(-90+corner*90+step*15)*3.141592653589793/180;
  int cx=corner<2?w-radius:radius,cy=(corner==1||corner==2)?h-radius:radius;
  evas_object_polygon_point_add(o,x+cx+(int)(radius*cos(a)),y+cy+(int)(radius*sin(a)));
 }
}
#include "hub-art.h"
/* Focus: a bright ring with a dark gap around the target. Tiles also get a soft outer halo
 * and their brand light brightens (card_lift). Only these focus objects move; cards are retained. */
static Obj *ring_extra[2];
static Obj *focus_band(int x,int y,int w,int h,int radius,int width,int r,int g,int b,int a){
 Obj *o=evas_object_polygon_add(canvas);contour(o,x,y,w,h,radius,0);
 if(width)contour(o,x+width,y+width,w-2*width,h-2*width,radius-width,1);
 evas_object_color_set(o,r*a/255,g*a/255,b*a/255,a);evas_object_show(o);return o;
}
static void focus_ring(void){
 if(ring){evas_object_del(ring);ring=0;}for(int k=0;k<2;k++)if(ring_extra[k]){evas_object_del(ring_extra[k]);ring_extra[k]=0;}
 int i=hub.focus;if(i<0||i>=buttons||!bw[i])return;
 const HubSaved *s=hub.page==MOVING?&hub.draft:&hub.saved;int tile=(hub.page==HOME||hub.page==MOVING)&&i<s->count;
 int radius=tile?card_radius(bw[i]):br[i]?br[i]:bh[i]<70?bh[i]/2:16,gap=tile?6:5,width=tile?5:4,o=gap+width;
 if(tile){ring_extra[0]=focus_band(bx[i]-o-8,by[i]-o-8,bw[i]+2*o+16,bh[i]+2*o+16,radius+o+8,8,255,255,255,20);
  ring_extra[1]=card_lift(bx[i],by[i],bw[i],bh[i],s->apps[i].id);}
 ring=focus_band(bx[i]-o,by[i]-o,bw[i]+2*o,bh[i]+2*o,radius+o,width,248,247,243,255);
}
static void clock_update(void){if(!clock_label)return;time_t t=time(0);struct tm *tm=localtime(&t);if(!tm||clock_minute==tm->tm_min)return;clock_minute=tm->tm_min;char value[40];strftime(value,sizeof(value),hub.saved.clock==2?"%H:%M":"%I:%M %p",tm);evas_object_text_text_set(clock_label,value);evas_object_move(clock_label,MR-text_w(clock_label),HEAD_Y);}
static void preview_panel(void);
static void redraw(void){
 if(ring){evas_object_del(ring);ring=0;}for(int i=0;i<scene_count;i++)evas_object_del(scene[i]);scene_count=0;clock_label=0;clock_minute=-1;buttons=0;title_right=0;memset(bw,0,sizeof(bw));
 HubSaved *s=hub.page==MOVING?&hub.draft:&hub.saved;
 if(hub.page==HOME||hub.page==MOVING){
  if(hub.page==MOVING){char moving[180];snprintf(moving,sizeof(moving),"Move %s",s->apps[hub.move_at].name);title_right=MX+text_w(label(MX,HEAD_Y-8,T_TITLE,moving,1100,0));
   if(!hub.notice[0]){snprintf(moving,sizeof(moving),"Position %d of %d",hub.move_at+1,s->count);right_label(MR,HEAD_Y,T_DETAIL+4,moving,400,1);}}
  else if(s->clock){clock_label=label(MR-160,HEAD_Y,30,"",220,2);clock_update();}
  int cols=hub_columns(s),rows=s->compact?3:2,gap=s->compact?GRID_GAP_C:GRID_GAP,w=(MR-MX-(cols-1)*gap)/cols,h=w*9/16;
  if(cols==1) {w=820;h=w*9/16;}
  int row_at=hub.focus<s->count?hub.focus/cols:(hub.home_focus<s->count?hub.home_focus:0)/cols,top=row_at>=rows?row_at-rows+1:0;
  int visible=(s->count+cols-1)/cols;if(visible>rows)visible=rows;
  /* Optical centre (45/55) between the top margin and the footer; never above 132 (header line). */
  int gh=visible*h+(visible-1)*gap,y0=HEAD_Y+(FOOT_Y-32-HEAD_Y-gh)*9/20;if(y0<132)y0=132;
  for(int i=top*cols;i<s->count&&i<(top+rows)*cols;i++){
   int x=(cols==1?(1920-w)/2:MX+(MR-MX-(cols*w+(cols-1)*gap))/2)+(i%cols)*(w+gap),y=y0+(i/cols-top)*(h+gap);
   target(i,x,y,w,h,R_TILE);
   card_art(x,y,w,h,s->apps[i].id);
   wordmark(x,y,w,h,cols<3?76:cols==3?52:36,s->apps[i].name,s->apps[i].id);
  }
  if(!s->count){int ew=640,eh=360,ex=(1920-ew)/2,ey=HEAD_Y+(FOOT_Y-32-HEAD_Y-eh-64)/2;target(0,ex,ey,ew,eh,R_TILE);round_box(ex,ey,ew,eh,R_TILE,C_ROW);
   round_box(ex+ew/2-56,ey+92,112,112,56,C_BADGE);centered(ex+ew/2-56,ey+92,112,112,72,"+");centered(ex,ey+226,ew,48,T_HEAD,"Add apps");
   Obj *c=label(0,ey+eh+28,T_BODY,"Nothing on Home yet",ew,1);evas_object_move(c,(1920-text_w(c))/2,ey+eh+28);}
  int base=s->count?s->count:1;
  if(hub.page==MOVING){static const char *const names[]={"Cancel","Save position"};segments(base,2,names,0);}
  else {static const char *const names[]={"Edit apps","Samsung Home","Settings","Web Hub","Undo remove"};segments(base,hub.undo_at>=0?5:4,names,hub.undo_at>=0);}
  if(top>0)centered_tone(MR,y0,120,h,32,"↑",1);if((top+rows)*cols<s->count)centered_tone(MR,y0+(rows-1)*(h+gap),120,h,32,"↓",1);
 }else{
  const char *titles[]={"","Edit apps","Add apps","App actions","","Settings","Reset shortcuts?","Could not open app"};
  title_right=MX+text_w(label(MX,HEAD_Y-8,T_TITLE,titles[hub.page],1100,0));
  char rows[132][160],values[132][24];int count=0;memset(values,0,sizeof(values));
  if(hub.page==EDIT){strcpy(values[count],"+");strcpy(rows[count++],"Add apps");for(int i=0;i<s->count;i++)snprintf(rows[count++],160,"%s",s->apps[i].name);}
  if(hub.page==PICK){for(int i=0;i<hub.catalog_count;i++){strcpy(values[count],hub_has(s,hub.catalog[i].id)?"Added":"+");snprintf(rows[count++],160,"%s",hub.catalog[i].name);}}
  if(hub.page==ACTIONS){strcpy(rows[count++],"Move");strcpy(rows[count++],"Remove from Home");strcpy(rows[count++],"Cancel");}
  if(hub.page==SETTINGS){strcpy(values[count],s->compact?"Compact":"Comfortable");strcpy(rows[count++],"Tile layout");strcpy(values[count],s->clock==2?"24 hour":s->clock==1?"12 hour":"Off");strcpy(rows[count++],"Clock");strcpy(values[count],s->first?"First favorite":"Last selected");strcpy(rows[count++],"Start on");strcpy(rows[count++],"Reset shortcuts");strcpy(rows[count++],"Advanced settings in Web Hub");}
  if(hub.page==RESET){strcpy(rows[count++],"Keep my shortcuts");strcpy(rows[count++],"Reset to Plex and YouTube");}
  if(hub.page==ERROR_PAGE){strcpy(rows[count++],"Back to apps");strcpy(rows[count++],"Retry");strcpy(rows[count++],"Samsung Home");}
  int top=hub.focus>=7?hub.focus-6:0;for(int i=top;i<count&&i<top+7;i++)row(i,MX,BODY_Y+(i-top)*ROW_STRIDE,rows[i],values[i],strcmp(values[i],"+")?1:3);
  buttons=count;
  if(top)centered_tone(MX+ROW_W,BODY_Y,PANEL_X-MX-ROW_W,ROW_H,30,"↑",1);if(top+7<count)centered_tone(MX+ROW_W,BODY_Y+6*ROW_STRIDE,PANEL_X-MX-ROW_W,ROW_H,30,"↓",1);
  preview_start=scene_count;
  preview_panel();
 }
 hints();focus_ring();
}
/* Key hints, right-aligned on the footer row: quiet keycap chips and secondary labels.
 * A notice takes the free side of the header line (left on Home, right elsewhere). */
static void hints(void){
 const char *keys[3]={"↑ ↓ ← →","OK","Back"},*says[3]={hub.page==MOVING?"Move":"Choose",hub.page==HOME?"Open":"Select","Return"};
 int n=hub.page==HOME?2:3,right=MR,ch=40,cy=FOOT_Y+(FOOT_H-ch)/2;
 for(int k=n-1;k>=0;k--){
  int lw=measure(T_DETAIL,says[k]),kw=measure(T_HINT,keys[k])+28;if(kw<56)kw=56;
  int lx=right-lw,kx=lx-12-kw;round_box(kx,cy,kw,ch,R_CHIP,C_CHIP);centered_tone(kx,cy,kw,ch,T_HINT,keys[k],0);
  Obj *l=label(lx,0,T_DETAIL,says[k],lw+4,1);evas_object_move(l,lx,cy+(ch-text_h(l))/2);right=kx-32;
 }
 if(hub.notice[0]){
  int left=hub.page==HOME?MX:title_right+64,maxw=(hub.page==HOME&&clock_label?MR-220:MR)-left-28;
  int tw=measure(T_DETAIL,hub.notice);if(tw>maxw)tw=maxw;int x=hub.page==HOME?MX:MR-tw-28;
  round_box(x,HEAD_Y+11,12,12,6,228,196,132);label(x+28,HEAD_Y+2,T_DETAIL,hub.notice,maxw,0);
 }
}
static void glyph_badge(int x,int y,int w,int h,const char *g,int alert){
 int d=128;round_box(x+(w-d)/2,y+(h-d)/2,d,d,30,alert?212:50,alert?152:53,alert?102:50);
 Obj *o=centered_tone(x+(w-d)/2,y+(h-d)/2,d,d,72,g,0);if(alert)evas_object_color_set(o,17,18,18,255);
}
static void preview_panel(void){
 const HubApp *app=0;
 if(hub.page==EDIT&&hub.focus>0&&hub.focus<=hub.saved.count)app=&hub.saved.apps[hub.focus-1];
 if(hub.page==PICK&&hub.focus<hub.catalog_count)app=&hub.catalog[hub.focus];
 if(hub.page==ACTIONS)app=&hub.saved.apps[hub.target];
 int px=PANEL_X,pw=MR-PANEL_X,wx=px+32,wy=BODY_Y+32,ww=pw-64,wh=ww*9/16,ty=wy+wh+36;
 int lines=!app&&(hub.page==RESET||hub.page==ERROR_PAGE)?(hub.page==RESET?4:3):2;
 round_box(px,BODY_Y,pw,ty+50+(lines-2)*38+29+40-BODY_Y,R_PANEL,C_PANEL);
 if(app){card_art(wx,wy,ww,wh,app->id);wordmark(wx,wy,ww,wh,58,app->name,app->id);label(wx,ty,T_HEAD,app->name,ww,0);label(wx,ty+50,T_DETAIL,hub.page==PICK?(hub_has(&hub.saved,app->id)?"Already on Home":"OK adds this app to Home"):"Move it or remove its shortcut",ww,1);return;}
 round_box(wx,wy,ww,wh,R_TILE-3,C_WELL);
 const char *title="Your apps, your order",*detail="Choose an app to preview it.";
 if(hub.page==RESET){title="Reset your Home shortcuts?";detail="Your other settings stay as they are.";}
 if(hub.page==ERROR_PAGE){title="The TV did not open this app";detail="Your shortcuts and settings are unchanged.";}
 if(hub.page==PICK){title="Add your favorites";detail=catalog_loaded?"Choose an app to add to your Home screen.":"Only default apps are available in this preview.";}
 if(hub.page==EDIT){title="Make room for your favorites";detail="Add apps without changing installed applications.";}
 if(hub.page==SETTINGS){const char *titles[]={"Space to settle in","A quiet clock","Pick up where you left off","Start fresh","More settings"};const char *details[]={"Comfortable: six tiles. Compact: twelve.","Show the time on your Home screen.","Remember your selection or start at the first app.","Reset shortcuts. Keep your other settings.","Open the installed web Hub for advanced settings."};title=titles[hub.focus];detail=details[hub.focus];
  if(hub.focus==0){int cols=hub.saved.compact?4:3,rows=hub.saved.compact?3:2,g=14,mw=(ww-80-(cols-1)*g)/cols,mh=mw*9/16,gx=wx+(ww-(cols*mw+(cols-1)*g))/2,gy=wy+(wh-(rows*mh+(rows-1)*g))/2;
   for(int i=0;i<cols*rows;i++)round_box(gx+(i%cols)*(mw+g),gy+(i/cols)*(mh+g),mw,mh,8,C_BADGE);}
  else if(hub.focus==1)centered(wx,wy,ww,wh,72,hub.saved.clock==2?"21:41":hub.saved.clock==1?"9:41 PM":"Clock off");
  else if(hub.focus==2)centered(wx,wy,ww,wh,48,hub.saved.first?"First favorite":"Last selected");
  else if(hub.focus==3)glyph_badge(wx,wy,ww,wh,"↺",0);
  else centered(wx,wy,ww,wh,56,"Web Hub");
 }else glyph_badge(wx,wy,ww,wh,hub.page==ERROR_PAGE?"!":hub.page==RESET?"↺":"+",hub.page==ERROR_PAGE);
 label(wx,ty,T_HEAD,title,ww,0);label(wx,ty+50,T_DETAIL,detail,ww,1);
 if(hub.page==RESET){label(wx,ty+88,T_DETAIL,"Plex and YouTube will replace your shortcuts.",ww,1);label(wx,ty+126,T_DETAIL,"No apps will be uninstalled.",ww,1);}
 if(hub.page==ERROR_PAGE){label(wx,ty+88,T_DETAIL,"Retry, or return to your apps with Back.",ww,1);}
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
