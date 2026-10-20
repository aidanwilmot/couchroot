/* One bounded triangle batch for all vectors and particles. No fullscreen shader. */
#ifndef SAVER_MESH_H
#define SAVER_MESH_H
#include "simulation.h"
#define MAX_VERTICES 16384
typedef struct {float x,y,r,g,b,edge;} Vertex;
typedef struct {Vertex v[MAX_VERTICES];unsigned count,overflow;} Mesh;
static const Vec ring_unit[24]={{1.0f,0.0f},{0.965925826f,0.258819045f},{0.866025404f,0.5f},{0.707106781f,0.707106781f},{0.5f,0.866025404f},{0.258819045f,0.965925826f},{6.123234e-17f,1.0f},{-0.258819045f,0.965925826f},{-0.5f,0.866025404f},{-0.707106781f,0.707106781f},{-0.866025404f,0.5f},{-0.965925826f,0.258819045f},{-1.0f,1.2246468e-16f},{-0.965925826f,-0.258819045f},{-0.866025404f,-0.5f},{-0.707106781f,-0.707106781f},{-0.5f,-0.866025404f},{-0.258819045f,-0.965925826f},{-1.8369702e-16f,-1.0f},{0.258819045f,-0.965925826f},{0.5f,-0.866025404f},{0.707106781f,-0.707106781f},{0.866025404f,-0.5f},{0.965925826f,-0.258819045f}};
static const float palette[3][3]={{0.157f,0.142f,0.112f},{0.175f,0.151f,0.104f},{0.112f,0.093f,0.070f}};
static void line(Mesh *m,Vec a,Vec b,float width,int color,float light){
    Vec d={b.x-a.x,b.y-a.y};float n=sqrtf(length2(d));if(n<0.00001f)return;
    if(m->count+6>MAX_VERTICES){m->overflow++;return;}
    Vec off={-d.y*width/n,d.x*width/n};
    Vec q[4]={add(a,off),add(a,scale(off,-1)),add(b,off),add(b,scale(off,-1))};
    const int index[6]={0,1,2,2,1,3};
    for(int k=0;k<6;k++){int j=index[k];m->v[m->count++]=(Vertex){q[j].x,q[j].y,palette[color][0]*light,palette[color][1]*light,palette[color][2]*light,j%2?-1:1};}
}
static Vec rotate(Vec p,float c,float s){return (Vec){p.x*c-p.y*s,p.x*s+p.y*c};}
static void mesh_build(const Simulation *s,Mesh *m,float pixel){
    m->count=m->overflow=0;
    const float width=fmaxf(0.0015f,pixel*0.75f);
    /* Wrap copies are culled before drawing; only edge-straddling objects duplicate. */
    for(int oy=-1;oy<=1;oy++)for(int ox=-1;ox<=1;ox++){
        Vec offset={ox*2*s->aspect,oy*2.0f};
        for(int i=0;i<ROCKS;i++)if(s->rocks[i].active){
            const Rock *r=&s->rocks[i];Vec p=add(r->p,offset);float radius=r->radius;
            if(fabsf(p.x)>s->aspect+radius || fabsf(p.y)>1+radius)continue;
            float c=cosf(r->angle),sn=sinf(r->angle),light=(0.64f+0.20f*(i%3))*smooth(0,1.5f,r->age);
            for(int k=0;k<CORNERS;k++)line(m,add(p,scale(rotate(r->outline[k],c,sn),radius)),add(p,scale(rotate(r->outline[(k+1)%CORNERS],c,sn),radius)),width,i%3,light);
        }
        Vec p=add(s->ship,offset);
        if(s->respawn<=0 && fabsf(p.x)<s->aspect+0.08f && fabsf(p.y)<1.08f){
            float c=cosf(s->heading),sn=sinf(s->heading);Vec ship[4]={{0.049f,0},{-0.033f,0.028f},{-0.020f,0},{-0.033f,-0.028f}};
            float light=s->shield>0?0.65f+0.25f*sinf(s->time*2.5f):1;
            for(int k=0;k<4;k++)line(m,add(p,rotate(ship[k],c,sn)),add(p,rotate(ship[(k+1)%4],c,sn)),width*1.15f,0,light);
            if(s->thrust){float extent=0.054f+0.012f*sinf(s->time*17);Vec flame[3]={{-0.031f,-0.013f},{-extent,0},{-0.031f,0.013f}};
                for(int k=0;k<2;k++)line(m,add(p,rotate(flame[k],c,sn)),add(p,rotate(flame[k+1],c,sn)),width,1,0.65f);
            }
        }
        for(int i=0;i<SHOTS;i++)if(s->shots[i].life>0){const Shot *b=&s->shots[i];Vec a=add(b->p,offset);
            if(fabsf(a.x)<s->aspect+0.04f && fabsf(a.y)<1.04f)line(m,a,add(a,scale(b->v,-0.025f)),width,1,fminf(1,b->life*3));}
        for(int i=0;i<SPARKS;i++)if(s->sparks[i].life>0){const Spark *a=&s->sparks[i];Vec p2=add(a->p,offset);
            if(fabsf(p2.x)<s->aspect+0.04f && fabsf(p2.y)<1.04f)line(m,p2,add(p2,scale(a->v,-0.13f)),width*0.8f,i%3,0.8f*a->life/a->total);}
        for(int i=0;i<RINGS;i++)if(s->rings[i].age<s->rings[i].life){const Ring *r=&s->rings[i];Vec center=add(r->p,offset);float radius=r->radius+r->age*0.07f;
            if(fabsf(center.x)>s->aspect+radius || fabsf(center.y)>1+radius)continue;
            for(int k=0;k<24;k++)line(m,add(center,scale(ring_unit[k],radius)),add(center,scale(ring_unit[(k+1)%24],radius)),width*0.65f,1,0.26f*(1-r->age/r->life));}
    }
}
#endif
