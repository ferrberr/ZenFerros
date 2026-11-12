"""Unit-test the real Zen RAMFS/VFS code with host-safe buffers.

TASK-919: vfs.zen now serves optional ZENFS01 files from a read-only snapshot
published at boot. This fixture never publishes one, so the original RAMFS
contract (two names, 20-byte listing, no PFS) is exercised unchanged; QEMU
coverage for the visible/read-only PFS path lives in test_pfs_vfs.py.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen/compiler/target/release/zen"


def memory_prefix():
    return (ROOT / "ferros/kernel/memory.zen").read_text().split("fn memory_state_read(")[0]


class VfsTests(unittest.TestCase):
    def test_ramfs_vfs_error_paths_without_privileged_code(self):
        source = "\n".join([
            (ROOT / "ferros/tests/fixtures/vfs_test_support.zen").read_text(),
            memory_prefix(),
            (ROOT / "ferros/kernel/vfs.zen").read_text(),
            (ROOT / "ferros/tests/fixtures/vfs_test_api.zen").read_text(),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "vfs.zen").write_text(source)
            for optimized in (False, True):
                with self.subTest(optimized=optimized):
                    args = [str(ZEN), "build", str(tmp / "vfs.zen"), "--target",
                            "x86_64-unknown-none", "--emit", "obj", "-o", str(tmp / "vfs.o")]
                    if optimized:
                        args.append("--release")
                    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run(
                        ["cc", "-std=c11", "-fno-builtin", "-fno-pie", "-no-pie",
                         str(ROOT / "ferros/tests/fixtures/vfs_mock.c"), str(tmp / "vfs.o"),
                         "-o", str(tmp / "mock")],
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(tmp / "mock")], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("VFS OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
