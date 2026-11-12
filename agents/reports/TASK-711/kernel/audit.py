from pathlib import Path
import sys,json,struct,hashlib,time
ROOT=Path('/home/ferranfg/proyectos/ZenFerros')
OUT=Path('/tmp/zenferros-task711-sol')
sys.path.insert(0,str(ROOT/'infrastructure/scripts'))
from build_ferros import build_kernel
from boot_ferros import boot
ZEN=ROOT/'zen/compiler/target/release/zen'
files=['ferros/kernel/userspace.zen','ferros/kernel/interrupts.zen','ferros/kernel/main.zen','ferros/kernel/arch/x86_64/userspace.S','ferros/kernel/arch/x86_64/interrupts.S','infrastructure/scripts/build_ferros.py','infrastructure/scripts/boot_ferros.py']
initial={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
results=[]
for release in [False,True]:
    name='release' if release else 'debug'
    output=OUT/name
    build=build_kernel(ZEN,output,release)
    run=boot(build['image_path'],output/'boot',timeout=15,memory_mib=64)
    assert run['status']==33 and run['passed']
    assert run['userspace']['runs']==7 and run['userspace']['rejected']>=6 and run['userspace']['irqs']>=1
    results.append(dict(profile=name,scenario='good64',status=run['status'],passed=True,seconds=run['seconds'],userspace=run['userspace'],image=build['image_path']))
    ram=32 if not release else 128
    variation=boot(build['image_path'],output/f'boot-{ram}m',timeout=15,memory_mib=ram)
    assert variation['passed']
    results.append(dict(profile=name,scenario=f'good{ram}',status=variation['status'],passed=True,seconds=variation['seconds'],userspace=variation['userspace']))
    good_user=Path(build['user']['artifact_path']).read_bytes()
    invalid=bytearray(good_user);invalid[4]=1
    invalid_path=OUT/f'invalid-class-{name}.elf';invalid_path.write_bytes(invalid)
    kernel_entry=bytearray(good_user);struct.pack_into('<Q',kernel_entry,24,0x100000)
    kernel_entry_path=OUT/f'kernel-entry-{name}.elf';kernel_entry_path.write_bytes(kernel_entry)
    source=(ROOT/'ferros/kernel/userspace.zen').read_text()
    old='fn user_write(address:u64,length:u64)->u64 {'
    assert old in source
    fault_source=OUT/f'kernel-origin-fault-{name}.zen'
    fault_source.write_text(source.replace(old,old+'\n    if memory_read8(0)==0u8 { kernel_panic("unexpected null read returned"); return 0; }',1))
    for scenario,overrides,image,expected in [
        ('invalid-class',None,invalid_path,b'FERROS PANIC: userspace test failed\n'),
        ('entry-kernel',None,kernel_entry_path,b'FERROS PANIC: userspace test failed\n'),
        ('kernel-origin-pf',{'userspace.zen':fault_source},None,b'FERROS PANIC: unexpected interrupt or exception\n'),
    ]:
        negative=OUT/f'{name}-{scenario}'
        built=build_kernel(ZEN,negative,release,unit_overrides=overrides,user_image_override=image)
        try:
            boot(built['image_path'],negative/'boot',timeout=15,memory_mib=64)
        except RuntimeError as err:
            result=json.loads((negative/'boot/result.json').read_text())
            serial=(negative/'boot/serial.log').read_bytes()
            assert result['status']==35 and not result['timed_out'],(scenario,result)
            assert expected in serial,(scenario,serial)
            assert b'USERSPACE: RING3 AND SYSCALLS OK' not in serial
            assert b'HITO 6 OK' not in serial
            results.append(dict(profile=name,scenario=scenario,status=result['status'],expected_failure=True,seconds=result['seconds'],panic=expected.decode().strip()))
        else: raise AssertionError(f'accepted negative {scenario}')
    print(name, 'normal+RAMvariation and 3 negatives PASS', flush=True)
final={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
assert initial==final,'reviewed sources changed during validation'
(OUT/'audit-results.json').write_text(json.dumps(dict(results=results,source_sha256=final),indent=2)+'\n')
print('INDEPENDENT KERNEL AUDIT: PASS',flush=True)
