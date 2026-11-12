"""TASK-703 shell acceptance without QEMU: transcript, injection logic and defaults."""
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"infrastructure/scripts"))
from boot_ferros import (DEFAULT_INPUT,EXPECTED,EXPECTED_MESSAGES,PERSIST_LINE,PFS_LINE,SHELL_DONE,SHELL_READY,
                         SHELL_TRANSCRIPT,SUCCESS_STATUS,VFS_BLOCK,_inject_after_ready,
                         boot,run_process,validate_boot)


class RecordingStdin:
    def __init__(self):
        self.data=bytearray();self.closed=False
    def write(self,payload):
        if self.closed: raise ValueError("write to closed stdin")
        self.data.extend(payload);return len(payload)
    def flush(self): pass
    def close(self): self.closed=True


class ScriptedStdout:
    def __init__(self,chunks,on_read=None):
        self.chunks=list(chunks);self.on_read=on_read
    def read(self,size=-1):
        if self.on_read is not None: self.on_read(len(self.chunks))
        return self.chunks.pop(0) if self.chunks else b""


class ShellContractTests(unittest.TestCase):
    def test_canonical_transcript_is_accepted(self):
        stats=validate_boot(SUCCESS_STATUS,EXPECTED,b"")
        self.assertEqual(stats["completed"],3)

    def test_variable_width_counters_do_not_break_order_checks(self):
        serial=(EXPECTED.replace(b"switches=45",b"switches=123")
                .replace(b"preemptions=25",b"preemptions=100")
                .replace(b"rejected=6",b"rejected=10")
                .replace(b"irqs=1",b"irqs=12"))
        self.assertEqual(validate_boot(SUCCESS_STATUS,serial,b"")["switches"],123)

    def test_missing_or_duplicated_shell_markers_are_rejected(self):
        marker=SHELL_READY+b"\n"
        invalid=[EXPECTED.replace(marker,b""),
                 EXPECTED.replace(marker,marker+marker),
                 EXPECTED.replace(SHELL_DONE+b"\n",b""),
                 EXPECTED.replace(SHELL_TRANSCRIPT,b"")]
        for serial in invalid:
            with self.subTest(serial=serial),self.assertRaises(RuntimeError):
                validate_boot(SUCCESS_STATUS,serial,b"")

    def test_shell_transcript_is_the_frozen_block_after_vfs(self):
        self.assertEqual(SHELL_TRANSCRIPT,
            b"SHELL: READY\nSHELL> ls\nhello.zen\nnotes.txt\nboot.txt\nSHELL> cat hello.zen\nHello\n"
            b"SHELL> help\ncommands: help ls cat put exit\nSHELL> exit\nSHELL: DONE\n")
        self.assertEqual(EXPECTED_MESSAGES.count(SHELL_TRANSCRIPT),1)
        # TASK-919 only widens `ls`: RAMFS names first, then the PFS file.
        self.assertEqual(SHELL_TRANSCRIPT.index(b"hello.zen\nnotes.txt\nboot.txt\n"),
                         SHELL_TRANSCRIPT.index(b"SHELL> ls\n")+len(b"SHELL> ls\n"))
        self.assertEqual(SHELL_TRANSCRIPT.count(b"boot.txt"),1)
        # The new block starts exactly where the Hito 7 VFS block ends.
        self.assertEqual(EXPECTED.index(VFS_BLOCK)+len(VFS_BLOCK),EXPECTED.index(SHELL_READY))

    def test_userspace_writes_are_exactly_eighteen(self):
        self.assertIn(b"writes=18",EXPECTED)
        self.assertIn(b"runs=7",EXPECTED)
        self.assertIn(b"rejected=6",EXPECTED)
        for wrong in (b"writes=5",b"writes=17",b"writes=19",b"writes=0"):
            with self.subTest(wrong=wrong),self.assertRaises(RuntimeError):
                validate_boot(SUCCESS_STATUS,EXPECTED.replace(b"writes=18",wrong),b"")

    def test_persistence_line_is_frozen_before_the_shell(self):
        self.assertEqual(EXPECTED.count(PERSIST_LINE),1)
        self.assertLess(EXPECTED.index(b"SCHEDULER: STATS"),EXPECTED.index(PERSIST_LINE))
        self.assertLess(EXPECTED.index(PERSIST_LINE),EXPECTED.index(b"USER: Hello from Zen"))
        self.assertEqual(EXPECTED.count(b"PERSIST:"),1)

    def test_pfs_line_follows_persistence_and_precedes_the_shell(self):
        self.assertEqual(EXPECTED.count(PFS_LINE),1)
        self.assertEqual(EXPECTED.index(PERSIST_LINE)+len(PERSIST_LINE),EXPECTED.index(PFS_LINE))
        self.assertLess(EXPECTED.index(PFS_LINE),EXPECTED.index(b"USER: Hello from Zen"))
        self.assertEqual(EXPECTED.count(b"PFS:"),1)

    def test_default_input_and_runner_api_are_frozen(self):
        self.assertEqual(DEFAULT_INPUT,b"ls\ncat hello.zen\nhelp\nexit\n")
        self.assertEqual(inspect.signature(boot).parameters["input"].default,DEFAULT_INPUT)
        self.assertIsNone(inspect.signature(boot).parameters["disk_image"].default)
        self.assertIsNone(inspect.signature(run_process).parameters["input"].default)


class ShellInjectionTests(unittest.TestCase):
    def test_writer_waits_for_split_marker_before_writing(self):
        stdin=RecordingStdin();sink=bytearray();guard=threading.Lock()
        chunks=[b"SHELL",b": REA",b"DY\n",b"SHELL> ls\n"]
        observed=[]
        reader=ScriptedStdout(chunks,lambda remaining: observed.append((remaining,bytes(stdin.data))))
        state={"injected":False,"error":None}
        _inject_after_ready(reader,stdin,sink,guard,DEFAULT_INPUT,state)
        self.assertTrue(state["injected"]);self.assertIsNone(state["error"])
        self.assertEqual(bytes(stdin.data),DEFAULT_INPUT);self.assertTrue(stdin.closed)
        self.assertEqual(bytes(sink),b"SHELL: READY\nSHELL> ls\n")
        # Reads with 4/3/2 chunks left happen before the marker is complete.
        self.assertEqual(observed,[(4,b""),(3,b""),(2,b""),(1,DEFAULT_INPUT),(0,DEFAULT_INPUT)])

    def test_writer_never_injects_without_marker(self):
        stdin=RecordingStdin();sink=bytearray();guard=threading.Lock()
        reader=ScriptedStdout([b"SHELL> ls\n",b"hello.zen\n"])
        state={"injected":False,"error":None}
        _inject_after_ready(reader,stdin,sink,guard,DEFAULT_INPUT,state)
        self.assertFalse(state["injected"]);self.assertIsNone(state["error"])
        self.assertEqual(bytes(stdin.data),b"");self.assertTrue(stdin.closed)

    def test_run_process_injects_after_marker_with_fake_guest(self):
        cut=EXPECTED.index(SHELL_READY)+len(SHELL_READY)+1
        prefix,suffix=EXPECTED[:cut],EXPECTED[cut:]
        code="\n".join([
            "import select,sys",
            "assert not select.select([sys.stdin],[],[],0)[0], 'input arrived before SHELL: READY'",
            f"sys.stdout.buffer.write({prefix!r})",
            "sys.stdout.buffer.flush()",
            "data=sys.stdin.buffer.read()",
            f"assert data=={DEFAULT_INPUT!r}, data",
            f"sys.stdout.buffer.write({suffix!r})",
            "sys.stdout.buffer.flush()",
            "sys.exit(33)",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            result=run_process([sys.executable,"-u","-c",code],os.environ.copy(),5,Path(tmp),input=DEFAULT_INPUT)
            self.assertTrue(result["passed"])
            self.assertEqual(result["status"],SUCCESS_STATUS)
            self.assertEqual((Path(tmp)/"serial.log").read_bytes(),EXPECTED)

    def test_run_process_timeout_with_input_kills_guest_and_keeps_logs(self):
        code="import sys,time; sys.stdout.write('SHELL: READY\\n'); sys.stdout.flush(); time.sleep(60)"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,"timed out"):
                run_process([sys.executable,"-u","-c",code],os.environ.copy(),1,Path(tmp),input=DEFAULT_INPUT)
            result=json.loads((Path(tmp)/"result.json").read_text())
            self.assertTrue(result["timed_out"]);self.assertFalse(result["passed"])
            self.assertLess(result["seconds"],4)
            self.assertEqual((Path(tmp)/"serial.log").read_bytes(),b"SHELL: READY\n")

    def test_run_process_cancellation_with_input_kills_group_and_keeps_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);pidfile=tmp/"child.pid";logs=tmp/"logs"
            child_code=f"import os,time; from pathlib import Path; print('SHELL: READY',flush=True); Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)"
            wrapper=f"import sys,os; from pathlib import Path; sys.path.insert(0,{str(ROOT/'infrastructure/scripts')!r}); from boot_ferros import run_process, DEFAULT_INPUT; run_process({[sys.executable,'-u','-c',child_code]!r},os.environ.copy(),30,Path({str(logs)!r}),input=DEFAULT_INPUT)"
            process=subprocess.Popen([sys.executable,"-c",wrapper],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            child_pid=None
            try:
                deadline=time.monotonic()+5
                while not pidfile.exists() and time.monotonic()<deadline: time.sleep(0.01)
                self.assertTrue(pidfile.exists(),"dummy guest did not start")
                child_pid=int(pidfile.read_text())
                process.send_signal(signal.SIGINT)
                process.communicate(timeout=6)
                result=json.loads((logs/"result.json").read_text())
                self.assertTrue(result["cancelled"]);self.assertFalse(result["passed"])
                self.assertEqual((logs/"serial.log").read_bytes(),b"SHELL: READY\n")
                with self.assertRaises(ProcessLookupError): os.kill(child_pid,0)
            finally:
                if process.poll() is None: process.kill();process.communicate()
                if child_pid is not None:
                    try: os.killpg(child_pid,signal.SIGKILL)
                    except ProcessLookupError: pass


if __name__=="__main__":unittest.main()
