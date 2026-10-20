/* One contract matrix included by both launcher host test suites. */
#include <assert.h>
static int matrix_writes;
static const char *matrix_isp, *matrix_last, *matrix_fg;
static char *matrix_get(const char *key) {
 const char *v=!strcmp(key,"db/was/isp_app_id")?matrix_isp:!strcmp(key,"db/boot/last_service")?matrix_last:matrix_fg;
 return v?strdup(v):NULL;
}
static int matrix_set(const char *key,const char *value) {
 assert(!strcmp(key,"db/boot/last_service"));assert(!strcmp(value,"isp-service"));
 matrix_writes++;matrix_last=value;return 0;
}
static void platform_matrix(void) {
 const char *valid[]={"isp-service","MiniHub001.Hub","lcdon",""};
 assert(native_settings_match(valid[0],valid[1],valid[2],valid[3]));
 assert(home_settings_match(valid[0],valid[1],valid[2],"consumer.app"));
 for(int i=0;i<4;i++) {
  const char *v[]={valid[0],valid[1],valid[2],valid[3]};v[i]=NULL;
  assert(!native_settings_match(v[0],v[1],v[2],v[3]));assert(!home_settings_match(v[0],v[1],v[2],v[3]));
  v[i]="unexpected";assert(!native_settings_match(v[0],v[1],v[2],v[3]));
 }
 normal_settings_note(valid[0],valid[1],"lcdoff","");assert(normal_state==NORMAL_WAIT);
 normal_settings_note(valid[0],valid[1],valid[2],TV_VIEWER);assert(normal_state==NORMAL_LAUNCH);
 assert(normal_settings_note(valid[0],valid[1],valid[2],"MiniHub001.Hub"));
 normal_settings_note(valid[0],valid[1],valid[2],"consumer.app");assert(normal_state==NORMAL_CANCEL);
 normal_settings_note("tv",valid[1],valid[2],"");assert(normal_state==NORMAL_CANCEL);
 matrix_isp=valid[1];matrix_last="tv";matrix_fg=TV_VIEWER;matrix_writes=0;
 assert(source_rearm(matrix_get,matrix_set,1).result==REARM_NEEDED);assert(!matrix_writes);
 assert(source_rearm(matrix_get,matrix_set,0).result==REARM_NEEDED);assert(matrix_writes==1);
 assert(source_rearm(matrix_get,matrix_set,0).result==REARM_OK);assert(matrix_writes==1);
 assert(source_rearm(matrix_get,matrix_set,1).result==REARM_OK);assert(matrix_writes==2);
 matrix_isp=NULL;assert(source_rearm(matrix_get,matrix_set,0).result==REARM_UNREADABLE);assert(matrix_writes==2);
 matrix_isp="other";assert(source_rearm(matrix_get,matrix_set,0).result==REARM_NOT_ISP);assert(matrix_writes==2);
 assert(platform_consumer("org.tizen.netflix-app",NULL,0));
 assert(platform_consumer("third.party","Abcdef1234",0));
 assert(!platform_consumer("internal.tool","org.tizen.internal",1));
 assert(!platform_consumer("com.samsung.tv.tvplus","org.tizen.internal",0));
 assert(platform_consumer("com.samsung.tv.tvplus","org.tizen.internal",1));
 int pair[2];assert(!platform_pipe(pair));
 assert(fcntl(pair[0],F_GETFD)&FD_CLOEXEC);assert(fcntl(pair[1],F_GETFD)&FD_CLOEXEC);close(pair[0]);close(pair[1]);
 assert(!platform_socketpair(pair));assert(fcntl(pair[0],F_GETFD)&FD_CLOEXEC);assert(fcntl(pair[1],F_GETFD)&FD_CLOEXEC);close(pair[0]);close(pair[1]);
 puts("Shared platform matrix: boot/Home, normal mode, rearm/probe, consumer policy and CLOEXEC passed");
}
