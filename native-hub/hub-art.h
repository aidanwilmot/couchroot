/* Per-app card art from the generated, validated style table (cards/cards.py).
 * One shared anatomy: deep brand-tinted rounded base, 2-3 translucent glow layers from one
 * anchor, centred wordmark on one type scale. Flat polygons and text only: no image loader,
 * network, animation or full-screen texture. At most CARD_MAX_OBJECTS objects per card. */
#include "hub-cards.h"
static const CardStyle card_fallback={"*default*","",{26,29,32},{243,241,236},{141,150,160},1,0,0,0,{{0}}};
static const CardStyle *card_style(const char *id){
 const CardStyle *fallback=&card_fallback;
 for(int i=0;i<CARD_STYLE_COUNT;i++){if(!strcmp(card_styles[i].id,id))return &card_styles[i];if(!strcmp(card_styles[i].id,"*default*"))fallback=&card_styles[i];}
 return fallback;
}
static int card_radius(int w){return (int)(w*CARD_RADIUS_W+.5f);}
/* Evas colours are premultiplied. */
static void tint(Obj *o,int r,int g,int b,int a){evas_object_color_set(o,r*a/255,g*a/255,b*a/255,a);}
static Obj *card_poly(Obj *o,int x,int y,int w,int h,const CardShape *s,const unsigned char *rgb,int a){
 for(int i=0;i<s->n&&i<CARD_MAX_POINTS;i++)evas_object_polygon_point_add(o,x+(int)(s->p[i][0]*w+.5f),y+(int)(s->p[i][1]*h+.5f));
 tint(o,rgb[0],rgb[1],rgb[2],a);evas_object_show(o);return o;
}
static void card_shape(int x,int y,int w,int h,const CardShape *s){card_poly(remember(evas_object_polygon_add(canvas)),x,y,w,h,s,s->rgba,s->rgba[3]);}
/* Focus lift for a tile: its outer glow layer again, in the brand accent, so the light under
 * the wordmark brightens. Not part of the retained scene; the focus ring owns it. */
static Obj *card_lift(int x,int y,int w,int h,const char *id){
 const CardStyle *s=card_style(id);if(!s->shapes)return 0;
 return card_poly(evas_object_polygon_add(canvas),x,y,w,h,&s->shape[0],s->accent,CARD_LIFT_ALPHA);
}
static void card_art(int x,int y,int w,int h,const char *id){
 const CardStyle *s=card_style(id);
 round_box(x,y,w,h,card_radius(w),s->base[0],s->base[1],s->base[2]);
 for(int i=0;i<s->shapes&&i<CARD_MAX_SHAPES;i++)card_shape(x,y,w,h,&s->shape[i]);
}
static Obj *mark_text(const char *font,int size,const char *t,int *tw,int *th){
 Obj *o=remember(evas_object_text_add(canvas));evas_object_text_font_set(o,font,size);evas_object_text_text_set(o,t);
 evas_object_geometry_get(o,0,0,tw,th);evas_object_show(o);return o;
}
static void mark_size(Obj *o,const char *font,int size,int *tw,int *th){evas_object_text_font_set(o,font,size);evas_object_geometry_get(o,0,0,tw,th);}
/* Wordmark: the style's word (the app name for the fallback), optional accent tail and play
 * glyph. One type scale for every brand: size follows the card height (the caller's size is
 * ignored), short words grow a little, long words shrink to fit, then ellipsize. */
static void wordmark(int x,int y,int w,int h,int size,const char *name,const char *id){
 const CardStyle *s=card_style(id);const char *text=s->word[0]&&strcmp(s->id,"*default*")?s->word:name;
 char head[128];snprintf(head,sizeof(head),"%s",text);size_t len=strlen(head);
 int split=s->split&&s->split<len?s->split:0;head[len-split]=0;
 const char *font=s->bold?"Sans:style=Bold":"Sans";
 size=(int)(h*CARD_TYPE_H+.5f);int maxw=(int)(w*CARD_TYPE_MAXW),floor_size=size*6/10;
 int tw,th,lw=0;Obj *word=mark_text(font,size,head,&tw,&th),*tail=0;
 if(split){tail=mark_text(font,size,text+len-split,&lw,0);evas_object_color_set(tail,s->accent[0],s->accent[1],s->accent[2],255);}
 int glyph=s->play?size*85/100:0,total=tw+lw+glyph;
 int fit=size;
 if(total>0&&total<w*CARD_TYPE_SHORT){float k=w*CARD_TYPE_SHORT/total;fit=(int)(size*(k<CARD_TYPE_BOOST?k:CARD_TYPE_BOOST));}
 else if(total>maxw)fit=size*maxw/total;
 if(fit<floor_size)fit=floor_size;
 if(fit!=size){size=fit;mark_size(word,font,size,&tw,&th);if(tail)mark_size(tail,font,size,&lw,0);glyph=s->play?size*85/100:0;}
 if(tw+lw+glyph>maxw&&!tail){ /* still too wide (long fallback names): widen, then ellipsize */
  size_t n=strlen(head);char shown[136];maxw=w*84/100;
  while(tw+glyph>maxw&&n){n--;while(n&&((unsigned char)head[n]&0xc0)==0x80)n--;head[n]=0;snprintf(shown,sizeof(shown),"%s…",head);evas_object_text_text_set(word,shown);evas_object_geometry_get(word,0,0,&tw,&th);}
 }
 int lift=(int)(h*CARD_TYPE_LIFT),left=x+(w-tw-lw-glyph)/2,top=y+(h-th)/2-lift;
 if(s->play){int gh=size*62/100,gt=y+(h-gh)/2-lift;Obj *tri=remember(evas_object_polygon_add(canvas));
  evas_object_polygon_point_add(tri,left,gt);evas_object_polygon_point_add(tri,left+gh*86/100,gt+gh/2);evas_object_polygon_point_add(tri,left,gt+gh);
  evas_object_color_set(tri,s->accent[0],s->accent[1],s->accent[2],255);evas_object_show(tri);left+=glyph;}
 evas_object_color_set(word,s->ink[0],s->ink[1],s->ink[2],255);evas_object_move(word,left,top);
 if(tail)evas_object_move(tail,left+tw,top);
}
