/* Replacement for spotlight-ss's small rendering ABI. Samsung retains the
 * idle trigger, overlay window, app lifecycle, power handling and key grabs.
 * This library never changes TV settings or launches a process. */
#include <GLES2/gl2.h>
#include <stddef.h>
#include <stdio.h>
#include <time.h>
#include "mesh.h"

static GLuint program, vertices;
static GLint aspect_location, gain_location;
static double started, last_tick, accumulator;
static Simulation simulation;
static Mesh mesh;
static int mesh_dirty, mesh_width, mesh_height;
static const char *vertex_shader =
    "attribute vec2 position; attribute vec3 color; attribute float edge;"
    "uniform float aspect; varying vec3 ink; varying float across;"
    "void main(){ink=color;across=edge;gl_Position=vec4(position.x/aspect,position.y,0.0,1.0);}";
static const char *fragment_shader =
    "precision mediump float; varying vec3 ink; varying float across; uniform float gain;"
    "void main(){float coverage=1.0-smoothstep(0.50,1.0,abs(across));"
    "gl_FragColor=vec4(min(ink,vec3(0.18))*gain,coverage);}";

static double now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return started;
    return ts.tv_sec + ts.tv_nsec / 1000000000.0;
}
static GLuint compile(GLenum type, const char *source) {
    GLuint shader = glCreateShader(type);
    GLint ok = 0;
    glShaderSource(shader, 1, &source, 0);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512]; glGetShaderInfoLog(shader, sizeof(log), 0, log);
        fprintf(stderr, "MinimalSaver shader: %s\n", log);
        glDeleteShader(shader); return 0;
    }
    return shader;
}
void OnTerminateGlApp(void) {
    if (vertices) glDeleteBuffers(1, &vertices);
    if (program) glDeleteProgram(program);
    vertices = program = 0;
}
void OnCreateGlApp(const char *resources, const char *config, int device) {
    (void)resources; (void)config; (void)device;
    /* A fresh context may reuse old numeric names; do not delete stale names. */
    vertices = program = 0;
    GLuint vs = compile(GL_VERTEX_SHADER, vertex_shader);
    GLuint fs = compile(GL_FRAGMENT_SHADER, fragment_shader);
    if (!vs || !fs) { if(vs) glDeleteShader(vs); if(fs) glDeleteShader(fs); return; }
    program = glCreateProgram();
    glAttachShader(program, vs); glAttachShader(program, fs);
    glBindAttribLocation(program, 0, "position");
    glBindAttribLocation(program, 1, "color");
    glBindAttribLocation(program, 2, "edge"); glLinkProgram(program);
    glDeleteShader(vs); glDeleteShader(fs);
    GLint ok = 0; glGetProgramiv(program, GL_LINK_STATUS, &ok);
    if (!ok) { OnTerminateGlApp(); return; }
    aspect_location = glGetUniformLocation(program, "aspect");
    gain_location = glGetUniformLocation(program, "gain");
    GLint previous; glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &previous);
    glGenBuffers(1, &vertices); glBindBuffer(GL_ARRAY_BUFFER, vertices);
    glBufferData(GL_ARRAY_BUFFER, sizeof(mesh.v), 0, GL_STREAM_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, previous);
    last_tick = now(); accumulator = 0; mesh_dirty = 1;
    /* Context recreation must not restart the black deadline within a process. */
    if (started <= 0) {
        started = last_tick;
        sim_init(&simulation, (uint32_t)fmod(started*1000.0,4294967295.0), 16.0f/9.0f);
    }
    fprintf(stderr, "MinimalSaver: vector Asteroids ready; black after 600 seconds\n");
}
void OnUpdateGlApp(void) {
    GLint viewport[4]; glGetIntegerv(GL_VIEWPORT, viewport);
    glDisable(GL_SCISSOR_TEST); glDisable(GL_DEPTH_TEST);
    glDisable(GL_STENCIL_TEST); glDisable(GL_CULL_FACE); glDisable(GL_BLEND);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
    const double current = now(), elapsed = current-started;
    if (!program || viewport[2]<=0 || viewport[3]<=0 || !isfinite(elapsed) || elapsed<0 || elapsed>=600) return;
    simulation.aspect = (float)viewport[2]/viewport[3];
    /* 30 Hz simulation, at most six catch-up ticks. Wall time still controls
     * fading, so a stalled host cannot extend the ten-minute exposure window. */
    accumulator += fmin(0.2,fmax(0,current-last_tick)); last_tick=current;
    int steps=0;
    while(accumulator>=STEP && steps++<6){sim_step(&simulation);accumulator-=STEP;}
    int upload = mesh_dirty || steps>0 || mesh_width!=viewport[2] || mesh_height!=viewport[3];
    if (upload) {
        mesh_build(&simulation,&mesh,2.0f/viewport[3]);
        mesh_dirty=0; mesh_width=viewport[2]; mesh_height=viewport[3];
    }
    if (!mesh.count) return;
    glUseProgram(program);
    glUniform1f(aspect_location,simulation.aspect);
    glUniform1f(gain_location,saver_gain(elapsed));
    /* Source-over cannot produce an additive brightness hotspot. Keep alpha
     * opaque over the cleared black target even at antialiased line edges. */
    glEnable(GL_BLEND); glBlendFuncSeparate(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA,GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
    glBindBuffer(GL_ARRAY_BUFFER,vertices);
    if (upload) glBufferSubData(GL_ARRAY_BUFFER,0,mesh.count*sizeof(Vertex),mesh.v);
    for(int i=0;i<3;i++)glEnableVertexAttribArray((GLuint)i);
    glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)offsetof(Vertex,x));
    glVertexAttribPointer(1,3,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)offsetof(Vertex,r));
    glVertexAttribPointer(2,1,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)offsetof(Vertex,edge));
    glDrawArrays(GL_TRIANGLES,0,(GLsizei)mesh.count);
    for(int i=0;i<3;i++)glDisableVertexAttribArray((GLuint)i);
    glBindBuffer(GL_ARRAY_BUFFER,0);glUseProgram(0);glDisable(GL_BLEND);
}
/* Optional callbacks in LegacyPlayer; this saver is silent and needs no data. */
void OnConfigUpdateGlApp(const char *s) { (void)s; }
void InformationCallback(const char *s) { (void)s; }
void RegisterAudioPlay(void *cb) { (void)cb; }
void RegisterAudioStop(void *cb) { (void)cb; }
void UpdateFontColor(int value) { (void)value; }
void GetCountryCode(const char *s) { (void)s; }
void UpdateRotateInfo(int value) { (void)value; }
