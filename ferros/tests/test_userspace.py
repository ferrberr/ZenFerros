"""Exercise the actual Zen loader and policies with host-safe CPU/PMM mocks."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
ZEN=ROOT/"zen/compiler/target/release/zen"
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from build_ferros import build_kernel
from build_user import build_user
from boot_ferros import boot

class UserPolicyTests(unittest.TestCase):
    def test_elf_rollback_memory_permissions_buffers_and_faults(self):
        # Reuse only raw byte helpers, with PMM/IO/CPU replaced by safe mocks.
        memory=(ROOT/"ferros/kernel/memory.zen").read_text().split("fn memory_state_read(")[0]
        source="\n".join([(ROOT/"ferros/kernel/arch/x86_64/abi.zen").read_text(),memory,
                            (ROOT/"ferros/kernel/vfs.zen").read_text(),
                            (ROOT/"ferros/kernel/userspace.zen").read_text(),
                            (ROOT/"ferros/tests/fixtures/user_test_api.zen").read_text()])
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);(tmp/"user.zen").write_text(source)
            for optimized in [False,True]:
                for sanitized in [False,True]:
                    with self.subTest(optimized=optimized,sanitized=sanitized):
                        kind="c" if sanitized else "obj"
                        args=[str(ZEN),"build",str(tmp/"user.zen"),"--target","x86_64-unknown-none","--emit",kind,"-o",str(tmp/("user.c" if sanitized else "user.o"))]
                        if optimized:args.append("--release")
                        result=subprocess.run(args,capture_output=True,text=True,timeout=30)
                        self.assertEqual(result.returncode,0,result.stderr)
                        sanitizer=["-fsanitize=undefined","-fno-sanitize-recover=all"] if sanitized else []
                        if sanitized:
                            subprocess.run(["cc","-std=c11","-O2" if optimized else "-O0","-ffreestanding","-fno-builtin","-fno-pie","-mno-red-zone","-mgeneral-regs-only","-mcmodel=kernel",*sanitizer,"-c",str(tmp/"user.c"),"-o",str(tmp/"user.o")],check=True,capture_output=True,timeout=30)
                        result=subprocess.run(["cc","-std=c11","-no-pie",*sanitizer,str(ROOT/"ferros/tests/fixtures/user_mock.c"),str(tmp/"user.o"),"-o",str(tmp/"mock")],capture_output=True,text=True,timeout=30)
                        self.assertEqual(result.returncode,0,result.stderr)
                        result=subprocess.run([str(tmp/"mock")],capture_output=True,text=True,timeout=5)
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertIn("8 rollback stages",result.stdout)

    def test_real_cpl3_syscalls_and_six_contained_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            for release in [False,True]:
                with self.subTest(release=release):
                    output=Path(tmp)/str(release)
                    build=build_kernel(ZEN,output,release)
                    result=boot(build["image_path"],output/"boot")
                    self.assertEqual(result["userspace"]["runs"],7)
                    self.assertEqual(result["userspace"]["writes"],18)
                    self.assertEqual(result["userspace"]["rejected"],6)
                    self.assertGreaterEqual(result["userspace"]["irqs"],1)
                    self.assertEqual((output/"boot/qemu.stderr.log").read_bytes(),b"")

    def test_real_qemu_rejects_invalid_elf_missing_user_bit_and_kernel_fault(self):
        source=(ROOT/"ferros/kernel/userspace.zen").read_text()
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            no_user=tmp/"no-user.zen"
            no_user.write_text(source.replace("memory_store64(root,parent|4u64);","memory_store64(root,parent);"))
            kernel_fault=tmp/"kernel-fault.zen"
            kernel_fault.write_text(source.replace("fn user_write(address:u64,length:u64)->u64 {", "fn user_write(address:u64,length:u64)->u64 {\n    if memory_read8(0)==0u8 { kernel_panic(\"kernel syscall fault returned\"); return 0; }"))
            good=build_user(ZEN,tmp/"elf")
            data=bytearray(Path(good["artifact_path"]).read_bytes());data[4]=1
            bad_elf=tmp/"bad.elf";bad_elf.write_bytes(data)
            for release in [False,True]:
                for scenario,overrides,image,reason in [
                    ("invalid-elf",None,bad_elf,b"userspace test failed"),
                    ("no-user",{"userspace.zen":no_user},None,b"userspace test failed"),
                    ("kernel-fault",{"userspace.zen":kernel_fault},None,b"unexpected interrupt or exception"),
                ]:
                    with self.subTest(release=release,scenario=scenario):
                        output=tmp/f"{scenario}-{release}"
                        build=build_kernel(ZEN,output,release,unit_overrides=overrides,user_image_override=image)
                        with self.assertRaisesRegex(RuntimeError,"status 35"):
                            boot(build["image_path"],output/"boot")
                        result=json.loads((output/"boot/result.json").read_text())
                        serial=(output/"boot/serial.log").read_bytes()
                        self.assertFalse(result["timed_out"])
                        self.assertIn(b"FERROS PANIC: "+reason+b"\n",serial)
                        self.assertNotIn(b"USERSPACE: RING3 AND SYSCALLS OK",serial)
                        self.assertNotIn(b"HITO 7 OK",serial)

if __name__=="__main__":unittest.main()
