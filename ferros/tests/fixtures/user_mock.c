#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>

extern _Bool test_elf(uint64_t,uint64_t),test_load(uint64_t,uint64_t),test_clear(void),test_buffer(uint64_t,uint64_t);
extern uint64_t test_write(uint64_t,uint64_t);
extern void test_dispatch(uint64_t,uint64_t,uint64_t,uint64_t);
_Alignas(4096) static uint64_t state[512],tables[1024];
_Alignas(4096) static unsigned char pool[32][4096];
_Alignas(4096) static uint64_t trap[4096];
_Alignas(4096) static uint64_t vfs_state[512];
_Alignas(4096) static unsigned char ramfs_pool[256][4096];
_Alignas(16) static unsigned char scratch[512];
static unsigned char elf[16384],original[16384],used[32];
static unsigned allocations,fail_at,serial_bytes,panics,leaves,invalidations;
static jmp_buf escape;
static const size_t elf_len=12289;
#define PTR(x) ((uint64_t)(uintptr_t)(x))
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static void w16(size_t o,uint16_t v){memcpy(elf+o,&v,2);}
static void w32(size_t o,uint32_t v){memcpy(elf+o,&v,4);}
static void w64(size_t o,uint64_t v){memcpy(elf+o,&v,8);}
static uint64_t r64(const unsigned char *p){uint64_t v;memcpy(&v,p,8);return v;}
static uint64_t free_count(void){unsigned n=0;for(unsigned i=0;i<32;i++)n+=!used[i];return n;}
uint64_t test_free_count(void){return free_count();}
uint64_t test_pmm_alloc(void){
    if(++allocations==fail_at)return 0;
    for(unsigned i=0;i<32;i++)if(!used[i]){used[i]=1;memset(pool[i],0xa5,4096);return PTR(pool[i]);}
    return 0;
}
uint64_t test_pmm_free(uint64_t p){
    for(unsigned i=0;i<32;i++)if(p==PTR(pool[i])&&used[i]){used[i]=0;return 1;}
    return 0;
}
uint64_t test_serial(uint8_t v){(void)v;serial_bytes++;return 1;}
void test_panic(void){panics++;longjmp(escape,1);}
uint64_t ferros_user_state(void){return PTR(state);}
uint64_t ferros_user_tables(void){return PTR(tables);}
uint64_t ferros_user_kernel_stack_bottom(void){return PTR(trap);}
uint64_t ferros_user_kernel_stack_top(void){return PTR(trap+4096);}
uint64_t ferros_user_scratch(void){return PTR(scratch);}
uint64_t ferros_vfs_state(void){return PTR(vfs_state);}
uint64_t ferros_ramfs_pool(void){return PTR(ramfs_pool);}
void ferros_invlpg(uint64_t a){(void)a;invalidations++;}
uint64_t ferros_page_tables(void){abort();}
uint64_t ferros_read_cr3(void){abort();}
void ferros_load_cr3(uint64_t a){(void)a;abort();}
uint64_t ferros_rodata_end(void){abort();}
uint64_t ferros_kernel_end(void){abort();}
uint64_t ferros_user_arch_init(void){abort();}
uint64_t ferros_user_image_start(void){abort();}
uint64_t ferros_user_image_end(void){abort();}
uint64_t ferros_user_enter(uint64_t a,uint64_t b,uint64_t c){(void)a;(void)b;(void)c;abort();}
void ferros_user_leave(uint64_t status){(void)status;leaves++;longjmp(escape,2);}
static void make_elf(void){
    memset(elf,0,sizeof elf);memcpy(elf,"\177ELF\2\1\1",7);
    w16(16,2);w16(18,62);w32(20,1);w64(24,0x40000000);w64(32,64);
    w16(52,64);w16(54,56);w16(56,3);
    for(unsigned i=0;i<3;i++){
        size_t h=64+i*56;w32(h,1);w32(h+4,i==0?5:i==1?4:6);
        w64(h+8,(i+1)*4096);w64(h+16,0x40000000+i*4096);w64(h+24,0x40000000+i*4096);
        w64(h+32,1);w64(h+40,i==2?8192:1);w64(h+48,4096);
        elf[(i+1)*4096]=(unsigned char)(0x80+i);
    }
    memcpy(original,elf,sizeof elf);
}
static void reset(void){
    memset(state,0,sizeof state);state[0]=1;memset(tables,0,sizeof tables);
    memset(used,0,sizeof used);allocations=fail_at=serial_bytes=panics=leaves=invalidations=0;
    memcpy(elf,original,sizeof elf);
}
int main(void){
    make_elf();reset();CHECK(test_elf(PTR(elf),elf_len));
    // Header and segment mutations cover boundary arithmetic, entry, W^X,
    // alignment, truncation, file/memory extents and page overlap.
    struct Mutation{size_t offset;uint64_t value;unsigned width;} bad[]={
        {0,0,4},{4,1,1},{5,2,1},{6,0,1},{7,3,1},{16,3,2},{18,3,2},{20,0,4},
        {24,0x40001000,8},{24,0x40000001,8},{32,UINT64_MAX,8},{32,0,8},
        {48,1,4},{52,63,2},{54,55,2},{56,0,2},{56,9,2},
        {64,2,4},{68,7,4},{68,1,4},{68,13,4},{72,UINT64_MAX,8},{72,4097,8},
        {80,0x100000,8},{80,0x40100000,8},{80,0x40000001,8},{88,0,8},
        {96,4097,8},{104,0,8},{104,UINT64_MAX,8},{112,8192,8},
        {136,0x40000000,8},{144,0x40000000,8},
    };
    unsigned rejected=0;
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++){
        memcpy(elf,original,sizeof elf);memcpy(elf+bad[i].offset,&bad[i].value,bad[i].width);
        CHECK(!test_elf(PTR(elf),elf_len));rejected++;
    }
    memcpy(elf,original,sizeof elf);
    for(unsigned n=0;n<64;n++)CHECK(!test_elf(PTR(elf),n));
    CHECK(!test_elf(PTR(elf),131073));CHECK(!test_elf(UINT64_MAX-10,64));
    // Every allocation failure unwinds previously published leaves and PMM.
    for(unsigned failure=1;failure<=8;failure++){
        reset();fail_at=failure;CHECK(!test_load(PTR(elf),elf_len));
        CHECK(free_count()==32&&state[10]==0);
        for(unsigned i=512;i<1024;i++)CHECK(!tables[i]);
    }
    reset();CHECK(test_load(PTR(elf),elf_len));CHECK(free_count()==24);
    CHECK(state[9]==0x40000000&&state[10]==1);
    CHECK((tables[512]&UINT64_C(0x8000000000000007))==5);
    CHECK((tables[513]&UINT64_C(0x8000000000000007))==UINT64_C(0x8000000000000005));
    CHECK((tables[514]&UINT64_C(0x8000000000000007))==UINT64_C(0x8000000000000007));
    for(unsigned p=0;p<4;p++){
        const unsigned char *bytes=(void*)(uintptr_t)(tables[512+p]&UINT64_C(0x000ffffffffff000));
        CHECK(bytes[0]==(p<3?0x80+p:0));
        for(unsigned j=1;j<4096;j++)CHECK(bytes[j]==0);
    }
    CHECK(!tables[512+507]&&tables[512+508]&&tables[1023]);
    CHECK(test_buffer(0x40000000,4097));CHECK(!test_buffer(0x40003fff,2));
    CHECK(!test_buffer(0x100000,1));CHECK(!test_buffer(UINT64_MAX,2));
    CHECK(!test_buffer(0x401fbfff,2));CHECK(test_buffer(0x401fc000,16384));
    tables[513]&=~UINT64_C(4);CHECK(!test_buffer(0x40000fff,2));tables[513]|=4;
    CHECK(test_write(0x40003fff,2)==(uint64_t)-14&&serial_bytes==0);
    CHECK(test_write(0x100000,1)==(uint64_t)-14&&serial_bytes==0);
    CHECK(test_write(UINT64_MAX,4097)==(uint64_t)-22&&serial_bytes==0);
    CHECK(!test_load(PTR(elf),elf_len));CHECK(test_clear());CHECK(free_count()==32);
    // Mock trap stack: verify syscall result slot and system/user classification.
    uint64_t *frame=trap+4096-5;
    memset(trap,0,sizeof trap);frame[1]=0x23;frame[4]=0x1b;state[1]=1;
    // RAX is three slots below RIP, inside the same whole trap array.
    trap[4088]=999;test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-38);
    trap[4088]=3;test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==42);
    // syscall 5: the kernel writes into the user buffer, so a read-only page
    // must be rejected with EFAULT before any store; a writable page with an
    // unopened descriptor then reports EBADF.
    state[1]=1;trap[4088]=5;
    trap[4083]=100; /* RDI: fd */
    trap[4084]=0x40000000u; /* RSI: user buffer */
    trap[4085]=1; /* RDX: count */
    tables[512]=UINT64_C(0x8000000000000005); /* present, user, read-only */
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-14);
    tables[512]|=UINT64_C(2);
    trap[4088]=5;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-9);
    // syscall 6: CPL3 write is denied by mode (EACCES) before any store.
    vfs_state[0]=1;vfs_state[129]=PTR(ramfs_pool);
    *((uint64_t*)ramfs_pool)=1;*((uint64_t*)ramfs_pool+1)=420; /* file, 0644 */
    trap[4088]=6;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-13);
    trap[4088]=6;trap[4084]=0;trap[4085]=1;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-14);
    trap[4088]=6;trap[4084]=UINT64_MAX-1;trap[4085]=4;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-14);
    trap[4088]=6;trap[4084]=0x40000000u;trap[4085]=4097;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-22);
    vfs_state[0]=0;
    // syscall 9 (readdir): size limit, writable destination, uninitialised VFS.
    trap[4088]=9;trap[4083]=0x40000000u;trap[4084]=4097u;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-22);
    tables[512]=UINT64_C(0x8000000000000005);
    trap[4088]=9;trap[4084]=1u;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-14);
    tables[512]=UINT64_C(0x8000000000000007);
    trap[4088]=9;
    test_dispatch(128,0,PTR(frame),0);CHECK(trap[4088]==(uint64_t)-1);
    test_dispatch(32,0,PTR(frame),0);CHECK(state[8]==1);
    const unsigned fatal[]={2,8,18,33,255};
    for(unsigned i=0;i<sizeof fatal/sizeof fatal[0];i++){
        state[1]=1;unsigned old=panics;
        if(!setjmp(escape))test_dispatch(fatal[i],0,PTR(frame),0);
        CHECK(panics==old+1&&!leaves&&state[1]==1);
    }
    if(!setjmp(escape))test_dispatch(14,13,PTR(frame),0x100000);
    CHECK(panics==6&&!leaves&&state[1]==1);
    if(!setjmp(escape))test_dispatch(14,5,PTR(frame),0x100000);
    CHECK(leaves==1&&!state[1]&&state[2]==142&&state[3]==14&&state[4]==5&&state[5]==0x100000);
    state[1]=1;frame[1]=8;
    if(!setjmp(escape))test_dispatch(128,0,PTR(frame),0);
    CHECK(panics==7&&leaves==1);
    printf("ELF %u mutations, truncation, 8 rollback stages, BSS/WX, buffers and trap classification verified\n",rejected);
    return 0;
}
