/* Exercise the native worker's real wire reader/MAC implementation offline. */
#include "../research/autonomous-root/native-worker/common.h"
int main(int argc,char **argv) {
 if(argc!=5)return 2;
 if(!strcmp(argv[1],"timeout"))return exec_timeout_valid(strtoll(argv[4],NULL,10),0)?0:1;
 libraries();Wire w={.fd=0};
 if(!unhex(argv[2],w.secret,32)||!unhex(argv[3],w.nonce,32))return 2;
 char *value=!strcmp(argv[1],"mac")?receive(&w):(strtoul(argv[4],NULL,10)==512?bounded_line(&w,PREAUTH_BYTES):line(&w));
 if(!strcmp(argv[1],"mac"))puts(value);
 free(value);return 0;
}
