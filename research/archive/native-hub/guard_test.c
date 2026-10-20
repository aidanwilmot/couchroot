#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include "native-guard.h"
#include "../../../native/common/platform-matrix.h"
int main(void) {
    platform_matrix();
    const char *valid[]={"isp-service","MiniHub001.Hub","lcdon",""};
    assert(native_settings_match(valid[0],valid[1],valid[2],valid[3]));
    for(int i=0;i<4;i++) {
        const char *v[]={valid[0],valid[1],valid[2],valid[3]};
        v[i]=NULL; assert(!native_settings_match(v[0],v[1],v[2],v[3]));
        v[i]="unexpected"; assert(!native_settings_match(v[0],v[1],v[2],v[3]));
    }
    assert(!native_settings_match("tv",valid[1],valid[2],valid[3]));
    assert(!native_settings_match(valid[0],valid[1],"lcdoff",valid[3]));
    assert(!native_settings_match(valid[0],valid[1],valid[2],"MiniHub001.Hub"));
    assert(!native_settings_match(valid[0],valid[1],valid[2]," "));
    puts("Native guard denial matrix passed");
}
