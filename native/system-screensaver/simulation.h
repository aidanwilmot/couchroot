/* Bounded, deterministic attract-mode simulation. No allocation, I/O or input. */
#ifndef SAVER_SIMULATION_H
#define SAVER_SIMULATION_H
#include <math.h>
#include <stdint.h>
#include <string.h>
#define ROCKS 24
#define SHOTS 18
#define SPARKS 128
#define RINGS 6
#define CORNERS 11
#define PI 3.14159265358979323846f
#define STEP (1.0f/30.0f)
typedef struct {float x,y;} Vec;
typedef struct {Vec p,v,outline[CORNERS]; float radius,angle,spin,age; int active;} Rock;
typedef struct {Vec p,v; float life;} Shot;
typedef struct {Vec p,v; float life,total;} Spark;
typedef struct {Vec p; float age,life,radius;} Ring;
typedef struct {
    Rock rocks[ROCKS]; Shot shots[SHOTS]; Spark sparks[SPARKS]; Ring rings[RINGS];
    Vec ship,velocity; float heading,respawn,shield,cooldown,spawn,time,thrust,aspect;
    uint32_t rng; unsigned hits,splits,deaths,fired,steps;
} Simulation;
static Vec add(Vec a,Vec b){return (Vec){a.x+b.x,a.y+b.y};}
static Vec scale(Vec v,float s){return (Vec){v.x*s,v.y*s};}
static float length2(Vec v){return v.x*v.x+v.y*v.y;}
static Vec direction(float a){return (Vec){cosf(a),sinf(a)};}
static float clamp(float x,float lo,float hi){return fminf(hi,fmaxf(lo,x));}
static float smooth(float a,float b,float t){float x=clamp((t-a)/(b-a),0,1);return x*x*(3-2*x);}
static float saver_gain(double t){return smooth(0,4,(float)t)*(1-smooth(540,600,(float)t));}
static float random01(Simulation *s){s->rng^=s->rng<<13;s->rng^=s->rng>>17;s->rng^=s->rng<<5;return (s->rng>>8)*(1.0f/16777216.0f);}
static float range(Simulation *s,float a,float b){return a+(b-a)*random01(s);}
static Vec wrap(Vec p,float aspect){while(p.x>aspect)p.x-=2*aspect;while(p.x<-aspect)p.x+=2*aspect;while(p.y>1)p.y-=2;while(p.y<-1)p.y+=2;return p;}
static Vec delta(Vec from,Vec to,float aspect){return wrap((Vec){to.x-from.x,to.y-from.y},aspect);}
static int rock_count(const Simulation *s){int n=0;for(int i=0;i<ROCKS;i++)n+=s->rocks[i].active;return n;}
static void rock_add(Simulation *s,Vec p,Vec v,float radius){
    for(int i=0;i<ROCKS;i++)if(!s->rocks[i].active){
        Rock *r=&s->rocks[i]; memset(r,0,sizeof(*r));r->active=1;r->p=wrap(p,s->aspect);r->v=v;
        r->radius=radius;r->angle=range(s,0,2*PI);r->spin=range(s,-0.25f,0.25f);
        for(int k=0;k<CORNERS;k++)r->outline[k]=scale(direction(k*2*PI/CORNERS),range(s,0.72f,1.0f));
        return;
    }
}
static void burst(Simulation *s,Vec p,Vec v,int count,float size){
    for(int k=0;k<count;k++)for(int j=0;j<SPARKS;j++)if(s->sparks[j].life<=0){
        Spark *a=&s->sparks[j];a->p=p;a->v=add(scale(v,0.3f),scale(direction(range(s,0,2*PI)),range(s,0.04f,0.19f)));
        a->life=a->total=range(s,0.7f,2.2f);break;
    }
    for(int j=0;j<RINGS;j++)if(s->rings[j].age>=s->rings[j].life){
        s->rings[j]=(Ring){p,0,1.5f,size};break;
    }
}
static void spawn_ship(Simulation *s){
    /* Pick the clearest of several positions; never a fixed center respawn. */
    float best=-1;Vec chosen={0,0};
    for(int j=0;j<16;j++){
        Vec p={range(s,-s->aspect,s->aspect),range(s,-0.9f,0.9f)};float clearance=100;
        for(int i=0;i<ROCKS;i++)if(s->rocks[i].active){float d=sqrtf(length2(delta(p,s->rocks[i].p,s->aspect)))-s->rocks[i].radius;clearance=fminf(clearance,d);}
        if(clearance>best){chosen=p;best=clearance;}
    }
    s->ship=chosen;s->heading=range(s,0,2*PI);s->velocity=scale(direction(s->heading),0.17f);s->shield=3;
}
static void sim_init(Simulation *s,uint32_t seed,float aspect){
    memset(s,0,sizeof(*s));s->rng=seed?seed:1;s->aspect=aspect;s->spawn=5;
    for(int i=0;i<9;i++)rock_add(s,(Vec){range(s,-aspect,aspect),range(s,-1,1)},scale(direction(range(s,0,2*PI)),range(s,0.035f,0.10f)),range(s,0.10f,0.19f));
    spawn_ship(s);
}
static void sim_step(Simulation *s){
    s->time+=STEP;s->steps++;
    for(int i=0;i<ROCKS;i++)if(s->rocks[i].active){Rock *r=&s->rocks[i];r->p=wrap(add(r->p,scale(r->v,STEP)),s->aspect);r->angle+=r->spin*STEP;r->age+=STEP;}
    for(int i=0;i<SPARKS;i++)if(s->sparks[i].life>0){Spark *p=&s->sparks[i];p->life-=STEP;p->p=wrap(add(p->p,scale(p->v,STEP)),s->aspect);p->v=scale(p->v,0.989f);}
    for(int i=0;i<RINGS;i++)s->rings[i].age=fminf(s->rings[i].life,s->rings[i].age+STEP);
    if(s->respawn>0){s->respawn-=STEP;if(s->respawn<=0)spawn_ship(s);}
    else {
        Vec aim=direction(s->heading),avoid={0,0};float best=100;
        for(int i=0;i<ROCKS;i++)if(s->rocks[i].active){
            Rock *r=&s->rocks[i];Vec d=delta(s->ship,r->p,s->aspect);float distance=sqrtf(length2(d));
            if(distance<best){best=distance;aim=add(d,scale(r->v,distance/0.9f));}
            Vec future=add(d,scale(add(r->v,scale(s->velocity,-1)),0.75f));
            float near=sqrtf(length2(future)),margin=r->radius+0.20f;
            if(near<margin)avoid=add(avoid,scale(future,-3.0f*(margin-near)/(near+0.01f)));
        }
        Vec desired=length2(avoid)>0.003f?add(avoid,scale(direction(s->heading),0.12f)):aim;
        float target=atan2f(desired.y,desired.x),turn=remainderf(target-s->heading,2*PI);
        s->heading+=clamp(turn,-2.1f*STEP,2.1f*STEP);
        s->thrust=(length2(s->velocity)<0.045f || length2(avoid)>0.003f)?1:0;
        s->velocity=add(scale(s->velocity,0.997f),scale(direction(s->heading),s->thrust*0.18f*STEP));
        float speed=sqrtf(length2(s->velocity));if(speed>0.32f)s->velocity=scale(s->velocity,0.32f/speed);
        s->ship=wrap(add(s->ship,scale(s->velocity,STEP)),s->aspect);
        s->shield=fmaxf(0,s->shield-STEP);s->cooldown-=STEP;
        float aimError=remainderf(atan2f(aim.y,aim.x)-s->heading,2*PI);
        if(s->cooldown<=0 && fabsf(aimError)<0.16f && best<1.5f){
            for(int i=0;i<SHOTS;i++)if(s->shots[i].life<=0){Vec forward=direction(s->heading);s->shots[i]=(Shot){wrap(add(s->ship,scale(forward,0.052f)),s->aspect),add(s->velocity,scale(forward,0.90f)),1.6f};s->fired++;break;}
            s->cooldown=range(s,0.38f,0.60f);
        }
        if(s->shield<=0)for(int i=0;i<ROCKS;i++)if(s->rocks[i].active && length2(delta(s->ship,s->rocks[i].p,s->aspect))<powf(s->rocks[i].radius*0.78f+0.023f,2)){
            burst(s,s->ship,s->velocity,24,0.03f);s->deaths++;s->respawn=2.6f;break;
        }
    }
    for(int b=0;b<SHOTS;b++)if(s->shots[b].life>0){
        Shot *shot=&s->shots[b];Vec old=shot->p,travel=scale(shot->v,STEP);shot->life-=STEP;shot->p=wrap(add(old,travel),s->aspect);
        /* Swept segment collision avoids tunneling through small fragments. */
        for(int i=0;i<ROCKS;i++)if(s->rocks[i].active){
            Rock *r=&s->rocks[i];Vec d=delta(old,r->p,s->aspect);float u=clamp((d.x*travel.x+d.y*travel.y)/fmaxf(length2(travel),0.000001f),0,1);
            Vec closest=add(d,scale(travel,-u));
            if(length2(closest)<r->radius*r->radius*0.78f){
                Rock hit=*r;r->active=0;shot->life=0;s->hits++;burst(s,hit.p,hit.v,14,hit.radius*0.35f);
                if(hit.radius>0.095f){
                    Vec split=scale(direction(range(s,0,2*PI)),0.055f);s->splits++;
                    rock_add(s,add(hit.p,scale(split,0.3f)),add(hit.v,split),hit.radius*0.60f);
                    rock_add(s,add(hit.p,scale(split,-0.3f)),add(hit.v,scale(split,-1)),hit.radius*0.60f);
                }
                break;
            }
        }
    }
    s->spawn-=STEP;
    if(s->spawn<=0){
        if(rock_count(s)<10){float side=random01(s)<0.5f?-1:1;rock_add(s,(Vec){side*(s->aspect-0.01f),range(s,-1,1)},(Vec){-side*range(s,0.035f,0.075f),range(s,-0.06f,0.06f)},range(s,0.12f,0.19f));}
        s->spawn=4;
    }
}
#endif
