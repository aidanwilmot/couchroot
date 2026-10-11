/* Test real renderer lifecycle with a deterministic clock and stub GLES driver. */
#define _POSIX_C_SOURCE 200809L
#define clock_gettime test_clock_gettime
#include "renderer.c"
#include <assert.h>
static double test_time=100;
static int uploads,draws,clears,width=1920;
static float gain;
int test_clock_gettime(clockid_t id,struct timespec *ts){(void)id;ts->tv_sec=(time_t)test_time;ts->tv_nsec=(long)((test_time-ts->tv_sec)*1e9);return 0;}
GLuint glCreateShader(GLenum t){return 1;}
GLuint glCreateProgram(void){return 2;}
void glShaderSource(GLuint s,GLsizei c,const GLchar *const *text,const GLint *n){}
void glCompileShader(GLuint s){}
void glGetShaderiv(GLuint s,GLenum p,GLint *v){*v=1;}
void glGetShaderInfoLog(GLuint s,GLsizei size,GLsizei *n,GLchar *log){}
void glDeleteShader(GLuint s){}
void glDeleteProgram(GLuint s){}
void glAttachShader(GLuint p,GLuint s){}
void glBindAttribLocation(GLuint p,GLuint i,const GLchar *name){}
void glLinkProgram(GLuint p){}
void glGetProgramiv(GLuint p,GLenum name,GLint *v){*v=1;}
GLint glGetUniformLocation(GLuint p,const GLchar *name){return strcmp(name,"gain")==0?2:1;}
void glGetIntegerv(GLenum p,GLint *v){v[0]=0;if(p==GL_VIEWPORT){v[1]=0;v[2]=width;v[3]=1080;}}
void glGenBuffers(GLsizei n,GLuint *b){*b=3;}
void glDeleteBuffers(GLsizei n,const GLuint *b){}
void glBindBuffer(GLenum t,GLuint b){}
void glBufferData(GLenum t,GLsizeiptr n,const void *p,GLenum usage){assert(n==(GLsizeiptr)sizeof(mesh.v));}
void glBufferSubData(GLenum t,GLintptr o,GLsizeiptr n,const void *p){assert(n<=(GLsizeiptr)sizeof(mesh.v));uploads++;}
void glDisable(GLenum p){}
void glEnable(GLenum p){}
void glColorMask(GLboolean r,GLboolean g,GLboolean b,GLboolean a){assert(r&&g&&b&&a);}
void glClearColor(GLfloat r,GLfloat g,GLfloat b,GLfloat a){assert(r==0&&g==0&&b==0&&a==1);}
void glClear(GLbitfield mask){assert(mask==GL_COLOR_BUFFER_BIT);clears++;}
void glUseProgram(GLuint p){}
void glUniform1f(GLint loc,GLfloat v){if(loc==2)gain=v;}
void glBlendFuncSeparate(GLenum a,GLenum b,GLenum c,GLenum d){assert(a==GL_SRC_ALPHA&&b==GL_ONE_MINUS_SRC_ALPHA&&c==GL_ONE&&d==GL_ONE_MINUS_SRC_ALPHA);}
void glEnableVertexAttribArray(GLuint i){}
void glDisableVertexAttribArray(GLuint i){}
void glVertexAttribPointer(GLuint i,GLint n,GLenum t,GLboolean normal,GLsizei stride,const void *ptr){assert(stride==sizeof(Vertex));}
void glDrawArrays(GLenum mode,GLint first,GLsizei count){assert(mode==GL_TRIANGLES&&count<=MAX_VERTICES);draws++;}
int main(void){
    OnCreateGlApp("","",0);OnUpdateGlApp();assert(uploads==1&&draws==1);
    test_time=100.005;OnUpdateGlApp();test_time=100.010;OnUpdateGlApp();assert(uploads==1&&draws==3);
    test_time=100.04;OnUpdateGlApp();assert(uploads==2&&simulation.steps==1);
    width=2560;OnUpdateGlApp();assert(uploads==3); // viewport invalidates cached geometry
    unsigned before=simulation.steps;test_time=300;OnUpdateGlApp();assert(simulation.steps-before<=6);
    test_time=670;OnUpdateGlApp();assert(fabsf(gain-0.5f)<0.001f);
    OnTerminateGlApp();test_time=680;OnCreateGlApp("","",0);assert(started==100);
    int upload_before=uploads;OnUpdateGlApp();assert(uploads==upload_before+1);
    int drawn=draws,cleared=clears;before=simulation.steps;
    test_time=700;OnUpdateGlApp();assert(draws==drawn&&clears==cleared+1&&simulation.steps==before);
    test_time=900;OnUpdateGlApp();assert(draws==drawn&&clears==cleared+2&&simulation.steps==before);
    OnTerminateGlApp();puts("render-loop: cache reuse, resize/context invalidation, bounded catch-up, wall-clock fade and black cutoff passed");
    return 0;
}
