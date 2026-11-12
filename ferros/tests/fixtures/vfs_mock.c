/* Host-only mocks for the VFS unit suite: plain buffers, no privileged code. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern uint64_t test_vfs_suite(void);

_Alignas(4096) static uint64_t vfs_state[512];
_Alignas(4096) static unsigned char ramfs_pool[256][4096];

#define PTR(x) ((uint64_t)(uintptr_t)(x))

uint64_t test_vfs_state(void){return PTR(vfs_state);}
uint64_t test_ramfs_pool(void){return PTR(ramfs_pool);}

int main(void){
    memset(vfs_state,0,sizeof vfs_state);
    memset(ramfs_pool,0,sizeof ramfs_pool);
    uint64_t failures=test_vfs_suite();
    if(failures){
        fprintf(stderr,"VFS suite failures bitmask=0x%llx\n",(unsigned long long)failures);
        return 1;
    }
    printf("VFS OK: init/open/read/close, EBADF, ENOENT, EISDIR, EACCES, EMFILE, reuse, ENOSPC\n");
    return 0;
}
