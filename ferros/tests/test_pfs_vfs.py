"""TASK-919: ZENFS01 is visible and readable through the VFS/shell.

Two QEMU boots share one raw disk. The injected script lists the root and reads
`boot.txt` through the ordinary VFS syscalls (4/5/7); the first boot must show
`boot=1` and the second `boot=2`. The default acceptance script is not changed:
this test supplies its own input, so the runner's frozen transcript check is
expected to reject the output while the guest itself still exits with status 33.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
ZEN=ROOT/"zen/compiler/target/release/zen"
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from boot_ferros import boot
from build_ferros import build_kernel

# Four commands keep the shell write count at the frozen 18 (READY, 4 prompts,
# 4 echoes, 3 outputs, DONE) while exercising `ls` and `cat boot.txt`.
SHELL_INPUT=b"ls\ncat boot.txt\nhelp\nexit\n"


class PfsVfsGuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.exists():
            raise unittest.SkipTest(f"build the release compiler first: {ZEN}")

    def test_two_boots_same_disk_are_listed_and_read_through_the_vfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            disk=tmp/"pfs-vfs.img"
            with disk.open("wb") as stream: stream.truncate(1024*1024)
            build=build_kernel(ZEN,tmp/"build",True)
            for expected in (1,2):
                with self.subTest(boot=expected):
                    with self.assertRaises(RuntimeError):
                        # The runner validates the frozen default transcript; a
                        # custom script is a deliberate, non-passing run.
                        boot(build["image_path"],tmp/f"boot-{expected}",
                             input=SHELL_INPUT,disk_image=disk)
                    result=json.loads((tmp/f"boot-{expected}"/"result.json").read_text())
                    serial=(tmp/f"boot-{expected}"/"serial.log").read_bytes()
                    self.assertEqual(result["status"],33)
                    self.assertFalse(result["timed_out"])
                    self.assertNotIn(b"PANIC",serial)
                    self.assertIn(b"HITO 7 OK",serial)
                    self.assertIn(f"PFS: BOOT {expected} FILES=1\n".encode(),serial)
                    self.assertIn(f"PERSIST: BOOT {expected}\n".encode(),serial)
                    # ls enumerates RAMFS first and then the persistent file.
                    self.assertIn(b"SHELL> ls\nhello.zen\nnotes.txt\nboot.txt\n",serial)
                    # cat boot.txt goes through open/read/close, not a new command.
                    self.assertIn(f"SHELL> cat boot.txt\nboot={expected}\n".encode(),serial)
                    self.assertIn(b"SHELL> help\ncommands: help ls cat exit\n",serial)
                    self.assertIn(b"SHELL> exit\nSHELL: DONE\n",serial)
                    self.assertNotIn(b"SHELL: FILE ERROR",serial)
                    self.assertNotIn(b"SHELL: UNKNOWN COMMAND",serial)
                    self.assertIn(b"writes=18",serial)
                    self.assertIn(b"runs=7",serial)
                    self.assertEqual((tmp/f"boot-{expected}"/"qemu.stderr.log").read_bytes(),b"")
                    # Only one transcript: the valid_user_test prologue has no
                    # boot.txt because it still stages the frozen ls fixture.
                    self.assertEqual(serial.count(b"SHELL> cat boot.txt"),1)
                    self.assertLess(serial.index(b"PFS: BOOT "),serial.index(b"USER: Hello from Zen"))


if __name__=="__main__":
    unittest.main()
