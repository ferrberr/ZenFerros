"""Verify Zen descriptor/dispatch/PIC/PIT policy using host-safe architecture mocks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from build_ferros import build_kernel
from boot_ferros import boot

SHIMS=r"""
extern "C" { fn test_panic(); }
fn out8(port:u16,value:u8) { unsafe { ferros_out8(port,value); } }
fn kernel_panic(reason:str) { unsafe { test_panic(); } }
fn scheduler_on_timer() {}
fn user_trap_origin(frame:u64)->bool { return false; }
fn user_interrupt_dispatch(vector:u64,error:u64,frame:u64,cr2:u64) { unsafe { test_panic(); } }
pub fn test_irq_flow()->u64 {
    interrupts_init();
    if !breakpoint_self_test() { return 1; }
    if !page_fault_self_test() { return 2; }
    if !timer_self_test() { return 3; }
    return 0;
}
"""
HARNESS=r"""
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
_Alignas(4096) static uint64_t state[512], idt[512];
static unsigned panics,errors,eois,waits,pitbytes;
static unsigned char master_mask,pit[2],pit_command;
extern uint64_t test_irq_flow(void);
extern void interrupt_dispatch(uint64_t,uint64_t,uint64_t,uint64_t);
uint64_t ferros_interrupt_state(void){return (uint64_t)(uintptr_t)state;}
uint64_t ferros_idt_address(void){return (uint64_t)(uintptr_t)idt;}
uint64_t ferros_isr_address(uint64_t v){return UINT64_C(0xffff800012340000)+v*16;}
uint64_t ferros_text_start(void){return 0;}
uint64_t ferros_kernel_end(void){return UINT64_MAX;}
uint64_t ferros_thread_stack_guard(uint64_t id){return id>=1 && id<=3 ? 0x800000+id*0x10000 : 0;}
void ferros_load_idt(uint64_t base,uint16_t limit){if(base!=(uint64_t)(uintptr_t)idt||limit!=4095)errors++;}
void ferros_interrupt_disable(void){}
void test_panic(void){panics++;}
uint64_t ferros_null_fault_site(void){return 0x111;}
uint64_t ferros_null_fault_resume(void){return 0x222;}
uint64_t ferros_ro_fault_site(void){return 0x333;}
uint64_t ferros_ro_fault_resume(void){return 0x444;}
uint64_t ferros_ro_fault_address(void){return 0x9000;}
void ferros_breakpoint(void){interrupt_dispatch(3,0,0,0);}
void ferros_probe_null(void){uint64_t rip=0x111;interrupt_dispatch(14,0,(uint64_t)(uintptr_t)&rip,0);if(rip!=0x222)errors++;}
void ferros_probe_write_ro(void){uint64_t rip=0x333;interrupt_dispatch(14,3,(uint64_t)(uintptr_t)&rip,0x9000);if(rip!=0x444)errors++;}
void ferros_wait_interrupt(void){waits++;interrupt_dispatch(32,0,0,0);}
void ferros_out8(uint16_t port,uint8_t value){
    if(port==0x21)master_mask=value;
    if(port==0x20&&value==0x20)eois++;
    if(port==0x43)pit_command=value;
    if(port==0x40){if(pitbytes<2)pit[pitbytes]=value;pitbytes++;}
}
int main(void){
    if(test_irq_flow()!=0||panics||errors)return 1;
    if(state[0]!=1||state[1]!=2||state[2]!=3||state[3]||state[5]||state[6]||state[7])return 2;
    if(waits!=3||eois!=3||master_mask!=255||pit_command!=0x36||pitbytes!=2||pit[0]!=0x9c||pit[1]!=0x2e)return 3;
    if(idt[0]!=UINT64_C(0x12348e0000080000)||idt[1]!=UINT64_C(0xffff8000))return 4;
    if(idt[510]!=UINT64_C(0x12348e0000080ff0)||idt[511]!=UINT64_C(0xffff8000))return 5;
    uint64_t rip=0x111;state[3]=1;
    interrupt_dispatch(14,0,(uint64_t)(uintptr_t)&rip,123);
    if(panics!=1||rip!=0x111||state[3]!=1)return 6;
    interrupt_dispatch(14,0,1,0);if(panics!=2)return 7;
    state[3]=0;interrupt_dispatch(3,0,0,0);if(panics!=3)return 8;
    interrupt_dispatch(32,0,0,0);if(panics!=4)return 9;
    puts("IDT, one-shot PF recovery, unarmed/fatal paths, PIC EOI and PIT policy verified");
    return 0;
}
"""

class InterruptPolicyTests(unittest.TestCase):
    def test_zen_interrupt_policy_and_fatal_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            source="\n".join((ROOT/"ferros/kernel"/p).read_text() for p in ["arch/x86_64/abi.zen","interrupts.zen"])+SHIMS
            (tmp/"test.zen").write_text(source);(tmp/"mock.c").write_text(HARNESS)
            for optimized in [False,True]:
                with self.subTest(optimized=optimized):
                    cmd=[str(ROOT/"zen/compiler/target/release/zen"),"build",str(tmp/"test.zen"),"--target","x86_64-unknown-none","--emit","obj","-o",str(tmp/"test.o")]
                    if optimized:cmd.append("--release")
                    subprocess.run(cmd,check=True,capture_output=True,timeout=30)
                    subprocess.run(["cc","-std=c11","-no-pie",str(tmp/"mock.c"),str(tmp/"test.o"),"-o",str(tmp/"mock")],check=True,capture_output=True,timeout=30)
                    out=subprocess.run([str(tmp/"mock")],capture_output=True,timeout=5)
                    self.assertEqual(out.returncode,0,out.stderr.decode())

    def test_unexpected_exception_in_real_qemu_fails_and_saves_panic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            for release in [False,True]:
                with self.subTest(release=release):
                    output=tmp/("release" if release else "debug")
                    build=build_kernel(ROOT/"zen/compiler/target/release/zen",output,release,ROOT/"ferros/tests/unexpected_exception.zen")
                    with self.assertRaisesRegex(RuntimeError,"status 35"):
                        boot(build["image_path"],output/"negative-boot")
                    result=json.loads((output/"negative-boot/result.json").read_text())
                    serial=(output/"negative-boot/serial.log").read_bytes()
                    self.assertEqual(result["status"],35)
                    self.assertIn(b"FERROS PANIC: unexpected interrupt or exception\n",serial)
                    self.assertNotIn(b"HITO 7 OK",serial)

if __name__=="__main__":unittest.main()
