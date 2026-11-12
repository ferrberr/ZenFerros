#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <malloc.h>
#include <errno.h>
#include <sys/personality.h>
#include <unistd.h>
_Alignas(4096) static uint8_t state[4096], bitmap[8192], tables[36*4096], arena[65536];
static uint64_t loaded_cr3, wp=0x10000, nx=1;
static unsigned invalidates;
uint64_t ferros_thread_stack_guard(uint64_t id){return id>=1&&id<=3 ? 0x800000+id*0x10000 : 0;}
void ferros_invlpg(uint64_t address){if(address==0x810000) invalidates++;}
extern bool test_guard_page(uint64_t);
uint64_t ferros_memory_state(void){return (uintptr_t)state;}
uint64_t ferros_pmm_bitmap(void){return (uintptr_t)bitmap;}
uint64_t ferros_page_tables(void){return (uintptr_t)tables;}
uint64_t ferros_heap_start(void){return (uintptr_t)arena;}
uint64_t ferros_heap_end(void){return (uintptr_t)arena+sizeof arena;}
uint64_t ferros_kernel_end(void){return 0x1000000;}
uint64_t ferros_text_start(void){return 0x100000;}
uint64_t ferros_text_end(void){return 0x102000;}
uint64_t ferros_rodata_start(void){return 0x102000;}
uint64_t ferros_rodata_end(void){return 0x104000;}
uint64_t ferros_enable_nx(void){return nx;}
uint64_t ferros_read_cr0(void){return wp;}
uint64_t ferros_read_cr3(void){return loaded_cr3;}
void ferros_load_cr3(uint64_t value){loaded_cr3=value;}
extern bool test_pmm_init(uint64_t);
extern uint64_t test_pmm_alloc(void), test_free_count(void);
extern bool test_pmm_free(uint64_t), test_pmm_self(void),test_vmm_init(void),test_vmm_self(void),test_heap_self(void);
extern void test_heap_init(void);
extern uint64_t test_heap_alloc(uint64_t,uint64_t);
#define INFO 0x20000u
#define MAP 0x21001u
static void u32(uintptr_t at,uint32_t value){memcpy((void*)at,&value,4);}
static void u64(uintptr_t at,uint64_t value){memcpy((void*)at,&value,8);}
static void record(uintptr_t at,uint32_t size,uint64_t base,uint64_t length,uint32_t type){u32(at,size);u64(at+4,base);u64(at+12,length);u32(at+20,type);}
static void valid(void){
    memset((void*)INFO,0,0x10000);
    u32(INFO,0x40);u32(INFO+44,52);u32(INFO+48,MAP);
    record(MAP,24,0x2000000,0x2000000,1); // Extended size and unaligned metadata.
    record(MAP+28,20,0x2002001,1,2); // One overlapping partial page reserved.
}
static void require(int condition,const char* what){if(!condition){fprintf(stderr,"FAILED: %s\n",what);exit(1);}}
static void invalid(const char* what){require(!test_pmm_init(INFO),what);require(test_pmm_alloc()==0,"failed init disables alloc");}
int main(int argc,char**argv){
    (void)argc;
    // The fixed 32 MiB window can collide with ASLR-placed heap/sanitizer
    // mappings. Re-exec once with randomization disabled for a stable layout.
    if(!getenv("ZEN_MOCK_NO_ASLR")){
        if(personality(ADDR_NO_RANDOMIZE)!=-1){
            setenv("ZEN_MOCK_NO_ASLR","1",1);
            execv("/proc/self/exe",argv);
        }
    }
    require(mmap((void*)INFO,0x10000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0)!=(void*)-1,"map boot metadata");
    // The fixed 32 MiB window 0x02000000..0x04000000 can collide with the libc
    // heap under ASLR. Trim the heap (lowering brk) and retry before failing.
    void *managed=(void*)-1;
    for(unsigned attempt=0;attempt<4 && managed==(void*)-1;attempt++){
        managed=mmap((void*)0x2000000,0x2000000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if(managed==(void*)-1 && errno==EEXIST){ malloc_trim(0); }
    }
    require(managed!=(void*)-1,"map managed pages");
    valid();require(test_pmm_init(INFO),"valid extended unaligned mmap");
    require(test_free_count()==8191,"reserved partial page overrides available");
    uint64_t first=test_pmm_alloc(),second=test_pmm_alloc();
    require(first==0x2000000 && second==0x2001000,"allocator exact first pages");
    require(!test_pmm_free(0x2002000),"reject reserved page");
    require(!test_pmm_free(first+1),"reject unaligned free");
    require(test_pmm_free(first)&&!test_pmm_free(first)&&test_pmm_free(second),"free and double free");
    require(test_free_count()==8191 && test_pmm_self(),"PMM selftest exhaustion and restore");
    require(test_free_count()==8191,"free count after exhaustion restore");
    // Reverse firmware records: reserved priority must not depend on order.
    valid();record(MAP,24,0x2002001,1,2);record(MAP+28,20,0x2000000,0x2000000,1);
    require(test_pmm_init(INFO)&&test_free_count()==8191,"reserved precedence reversed order");
    valid();u32(INFO,0);invalid("missing mmap flag");
    valid();u32(MAP,19);invalid("short entry");
    valid();u32(MAP,0xffffffff);invalid("stride beyond table");
    valid();u32(INFO+44,51);invalid("truncated final entry");
    valid();u32(INFO+48,0xffff0);invalid("map beyond low boot region");
    valid();u64(MAP+4,UINT64_MAX-10);u64(MAP+12,20);invalid("base length overflow");
    valid();u32(INFO,0x48);u32(INFO+20,1);invalid("modules rejected");
    valid();u32(INFO,0x60);invalid("unsupported symbol data rejected");
    valid();u32(INFO,0x44);u32(INFO+16,0x4000000);invalid("command string beyond direct map");
    valid();u32(INFO,0x44);u32(INFO+16,0x23000);memset((void*)0x23000,'a',4096);invalid("unterminated command string");
    valid();u32(INFO,0x244);u32(INFO+16,0x23000);u32(INFO+64,0x24000);strcpy((char*)0x23000,"boot");strcpy((char*)0x24000,"loader");
    require(test_pmm_init(INFO),"supported low strings");
    valid();u32(INFO,0x244);u32(INFO+16,0x2000000);u32(INFO+64,0x2002050);
    strcpy((char*)0x2000000,"kernel command line");strcpy((char*)0x2002050,"QEMU loader");
    require(test_pmm_init(INFO),"loader strings above kernel end accepted");
    require(test_pmm_alloc()==0x2003000,"high loader strings reserved through highest page");
    require(!test_pmm_free(0x2000000)&&!test_pmm_free(0x2001000)&&!test_pmm_free(0x2002000),"boot strings and conservative gap reserved");
    valid();u32(INFO,0x44);u32(INFO+16,0x3fffffe);memset((void*)0x3fffffe,'a',2);
    invalid("string without NUL before direct-map boundary");
    // Availability is aligned inward; only the two complete interior pages survive.
    valid();u32(INFO+44,24);record(MAP,20,0x2000001,0x3ffe,1);
    require(test_pmm_init(INFO)&&test_free_count()==2,"partial available pages discarded");
    require(test_pmm_alloc()==0x2001000 && test_pmm_alloc()==0x2002000 && test_pmm_alloc()==0,"exact exhaustion");
    valid();u32(INFO+44,24);record(MAP,20,0,0x1000000,1);invalid("kernel and low memory reserved");
    valid();u32(INFO+44,24);record(MAP,20,0x4000000,0x100000,1);invalid("above direct map cap ignored");
    valid();require(test_pmm_init(INFO),"reinit after failures");
    require(test_heap_self(),"heap aligned allocation/exhaustion/overflow selftest");
    test_heap_init();require(test_heap_alloc(1,1)==(uintptr_t)arena,"heap first allocation");
    require(test_heap_alloc(1,1ull<<63)==0,"heap huge alignment rejected by bounds");
    test_heap_init();require(test_heap_alloc(sizeof arena,1)==(uintptr_t)arena && test_heap_alloc(1,1)==0,"heap full capacity exact bound");
    require(test_vmm_init()&&test_vmm_self(),"VMM structure, CR3, permissions");
    uint64_t* t=(void*)tables;
    require(t[0]==((uintptr_t)tables+4096+3),"PML4 pointer");
    require(t[1536]==0,"null leaf unmapped");
    require((t[1536+0x100000/4096]&((1ull<<63)|7))==1,"text RX");
    require((t[1536+0x102000/4096]&((1ull<<63)|7))==((1ull<<63)|1),"rodata R NX");
    require((t[1536+0x2000000/4096]&((1ull<<63)|7))==((1ull<<63)|3),"data RW NX");
    require(!test_guard_page(0x100000) && !test_guard_page(0x900000) && !test_guard_page(0x810001),"reject arbitrary or unaligned guard page");
    require(test_guard_page(0x810000) && invalidates==1,"approved guard is removed and flushed");
    require(t[1536+0x810000/4096]==0 && !test_guard_page(0x810000),"no double guard removal");
    require((t[1536+0x820000/4096]&1)==1,"other guards remain present until explicitly removed");
    wp=0;require(!test_vmm_init(),"WP required");wp=0x10000;
    nx=0;require(!test_vmm_init(),"NX required");nx=1;
    puts("Memory Zen PMM valid/malformed maps, overlap/reservations/exhaustion, heap and VMM verified");
    return 0;
}
