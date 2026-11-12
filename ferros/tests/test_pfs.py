"""TASK-916: persistent mini-FS (ZENFS01) host mock and three real QEMU boots."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
ZEN=ROOT/"zen/compiler/target/release/zen"
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from boot_ferros import boot
from build_ferros import build_kernel

HARNESS=r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Host-safe ATA PIO mock: 64 raw sectors shared by every FS call. */
#define SECTORS 64
static _Alignas(16) unsigned char disk[SECTORS][512];
static unsigned char sector[512];
static int disk_present=1;
static int data_pos=0;
static unsigned lba=0;
static unsigned char lba0=0, lba1=0, lba2=0;
static uint8_t status=0x50;
static char serial[8192];
static size_t serial_len=0;

extern void test_pfs_init(void);
extern void test_pfs_boot(void);
extern uint32_t test_pfs_list(void);
extern int64_t test_pfs_find(uint64_t id);
extern int64_t test_pfs_create(uint64_t id);
extern int64_t test_pfs_write(uint64_t id,uint64_t src,uint64_t len);
extern int64_t test_pfs_read(uint64_t id,uint64_t dst,uint64_t max);
extern int64_t test_pfs_delete(uint64_t id);

static void ata_reset(void) {
    data_pos=0;
    status=disk_present?0x50:0x00;
}

uint8_t ferros_in8(uint16_t port) {
    if(port==0x3fd) return 0x20;              /* THR empty: serial_write succeeds. */
    if(port==0x3f8) return 0;
    if(port==0x3f6 || port==0x1f7) return status;
    return 0;
}
void ferros_out8(uint16_t port,uint8_t value) {
    if(port==0x3f8) { if(serial_len+2<sizeof serial) { serial[serial_len++]=(char)value;serial[serial_len]=0; } return; }
    if(!disk_present) return;
    if(port==0x1f6) { ata_reset(); }
    else if(port==0x1f3) { lba0=value; }
    else if(port==0x1f4) { lba1=value; }
    else if(port==0x1f5) { lba2=value; }
    else if(port==0x1f7) {
        lba=(unsigned)lba0 | ((unsigned)lba1<<8) | ((unsigned)lba2<<16);
        if(lba>=SECTORS) { status=0x51; return; }
        if(value==0x20) { memcpy(sector,disk[lba],512); data_pos=0;status=0x58; }
        else if(value==0x30) { data_pos=0;status=0x58; }
        else if(value==0xe7) { status=0x50; }
    }
}
uint16_t ferros_ata_in16(uint16_t port) {
    uint16_t word;
    if(port!=0x1f0) return 0;
    word=(uint16_t)(sector[data_pos*2] | (sector[data_pos*2+1]<<8));
    data_pos++;
    if(data_pos>=256) { data_pos=0;status=0x50; }
    return word;
}
void ferros_ata_out16(uint16_t port,uint16_t value) {
    if(port!=0x1f0) return;
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

static uint32_t fnv32(const unsigned char* data,size_t length) {
    uint32_t hash=2166136261u;
    for(size_t i=0;i<length;i++) { hash^=data[i];hash*=16777619u; }
    return hash;
}

static int expect(const char* text,const char* where) {
    if(strcmp(serial,text)!=0) {
        fprintf(stderr,"%s: serial=%s expected=%s\n",where,serial,text);
        return 1;
    }
    return 0;
}

int main(void) {
    unsigned char payload[512], buffer[512];
    char text[64];
    memset(disk,0,sizeof disk);memset(memory_state,0,sizeof memory_state);
    ata_reset();test_pfs_init();

    /* Boot 1 formats the raw disk and creates boot.txt. */
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: BOOT 1 FILES=1\n","boot 1")) return 1;
    if(memcmp(disk[16],"ZENFS01",7)!=0 || disk[16][7]!=0) { puts("bad magic"); return 2; }
    if(*(uint32_t*)(disk[16]+8)!=1 || *(uint32_t*)(disk[16]+12)!=8) { puts("bad version/inodes"); return 3; }
    if(*(uint32_t*)(disk[16]+16)!=fnv32(disk[16],16)) { puts("bad superblock checksum"); return 4; }
    if(memcmp(disk[17],"boot.txt",8)!=0 || disk[17][8]!=0) { puts("bad inode name"); return 5; }
    if(*(uint64_t*)(disk[17]+24)!=7) { puts("bad boot.txt size"); return 6; }
    if(*(uint32_t*)(disk[17]+32)!=25) { puts("bad data lba"); return 7; }
    if(disk[17][36]!=1) { puts("bad used flag"); return 8; }
    if(memcmp(disk[25],"boot=1\n",7)!=0) { puts("bad boot.txt payload"); return 9; }
    if(test_pfs_list()!=1) { puts("first boot list"); return 10; }
    if(test_pfs_find(0)!=0) { puts("find boot.txt"); return 11; }
    if(test_pfs_find(9)!=-1 || test_pfs_find(10)!=-1 || test_pfs_find(11)!=-1) {
        puts("invalid names accepted"); return 12;
    }
    if(test_pfs_find(12)!=-5) { puts("missing name is not ENOENT"); return 13; }

    /* Boot 2 increments boot.txt and keeps one file. */
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: BOOT 2 FILES=1\n","boot 2")) return 14;
    if(memcmp(disk[25],"boot=2\n",7)!=0) { puts("counter not persisted"); return 15; }
    if(*(uint64_t*)(disk[17]+24)!=7) { puts("counter size changed"); return 16; }

    /* The decimal text grows with the counter: 3..10 must parse and resize. */
    for(int expected=3;expected<=10;expected++) {
        serial_len=0;serial[0]=0;test_pfs_boot();
        snprintf(text,sizeof text,"PFS: BOOT %d FILES=1\n",expected);
        if(expect(text,"counter growth")) return 54;
    }
    if(memcmp(disk[25],"boot=10\n",8)!=0) { puts("boot=10 payload"); return 55; }
    if(*(uint64_t*)(disk[17]+24)!=8) { puts("boot=10 size"); return 56; }

    /* create/write/read and duplicate detection. */
    if(test_pfs_create(1)!=1) { puts("create hello.zen"); return 17; }
    if(test_pfs_create(1)!=-1) { puts("duplicate accepted"); return 18; }
    memset(payload,0,sizeof payload);memcpy(payload,"Hello",5);
    if(test_pfs_write(1,(uint64_t)(uintptr_t)payload,5)!=5) { puts("write hello.zen"); return 19; }
    memset(buffer,0,sizeof buffer);
    if(test_pfs_read(1,(uint64_t)(uintptr_t)buffer,16)!=5 || memcmp(buffer,"Hello",5)!=0) { puts("read hello.zen"); return 20; }
    if(test_pfs_list()!=2) { puts("list after create"); return 21; }
    if(memcmp(disk[18],"hello.zen",9)!=0 || disk[18][9]!=0) { puts("second inode name"); return 22; }
    if(*(uint32_t*)(disk[18]+32)!=26) { puts("second data lba"); return 23; }
    if(memcmp(disk[26],"Hello",5)!=0) { puts("data block not written"); return 24; }
    if(test_pfs_write(1,(uint64_t)(uintptr_t)payload,513)!=-1) { puts("oversized write accepted"); return 25; }
    if(test_pfs_write(9,(uint64_t)(uintptr_t)payload,1)!=-1) { puts("write to invalid name"); return 26; }
    if(test_pfs_read(1,(uint64_t)(uintptr_t)buffer,512)!=5) { puts("read clamps to size"); return 27; }
    if(test_pfs_read(9,(uint64_t)(uintptr_t)buffer,1)!=-1) { puts("read from invalid name"); return 28; }
    if(test_pfs_write(12,(uint64_t)(uintptr_t)payload,1)!=-5) { puts("write missing name"); return 53; }

    /* Fill the eight inodes, reject the ninth and reuse a deleted slot. */
    for(uint64_t id=2;id<=7;id++) {
        if(test_pfs_create(id)!=(int64_t)id) { printf("create id %llu\n",(unsigned long long)id); return 29; }
    }
    if(test_pfs_create(8)!=-4) { puts("full table did not report ENOSPC"); return 30; }
    if(test_pfs_list()!=8) { puts("full table count"); return 31; }
    if(test_pfs_delete(1)!=0 || test_pfs_delete(1)!=-5) { puts("delete/ENOENT"); return 32; }
    if(test_pfs_list()!=7) { puts("count after delete"); return 33; }
    if(test_pfs_read(1,(uint64_t)(uintptr_t)buffer,16)!=-5) { puts("read deleted file"); return 34; }
    if(test_pfs_create(8)!=1) { puts("deleted slot not reused"); return 35; }
    if(test_pfs_delete(8)!=0) { puts("delete reused slot"); return 36; }
    for(uint64_t id=2;id<=7;id++) {
        if(test_pfs_delete(id)!=0) { printf("cleanup id %llu\n",(unsigned long long)id); return 37; }
    }
    if(test_pfs_delete(0)!=0) { puts("cleanup boot.txt"); return 38; }

    /* Boot 3 recreates boot.txt after the cleanup. */
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: BOOT 1 FILES=1\n","boot after cleanup")) return 39;

    /* A corrupt checksum is detected, then pfs_boot reformats. */
    disk[16][16]^=0xff;
    if(test_pfs_find(0)!=-3) { puts("corrupt checksum not detected"); return 40; }
    if(test_pfs_list()!=0) { puts("corrupt list not zero"); return 41; }
    if(test_pfs_create(1)!=-3) { puts("corrupt create not rejected"); return 42; }
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: BOOT 1 FILES=1\n","reformat boot")) return 43;
    if(memcmp(disk[16],"ZENFS01",7)!=0 || *(uint32_t*)(disk[16]+16)!=fnv32(disk[16],16)) {
        puts("reformat did not rebuild the superblock"); return 44;
    }
    if(memcmp(disk[25],"boot=1\n",7)!=0) { puts("reformat did not recreate boot.txt"); return 45; }

    /* No ATA device: every entry point reports -2 or UNAVAILABLE, never panics. */
    disk_present=0;
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: UNAVAILABLE\n","absent disk")) return 46;
    if(test_pfs_list()!=0) { puts("absent disk list"); return 47; }
    if(test_pfs_find(0)!=-2) { puts("absent disk find"); return 48; }
    if(test_pfs_create(1)!=-2) { puts("absent disk create"); return 49; }
    if(test_pfs_write(0,(uint64_t)(uintptr_t)payload,1)!=-2) { puts("absent disk write"); return 50; }
    if(test_pfs_read(0,(uint64_t)(uintptr_t)buffer,1)!=-2) { puts("absent disk read"); return 51; }
    if(test_pfs_delete(0)!=-2) { puts("absent disk delete"); return 52; }
    disk_present=1;

    puts("PFS OK: format, inodes, checksum, CRUD, limits, corruption and no ATA");
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

// C cannot build a Zen str, so the harness selects fixed names by id.
fn pfs_test_name(id:u64)->str {
    if id==0u64 { return "boot.txt"; }
    if id==1u64 { return "hello.zen"; }
    if id==2u64 { return "one.txt"; }
    if id==3u64 { return "two.txt"; }
    if id==4u64 { return "three.txt"; }
    if id==5u64 { return "four.txt"; }
    if id==6u64 { return "five.txt"; }
    if id==7u64 { return "six.txt"; }
    if id==8u64 { return "seven.txt"; }
    if id==9u64 { return ""; }
    if id==10u64 { return "bad/name"; }
    if id==11u64 { return "abcdefghijklmnopqrstuvwx"; }
    if id==12u64 { return "missing.txt"; }
    return "";
}

pub fn test_pfs_init() { heap_init(); }
pub fn test_pfs_boot() { pfs_boot(); }
pub fn test_pfs_list()->u32 { return pfs_list(); }
pub fn test_pfs_find(id:u64)->i64 { return pfs_find(pfs_test_name(id)); }
pub fn test_pfs_create(id:u64)->i64 { return pfs_create(pfs_test_name(id)); }
pub fn test_pfs_write(id:u64,src:u64,len:u64)->i64 { return pfs_write(pfs_test_name(id),src,len); }
pub fn test_pfs_read(id:u64,dst:u64,max:u64)->i64 { return pfs_read(pfs_test_name(id),dst,max); }
pub fn test_pfs_delete(id:u64)->i64 { return pfs_delete(pfs_test_name(id)); }
"""


HOST_ARCH=r"""
// Only the byte helpers serial.zen needs; the ATA unit declares its own inw/outw
// externs, so the full privileged abi.zen is deliberately not linked here.
extern "C" {
    fn ferros_in8(port:u16)->u8;
    fn ferros_out8(port:u16,value:u8);
}
"""


def fnv1a32(data):
    value=2166136261
    for byte in data:
        value=((value^byte)*16777619)&0xffffffff
    return value


class PfsHostTests(unittest.TestCase):
    def test_mini_fs_with_host_safe_ata_mock(self):
        source="\n".join([
            HOST_ARCH,
            memory_source(),
            (ROOT/"ferros/kernel/drivers/serial.zen").read_text(),
            (ROOT/"ferros/kernel/drivers/ata.zen").read_text(),
            (ROOT/"ferros/kernel/storage_fs.zen").read_text(),
            HOST_SUPPORT,
        ])
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);(tmp/"pfs.zen").write_text(source);(tmp/"mock.c").write_text(HARNESS)
            for optimized in (False,True):
                with self.subTest(optimized=optimized):
                    args=[str(ZEN),"build",str(tmp/"pfs.zen"),"--target",
                          "x86_64-unknown-none","--emit","obj","-o",str(tmp/"pfs.o")]
                    if optimized: args.append("--release")
                    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr)
                    result=subprocess.run(
                        ["cc","-std=c11","-fno-builtin","-fno-pie","-no-pie",
                         str(tmp/"mock.c"),str(tmp/"pfs.o"),"-o",str(tmp/"mock")],
                        capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr)
                    result=subprocess.run([str(tmp/"mock")],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn("PFS OK",result.stdout)


class PfsGuestTests(unittest.TestCase):
    """Three QEMU invocations with the same raw disk must report BOOT 1/2/3."""

    @classmethod
    def setUpClass(cls):
        if not ZEN.exists():
            raise unittest.SkipTest(f"build the release compiler first: {ZEN}")

    def test_three_boots_with_the_same_disk_increment_boot_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);disk=tmp/"pfs.img"
            with disk.open("wb") as stream: stream.truncate(1024*1024)
            build=build_kernel(ZEN,tmp/"build",True)
            for expected in (1,2,3):
                with self.subTest(boot=expected):
                    result=boot(build["image_path"],tmp/f"boot-{expected}",disk_image=disk)
                    self.assertEqual(result["status"],33)
                    self.assertEqual(result["pfs"],{"available":True,"boot":expected,"files":1})
                    self.assertEqual(result["persistence"],{"available":True,"boot":expected})
                    serial=(tmp/f"boot-{expected}"/"serial.log").read_bytes()
                    self.assertEqual(serial.count(f"PFS: BOOT {expected} FILES=1\n".encode()),1)
                    self.assertLess(serial.index(b"PERSIST: BOOT "),serial.index(b"PFS: BOOT "))
                    self.assertLess(serial.index(b"PFS: BOOT "),serial.index(b"USER: Hello from Zen"))
                    self.assertNotIn(b"PANIC",serial)
                    self.assertIn(b"HITO 7 OK",serial)
                    self.assertIn(b"writes=18",serial)
                    self.assertEqual((tmp/f"boot-{expected}"/"qemu.stderr.log").read_bytes(),b"")
                    log=json.loads((tmp/f"boot-{expected}"/"result.json").read_text())
                    self.assertTrue(log["passed"])
                    self.assertFalse(log["disk_temporary"])
            raw=disk.read_bytes()
            superblock=raw[16*512:17*512]
            self.assertEqual(superblock[:8],b"ZENFS01\x00")
            self.assertEqual(int.from_bytes(superblock[8:12],"little"),1)
            self.assertEqual(int.from_bytes(superblock[12:16],"little"),8)
            self.assertEqual(int.from_bytes(superblock[16:20],"little"),fnv1a32(superblock[:16]))
            inode=raw[17*512:17*512+64]
            self.assertEqual(inode[:9],b"boot.txt\x00")
            self.assertEqual(int.from_bytes(inode[24:32],"little"),7)
            self.assertEqual(int.from_bytes(inode[32:36],"little"),25)
            self.assertEqual(inode[36],1)
            self.assertEqual(raw[25*512:25*512+7],b"boot=3\n")
            # TASK-914's counter keeps living in sector 0 and also reached 3.
            self.assertEqual(raw[:8],b"ZENPERS1")
            self.assertEqual(int.from_bytes(raw[8:16],"little"),3)


if __name__=="__main__":
    unittest.main()
