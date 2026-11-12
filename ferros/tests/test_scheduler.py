"""Real Zen scheduler policies and actual QEMU guard/return/state failures."""
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

class SchedulerTests(unittest.TestCase):
    def test_scheduler_policy_frames_and_critical_sections_on_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            source="\n".join((ROOT/p).read_text() for p in ["ferros/kernel/arch/x86_64/abi.zen","ferros/kernel/scheduler.zen","ferros/tests/fixtures/scheduler_test_api.zen"])
            (tmp/"test.zen").write_text(source)
            for optimized in [False,True]:
                for sanitized in [False,True]:
                    with self.subTest(optimized=optimized,sanitized=sanitized):
                        cmd=[str(ROOT/"zen/compiler/target/release/zen"),"build",str(tmp/"test.zen"),"--target","x86_64-unknown-none","--emit","c" if sanitized else "obj","-o",str(tmp/("test.c" if sanitized else "test.o"))]
                        if optimized:cmd.append("--release")
                        subprocess.run(cmd,check=True,capture_output=True,timeout=30)
                        if sanitized:
                            subprocess.run(["cc","-std=c11","-O2" if optimized else "-O0","-ffreestanding","-fno-builtin","-fno-pie","-mno-red-zone","-mgeneral-regs-only","-mcmodel=kernel","-fsanitize=undefined","-fno-sanitize-recover=all","-c",str(tmp/"test.c"),"-o",str(tmp/"test.o")],check=True,capture_output=True,timeout=30)
                        cmd=["cc","-std=c11","-no-pie",str(ROOT/"ferros/tests/fixtures/scheduler_mock.c"),str(tmp/"test.o"),"-o",str(tmp/"mock")]
                        if sanitized:cmd.extend(["-fsanitize=undefined","-fno-sanitize-recover=all"])
                        subprocess.run(cmd,check=True,capture_output=True,timeout=30)
                        out=subprocess.run([str(tmp/"mock")],capture_output=True,timeout=5)
                        self.assertEqual(out.returncode,0,out.stderr.decode());self.assertEqual(out.stderr,b"")
                        self.assertIn(b"108 policy choices",out.stdout)

    def test_real_qemu_requires_timer_preemption_for_busy_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            source=(ROOT/"ferros/kernel/scheduler.zen").read_text()
            marker="fn scheduler_on_timer() {"
            self.assertEqual(source.count(marker),1)
            mutant=tmp/"no-preemption.zen"
            mutant.write_text(source.replace(marker,"fn unused_test_scheduler_on_timer() {",1)+"\nfn scheduler_on_timer() {}\n")
            result=build_kernel(ROOT/"zen/compiler/target/release/zen",tmp/"image",True,unit_overrides={"scheduler.zen":mutant})
            with self.assertRaisesRegex(RuntimeError,"timed out"):
                boot(result["image_path"],tmp/"boot",timeout=0.75)
            log=json.loads((tmp/"boot/result.json").read_text());serial=(tmp/"boot/serial.log").read_bytes()
            self.assertTrue(log["timed_out"]);self.assertFalse(log["passed"])
            self.assertIn(b"INTERRUPTS: TIMER OK",serial)
            self.assertNotIn(b"THREADS: CONTEXT OK",serial)
            self.assertNotIn(b"HITO 7 OK",serial)

    def test_real_qemu_rejects_guard_write_invalid_state_and_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            scheduler=(ROOT/"ferros/kernel/scheduler.zen").read_text()
            marker="pub fn thread_entry(id:u64) {"
            self.assertEqual(scheduler.count(marker),1)
            returned=tmp/"returned.zen"
            returned.write_text(scheduler.replace(marker,"fn unused_test_thread_entry(id:u64) {",1)+"\npub fn thread_entry(id:u64) {}\n")
            for release in [False,True]:
                for scenario,main,overrides,reason in [
                    ("guard",ROOT/"ferros/tests/scheduler_guard.zen",None,b"thread stack guard violation"),
                    ("state",ROOT/"ferros/tests/scheduler_invalid.zen",None,b"invalid thread scheduler state"),
                    ("return",None,{"scheduler.zen":returned},b"thread entry returned"),
                ]:
                    with self.subTest(release=release,scenario=scenario):
                        output=tmp/f"{scenario}-{release}"
                        result=build_kernel(ROOT/"zen/compiler/target/release/zen",output,release,main,overrides)
                        with self.assertRaisesRegex(RuntimeError,"status 35"):
                            boot(result["image_path"],output/"boot")
                        log=json.loads((output/"boot/result.json").read_text());serial=(output/"boot/serial.log").read_bytes()
                        self.assertEqual(log["status"],35);self.assertFalse(log["timed_out"])
                        self.assertIn(b"FERROS PANIC: "+reason+b"\n",serial)
                        self.assertNotIn(b"HITO 7 OK",serial)

if __name__=="__main__":unittest.main()
