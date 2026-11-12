"""TASK-914: ATA PIO boot counter, host-safe unit mock and two real QEMU boots."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
ZEN=ROOT/"zen/compiler/target/release/zen"
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from boot_ferros import DEFAULT_DISK_BYTES, _prepare_disk, boot
from build_ferros import build_kernel

HARNESS=r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern void test_storage_init(void);
extern void test_storage_boot(void);

static unsigned char disk[4][512];
static unsigned char sector[512];
static int disk_present=1, force_error=0, force_busy=0;
static int data_pos=0;
static unsigned lba=0;
static unsigned char lba0=0, lba1=0, lba2=0;
static uint8_t status=0x50;
static char serial[4096];
static size_t serial_len=0;

static void ata_reset(void) {
    data_pos=0;
    status=disk_present?0x50:0x00;
}

uint8_t ferros_in8(uint16_t port) {
    if(port==0x3fd) return 0x20;              /* THR empty: serial_write succeeds. */
    if(port==0x3f8) return 0;
    if(port==0x3f6 || port==0x1f7) return force_busy?0x80:status;
    return 0;
}
void ferros_out8(uint16_t port,uint8_t value) {
    if(port==0x3f8) { if(serial_len+1<sizeof serial) serial[serial_len++]=(char)value; return; }
    if(!disk_present) return;
    if(port==0x1f6) { ata_reset(); }
    else if(port==0x1f3) { lba0=value; }
    else if(port==0x1f4) { lba1=value; }
    else if(port==0x1f5) { lba2=value; }
    else if(port==0x1f7) {
        if(force_error) { status=0x51; return; }
        lba=(unsigned)lba0 | ((unsigned)lba1<<8) | ((unsigned)lba2<<16);
        if(value==0x20) { memcpy(sector,disk[lba],512); data_pos=0;status=0x58; }
        else if(value==0x30) { data_pos=0;status=0x58; }
        else if(value==0xe7) { status=0x50; }
    }
}
uint16_t ferros_ata_in16(uint16_t port) {
    uint16_t word;
    if(port!=0x1f0 || force_busy) return 0;
    word=(uint16_t)(sector[data_pos*2] | (sector[data_pos*2+1]<<8));
    data_pos++;
    if(data_pos>=256) { data_pos=0;status=force_error?0x51:0x50; }
    return word;
}
void ferros_ata_out16(uint16_t port,uint16_t value) {
    if(port!=0x1f0 || force_busy) return;
    sector[data_pos*2]=(unsigned char)(value&0xff);
    sector[data_pos*2+1]=(unsigned char)(value>>8);
    data_pos++;
    if(data_pos>=256) { memcpy(disk[lba],sector,512); data_pos=0;status=0x50; }
}

static uint64_t memory_state[512];
static _Alignas(16) unsigned char heap[65536];
uint64_t test_memory_state(void) { return (uint64_t)(uintptr_t)memory_state; }
uint64_t test_heap_start(void) { return (uint64_t)(uintptr_t)heap; }
uint64_t test_heap_end(void) { return (uint64_t)(uintptr_t)(heap+sizeof heap); }

static int expect(const char* text,const char* where) {
    if(strcmp(serial,text)!=0) {
        fprintf(stderr,"%s: serial=%s expected=%s\n",where,serial,text);
        return 1;
    }
    return 0;
}

int main(void) {
    memset(disk,0,sizeof disk);memset(memory_state,0,sizeof memory_state);
    ata_reset();test_storage_init();

    serial_len=0;serial[0]=0;test_storage_boot();
    if(expect("PERSIST: BOOT 1\n","first boot")) return 1;
    if(memcmp(disk[0],"ZENPERS1",8)!=0) { puts("missing superblock magic"); return 2; }
    if(*(uint64_t*)(disk[0]+8)!=1) { puts("first counter is not 1"); return 3; }

    serial_len=0;serial[0]=0;test_storage_boot();
    if(expect("PERSIST: BOOT 2\n","second boot")) return 4;
    if(*(uint64_t*)(disk[0]+8)!=2) { puts("second counter is not 2"); return 5; }

    disk_present=0;serial_len=0;serial[0]=0;test_storage_boot();
    if(expect("PERSIST: UNAVAILABLE\n","absent disk")) return 6;

    disk_present=1;force_error=1;serial_len=0;serial[0]=0;test_storage_boot();
    if(expect("PERSIST: UNAVAILABLE\n","device error")) return 7;

    force_error=0;force_busy=1;serial_len=0;serial[0]=0;test_storage_boot();
    if(expect("PERSIST: UNAVAILABLE\n","timeout")) return 8;

    if(memcmp(disk[0],"ZENPERS1",8)!=0 || *(uint64_t*)(disk[0]+8)!=2) {
        puts("failed boots corrupted the superblock"); return 9;
    }
    puts("ATA PIO storage OK: format, increment, error and timeout containment");
    return 0;
}
"""


def memory_source():
    """Only the byte helpers and heap allocator; PMM/VMM stay out of the mock."""
    source=(ROOT/"ferros/kernel/memory.zen").read_text()
    prefix=source.split("fn memory_state_read(")[0]
    state=source[source.index("fn memory_state_read("):source.index("fn memory_bit_read(")]
    heap=source[source.index("fn heap_init("):source.index("fn heap_self_test(")]
    return "\n".join([prefix,state,heap])


HOST_SUPPORT=r"""
extern "C" {
    fn test_memory_state()->u64;
    fn test_heap_start()->u64;
    fn test_heap_end()->u64;
}
fn ferros_memory_state()->u64 { unsafe { return test_memory_state(); } }
fn ferros_heap_start()->u64 { unsafe { return test_heap_start(); } }
fn ferros_heap_end()->u64 { unsafe { return test_heap_end(); } }
pub fn test_storage_init() { heap_init(); }
pub fn test_storage_boot() { storage_boot(); }
"""


HOST_ARCH=r"""
// Only the byte helpers serial.zen needs; the ATA unit declares its own inw/outw
// externs, so the full privileged abi.zen is deliberately not linked here.
extern "C" {
    fn ferros_in8(port:u16)->u8;
    fn ferros_out8(port:u16,value:u8);
}
"""


class AtaStorageUnitTests(unittest.TestCase):
    def test_driver_and_storage_with_host_safe_ata_mock(self):
        source="\n".join([
            HOST_ARCH,
            memory_source(),
            (ROOT/"ferros/kernel/drivers/serial.zen").read_text(),
            (ROOT/"ferros/kernel/drivers/ata.zen").read_text(),
            (ROOT/"ferros/kernel/storage.zen").read_text(),
            HOST_SUPPORT,
        ])
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);(tmp/"persistence.zen").write_text(source);(tmp/"mock.c").write_text(HARNESS)
            for optimized in (False,True):
                with self.subTest(optimized=optimized):
                    args=[str(ZEN),"build",str(tmp/"persistence.zen"),"--target",
                          "x86_64-unknown-none","--emit","obj","-o",str(tmp/"persistence.o")]
                    if optimized: args.append("--release")
                    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr)
                    result=subprocess.run(
                        ["cc","-std=c11","-fno-builtin","-fno-pie","-no-pie",
                         str(tmp/"mock.c"),str(tmp/"persistence.o"),"-o",str(tmp/"mock")],
                        capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr)
                    result=subprocess.run([str(tmp/"mock")],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn("ATA PIO storage OK",result.stdout)


class DiskImageTests(unittest.TestCase):
    def test_temporary_and_explicit_raw_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            temporary,temp_flag=_prepare_disk(tmp)
            self.assertTrue(temp_flag)
            self.assertTrue(temporary.exists())
            self.assertEqual(temporary.stat().st_size,DEFAULT_DISK_BYTES)
            temporary.unlink()
            explicit=tmp/"explicit.img"
            created,created_flag=_prepare_disk(tmp,explicit)
            self.assertFalse(created_flag)
            self.assertEqual(created,explicit.resolve())
            self.assertEqual(explicit.stat().st_size,DEFAULT_DISK_BYTES)
            explicit.write_bytes(b"x")
            with self.assertRaises(ValueError): _prepare_disk(tmp,explicit)


class PersistenceGuestTests(unittest.TestCase):
    """Two QEMU invocations with the same raw disk must report BOOT 1 and 2."""

    @classmethod
    def setUpClass(cls):
        if not ZEN.exists():
            raise unittest.SkipTest(f"build the release compiler first: {ZEN}")

    def test_two_boots_with_the_same_disk_increment_the_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);disk=tmp/"persist.img"
            with disk.open("wb") as stream: stream.truncate(1024*1024)
            build=build_kernel(ZEN,tmp/"build",True)
            for expected in (1,2):
                with self.subTest(boot=expected):
                    result=boot(build["image_path"],tmp/f"boot-{expected}",disk_image=disk)
                    self.assertEqual(result["status"],33)
                    self.assertEqual(result["persistence"],{"available":True,"boot":expected})
                    serial=(tmp/f"boot-{expected}"/"serial.log").read_bytes()
                    self.assertEqual(serial.count(f"PERSIST: BOOT {expected}\n".encode()),1)
                    self.assertNotIn(b"PANIC",serial)
                    self.assertIn(b"HITO 7 OK",serial)
                    self.assertIn(b"writes=18",serial)
                    self.assertEqual((tmp/f"boot-{expected}"/"qemu.stderr.log").read_bytes(),b"")
                    log=json.loads((tmp/f"boot-{expected}"/"result.json").read_text())
                    self.assertTrue(log["passed"])
                    self.assertFalse(log["disk_temporary"])
            raw=disk.read_bytes()
            self.assertEqual(raw[:8],b"ZENPERS1")
            self.assertEqual(int.from_bytes(raw[8:16],"little"),2)


if __name__=="__main__":
    unittest.main()
