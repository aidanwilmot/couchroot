/* Per-app card art from the generated, validated style table (cards/cards.py).
 * Flat polygons only: no image loader, network, animation or full-screen texture.
 * Bounded cost: one rounded base plus at most four shapes per visible card. */
#include "hub-cards.h"
static const CardStyle card_fallback={"*default*","",{38,40,37},{240,239,229},{223,193,132},1,0,0,0,{{0}}};
static const CardStyle *card_style(const char *id){
 const CardStyle *fallback=&card_fallback;
 for(int i=0;i<CARD_STYLE_COUNT;i++){if(!strcmp(card_styles[i].id,id))return &card_styles[i];if(!strcmp(card_styles[i].id,"*default*"))fallback=&card_styles[i];}
 return fallback;
}
static void card_shape(int x,int y,int w,int h,const CardShape *s){
 Obj *o=remember(evas_object_polygon_add(canvas));
 for(int i=0;i<s->n&&i<8;i++)evas_object_polygon_point_add(o,x+(int)(s->p[i][0]*w),y+(int)(s->p[i][1]*h));
 evas_object_color_set(o,s->rgb[0],s->rgb[1],s->rgb[2],255);evas_object_show(o);
}
static void card_art(int x,int y,int w,int h,const char *id){
 const CardStyle *s=card_style(id);
 round_box(x,y,w,h,20,s->base[0],s->base[1],s->base[2]);
 for(int i=0;i<s->shapes&&i<4;i++)card_shape(x,y,w,h,&s->shape[i]);
}
/* Wordmark: the style's word (the app name for the fallback), optional accent tail and
 * play badge. Short words are set larger. Text is fitted by label(). */
static void wordmark(int x,int y,int w,int h,int size,const char *name,const char *id){
 const CardStyle *s=card_style(id);const char *text=s->word[0]&&strcmp(s->id,"*default*")?s->word:name;
 char head[128];snprintf(head,sizeof(head),"%s",text);size_t len=strlen(head);
 int split=s->split&&s->split<len?s->split:0;head[len-split]=0;
 if(len<=4)size=size*3/2;
 const char *font=s->bold?"Sans:style=Bold":"Sans";
 int badge=s->play?size:0,gap=s->play?size/4:0;
 Obj *word=label(0,0,size,head,w-60-badge-gap,0);evas_object_text_font_set(word,font,size);
 int tw,th;evas_object_geometry_get(word,0,0,&tw,&th);int lw=0;Obj *tail=0;
 if(split){tail=label(0,0,size,text+len-split,w,0);evas_object_text_font_set(tail,font,size);evas_object_geometry_get(tail,0,0,&lw,0);
  evas_object_color_set(tail,s->accent[0],s->accent[1],s->accent[2],255);}
 if(tw+lw+badge+gap>w-40){size=size*(w-40)/(tw+lw+badge+gap);evas_object_text_font_set(word,font,size);evas_object_geometry_get(word,0,0,&tw,&th);
  if(tail){evas_object_text_font_set(tail,font,size);evas_object_geometry_get(tail,0,0,&lw,0);}badge=s->play?size:0;gap=s->play?size/4:0;}
 int left=x+(w-tw-lw-badge-gap)/2,top=y+(h-th)/2;
 if(s->play){int ih=badge*7/10,bt=y+(h-ih)/2;round_box(left,bt,badge,ih,ih/4,s->accent[0],s->accent[1],s->accent[2]);
  Obj *tri=remember(evas_object_polygon_add(canvas));evas_object_polygon_point_add(tri,left+badge*4/10,bt+ih/4);evas_object_polygon_point_add(tri,left+badge*7/10,bt+ih/2);evas_object_polygon_point_add(tri,left+badge*4/10,bt+ih*3/4);
  evas_object_color_set(tri,255,255,255,255);evas_object_show(tri);left+=badge+gap;}
 evas_object_color_set(word,s->ink[0],s->ink[1],s->ink[2],255);evas_object_move(word,left,top);
 if(tail)evas_object_move(tail,left+tw,top);
}
