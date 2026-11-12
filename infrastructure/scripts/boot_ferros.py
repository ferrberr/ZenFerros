#!/usr/bin/env python3
"""Build and boot Ferros in an isolated, bounded QEMU TCG guest."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from build_ferros import ROOT, build_kernel

# TASK-703 shell contract: the runner writes DEFAULT_INPUT only after the guest
# prints SHELL: READY, because serial_init flushes the COM1 FIFO at boot.
SHELL_READY=b"SHELL: READY"
SHELL_DONE=b"SHELL: DONE"
VFS_BLOCK=b"SHELL> ls\nhello.zen\nSHELL> cat hello.zen\nHello\n"
# TASK-919: `ls` now also lists the ZENFS01 file boot.txt; the command script,
# the VFS block and the shell write count (18) stay frozen.
SHELL_TRANSCRIPT=(SHELL_READY+b"\nSHELL> ls\nhello.zen\nnotes.txt\nboot.txt\nSHELL> cat hello.zen\nHello\n"
                  b"SHELL> help\ncommands: help ls cat exit\nSHELL> exit\n"+SHELL_DONE+b"\n")
DEFAULT_INPUT=b"ls\ncat hello.zen\nhelp\nexit\n"
PERSIST_LINE=b"PERSIST: BOOT 1\n"
PFS_LINE=b"PFS: BOOT 1 FILES=1\n"
EXPECTED_MESSAGES=(b"FERROS KERNEL\nPowered by Zen\nMEMORY: PMM OK\nMEMORY: VMM OK\nMEMORY: HEAP OK\n"
                   b"INTERRUPTS: BREAKPOINT OK\nINTERRUPTS: PAGE FAULT OK\nINTERRUPTS: TIMER OK\n"
                   b"THREADS: CONTEXT OK\nSCHEDULER: PREEMPTION OK\nSCHEDULER: YIELD AND EXIT OK\n"
                   b"USER: Hello from Zen\n"+VFS_BLOCK+SHELL_TRANSCRIPT+
                   b"USERSPACE: RING3 AND SYSCALLS OK\nUSERSPACE: ISOLATION AND CLEANUP OK\n"
                   b"FS: RAMFS OK\nFS: VFS OPEN/READ/CLOSE OK\nBoot successful\nHITO 7 OK\n")
# A canonical example is exported for validator tests; actual boots print actual counters.
STATS_PATTERN=re.compile(rb"SCHEDULER: STATS switches=([0-9]{1,10}) preemptions=([0-9]{1,10}) yields=([0-9]{1,10}) completed=([0-9]{1,10})\n")
USER_STATS_PATTERN=re.compile(rb"USERSPACE: STATS runs=([0-9]{1,10}) writes=([0-9]{1,10}) rejected=([0-9]{1,10}) irqs=([0-9]{1,10})\n")
# TASK-914: one boot line from the ATA PIO superblock, before the shell output.
PERSIST_PATTERN=re.compile(rb"PERSIST: (BOOT ([0-9]{1,20})|UNAVAILABLE)\n")
# TASK-916: the mini-FS line follows PERSIST and precedes the ring-3 shell.
PFS_PATTERN=re.compile(rb"PFS: (BOOT ([0-9]{1,20}) FILES=([0-9]{1,10})|UNAVAILABLE)\n")
FS_SERIES=b"FS: RAMFS OK\nFS: VFS OPEN/READ/CLOSE OK\n"
EXPECTED=EXPECTED_MESSAGES.replace(b"USER: Hello",b"SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3\n"+PERSIST_LINE+PFS_LINE+b"USER: Hello").replace(FS_SERIES,b"USERSPACE: STATS runs=7 writes=18 rejected=6 irqs=1\n"+FS_SERIES)
SUCCESS_STATUS=33
DEFAULT_DISK_BYTES=1024*1024


def validate_boot(status, serial, stderr, timed_out=False):
    if timed_out: raise RuntimeError("QEMU boot timed out")
    if status!=SUCCESS_STATUS: raise RuntimeError(f"QEMU status {status}, expected {SUCCESS_STATUS}")
    matches=list(STATS_PATTERN.finditer(serial))
    if len(matches)!=1: raise RuntimeError("missing or repeated scheduler statistics")
    match=matches[0]
    if match.start()!=EXPECTED_MESSAGES.index(b"USER: Hello"):
        raise RuntimeError("scheduler statistics are out of order")
    persist_matches=list(PERSIST_PATTERN.finditer(serial))
    if len(persist_matches)!=1: raise RuntimeError("missing or repeated persistence line")
    persist=persist_matches[0]
    if persist.start()!=match.end():
        raise RuntimeError("persistence line is out of order")
    pfs_matches=list(PFS_PATTERN.finditer(serial))
    if len(pfs_matches)!=1: raise RuntimeError("missing or repeated mini-FS line")
    pfs=pfs_matches[0]
    if pfs.start()!=persist.end():
        raise RuntimeError("mini-FS line is out of order")
    if not serial[pfs.end():].startswith(b"USER: Hello from Zen\n"):
        raise RuntimeError("mini-FS line must precede the shell output")
    persistence=dict(available=persist.group(2) is not None,
                     boot=int(persist.group(2)) if persist.group(2) is not None else None)
    if persistence["available"] and persistence["boot"]<1:
        raise RuntimeError(f"persistence counter violates acceptance: {persistence}")
    filesystem=dict(available=pfs.group(2) is not None,
                    boot=int(pfs.group(2)) if pfs.group(2) is not None else None,
                    files=int(pfs.group(3)) if pfs.group(3) is not None else None)
    if filesystem["available"] and (filesystem["boot"]<1 or filesystem["files"]<1):
        raise RuntimeError(f"mini-FS counters violate acceptance: {filesystem}")
    user_matches=list(USER_STATS_PATTERN.finditer(serial))
    if len(user_matches)!=1: raise RuntimeError("missing or repeated userspace statistics")
    user_match=user_matches[0]
    if user_match.start()<=match.end() or not serial[user_match.end():].startswith(FS_SERIES+b"Boot successful\n"):
        raise RuntimeError("userspace statistics are out of order")
    userspace=dict(zip(["runs","writes","rejected","irqs"],map(int,user_match.groups())))
    if userspace["runs"]!=7 or userspace["writes"]!=18 or userspace["rejected"]<6 or userspace["irqs"]<1:
        raise RuntimeError(f"userspace counters violate acceptance: {userspace}")
    if serial.count(SHELL_READY)!=1 or serial.count(SHELL_DONE)!=1:
        raise RuntimeError("missing or repeated shell transcript markers")
    ready=serial.index(SHELL_READY)
    vfs=serial.find(VFS_BLOCK)
    # Variable-width counters precede the VFS block, so compare relative order.
    if vfs<0 or ready!=vfs+len(VFS_BLOCK):
        raise RuntimeError("shell transcript is out of order")
    if serial[ready:ready+len(SHELL_TRANSCRIPT)]!=SHELL_TRANSCRIPT:
        raise RuntimeError("shell transcript violates acceptance")
    fixed=USER_STATS_PATTERN.sub(b"",PFS_PATTERN.sub(b"",PERSIST_PATTERN.sub(b"",STATS_PATTERN.sub(b"",serial))))
    if fixed!=EXPECTED_MESSAGES: raise RuntimeError(f"unexpected serial output: {serial!r}")
    stats=dict(zip(["switches","preemptions","yields","completed"],map(int,match.groups())))
    if stats["switches"]<6 or not 2<=stats["preemptions"]<=stats["switches"] or stats["yields"]!=16 or stats["completed"]!=3:
        raise RuntimeError(f"scheduler counters violate acceptance: {stats}")
    stats["persistence"]=persistence
    stats["pfs"]=filesystem
    if stderr: raise RuntimeError(f"QEMU stderr is not empty: {stderr!r}")
    return stats


def qemu_environment(explicit=None):
    local=ROOT/".tools/qemu"
    selected=explicit or os.environ.get("QEMU")
    if not selected:
        selected=local/"usr/bin/qemu-system-x86_64" if (local/"usr/bin/qemu-system-x86_64").exists() else shutil.which("qemu-system-x86_64")
    if not selected: raise RuntimeError("QEMU unavailable: install qemu-system-x86 or run infrastructure/scripts/setup_qemu.py")
    executable=Path(selected).resolve() if Path(selected).exists() else selected
    env=os.environ.copy();extra=[]
    if str(executable)==str((local/"usr/bin/qemu-system-x86_64").resolve()):
        env["LD_LIBRARY_PATH"]=str(local/"usr/lib")
        env["QEMU_MODULE_DIR"]=str(local/"usr/lib/qemu")
        extra=["-L",str(local/"usr/share/qemu")]
    return str(executable),env,extra


def stop_process(process):
    # The process group is isolated from the terminal; always stop it ourselves.
    try: os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError: pass
    try: return process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        return process.communicate()


def _terminate_group(process):
    # Reader threads own the pipes, so kill/wait instead of communicate().
    try: os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError: pass
    try: process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait()


def _read_chunk(stream):
    # read1() returns as soon as bytes are available; plain read(n) can block
    # until n bytes or EOF, delaying the SHELL: READY check until the guest exits.
    read=getattr(stream,"read1",stream.read)
    return read(4096)


def _read_stream(stream,sink,guard):
    while True:
        try: chunk=_read_chunk(stream)
        except (OSError,ValueError): break
        if not chunk: break
        with guard: sink.extend(chunk)


def _inject_after_ready(stdout,stdin,sink,guard,payload,state):
    while True:
        try: chunk=_read_chunk(stdout)
        except (OSError,ValueError): break
        if not chunk: break
        with guard:
            sink.extend(chunk)
            # Check the accumulated stream: SHELL: READY may span chunks.
            ready=not state["injected"] and SHELL_READY in sink
        if ready:
            state["injected"]=True
            try:
                stdin.write(payload);stdin.flush();stdin.close()
            except (BrokenPipeError,OSError,ValueError) as error:
                state["error"]=error
    if not stdin.closed:
        try: stdin.close()
        except (BrokenPipeError,OSError): pass


def _capture_with_input(process,timeout,payload):
    serial=bytearray();stderr=bytearray();guard=threading.Lock()
    state={"injected":False,"error":None}
    threads=[threading.Thread(target=_inject_after_ready,args=(process.stdout,process.stdin,serial,guard,payload,state),daemon=True),
             threading.Thread(target=_read_stream,args=(process.stderr,stderr,guard),daemon=True)]
    for thread in threads: thread.start()
    timed_out=False;cancelled=False;pending=None
    try: process.wait(timeout=timeout)
    except subprocess.TimeoutExpired: timed_out=True
    except BaseException as error:
        pending=error;cancelled=isinstance(error,KeyboardInterrupt)
    try:
        if timed_out or pending is not None:
            # Keep cleanup/reaping reliable if Ctrl+C is pressed again.
            previous=signal.signal(signal.SIGINT,signal.SIG_IGN)
            try: _terminate_group(process)
            finally: signal.signal(signal.SIGINT,previous)
        for thread in threads: thread.join(timeout=2)
    except BaseException as error:
        if pending is None:
            pending=error;cancelled=isinstance(error,KeyboardInterrupt)
    finally:
        for stream in (process.stdin,process.stdout,process.stderr):
            try: stream.close()
            except (OSError,ValueError): pass
    with guard:
        return bytes(serial),bytes(stderr),timed_out,cancelled,pending,process.returncode,state["error"]


def run_process(command,env,timeout,output,input=None,extra=None):
    if timeout<=0: raise ValueError("timeout must be positive")
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();timed_out=False
    serial=stderr=b"";status=None;process=None;pending=None;cancelled=False;injection_error=None
    try:
        if input is None:
            process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try: serial,stderr=process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired: timed_out=True
        else:
            process=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            serial,stderr,timed_out,cancelled,pending,status,injection_error=_capture_with_input(process,timeout,input)
    except BaseException as error:
        pending=error
    finally:
        if process is not None:
            if input is None:
                if timed_out or pending is not None:
                    # Keep cleanup/reaping reliable if Ctrl+C is pressed again.
                    previous=signal.signal(signal.SIGINT,signal.SIG_IGN)
                    try: serial,stderr=stop_process(process)
                    finally: signal.signal(signal.SIGINT,previous)
                status=process.returncode
            elif pending is not None and process.poll() is None:
                previous=signal.signal(signal.SIGINT,signal.SIG_IGN)
                try: _terminate_group(process)
                finally: signal.signal(signal.SIGINT,previous)
                status=process.returncode
        elif pending is not None:
            stderr=str(pending).encode()
        cancelled=cancelled or isinstance(pending,KeyboardInterrupt)
        result=dict(command=[str(c) for c in command],status=status,timed_out=timed_out,cancelled=cancelled,seconds=round(time.perf_counter()-started,6),passed=False)
        if extra: result.update(extra)
        if injection_error is not None: result["injection_error"]=str(injection_error)
        (output/"serial.log").write_bytes(serial);(output/"qemu.stderr.log").write_bytes(stderr)
        try:
            if pending is not None: raise RuntimeError("QEMU boot cancelled" if cancelled else str(pending))
            result["scheduler"]=validate_boot(status,serial,stderr,timed_out)
            result["persistence"]=result["scheduler"]["persistence"]
            result["pfs"]=result["scheduler"]["pfs"]
            result["userspace"]=dict(zip(["runs","writes","rejected","irqs"],map(int,USER_STATS_PATTERN.search(serial).groups())))
            result["passed"]=True
        except RuntimeError as error:
            result["error"]=str(error)
        (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    if pending is not None and not isinstance(pending,OSError): raise pending
    if not result["passed"]: raise RuntimeError(f"{result['error']}; logs: {output}")
    return result


def _prepare_disk(output,disk_image=None):
    """Return (path, temporary). A missing explicit image is formatted as raw."""
    if disk_image is not None:
        path=Path(disk_image).resolve()
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("wb") as stream: stream.truncate(DEFAULT_DISK_BYTES)
        elif path.stat().st_size<512:
            raise ValueError(f"disk image is smaller than one sector: {path}")
        return path,False
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix="disk-",suffix=".img",dir=output)
    try: os.ftruncate(descriptor,DEFAULT_DISK_BYTES)
    finally: os.close(descriptor)
    return Path(name),True


def boot(image,output,timeout=10,qemu=None,memory_mib=64,input=DEFAULT_INPUT,disk_image=None):
    if not 16<=memory_mib<=256: raise ValueError("guest memory must be 16..256 MiB")
    disk,temporary=_prepare_disk(output,disk_image)
    executable,env,extra=qemu_environment(qemu)
    command=[executable,*extra,"-machine","pc,accel=tcg","-cpu","qemu64","-m",f"{memory_mib}M","-smp","1","-nodefaults","-display","none","-monitor","none","-serial","stdio","-nic","none","-drive",f"file={disk},format=raw,if=ide,index=0","-no-reboot","-device","isa-debug-exit,iobase=0xf4,iosize=0x04","-kernel",str(Path(image).resolve())]
    try:
        result=run_process(command,env,timeout,output,input,extra={"disk":str(disk),"disk_temporary":temporary})
    finally:
        if temporary: disk.unlink(missing_ok=True)
    result.update(disk=str(disk),disk_temporary=temporary)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen",type=Path,default=ROOT/"zen/compiler/target/release/zen")
    parser.add_argument("--qemu")
    parser.add_argument("--release",action="store_true")
    parser.add_argument("--all",action="store_true",help="test both normal and optimized kernels")
    parser.add_argument("--repeat",type=int,default=1)
    parser.add_argument("--timeout",type=float,default=10)
    parser.add_argument("--memory-mib",type=int,default=64,help="guest RAM 16..256 MiB; PMM manages at most 64 MiB")
    parser.add_argument("--disk",type=Path,help="raw ATA disk image; a temporary 1 MiB image is used by default")
    args=parser.parse_args()
    if args.repeat<1 or args.timeout<=0: parser.error("repeat and timeout must be positive")
    if not 16<=args.memory_mib<=256: parser.error("guest memory must be 16..256 MiB")
    executable,env,_=qemu_environment(args.qemu)
    version=subprocess.check_output([executable,"--version"],env=env,text=True,timeout=10).splitlines()[0]
    results=[]
    for release in ([False,True] if args.all else [args.release]):
        output=ROOT/"ferros/build"/("release" if release else "debug")
        build=build_kernel(args.zen,output,release)
        for index in range(args.repeat):
            result=boot(build["image_path"],output/f"boot-{index+1:02}",args.timeout,args.qemu,args.memory_mib,disk_image=args.disk)
            result.update(release=release,iteration=index+1,qemu_version=version,memory_mib=args.memory_mib)
            results.append(result)
            print(f"{'release' if release else 'debug'} boot {index+1}: PASS (QEMU {result['status']}, {result['seconds']:.3f}s)")
    summary=ROOT/"ferros/build/boot-results.json"
    summary.write_text(json.dumps(results,indent=2)+"\n")
    print((output/f"boot-{args.repeat:02}"/"serial.log").read_text(),end="")
    print("Evidence:",summary)

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt:
        print("Boot cancelled; guest stopped and logs saved.")
        raise SystemExit(130)
