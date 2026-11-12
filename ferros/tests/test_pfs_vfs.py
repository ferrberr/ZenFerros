"""TASK-919/924: ZENFS01 reads and persistent CPL3 replacements via VFS/shell.

Two QEMU boots share one raw disk. The injected script lists the root and reads
`boot.txt` through the ordinary VFS syscalls (4/5/7); the first boot must show
`boot=1` and the second `boot=2`. The default acceptance script is not changed:
this test supplies its own input, so the runner's frozen transcript check is
expected to reject the output while the guest itself still exits with status 33.
"""
import json
import struct
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
ZEN=ROOT/"zen/compiler/target/release/zen"
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from boot_ferros import boot
from build_ferros import build_kernel
from ferros.tests.test_pfs import fnv1a32, v2_files

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
                    self.assertIn(b"SHELL> help\ncommands: help ls cat put exit\n",serial)
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


    def test_cpl3_replacement_survives_restart(self):
        # Start with a valid ZENFS01 image: migration must leave its sectors
        # untouched while later CPL3 replacements use ZENFS02.
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp); disk=tmp/"user-persist.img"
            raw=bytearray(1024*1024)
            raw[16*512:16*512+8]=b"ZENFS01\0"
            struct.pack_into("<II",raw,16*512+8,1,8)
            struct.pack_into("<I",raw,16*512+16,fnv1a32(raw[16*512:16*512+16]))
            raw[17*512:17*512+9]=b"saved.txt\0"
            struct.pack_into("<QIB",raw,17*512+24,0,25,1)
            raw[18*512:18*512+9]=b"boot.txt\0"
            struct.pack_into("<QIB",raw,18*512+24,7,26,1)
            raw[26*512:26*512+7]=b"boot=4\n"
            legacy=bytes(raw[16*512:33*512])
            disk.write_bytes(raw)
            for release in (False,True):
                # Each optimization profile writes a distinct value and proves
                # the second boot reads its exact bytes, including on-disk size.
                payload=b"Zen-CPL3-debug" if not release else b"Zen-CPL3-release"
                # Extra guest assertions run in CPL3 on the actual PFS fd before
                # the shell replacement: exact 512 B, oversize, bad pointer and
                # syscall-wide bound. Reads prove rejected writes changed no byte.
                source=(ROOT/"ferros/user/main.zen").read_text()
                anchor="        let result:u64=user_syscall(6u64,fd,base+split+1u64,size);"
                checks="""
        let probe:u64=user_storage_address()+1024u64;
        let ghost:u64=probe+2048u64;
        volatile_store(ghost as *mut u8,103u8);
        volatile_store((ghost+1u64) as *mut u8,104u8);
        volatile_store((ghost+2u64) as *mut u8,111u8);
        volatile_store((ghost+3u64) as *mut u8,115u8);
        volatile_store((ghost+4u64) as *mut u8,116u8);
        volatile_store((ghost+5u64) as *mut u8,46u8);
        volatile_store((ghost+6u64) as *mut u8,116u8);
        volatile_store((ghost+7u64) as *mut u8,120u8);
        volatile_store((ghost+8u64) as *mut u8,116u8);
        volatile_store((ghost+9u64) as *mut u8,0u8);
        let ghost_fd:u64=user_syscall(4u64,ghost,1u64,0u64);
        if ghost_fd<100u64 || ghost_fd>115u64 { finish(88u64); }
        if user_syscall(5u64,ghost_fd,probe,1u64)!=(-9i64 as u64) { finish(89u64); }
        if user_syscall(7u64,ghost_fd,0u64,0u64)!=0u64 { finish(90u64); }
        if user_syscall(4u64,ghost,0u64,0u64)!=(-2i64 as u64) { finish(91u64); }
        if user_syscall(4u64,ghost,2u64,0u64)!=(-22i64 as u64) { finish(92u64); }
        let mut i:u64=0;
        while i<512u64 {
            volatile_store((probe+i) as *mut u8,(i%251u64) as u8);
            i+=1u64;
        }
        if user_syscall(6u64,fd,probe,512u64)!=512u64 { finish(80u64); }
        if user_syscall(6u64,fd,probe,513u64)!=(-27i64 as u64) { finish(81u64); }
        if user_syscall(6u64,fd,0u64,1u64)!=(-14i64 as u64) { finish(82u64); }
        if user_syscall(6u64,fd,probe,4097u64)!=(-22i64 as u64) { finish(83u64); }
        if user_syscall(5u64,fd,probe+1024u64,512u64)!=512u64 { finish(84u64); }
        i=0;
        while i<512u64 {
            if volatile_load((probe+1024u64+i) as *u8)!=(i%251u64) as u8 { finish(85u64); }
            i+=1u64;
        }
        if user_syscall(6u64,fd,probe,0u64)!=0u64 { finish(86u64); }
        if user_syscall(5u64,fd,probe+1024u64,512u64)!=0u64 { finish(87u64); }
"""
                guest=tmp/f"user-{release}.zen"
                guest.write_text(source.replace(anchor,checks+anchor))
                build=build_kernel(ZEN,tmp/f"build-{release}",release,user_source_override=guest)
                for phase,script in enumerate((b"put saved.txt "+payload+b"\ncat saved.txt\nhelp\nexit\n",
                                                b"ls\ncat saved.txt\nhelp\nexit\n")):
                    output=tmp/f"boot-{release}-{phase}"
                    with self.assertRaises(RuntimeError):
                        boot(build["image_path"],output,input=script,disk_image=disk)
                    result=json.loads((output/"result.json").read_text())
                    serial=(output/"serial.log").read_bytes()
                    self.assertEqual(result["status"],33,serial.decode())
                    self.assertFalse(result["timed_out"])
                    self.assertEqual((output/"qemu.stderr.log").read_bytes(),b"")
                    self.assertIn(b"SHELL> cat saved.txt\n"+payload+b"\n",serial)
                    self.assertIn(b"USERSPACE: ISOLATION AND CLEANUP OK\n",serial)
                    self.assertIn(b"HITO 7 OK\n",serial)
                    self.assertNotIn(b"SHELL: FILE ERROR",serial)
                    if phase==0: self.assertIn(b"SHELL: STORED\n",serial)
                    persisted=disk.read_bytes()
                    self.assertEqual(persisted[16*512:33*512],legacy)
                    self.assertEqual(v2_files(persisted)["saved.txt"],payload)
                    self.assertIn("boot.txt",v2_files(persisted))

    def test_cpl3_creation_and_replacement_survive_restart(self):
        for release in (False,True):
            with self.subTest(release=release), tempfile.TemporaryDirectory() as tmp:
                tmp=Path(tmp)
                disk=tmp/"new-file.img"
                with disk.open("wb") as stream: stream.truncate(1024*1024)
                build=build_kernel(ZEN,tmp/"build",release)
                scripts=(
                    (b"put new.txt first\ncat new.txt\nhelp\nexit\n",b"first",True),
                    (b"ls\ncat new.txt\nhelp\nexit\n",b"first",False),
                    (b"put new.txt second\ncat new.txt\nhelp\nexit\n",b"second",True),
                    (b"ls\ncat new.txt\nhelp\nexit\n",b"second",False),
                )
                for phase,(script,expected,writing) in enumerate(scripts):
                    with self.assertRaises(RuntimeError):
                        boot(build["image_path"],tmp/f"boot-{phase}",input=script,disk_image=disk)
                    result=json.loads((tmp/f"boot-{phase}"/"result.json").read_text())
                    serial=(tmp/f"boot-{phase}"/"serial.log").read_bytes()
                    self.assertEqual(result["status"],33,serial.decode(errors="replace"))
                    self.assertFalse(result["timed_out"])
                    self.assertIn(b"SHELL> cat new.txt\n"+expected+b"\n",serial)
                    self.assertNotIn(b"SHELL: FILE ERROR",serial)
                    if writing:
                        self.assertIn(b"SHELL: STORED\n",serial)
                    self.assertEqual(v2_files(disk.read_bytes())["new.txt"],expected)


if __name__=="__main__":
    unittest.main()
