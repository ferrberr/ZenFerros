#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
_Alignas(4096) static uint8_t stacks[3][36864];
_Alignas(4096) static uint64_t state[512];
static uint64_t flags=512;
static unsigned guards,fail_guard,timers;
static jmp_buf panic_target;
extern bool test_init(void),test_self(void),test_stack(uint64_t),test_running(void);
extern uint64_t test_get(uint64_t),test_next(uint64_t);
extern void test_set(uint64_t,uint64_t),test_yield(void),test_timer(void),thread_returned(void);
static void require(bool ok,const char *why){if(!ok){fprintf(stderr,"FAILED %s\n",why);exit(1);}}
uint64_t ferros_irq_save(void){uint64_t old=flags;flags&=~512u;return old;}
void ferros_irq_restore(uint64_t old){flags=(flags&~512u)|(old&512u);}
uint64_t ferros_scheduler_state(void){return (uintptr_t)state;}
uint64_t ferros_thread_stack_guard(uint64_t id){return id>=1&&id<=3?(uintptr_t)stacks[id-1]:0;}
uint64_t ferros_thread_stack_top(uint64_t id){return ferros_thread_stack_guard(id)+36864;}
uint64_t ferros_thread_trampoline(void){return 0x12345678;}
void ferros_context_switch(uint64_t old,uint64_t next){(void)old;(void)next;require(false,"host must never switch CPU context");}
uint64_t ferros_context_probe(void){require(false,"host must never probe privileged CPU state");return 0;}
void host_panic(void){require(!(flags&512),"panic IF off");longjmp(panic_target,1);}
bool host_guard(uint64_t address){require(!(flags&512),"guard IF off");guards++;require(address==ferros_thread_stack_guard(guards),"guard exact IDs/order");return guards!=fail_guard;}
uint64_t host_ticks(void){return 3;}
void host_timer_start(void){timers++;}
void host_timer_stop(void){timers++;}
static void reset(void){memset(state,0,sizeof state);memset(stacks,0,sizeof stacks);flags=512;guards=fail_guard=timers=0;}
static uint64_t rec(unsigned id,unsigned offset){return 128+id*128+offset;}
int main(void){
 reset();require(test_init(),"init succeeds");require(flags==512&&guards==3,"init IRQ restoration/three guards");
 require(test_get(0)==1&&test_get(8)==0&&test_get(rec(0,8))==2,"controller initialized");
 require(!test_init()&&flags==512&&guards==3,"init cannot reset live stacks");
 for(unsigned id=1;id<=3;id++){
  uint64_t top=ferros_thread_stack_top(id),rsp=test_get(rec(id,0));
  require(rsp==top-64&&test_stack(id),"initial stack range/canary");
  uint64_t *f=(void*)(uintptr_t)rsp;
  require(f[0]==0&&f[1]==0&&f[2]==0&&f[3]==id&&f[4]==0&&f[5]==0&&f[6]==0x12345678&&f[7]==0,"initial six-GPR frame ABI");
  require(test_get(rec(id,8))==1&&test_get(rec(id,24))==id,"ready initial hash");
 }
 const unsigned states[]={1,3,4}; unsigned choices=0;
 for(unsigned a=0;a<3;a++)for(unsigned b=0;b<3;b++)for(unsigned c=0;c<3;c++){
  test_set(rec(1,8),states[a]);test_set(rec(2,8),states[b]);test_set(rec(3,8),states[c]);
  for(unsigned current=0;current<=3;current++){
   static const unsigned order[4][3]={{1,2,3},{2,3,0},{3,1,0},{1,2,0}};
   unsigned expected=0;
   for(unsigned slot=0;slot<3;slot++){unsigned candidate=order[current][slot];if(candidate && test_get(rec(candidate,8))==1){expected=candidate;break;}}
   require(test_next(current)==expected,"round robin skips blocked/exited/current");choices++;
  }
 }
 test_set(8,1);test_set(16,1);test_set(rec(0,8),4);
 test_set(rec(1,8),2);test_set(rec(2,8),1);test_set(rec(3,8),1);
 require(test_running(),"valid active state");
 test_set(rec(2,8),3);require(test_running(),"exited worker allowed but not selected");
 test_set(rec(2,8),9);require(!test_running(),"invalid state rejected");test_set(rec(2,8),1);
 uint64_t saved=test_get(rec(2,0));test_set(rec(2,0),1);require(!test_stack(2),"saved RSP outside stack rejected");test_set(rec(2,0),saved);
 uint64_t *canary=(void*)(uintptr_t)test_get(rec(3,48));(*canary)++;require(!test_stack(3),"stack canary corruption rejected");(*canary)--;
 test_set(8,0);uint64_t before=test_get(56);test_timer();require(test_get(56)==before&&flags==512,"inactive IRQ is inert and restores IF");
 if(!setjmp(panic_target)){test_yield();require(false,"invalid active state must panic");}require(test_get(64)==1&&test_get(24)==0,"invalid yield fails before switch");
 if(!setjmp(panic_target)){thread_returned();require(false,"thread return must panic");}require(test_get(64)==2,"returned worker counted as failure");
 reset();fail_guard=2;require(!test_self()&&test_get(0)==0&&guards==2&&timers==0&&flags==512,"guard failure prevents scheduler start/switch and restores flags");
 printf("Scheduler host: %u policy choices, frames, IF restoration, invalid states/canaries/RSP, init failure and fatal return verified\n",choices);
}
