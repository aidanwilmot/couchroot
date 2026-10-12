/* Optional startup profiler, enabled only by COUCHROOT_NATIVE_PROFILE=1.
 * Diagnostics for the boot critical path: per-milestone scheduler counters for the
 * main thread (run time, run-queue wait, faults, context switches) and a 4 ms
 * wall-clock sampler of the main thread's kernel state, syscall and wait channel.
 * It reads only this process's /proc entries, sends no signals, changes no
 * scheduling, and stops after the first rendered frame. Off by default. */
#ifndef HUB_PROFILE_INCLUDED
#define HUB_PROFILE_INCLUDED
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#define PROF_SYS 12
#define PROF_WCHAN 8
typedef struct {
 unsigned n,r,d,s,other;
 int sys_nr[PROF_SYS];unsigned sys_n[PROF_SYS];
 char wchan[PROF_WCHAN][40];unsigned wchan_n[PROF_WCHAN];
} ProfBucket;
/* Pure helpers, host-tested. */
static char prof_state(const char *stat){const char *p=strrchr(stat,')');return p&&p[1]==' '&&p[2]?p[2]:'?';}
static int prof_syscall_nr(const char *text){
 if(!strncmp(text,"running",7))return -2;
 char *end;long v=strtol(text,&end,10);return end==text?-3:(int)v;
}
static void prof_count(ProfBucket *b,char state,int nr,const char *wchan){
 b->n++;
 if(state=='R'){b->r++;return;}
 if(state=='D')b->d++;else if(state=='S')b->s++;else b->other++;
 int i;for(i=0;i<PROF_SYS&&b->sys_n[i]&&b->sys_nr[i]!=nr;i++);
 if(i<PROF_SYS){b->sys_nr[i]=nr;b->sys_n[i]++;}
 if(!wchan||!wchan[0])return;
 for(i=0;i<PROF_WCHAN&&b->wchan_n[i]&&strcmp(b->wchan[i],wchan);i++);
 if(i<PROF_WCHAN){snprintf(b->wchan[i],sizeof(b->wchan[i]),"%s",wchan);b->wchan_n[i]++;}
}
static void prof_print_bucket(FILE *f,const char *event,const ProfBucket *b){
 fprintf(f,"samp %s n=%u R=%u D=%u S=%u other=%u",event,b->n,b->r,b->d,b->s,b->other);
 for(int i=0;i<PROF_SYS&&b->sys_n[i];i++)fprintf(f," sys%d=%u",b->sys_nr[i],b->sys_n[i]);
 for(int i=0;i<PROF_WCHAN&&b->wchan_n[i];i++)fprintf(f," w:%s=%u",b->wchan[i],b->wchan_n[i]);
 fputc('\n',f);
}
#if defined(__linux__)
#include <pthread.h>
#include <fcntl.h>
#include <sys/syscall.h>
#include <sys/resource.h>
#include <sched.h>
#ifndef RUSAGE_THREAD
#define RUSAGE_THREAD 1
#endif
static int prof_enabled,prof_running,prof_stat_fd=-1,prof_sys_fd=-1,prof_wchan_fd=-1,prof_sched_fd=-1;
static volatile int prof_stop;static pthread_t prof_thread;static pthread_mutex_t prof_lock=PTHREAD_MUTEX_INITIALIZER;
static ProfBucket prof_bucket;
static struct {double run,rq;unsigned long slices;struct rusage ru;double proc_cpu;} prof_last;
static ssize_t prof_read(int fd,char *buf,size_t size){ssize_t n=fd<0?-1:pread(fd,buf,size-1,0);buf[n>0?n:0]=0;return n;}
static void *prof_sample(void *unused){
 (void)unused;char stat[512],sys[128],wchan[64];
 while(!prof_stop){
  struct timespec delay={0,4000000};nanosleep(&delay,0);
  if(prof_read(prof_stat_fd,stat,sizeof(stat))<=0)continue;
  char state=prof_state(stat);int nr=-1;wchan[0]=0;
  if(state!='R'){if(prof_read(prof_sys_fd,sys,sizeof(sys))>0)nr=prof_syscall_nr(sys);prof_read(prof_wchan_fd,wchan,sizeof(wchan));if(!strcmp(wchan,"0"))wchan[0]=0;}
  pthread_mutex_lock(&prof_lock);prof_count(&prof_bucket,state,nr,wchan);pthread_mutex_unlock(&prof_lock);
 }
 return 0;
}
static double prof_tv(struct timeval t){return t.tv_sec*1e3+t.tv_usec/1e3;}
/* System-wide context since the previous milestone: all-CPU busy/iowait, runnable and
 * blocked tasks now, and eMMC busy time. Reads /proc/stat and /proc/diskstats only. */
static struct {unsigned long long total,idle,iowait,disk_ms;double wall;} prof_sys_last;
static void prof_system(const char *event){
 char buf[4096];unsigned long long u=0,n=0,sy=0,id=0,io=0,irq=0,sirq=0,disk=0;int running=-1,blocked=-1;
 int fd=open("/proc/stat",O_RDONLY|O_CLOEXEC);if(fd<0)return;ssize_t len=prof_read(fd,buf,sizeof(buf));close(fd);if(len<=0)return;
 sscanf(buf,"cpu %llu %llu %llu %llu %llu %llu %llu",&u,&n,&sy,&id,&io,&irq,&sirq);
 const char *r=strstr(buf,"procs_running ");if(r)sscanf(r,"procs_running %d",&running);
 const char *b=strstr(buf,"procs_blocked ");if(b)sscanf(b,"procs_blocked %d",&blocked);
 fd=open("/proc/diskstats",O_RDONLY|O_CLOEXEC);
 if(fd>=0){if(prof_read(fd,buf,sizeof(buf))>0){const char *m=strstr(buf," mmcblk0 ");if(m)sscanf(m," mmcblk0 %*u %*u %*u %*u %*u %*u %*u %*u %*u %llu",&disk);}close(fd);}
 struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);double wall=t.tv_sec*1e3+t.tv_nsec/1e6;
 unsigned long long total=u+n+sy+id+io+irq+sirq,dt=total-prof_sys_last.total;
 if(prof_sys_last.total&&dt)printf("sys %s busy=%.0f%% iowait=%.0f%% running=%d blocked=%d disk_util=%.0f%%\n",event,
  100.0*(dt-(id-prof_sys_last.idle)-(io-prof_sys_last.iowait))/dt,100.0*(io-prof_sys_last.iowait)/dt,running,blocked,
  wall>prof_sys_last.wall?100.0*(disk-prof_sys_last.disk_ms)/(wall-prof_sys_last.wall):0);
 else printf("sys %s running=%d blocked=%d\n",event,running,blocked);
 prof_sys_last.total=total;prof_sys_last.idle=id;prof_sys_last.iowait=io;prof_sys_last.disk_ms=disk;prof_sys_last.wall=wall;
}
static void prof_milestone(const char *event){
 if(!prof_running)return;
 char buf[512];double run=0,rq=0,proc_cpu=0;unsigned long slices=0;int threads=0;
 if(prof_read(prof_sched_fd,buf,sizeof(buf))>0){unsigned long long a=0,b=0;sscanf(buf,"%llu %llu %lu",&a,&b,&slices);run=a/1e6;rq=b/1e6;}
 int fd=open("/proc/self/stat",O_RDONLY|O_CLOEXEC);
 if(fd>=0){if(prof_read(fd,buf,sizeof(buf))>0){const char *p=strrchr(buf,')');unsigned long ut=0,st=0;
  /* After ')': state(3) ... utime(14) stime(15) ... num_threads(20). */
  if(p&&sscanf(p+2,"%*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %lu %lu %*d %*d %*d %*d %d",&ut,&st,&threads)==3)proc_cpu=(ut+st)*1000.0/sysconf(_SC_CLK_TCK);}
  close(fd);}
 struct rusage ru;memset(&ru,0,sizeof(ru));getrusage(RUSAGE_THREAD,&ru);
 printf("prof %s policy=%d run=%.1fms rq=%.1fms slices=%lu utime=%.0fms stime=%.0fms majflt=%ld minflt=%ld vcs=%ld ivcs=%ld proc_cpu=%.0fms threads=%d\n",event,
  sched_getscheduler(0),run-prof_last.run,rq-prof_last.rq,slices-prof_last.slices,prof_tv(ru.ru_utime)-prof_tv(prof_last.ru.ru_utime),prof_tv(ru.ru_stime)-prof_tv(prof_last.ru.ru_stime),
  ru.ru_majflt-prof_last.ru.ru_majflt,ru.ru_minflt-prof_last.ru.ru_minflt,ru.ru_nvcsw-prof_last.ru.ru_nvcsw,ru.ru_nivcsw-prof_last.ru.ru_nivcsw,proc_cpu-prof_last.proc_cpu,threads);
 prof_last.run=run;prof_last.rq=rq;prof_last.slices=slices;prof_last.ru=ru;prof_last.proc_cpu=proc_cpu;
 ProfBucket copy;pthread_mutex_lock(&prof_lock);copy=prof_bucket;memset(&prof_bucket,0,sizeof(prof_bucket));pthread_mutex_unlock(&prof_lock);
 prof_print_bucket(stdout,event,&copy);prof_system(event);fflush(stdout);
}
static void prof_start(void){
 const char *flag=getenv("COUCHROOT_NATIVE_PROFILE");prof_enabled=flag&&!strcmp(flag,"1");if(!prof_enabled)return;
 char path[96];long tid=syscall(SYS_gettid);
 snprintf(path,sizeof(path),"/proc/self/task/%ld/stat",tid);prof_stat_fd=open(path,O_RDONLY|O_CLOEXEC);
 snprintf(path,sizeof(path),"/proc/self/task/%ld/syscall",tid);prof_sys_fd=open(path,O_RDONLY|O_CLOEXEC);
 snprintf(path,sizeof(path),"/proc/self/task/%ld/wchan",tid);prof_wchan_fd=open(path,O_RDONLY|O_CLOEXEC);
 snprintf(path,sizeof(path),"/proc/self/task/%ld/schedstat",tid);prof_sched_fd=open(path,O_RDONLY|O_CLOEXEC);
 char buf[512];unsigned long long start=0;int fd=open("/proc/self/stat",O_RDONLY|O_CLOEXEC);
 if(fd>=0){if(prof_read(fd,buf,sizeof(buf))>0){const char *p=strrchr(buf,')');if(p)sscanf(p+2,"%*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %*u %*u %*d %*d %*d %*d %*d %*d %llu",&start);}close(fd);}
 printf("process-start %.3f\n",start/(double)sysconf(_SC_CLK_TCK));
 printf("profile-fds stat=%d syscall=%d wchan=%d schedstat=%d\n",prof_stat_fd>=0,prof_sys_fd>=0,prof_wchan_fd>=0,prof_sched_fd>=0);
 prof_running=prof_stat_fd>=0&&pthread_create(&prof_thread,0,prof_sample,0)==0;
 prof_milestone("profile-start");
}
static void prof_finish(void){
 if(!prof_running)return;prof_stop=1;pthread_join(prof_thread,0);prof_running=0;
 if(prof_stat_fd>=0)close(prof_stat_fd);if(prof_sys_fd>=0)close(prof_sys_fd);if(prof_wchan_fd>=0)close(prof_wchan_fd);if(prof_sched_fd>=0)close(prof_sched_fd);
 prof_stat_fd=prof_sys_fd=prof_wchan_fd=prof_sched_fd=-1;printf("profile-stopped\n");fflush(stdout);
}
#else
static int prof_enabled;
static void prof_milestone(const char *event){(void)event;}
static void prof_start(void){}
static void prof_finish(void){}
#endif
#endif
