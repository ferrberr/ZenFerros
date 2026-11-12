"""Test actual Zen memory algorithms against synthetic maps and safe CPU mocks."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class MemoryPolicyTests(unittest.TestCase):
    def test_real_zen_pmm_heap_and_vmm_with_edge_cases_and_ubsan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            source="\n".join((ROOT/path).read_text() for path in ["ferros/kernel/arch/x86_64/abi.zen","ferros/kernel/memory.zen","ferros/tests/fixtures/memory_test_api.zen"])
            (tmp/"memory.zen").write_text(source)
            zen=ROOT/"zen/compiler/target/release/zen"
            for optimized in [False,True]:
                for sanitized in [False,True]:
                    with self.subTest(optimized=optimized,sanitized=sanitized):
                        command=[str(zen),"build",str(tmp/"memory.zen"),"--target","x86_64-unknown-none","--emit","c" if sanitized else "obj","-o",str(tmp/("memory.c" if sanitized else "memory.o"))]
                        if optimized:command.append("--release")
                        subprocess.run(command,check=True,capture_output=True,timeout=30)
                        if sanitized:
                            subprocess.run(["cc","-std=c11","-O2" if optimized else "-O0","-ffreestanding","-fno-builtin","-fno-stack-protector","-fno-pie","-mno-red-zone","-mgeneral-regs-only","-mcmodel=kernel","-fsanitize=undefined","-fno-sanitize-recover=all","-c",str(tmp/"memory.c"),"-o",str(tmp/"memory.o")],check=True,capture_output=True,timeout=30)
                        command=["cc","-std=c11","-no-pie",str(ROOT/"ferros/tests/fixtures/memory_mock.c"),str(tmp/"memory.o"),"-o",str(tmp/"mock")]
                        if sanitized:command.extend(["-fsanitize=undefined","-fno-sanitize-recover=all"])
                        subprocess.run(command,check=True,capture_output=True,timeout=30)
                        out=subprocess.run([str(tmp/"mock")],capture_output=True,timeout=10)
                        self.assertEqual(out.returncode,0,out.stderr.decode())
                        self.assertEqual(out.stderr,b"")
                        self.assertIn(b"Memory Zen PMM",out.stdout)

if __name__=="__main__":unittest.main()
