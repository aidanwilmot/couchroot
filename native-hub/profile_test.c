/* Linux-only profiler lifecycle test: real sampler thread and /proc reads, no TV APIs.
 * Run under ThreadSanitizer by test.sh when COUCHROOT_TSAN=1. */
#define _GNU_SOURCE
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include "hub-profile.h"
static int threads(void){
 DIR *d=opendir("/proc/self/task");assert(d);int n=0;struct dirent *e;
 while((e=readdir(d)))if(e->d_name[0]!='.')n++;closedir(d);return n;
}
static int open_fds(void){
 DIR *d=opendir("/proc/self/fd");assert(d);int n=0;struct dirent *e;
 while((e=readdir(d)))if(e->d_name[0]!='.')n++;closedir(d);return n;
}
int main(void){
 int base_threads=threads(),base_fds=open_fds();
 /* Absent or inexact values leave the profiler completely inert. */
 const char *off[]={0,"","0","true","1 "};
 for(int i=0;i<5;i++){
  if(off[i])setenv("COUCHROOT_NATIVE_PROFILE",off[i],1);else unsetenv("COUCHROOT_NATIVE_PROFILE");
  prof_start();assert(!prof_enabled&&!prof_running&&prof_stat_fd<0&&threads()==base_threads&&open_fds()==base_fds);
  prof_milestone("off");prof_finish();
 }
 /* Enabled: the sampler runs, buckets fill, and finish joins the thread and closes every descriptor.
  * Repeated cycles exercise the stop handshake; a lost stop would hang in pthread_join. */
 setenv("COUCHROOT_NATIVE_PROFILE","1",1);
 for(int cycle=0;cycle<25;cycle++){
  prof_start();assert(prof_enabled&&prof_running&&threads()==base_threads+1);
  struct timespec pause={0,cycle%5?2000000:20000000};nanosleep(&pause,0);
  prof_milestone("cycle");prof_finish();
  assert(!prof_running&&prof_stat_fd<0&&prof_sys_fd<0&&prof_wchan_fd<0&&prof_sched_fd<0);
  for(int i=0;i<200&&threads()!=base_threads;i++){struct timespec t={0,1000000};nanosleep(&t,0);}
  assert(threads()==base_threads&&open_fds()==base_fds);
 }
 fprintf(stderr,"native profiler (Linux): inert unless exactly 1; 25 start/stop cycles joined and closed descriptors\n");
 return 0;
}
