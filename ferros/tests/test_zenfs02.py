"""ZENFS02 disk recovery tests against the real Zen storage code and ATA mock."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from ferros.tests.test_pfs import HARNESS, HOST_ARCH, HOST_SUPPORT, ROOT, ZEN, memory_source


MAIN = r"""
static _Alignas(16) unsigned char cache[8192];
static unsigned char original_v1[17][512];

static void reboot(void) {
    memset(memory_state,0,sizeof memory_state);
    ata_reset(); test_pfs_init(); serial_len=0;serial[0]=0;
    test_pfs_boot();
    memset(cache,0,sizeof cache);
    test_pfs_export((uint64_t)(uintptr_t)cache);
}
static int read_saved(const char *expected,size_t length) {
    unsigned char out[512];memset(out,0xa5,sizeof out);
    if(test_pfs_read(1,(uint64_t)(uintptr_t)out,512)!=(int64_t)length) return 0;
    return memcmp(out,expected,length)==0;
}
static int commit_saved(const char *value,size_t length) {
    return (int)test_pfs_commit((uint64_t)(uintptr_t)"hello.zen",
      (uint64_t)(uintptr_t)value,length,(uint64_t)(uintptr_t)cache);
}
static void seed_v1(void) {
    memset(disk,0,sizeof disk);
    memcpy(disk[16],"ZENFS01",7);
    *(uint32_t*)(disk[16]+8)=1;
    *(uint32_t*)(disk[16]+12)=8;
    *(uint32_t*)(disk[16]+16)=fnv32(disk[16],16);
    memcpy(disk[17],"boot.txt",8);
    *(uint64_t*)(disk[17]+24)=7;
    *(uint32_t*)(disk[17]+32)=25;
    disk[17][36]=1;
    memcpy(disk[25],"boot=7\n",7);
    memcpy(disk[18],"hello.zen",9);
    *(uint64_t*)(disk[18]+24)=6;
    *(uint32_t*)(disk[18]+32)=26;
    disk[18][36]=1;
    memcpy(disk[26],"legacy",6);
    memcpy(original_v1,disk+16,sizeof original_v1);
}
static int v1_intact(void) { return memcmp(original_v1,disk+16,sizeof original_v1)==0; }

int main(void) {
    char full[512]; memset(full,'F',sizeof full);
    memset(disk,0,sizeof disk); reboot();
    if(strcmp(serial,"PFS: BOOT 1 FILES=1\n") || memcmp(disk[33],"ZENFS02",7) || memcmp(disk[46],"ZENACT02",8)) return 1;
    if(commit_saved("old",3)!=3 || !read_saved("old",3)) return 2;
    if(commit_saved(full,512)!=512 || !read_saved(full,512)) return 3;
    if(commit_saved("",0)!=0 || !read_saved("",0)) return 4;
    if(commit_saved("x",513)!=-27) return 5;
    if(test_pfs_commit((uint64_t)(uintptr_t)"boot.txt",0,0,(uint64_t)(uintptr_t)cache)!=-13) return 6;
    if(commit_saved("old",3)!=3) return 7;
    reboot(); if(!read_saved("old",3)) return 8;
    const char *names[]={"one.txt","two.txt","three.txt","four.txt","five.txt","six.txt"};
    for(int i=0;i<6;i++) {
        if(test_pfs_commit((uint64_t)(uintptr_t)names[i],(uint64_t)(uintptr_t)"z",1,(uint64_t)(uintptr_t)cache)!=1) return 9+i;
        if(test_pfs_export((uint64_t)(uintptr_t)cache)!=0) return 15+i;
    }
    if(test_pfs_list()!=8) return 19;
    if(test_pfs_commit((uint64_t)(uintptr_t)"overflow.txt",(uint64_t)(uintptr_t)"x",1,(uint64_t)(uintptr_t)cache)!=-28) return 20;

    /* Each failed or torn COW stage must remount an older or complete value. */
    unsigned char baseline[SECTORS][512]; memcpy(baseline,disk,sizeof disk);
    for(int stage=0;stage<3;stage++) for(int torn=0;torn<2;torn++) {
        memcpy(disk,baseline,sizeof disk); reboot();
        fail_command=torn?0:0x30;fail_lba=0;fail_skip=(unsigned)stage;
        tear_skip=(unsigned)stage;tear_enabled=torn;tear_bytes=257;
        int result=commit_saved("new!",4);
        fail_command=0;tear_enabled=0;
        if(result>=0 || *(uint64_t*)cache!=0) return 20+stage*2+torn;
        reboot();
        if(!read_saved("old",3) && !read_saved("new!",4)) return 30+stage*2+torn;
    }
    for(int stage=0;stage<3;stage++) {
        memcpy(disk,baseline,sizeof disk); reboot();
        fail_command=0xe7;fail_lba=0;fail_skip=(unsigned)stage;
        int result=commit_saved("new!",4);fail_command=0;
        if(result>=0 || *(uint64_t*)cache!=0) return 36+stage;
        reboot();
        if(!read_saved("old",3) && !read_saved("new!",4)) return 39+stage;
    }

    /* A valid v1 disk is migrated without changing any of its 17 sectors. */
    seed_v1(); reboot();
    if(strcmp(serial,"PFS: BOOT 8 FILES=2\n") || !v1_intact() || !read_saved("legacy",6)) return 40;
    reboot(); if(strcmp(serial,"PFS: BOOT 9 FILES=2\n") || !v1_intact() || !read_saved("legacy",6)) return 41;

    /* Cut every migration write, including activation; the next boot retries. */
    for(int stage=0;stage<5;stage++) for(int torn=0;torn<2;torn++) {
        seed_v1();
        fail_command=torn?0:0x30;fail_lba=0;fail_skip=(unsigned)stage;
        tear_skip=(unsigned)stage;tear_enabled=torn;tear_bytes=191;
        reboot();
        fail_command=0;tear_enabled=0;
        if(!v1_intact()) return 50+stage*2+torn;
        reboot();
        if(!v1_intact() || !read_saved("legacy",6) || test_pfs_list()!=2) return 60+stage*2+torn;
    }

    seed_v1();disk[16][16]^=1;memcpy(original_v1,disk+16,sizeof original_v1);reboot();
    if(strcmp(serial,"PFS: UNAVAILABLE\n") || !v1_intact()) return 70;
    memset(disk,0,sizeof disk);reboot();
    disk[33][36]^=1;disk[34][36]^=1;
    unsigned char corrupt[SECTORS][512];memcpy(corrupt,disk,sizeof disk);
    reboot();
    if(strcmp(serial,"PFS: UNAVAILABLE\n") || memcmp(corrupt,disk,sizeof disk)) return 72;
    disk_present=0;reboot();
    if(strcmp(serial,"PFS: UNAVAILABLE\n")) return 71;
    puts("ZENFS02 OK: creation, COW, migration, cuts, tears, corruption, no ATA");
    return 0;
}
"""


def mocked_harness():
    prefix = HARNESS.split("int main(void)", 1)[0]
    prefix = prefix.replace("static int data_pos=0;", "static int tear_enabled=0; static unsigned tear_skip=0,tear_bytes=0; static int tear_this=0;\nstatic int data_pos=0;")
    prefix = prefix.replace("else if(value==0x30) { data_pos=0;status=0x58; }", "else if(value==0x30) { data_pos=0;status=0x58; tear_this=0; if(tear_enabled) { if(tear_skip) tear_skip--; else { tear_this=1; tear_enabled=0; } } }")
    prefix = prefix.replace("memcpy(disk[lba],sector,512); data_pos=0;status=0x50;", "if(tear_this) { memcpy(disk[lba],sector,tear_bytes);status=0x51;tear_this=0; } else { memcpy(disk[lba],sector,512);status=0x50; } data_pos=0;")
    return prefix + MAIN


class Zenfs02HostTests(unittest.TestCase):
    def test_recovery_with_mock_ata(self):
        source="\n".join((HOST_ARCH, memory_source(),
            (ROOT/"ferros/kernel/drivers/serial.zen").read_text(),
            (ROOT/"ferros/kernel/drivers/ata.zen").read_text(),
            (ROOT/"ferros/kernel/storage_fs.zen").read_text(),HOST_SUPPORT))
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            (tmp/"pfs.zen").write_text(source)
            (tmp/"mock.c").write_text(mocked_harness())
            for release in (False,True):
                with self.subTest(release=release):
                    args=[str(ZEN),"build",str(tmp/"pfs.zen"),"--target", "x86_64-unknown-none","--emit","obj","-o",str(tmp/"pfs.o")]
                    if release: args.append("--release")
                    built=subprocess.run(args,capture_output=True,text=True,timeout=30)
                    self.assertEqual(built.returncode,0,built.stderr)
                    linked=subprocess.run(["cc","-std=c11","-fno-builtin","-fno-pie","-no-pie",str(tmp/"mock.c"),str(tmp/"pfs.o"),"-o",str(tmp/"mock")],capture_output=True,text=True,timeout=30)
                    self.assertEqual(linked.returncode,0,linked.stderr)
                    run=subprocess.run([str(tmp/"mock")],capture_output=True,text=True,timeout=30)
                    self.assertEqual(run.returncode,0,f"exit={run.returncode}\n{run.stdout}\n{run.stderr}")
                    self.assertIn("ZENFS02 OK",run.stdout)
