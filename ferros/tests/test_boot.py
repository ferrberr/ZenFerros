"""Boot pipeline regression: host-safe UART mocks and runner failure paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import signal
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from boot_ferros import EXPECTED, PERSIST_LINE, PFS_LINE, SUCCESS_STATUS, validate_boot, run_process, qemu_environment
from build_ferros import inspect_image

HARNESS=r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern void kernel_entry(uint64_t,uint64_t);
static unsigned char bytes[256], divisor, line_control, modem, fifo, interrupts;
static unsigned length, bad_port, halted, line_reads;
static uint32_t status;
static int fail_loopback, stuck;
uint8_t ferros_in8(uint16_t port) {
    if (port==0x3f8) return fail_loopback ? 0 : 0xae;
    if (port==0x3fd) { line_reads++; return stuck ? 0 : 0x20; }
    bad_port++; return 0;
}
void ferros_out8(uint16_t port,uint8_t value) {
    if(port==0x3fb) line_control=value;
    else if(port==0x3fc) modem=value;
    else if(port==0x3fa) fifo=value;
    else if(port==0x3f9) interrupts=value;
    else if(port==0x3f8) {
        if(line_control&0x80) divisor=value;
        else if(!(modem&0x10)) { if(length<sizeof bytes) bytes[length++]=value; else bad_port++; }
    } else bad_port++;
}
void ferros_out32(uint16_t port,uint32_t value) { if(port!=0xf4) bad_port++; status=value; }
void ferros_halt(void) { halted++; }
static void reset(void) {
    memset(bytes,0,sizeof bytes); divisor=line_control=modem=fifo=interrupts=0;
    length=bad_port=halted=line_reads=status=0; fail_loopback=stuck=0;
}
static int check(const char* expected,uint32_t exit_code) {
    return !bad_port && halted==1 && status==exit_code && length==strlen(expected) && !memcmp(bytes,expected,length);
}
int main(void) {
    reset(); kernel_entry(0x2badb002,0x9500);
    if(!check("FERROS KERNEL\nPowered by Zen\nBoot successful\n",0x10)) return 1;
    if(divisor!=3 || line_control!=3 || modem!=0x0f || fifo!=0xc7 || interrupts!=0) return 2;
    reset(); kernel_entry(0,0x9500);
    if(!check("FERROS PANIC: invalid Multiboot handoff\n",0x11)) return 3;
    reset(); kernel_entry(0x2badb002,0);
    if(!check("FERROS PANIC: invalid Multiboot handoff\n",0x11)) return 4;
    reset(); fail_loopback=1; kernel_entry(0x2badb002,0x9500);
    if(!check("",0x11)) return 5;
    reset(); stuck=1; kernel_entry(0x2badb002,0x9500);
    if(!check("",0x11) || line_reads!=1000000) return 6;
    puts("Zen UART success, handoff panic, loopback failure and bounded polling verified");
    return 0;
}
"""

class BootValidationTests(unittest.TestCase):
    def test_exact_success_contract(self):
        validate_boot(SUCCESS_STATUS,EXPECTED,b"")

    def test_rejects_status_output_panic_stderr_and_timeout(self):
        for case in [(0,EXPECTED,b"",False),(35,EXPECTED,b"",False),(33,b"",b"",False),
                     (33,EXPECTED+b"FERROS PANIC\n",b"",False),(33,EXPECTED,b"error",False),
                     (33,EXPECTED,b"",True)]:
            with self.subTest(case=case),self.assertRaises(RuntimeError): validate_boot(*case)

    def test_scheduler_statistics_are_required_and_consistent(self):
        line=b"SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3\n"
        invalid=[EXPECTED.replace(line,b""), EXPECTED.replace(line,line+line),
                 EXPECTED.replace(b"preemptions=25",b"preemptions=1"),
                 EXPECTED.replace(b"yields=16",b"yields=15"),
                 EXPECTED.replace(b"completed=3",b"completed=2"),
                 EXPECTED.replace(b"switches=45",b"switches=1"),
                 line+EXPECTED.replace(line,b"")]
        for serial in invalid:
            with self.subTest(serial=serial),self.assertRaises(RuntimeError):
                validate_boot(33,serial,b"")

    def test_userspace_statistics_and_markers_are_required(self):
        line=b"USERSPACE: STATS runs=7 writes=18 rejected=6 irqs=1\n"
        invalid=[EXPECTED.replace(line,b""),EXPECTED.replace(line,line+line),
                 EXPECTED.replace(b"runs=7",b"runs=6"),EXPECTED.replace(b"rejected=6",b"rejected=5"),
                 EXPECTED.replace(b"irqs=1",b"irqs=0"),EXPECTED.replace(b"writes=18",b"writes=5"),
                 EXPECTED.replace(b"writes=18",b"writes=17"),
                 EXPECTED.replace(b"USERSPACE: ISOLATION AND CLEANUP OK\n",b""),
                 line+EXPECTED.replace(line,b"")]
        for serial in invalid:
            with self.subTest(serial=serial),self.assertRaises(RuntimeError):
                validate_boot(33,serial,b"")

    def test_shell_transcript_and_markers_are_required(self):
        marker=b"SHELL: READY\n"
        invalid=[EXPECTED.replace(marker,b""),EXPECTED.replace(marker,marker+marker),
                 EXPECTED.replace(b"SHELL: DONE\n",b""),
                 EXPECTED.replace(b"SHELL> help\ncommands: help ls cat put exit\n",b""),
                 EXPECTED.replace(b"commands: help ls cat put exit",b"commands: help ls"),
                 EXPECTED.replace(b"hello.zen\nnotes.txt\nboot.txt\n",b"hello.zen\nnotes.txt\n"),
                 EXPECTED.replace(b"hello.zen\nnotes.txt\nboot.txt\n",b"hello.zen\nboot.txt\nnotes.txt\n")]
        for serial in invalid:
            with self.subTest(serial=serial),self.assertRaises(RuntimeError):
                validate_boot(33,serial,b"")
        # TASK-919: `ls` lists RAMFS files first and then the PFS file, and only
        # the listing changed (the input script is still the TASK-703 one).
        self.assertIn(b"SHELL> ls\nhello.zen\nnotes.txt\nboot.txt\nSHELL> cat hello.zen\n",EXPECTED)

    def test_persistence_boot_line_and_counter_are_required(self):
        marker=PERSIST_LINE
        invalid=[EXPECTED.replace(marker,b""),
                 EXPECTED.replace(marker,marker+marker),
                 EXPECTED.replace(marker,b"PERSIST: BOOT 0\n"),
                 EXPECTED.replace(marker,b"PERSIST: BOOT nope\n"),
                 EXPECTED.replace(PERSIST_LINE+PFS_LINE,PFS_LINE+PERSIST_LINE)]
        for serial in invalid:
            with self.subTest(serial=serial),self.assertRaises(RuntimeError):
                validate_boot(SUCCESS_STATUS,serial,b"")
        second=validate_boot(SUCCESS_STATUS,EXPECTED.replace(marker,b"PERSIST: BOOT 2\n"),b"")
        self.assertEqual(second["persistence"],{"available":True,"boot":2})
        unavailable=validate_boot(SUCCESS_STATUS,EXPECTED.replace(marker,b"PERSIST: UNAVAILABLE\n"),b"")
        self.assertEqual(unavailable["persistence"],{"available":False,"boot":None})

    def test_pfs_boot_line_and_counters_are_required(self):
        marker=PFS_LINE
        invalid=[EXPECTED.replace(marker,b""),
                 EXPECTED.replace(marker,marker+marker),
                 EXPECTED.replace(marker,b"PFS: BOOT 0 FILES=1\n"),
                 EXPECTED.replace(marker,b"PFS: BOOT 1 FILES=0\n"),
                 EXPECTED.replace(marker,b"PFS: BOOT nope FILES=1\n"),
                 EXPECTED.replace(PERSIST_LINE+PFS_LINE,PFS_LINE+PERSIST_LINE),
                 EXPECTED.replace(marker+b"USER: Hello",b"USER: Hello"+marker)]
        for serial in invalid:
            with self.subTest(serial=serial),self.assertRaises(RuntimeError):
                validate_boot(SUCCESS_STATUS,serial,b"")
        second=validate_boot(SUCCESS_STATUS,EXPECTED.replace(marker,b"PFS: BOOT 2 FILES=1\n"),b"")
        self.assertEqual(second["pfs"],{"available":True,"boot":2,"files":1})
        unavailable=validate_boot(SUCCESS_STATUS,EXPECTED.replace(marker,b"PFS: UNAVAILABLE\n"),b"")
        self.assertEqual(unavailable["pfs"],{"available":False,"boot":None,"files":None})

    def test_timeout_kills_process_and_saves_partial_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            command=[sys.executable,"-u","-c","import time; print('partial serial',flush=True); time.sleep(60)"]
            with self.assertRaisesRegex(RuntimeError,"timed out"):
                run_process(command,os.environ.copy(),0.1,Path(tmp))
            result=json.loads((Path(tmp)/"result.json").read_text())
            self.assertTrue(result["timed_out"]);self.assertFalse(result["passed"])
            self.assertLess(result["seconds"],4)
            self.assertEqual((Path(tmp)/"serial.log").read_bytes(),b"partial serial\n")

    def test_interrupt_stops_guest_group_and_saves_partial_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);pidfile=tmp/"child.pid";logs=tmp/"logs"
            child_code=f"import os,time; from pathlib import Path; print('interrupt serial',flush=True); Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)"
            child_command=[sys.executable,"-u","-c",child_code]
            wrapper=f"import sys,os; from pathlib import Path; sys.path.insert(0,{str(ROOT/'infrastructure/scripts')!r}); from boot_ferros import run_process; run_process({child_command!r},os.environ.copy(),30,Path({str(logs)!r}))"
            process=subprocess.Popen([sys.executable,"-c",wrapper],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            child_pid=None
            try:
                deadline=time.monotonic()+3
                while not pidfile.exists() and time.monotonic()<deadline: time.sleep(0.01)
                self.assertTrue(pidfile.exists(),"dummy guest did not start")
                child_pid=int(pidfile.read_text())
                process.send_signal(signal.SIGINT)
                process.communicate(timeout=4)
                result=json.loads((logs/"result.json").read_text())
                self.assertTrue(result["cancelled"]);self.assertFalse(result["passed"])
                self.assertEqual((logs/"serial.log").read_bytes(),b"interrupt serial\n")
                with self.assertRaises(ProcessLookupError): os.kill(child_pid,0)
            finally:
                if process.poll() is None: process.kill();process.communicate()
                if child_pid is not None:
                    try: os.killpg(child_pid,signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_start_failure_is_saved_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError): run_process(["/no-such-qemu"],os.environ.copy(),1,Path(tmp))
            result=json.loads((Path(tmp)/"result.json").read_text())
            self.assertIsNone(result["status"]);self.assertFalse(result["passed"])
            self.assertTrue((Path(tmp)/"qemu.stderr.log").read_bytes())

    def test_nonzero_program_preserves_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            command=[sys.executable,"-c","import sys; print('wrong output'); sys.exit(35)"]
            with self.assertRaises(RuntimeError): run_process(command,os.environ.copy(),1,Path(tmp))
            result=json.loads((Path(tmp)/"result.json").read_text())
            self.assertEqual(result["status"],35)
            self.assertEqual((Path(tmp)/"serial.log").read_bytes(),b"wrong output\n")

    def test_rejects_invalid_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/"invalid.elf";image.write_bytes(b"not an ELF")
            with self.assertRaises(ValueError): inspect_image(image,1)

class KernelZenTests(unittest.TestCase):
    def test_uart_logic_in_real_zen_object_with_host_safe_mocks(self):
        zen=ROOT/"zen/compiler/target/release/zen"
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);(tmp/"mock.c").write_text(HARNESS)
            # Test the shared UART unit without linking privileged architecture code.
            baseline=(ROOT/"ferros/tests/uart_entry.zen").read_text()
            source="\n".join((ROOT/"ferros/kernel"/name).read_text() for name in ["arch/x86_64/abi.zen","drivers/serial.zen"])+"\n"+baseline
            (tmp/"uart.zen").write_text(source)
            for optimized in [False,True]:
                with self.subTest(optimized=optimized):
                    cmd=[str(zen),"build",str(tmp/"uart.zen"),"--target","x86_64-unknown-none","--emit","obj","-o",str(tmp/"kernel.o")]
                    if optimized: cmd.append("--release")
                    subprocess.run(cmd,check=True,capture_output=True,timeout=30)
                    subprocess.run(["cc","-std=c11","-no-pie",str(tmp/"mock.c"),str(tmp/"kernel.o"),"-o",str(tmp/"mock")],check=True,capture_output=True,timeout=30)
                    result=subprocess.run([str(tmp/"mock")],capture_output=True,timeout=5)
                    self.assertEqual(result.returncode,0,result.stderr.decode())
                    self.assertIn(b"bounded polling verified",result.stdout)

class ShellGuestTests(unittest.TestCase):
    """TASK-703: shell paths outside the frozen acceptance script."""

    @classmethod
    def setUpClass(cls):
        cls.zen=ROOT/"zen/compiler/target/release/zen"
        if not cls.zen.exists():
            raise unittest.SkipTest(f"build the release compiler first: {cls.zen}")

    def _boot(self,tmp,input):
        from build_ferros import build_kernel
        build=build_kernel(self.zen,Path(tmp)/"build",True)
        from boot_ferros import boot
        with self.assertRaises(RuntimeError):
            boot(build["image_path"],Path(tmp)/"boot",input=input)
        result=json.loads((Path(tmp)/"boot/result.json").read_text())
        serial=(Path(tmp)/"boot/serial.log").read_bytes()
        return result,serial

    def test_no_input_shell_terminates_cleanly(self):
        import re
        with tempfile.TemporaryDirectory() as tmp:
            result,serial=self._boot(tmp,None)
            self.assertEqual(result["status"],33)
            self.assertFalse(result["timed_out"])
            self.assertLess(result["seconds"],8.0,"no-input path must not hang the default timeout")
            self.assertIn(b"SHELL: NO INPUT",serial)
            self.assertIn(b"SHELL: DONE",serial)
            self.assertNotIn(b"PANIC",serial)
            stats=re.search(rb"USERSPACE: STATS runs=(\d+) writes=(\d+)",serial)
            self.assertIsNotNone(stats)
            self.assertEqual(int(stats.group(1)),7)
            self.assertEqual(int(stats.group(2)),9)

    def test_negative_shell_commands_are_contained(self):
        import re
        with tempfile.TemporaryDirectory() as tmp:
            result,serial=self._boot(tmp,b"bogus\ncat nope.zen\nexit\n")
            self.assertEqual(result["status"],33)
            self.assertIn(b"SHELL: UNKNOWN COMMAND",serial)
            self.assertIn(b"SHELL: FILE ERROR",serial)
            self.assertNotIn(b"PANIC",serial)
            stats=re.search(rb"USERSPACE: STATS runs=(\d+) writes=(\d+)",serial)
            self.assertIsNotNone(stats)
            self.assertEqual(int(stats.group(1)),7)
            self.assertEqual(int(stats.group(2)),15)

if __name__=="__main__":unittest.main()
