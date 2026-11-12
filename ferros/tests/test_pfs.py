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
static unsigned fail_command=0, fail_lba=0, fail_skip=0;
static int data_pos=0;
static unsigned lba=0;
static unsigned char lba0=0, lba1=0, lba2=0;
static uint8_t status=0x50;
static char serial[8192];
static size_t serial_len=0;

extern int64_t test_pfs_export(uint64_t cache);
extern int64_t test_pfs_commit(uint64_t name,uint64_t src,uint64_t len,uint64_t cache);
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
        if(value==fail_command && (fail_lba==0 || lba==fail_lba)) {
            if(fail_skip) fail_skip--; else { status=0x51; return; }
        }
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
    unsigned char out[512];
    memset(disk,0,sizeof disk);memset(memory_state,0,sizeof memory_state);
    ata_reset();test_pfs_init();
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: BOOT 1 FILES=1\n","first boot")) return 1;
    if(memcmp(disk[33],"ZENFS02",7)!=0 || memcmp(disk[46],"ZENACT02",8)!=0) return 2;
    if(test_pfs_list()!=1 || test_pfs_find(0)<0) return 3;
    memset(out,0,sizeof out);
    if(test_pfs_read(0,(uint64_t)(uintptr_t)out,512)!=7 || memcmp(out,"boot=1\n",7)!=0) return 4;
    serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: BOOT 2 FILES=1\n","second boot")) return 5;
    disk_present=0;serial_len=0;serial[0]=0;test_pfs_boot();
    if(expect("PFS: UNAVAILABLE\n","no ATA")) return 6;
    puts("PFS OK: ZENFS02 boot, counter, protected file and no ATA");
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

pub fn test_pfs_export(cache:u64)->i64 { return pfs_export(cache); }
pub fn test_pfs_commit(name:u64,src:u64,len:u64,cache:u64)->i64 { return pfs_commit_ptr(name,src,len,cache); }
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


def v2_files(raw):
    """Decode the newest fully verified ZENFS02 root from a raw disk."""
    candidates=[]
    for bank in (0,1):
        root=raw[(33+bank)*512:(34+bank)*512]
        if root[:8]!=b"ZENFS02\0" or int.from_bytes(root[8:12],"little")!=2:
            continue
        if int.from_bytes(root[36:40],"little")!=fnv1a32(root[:36]):
            continue
        table=raw[(35+bank)*512:(36+bank)*512]
        if int.from_bytes(root[28:32],"little")!=fnv1a32(table):
            continue
        files={}
        sectors=bytearray()
        for index in range(8):
            entry=table[index*64:(index+1)*64]
            if entry[40]!=1:
                continue
            name=entry[:24].split(b"\0",1)[0].decode("ascii")
            size=int.from_bytes(entry[24:32],"little")
            lba=int.from_bytes(entry[32:36],"little")
            assert size<=512 and 37<=lba<=45
            sector=raw[lba*512:(lba+1)*512]
            if int.from_bytes(entry[36:40],"little")!=fnv1a32(sector):
                break
            sectors.extend(sector)
            files[name]=sector[:size]
        else:
            if len(files)==int.from_bytes(root[12:16],"little") and int.from_bytes(root[32:36],"little")==fnv1a32(sectors):
                candidates.append((int.from_bytes(root[16:24],"little"),files))
    if not candidates:
        raise AssertionError("no valid ZENFS02 root")
    return max(candidates,key=lambda item:item[0])[1]


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
            self.assertEqual(raw[16*512:33*512],bytes(17*512))
            self.assertEqual(raw[46*512:46*512+8],b"ZENACT02")
            self.assertEqual(v2_files(raw),{"boot.txt":b"boot=3\n"})
            # TASK-914's counter keeps living in sector 0 and also reached 3.
            self.assertEqual(raw[:8],b"ZENPERS1")
            self.assertEqual(int.from_bytes(raw[8:16],"little"),3)


if __name__=="__main__":
    unittest.main()
