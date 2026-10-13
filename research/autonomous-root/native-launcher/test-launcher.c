/* Failure-injection checks; no real credentials or Smack changes. SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static int failure, stage, executions, sentinel;
static uid_t fake_getuid(void) { return failure==1 ? 5001 : stage>=3 ? 5001 : 0; }
static gid_t fake_getgid(void) { return stage>=2 ? 100 : 0; }
static int fake_setgroups(size_t n, const gid_t *g) { assert(!n && !g); if(failure==4)return -1;stage=1;return 0; }
static int fake_setgid(gid_t g) { assert(stage==1 && g==100);if(failure==5)return -1;stage=2;return 0; }
static int fake_setuid(uid_t u) { assert(stage==2 && u==5001);if(failure==6)return -1;stage=3;return 0; }
static int fake_getgroups(int n, gid_t *g) { assert(!n && !g);return failure==7 ? 1 : 0; }
static int fake_open(const char *p, int flags, ...) { assert(!strcmp(p,"/proc/self/attr/current"));(void)flags;return failure==2 ? -1 : 99; }
static int fake_close(int fd) { if(fd==99)return 0;return close(fd); }
static ssize_t fake_write(int fd,const void *buf,size_t n) { assert(fd==99 && n==4 && !memcmp(buf,"User",4));return failure==3 ? 2 : 4; }
static ssize_t fake_read(int fd,void *buf,size_t n) { assert(fd==99 && n>=4);memcpy(buf,failure==8 ? "Nope" : "User",4);return 4; }
static int fake_stat(const char *p,struct stat *s) { assert(!strcmp(p,"/sys/fs/kdbus/0-system"));memset(s,0,sizeof(*s));s->st_mode=S_IFDIR;return failure==11 ? -1 : 0; }
static int fake_chdir(const char *p) { assert(!strcmp(p,"/home/owner"));return failure==10 ? -1 : 0; }
/* macOS lacks /proc: use its descriptor directory for the real close test. */
static DIR *fake_opendir(const char *p) {
 assert(!strcmp(p,"/proc/self/fd")); if(failure==9)return NULL;
#ifdef __APPLE__
 return opendir("/dev/fd");
#else
 return opendir(p);
#endif
}
static int fake_execve(const char *p,char *const argv[],char *const env[]) {
 assert(stage==3 && !strcmp(p,"/bin/sh"));
 assert(!strcmp(argv[0],"sh") && !strcmp(argv[1],"-c") && !strcmp(argv[2],"exit 7") && argv[3]==NULL);
 const char *expected[]={"HOME=/home/owner","USER=owner","LOGNAME=owner","XDG_RUNTIME_DIR=/run/user/5001","WAYLAND_DISPLAY=wayland-0","DBUS_SESSION_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/5001-user/bus",failure==11 ? "DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket" : "DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus","PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=en_US.UTF-8",NULL};
 for(int i=0;i<9;i++) { assert(env[i] && !strcmp(env[i],expected[i])); }
 assert(env[9]==NULL);
 errno=0;assert(fcntl(sentinel,F_GETFD)==-1 && errno==EBADF);
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
#define chdir fake_chdir
#define execve fake_execve
#define opendir fake_opendir
#define stat(p,s) fake_stat(p,s)
#define main launcher_main
#include "app-launcher.c"
#undef main
#undef open
#undef close
int main(void) {
 char *args[]={"launcher","--command","exit 7",NULL};
 assert(launcher_main(1,args)==64);
 assert(setenv("COUCHROOT_TEST_SECRET","must-not-reach-child",1)==0);
 for(failure=0;failure<=11;failure++) {
  stage=executions=0;errno=EPERM;sentinel=open("/dev/null",O_RDONLY);assert(sentinel>2 && sentinel!=99);
  assert(launcher_main(3,args)==77);
  assert(executions==((failure==0 || failure==11) ? 1 : 0));
  close(sentinel);
 }
 puts("PASS fail-closed transitions, descriptor cleanup, clean environment and exact shell arguments");return 0;
}
