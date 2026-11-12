#!/usr/bin/env python3
"""Build, inspect, link and execute the no-libc Linux adapter for Zen objects.
This verifies freestanding object generation; it does not boot an OS.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ROOT / "zen/compiler/target/release/zen")
    parser.add_argument("--output", type=Path, default=ROOT / "zen/compiler/target/milestone-2")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    logs = []
    metrics = []

    def run(command):
        command = [str(item) for item in command]
        started = time.perf_counter()
        env = dict(os.environ, LC_ALL="C", LANG="C")
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
        elapsed = time.perf_counter() - started
        logs.append("$ " + " ".join(command) + "\n" + result.stdout + result.stderr + f"exit={result.returncode}\n")
        if result.returncode:
            raise RuntimeError(logs[-1])
        return result.stdout, elapsed

    try:
        run([os.environ.get("CC", "cc"), "-c", "-m64", "-fno-pie", ROOT / "infrastructure/freestanding/linux_start.S", "-o", output / "start.o"])
        for optimized in (False, True):
            suffix = "optimized" if optimized else "debug"
            obj = output / f"zen-{suffix}.o"
            elf = output / f"zen-{suffix}.elf"
            command = [args.zen.resolve(), "build", ROOT / "zen/examples/freestanding.zen", "--target", "x86_64-unknown-none", "--emit", "obj", "-o", obj]
            if optimized:
                command.append("--release")
            _, compile_seconds = run(command)
            header, _ = run(["readelf", "-h", obj])
            if "REL (Relocatable file)" not in header or "ELF64" not in header or "X86-64" not in header:
                raise RuntimeError("unexpected object target or type")
            undefined, _ = run(["nm", "-u", obj])
            if undefined.split() != ["U", "emit_byte"]:
                raise RuntimeError(f"unexpected object imports: {undefined}")
            _, link_seconds = run(["ld", "-nostdlib", "-static", "-z", "noexecstack", "-T", ROOT / "infrastructure/freestanding/linux_test.ld", output / "start.o", obj, "-o", elf])
            dynamic, _ = run(["readelf", "-d", elf])
            segments, _ = run(["readelf", "-lW", elf])
            undefined, _ = run(["nm", "-u", elf])
            if "NEEDED" in dynamic or "INTERP" in segments or undefined.strip():
                raise RuntimeError("linked executable has unexpected runtime dependencies")
            stdout, _ = run([elf])
            if stdout != "Zen freestanding OK\n":
                raise RuntimeError(f"unexpected program output: {stdout!r}")
            metrics.append(dict(optimized=optimized, compile_seconds=round(compile_seconds, 6), link_seconds=round(link_seconds, 6), object_bytes=obj.stat().st_size, executable_bytes=elf.stat().st_size, stdout=stdout, exit_code=0, unresolved_final_symbols=0, dynamic_dependencies=0))
            print(f"{suffix}: ELF64 object + static no-libc executable verified; {stdout.strip()}")
        (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    finally:
        (output / "validation.log").write_text("\n".join(logs))

if __name__ == "__main__":
    main()
