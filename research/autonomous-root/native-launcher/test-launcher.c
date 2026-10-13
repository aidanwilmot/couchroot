/* Failure-injection checks; no real credentials or Smack changes. SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static int failure, stage, executions, env_count;
static uid_t fake_getuid(void) { return failure==1 ? 5001 : stage>=3 ? 5001 : 0; }
static gid_t fake_getgid(void) { return stage>=2 ? 100 : 0; }
static int fake_setgroups(size_t n, const gid_t *g) { assert(!n && !g); if(failure==4)return -1;stage=1;return 0; }
static int fake_setgid(gid_t g) { assert(stage==1 && g==100);if(failure==5)return -1;stage=2;return 0; }
static int fake_setuid(uid_t u) { assert(stage==2 && u==5001);if(failure==6)return -1;stage=3;return 0; }
static int fake_getgroups(int n, gid_t *g) { assert(!n && !g);return failure==7 ? 1 : 0; }
static int fake_open(const char *p, int flags, ...) { assert(!strcmp(p,"/proc/self/attr/current"));(void)flags;return failure==2 ? -1 : 99; }
static int fake_close(int fd) { assert(fd==99);return 0; }
static ssize_t fake_write(int fd,const void *buf,size_t n) { assert(fd==99 && n==4 && !memcmp(buf,"User",4));return failure==3 ? 2 : 4; }
static ssize_t fake_read(int fd,void *buf,size_t n) { assert(fd==99 && n>=4);memcpy(buf,failure==8 ? "Nope" : "User",4);return 4; }
static int fake_stat(const char *p,struct stat *s) { assert(!strcmp(p,"/sys/fs/kdbus/0-system"));memset(s,0,sizeof(*s));s->st_mode=S_IFDIR;return 0; }
static int fake_setenv(const char *k,const char *v,int replace) {
 assert(k && v && replace==1);env_count++;
 if(!strcmp(k,"DBUS_SYSTEM_BUS_ADDRESS"))assert(!strcmp(v,"kernel:path=/sys/fs/kdbus/0-system/bus"));
 return failure==9 ? -1 : 0;
}
static int fake_chdir(const char *p) { assert(!strcmp(p,"/home/owner"));return failure==10 ? -1 : 0; }
static int fake_execl(const char *p,const char *arg,...) {
 assert(stage==3 && env_count==8 && !strcmp(p,"/bin/sh") && !strcmp(arg,"sh"));
 va_list a;va_start(a,arg);assert(!strcmp(va_arg(a,char *),"-c"));assert(!strcmp(va_arg(a,char *),"exit 7"));assert(va_arg(a,char *)==NULL);va_end(a);
 executions++;errno=ENOENT;return -1;
}
#define getuid fake_getuid
#define geteuid fake_getuid
#define getgid fake_getgid
#define getegid fake_getgid
#define setgroups fake_setgroups
#define setgid fake_setgid
#define setuid fake_setuid
#define getgroups fake_getgroups
#define open fake_open
#define close fake_close
#define write fake_write
#define read fake_read
#define setenv fake_setenv
#define chdir fake_chdir
#define execl fake_execl
#define main launcher_main
/* Preserve struct stat's tag while substituting the function. */
#define stat(p,s) fake_stat(p,s)
#include "app-launcher.c"
#undef main
int main(void) {
 char *args[]={"launcher","--command","exit 7",NULL};
 assert(launcher_main(1,args)==64);
 for(failure=0;failure<=10;failure++) {
  stage=executions=env_count=0;errno=EPERM;
  assert(launcher_main(3,args)==77);
  assert(executions==(failure==0 ? 1 : 0));
 }
 puts("PASS fail-closed transitions and exact shell arguments");return 0;
}
