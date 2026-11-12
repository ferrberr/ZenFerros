#!/usr/bin/env python3
"""Bootstrap the partial Zen CLI; no compiler invocation occurs at CLI runtime."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def build(zen, output, cc=None):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zen-selfhost-build-") as tmp:
        tmp = Path(tmp)
        source = tmp / "compiler.zen"
        source.write_text("\n".join((ROOT / "zen/selfhost" / name).read_text()
                                    for name in ("lexer_tokens.zen", "codegen_structs.zen", "cli.zen")))
        obj = tmp / "compiler.o"
        subprocess.run([str(zen), "build", str(source), "--target", "x86_64-unknown-none",
                        "--emit", "obj", "-o", str(obj)], check=True)
        subprocess.run([cc or os.environ.get("CC", "cc"), "-std=c11", "-O2", "-Wall",
                        "-Wextra", "-Werror", "-fno-pie", "-no-pie",
                        str(ROOT / "zen/selfhost/cli_io.c"), str(obj), "-o", str(output)], check=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--zen", type=Path,
                        default=Path(os.environ.get("ZEN", ROOT / "zen/compiler/target/release/zen")))
    args = parser.parse_args()
    build(args.zen.resolve(), args.output)
