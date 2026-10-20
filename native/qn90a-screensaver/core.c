/* Shared Asteroids simulation and mesh, exposed to the older TV's WebGL host. */
#include "../system-screensaver/mesh.h"
static Simulation scene;
static Mesh batch;
static double started,last,accumulator;
static int previous_width,previous_height,dirty;
void saver_init(unsigned seed,double time) {
    sim_init(&scene,seed,16.0f/9.0f); started=last=time; accumulator=0;
    previous_width=previous_height=0; dirty=1;
}
int saver_frame(double time,int width,int height) {
    double elapsed=time-started;
    if(!isfinite(time)||elapsed<0||elapsed>=600||width<1||height<1)return -2;
    scene.aspect=(float)width/height;
    accumulator+=fmin(0.2,fmax(0,time-last));last=time;
    int steps=0;
    while(accumulator>=STEP && steps++<6){sim_step(&scene);accumulator-=STEP;}
    if(!dirty&&!steps&&previous_width==width&&previous_height==height)return -1;
    // QN90A LCD: wider strokes remain visible where the OLED's thin dim lines do not.
    mesh_build(&scene,&batch,4.0f/height);dirty=0;previous_width=width;previous_height=height;
    return (int)batch.count;
}
Vertex *saver_vertices(void){return batch.v;}
float saver_light(double time){return saver_gain(time-started);}
unsigned saver_steps(void){return scene.steps;}
