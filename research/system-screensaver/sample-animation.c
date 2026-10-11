/* Run the real simulation and export actual vector batches for WebGL validation. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "mesh.h"
static Simulation s;
static Mesh m;
static void validate(void){
    assert(isfinite(s.ship.x)&&isfinite(s.ship.y));
    assert(fabsf(s.ship.x)<=s.aspect&&fabsf(s.ship.y)<=1);
    assert(rock_count(&s)<=ROCKS);
    mesh_build(&s,&m,2.0f/540);
    assert(!m.overflow && m.count<=MAX_VERTICES && m.count%6==0);
    for(unsigned i=0;i<m.count;i++){
        const Vertex *v=&m.v[i];
        assert(isfinite(v->x)&&isfinite(v->y));
        assert(v->r>=0&&v->r<=0.18f&&v->g>=0&&v->g<=v->r&&v->b>=0&&v->b<=v->g);
    }
}
int main(int argc,char **argv){
    assert(argc==2);
    FILE *out=fopen(argv[1],"wb");assert(out);
    unsigned total_hits=0,total_deaths=0,total_splits=0,max_vertices=0;
    for(uint32_t seed=1;seed<=12;seed++){
        sim_init(&s,seed*7937,16.0f/9.0f);
        for(int tick=0;tick<=660*30;tick++){
            if(tick)sim_step(&s);
            if(tick%30==0){validate();if(m.count>max_vertices)max_vertices=m.count;}
            if(seed<=3 && tick%(10*30)==0){
                uint32_t time=(uint32_t)tick/30,count=m.count;float gain=saver_gain(time);
                if(time>=600)assert(gain==0);
                assert(fwrite(&time,4,1,out)==1&&fwrite(&count,4,1,out)==1&&fwrite(&gain,4,1,out)==1);
                assert(fwrite(m.v,sizeof(Vertex),count,out)==count);
            }
        }
        assert(s.fired>20 && s.hits>10 && s.splits>4);
        total_hits+=s.hits;total_deaths+=s.deaths;total_splits+=s.splits;
    }
    fclose(out);
    /* Force a ship collision to cover destruction and a collision-free respawn. */
    sim_init(&s,19,16.0f/9.0f);s.rocks[0].p=s.ship;s.rocks[0].v=s.velocity;s.shield=0;
    sim_step(&s);assert(s.deaths==1&&s.respawn>0);
    for(int i=0;i<90;i++)sim_step(&s);
    assert(s.respawn<=0&&s.shield>0);
    printf("{\"hits\":%u,\"splits\":%u,\"deaths\":%u,\"maxVertices\":%u,\"seeds\":12,\"minutesPerSeed\":11}\n",total_hits,total_splits,total_deaths,max_vertices);
    return 0;
}
