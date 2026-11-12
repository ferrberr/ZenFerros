#!/usr/bin/env python3
"""Build a separate static Zen ELF64 user image for the Ferros CPL3 loader.
No generated userspace or privileged probe is executed on the build host.
"""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
PAGE = 4096
USER_BASE = 0x40000000
USER_IMAGE_LIMIT = 0x40100000


def inspect_user(path):
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("expected ELF64 little-endian version1")
    kind, machine, version = struct.unpack_from("<HHI", data, 16)
    if (kind, machine, version) != (2, 62, 1):
        raise ValueError("expected static ET_EXEC x86_64")
    entry, phoff, shoff = struct.unpack_from("<QQQ", data, 24)
    ehsize, phentsize, phnum, shentsize, shnum = struct.unpack_from("<HHHHH", data, 52)
    if ehsize != 64 or phentsize != 56 or not 1 <= phnum <= 8 or phoff + phnum * phentsize > len(data):
        raise ValueError("invalid program-header table")
    segments = []
    for index in range(phnum):
        ptype, flags, offset, address, physical, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", data, phoff + index * phentsize)
        if ptype in (2, 3):
            raise ValueError("dynamic/interpreter segment forbidden")
        if ptype != 1:
            continue
        if flags not in (4, 5, 6) or not memsz or filesz > memsz or offset + filesz > len(data):
            raise ValueError("invalid LOAD flags or file size")
        if align != PAGE or offset % PAGE or address % PAGE or physical != address:
            raise ValueError("LOAD addresses/offsets must be page aligned")
        end = address + memsz
        if address < USER_BASE or end > USER_IMAGE_LIMIT or end <= address:
            raise ValueError("LOAD outside user image window")
        page_end = (end + PAGE - 1) & -PAGE
        if any(address < other["page_end"] and other["address"] < page_end for other in segments):
            raise ValueError("overlapping LOAD pages")
        segments.append(dict(address=address, file_offset=offset, file_bytes=filesz, memory_bytes=memsz, page_end=page_end, flags=flags))
    if entry != USER_BASE or not any(s["flags"] == 5 and s["address"] <= entry < s["address"] + s["file_bytes"] for s in segments):
        raise ValueError("entry is outside executable file-backed segment")
    if shnum:
        if shentsize != 64 or not shoff or shoff + shnum * shentsize > len(data):
            raise ValueError("invalid section-header table")
        for index in range(shnum):
            section_type = struct.unpack_from("<I", data, shoff + index * shentsize + 4)[0]
            if section_type in (4, 9):
                raise ValueError("unresolved relocation sections forbidden")
    return dict(entry=entry, bytes=len(data), load_segments=segments, bss_bytes=sum(s["memory_bytes"] - s["file_bytes"] for s in segments))


def build_user(zen, output, release=False, source_override=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source_override).resolve() if source_override is not None else ROOT / "ferros/user/main.zen"
    logs = []
    def run(command):
        command = [str(part) for part in command]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        logs.append("$ " + " ".join(command) + "\n" + result.stdout + result.stderr + f"exit={result.returncode}\n")
        if result.returncode:
            raise RuntimeError(logs[-1])
        return result.stdout
    started = time.perf_counter()
    try:
        command = [Path(zen).resolve(), "build", source, "--target", "x86_64-unknown-none", "--emit", "obj", "-o", output / "user.o"]
        if release:
            command.append("--release")
        run(command)
        run([os.environ.get("CC", "cc"), "-c", "-m64", "-ffreestanding", "-fno-pie", ROOT / "ferros/user/entry.S", "-o", output / "user-entry.o"])
        artifact = output / "ferros-user.elf"
        run(["ld", "-m", "elf_x86_64", "-z", "max-page-size=0x1000", "-z", "noexecstack", "-nostdlib", "-static", "-T", ROOT / "ferros/user/linker.ld", output / "user-entry.o", output / "user.o", "-o", artifact])
        if run(["nm", "-u", artifact]).strip():
            raise ValueError("unresolved user symbols")
        run(["readelf", "-h", "-lW", artifact])
        image = inspect_user(artifact)
        result = dict(artifact_path=str(artifact), source_path=str(source), release=release, undefined_symbols=0, build_seconds=round(time.perf_counter() - started, 6), **image)
        (output / "build.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        (output / "build.log").write_text("\n".join(logs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ROOT / "zen/compiler/target/release/zen")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "ferros/build/user" / ("release" if args.release else "debug")
    result = build_user(args.zen, output, args.release, args.source)
    print("Built", result["artifact_path"])


if __name__ == "__main__":
    main()
