#!/usr/bin/env python3
"""Download official Arch QEMU packages into .tools without installing to the host."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[2]
PREFIX=ROOT/".tools/qemu"
CACHE=PREFIX/"packages"

def download(url,path):
    print("Downloading",url,flush=True)
    with urllib.request.urlopen(url,timeout=60) as source, path.open("wb") as dest:
        shutil.copyfileobj(source,dest)


def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    records=json.loads((ROOT/"infrastructure/toolchains/qemu-packages.json").read_text())
    for record in records:
        name=record["name"]; url=record["url"]
        archive=CACHE/url.rsplit("/",1)[1]
        expected=record["sha256"]
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
            try:
                download(url,archive)
            except urllib.error.HTTPError as error:
                if error.code!=404: raise
                archived=f"https://archive.archlinux.org/packages/{name[0]}/{name}/{archive.name}"
                download(archived,archive)
        actual=hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual!=expected: raise RuntimeError(f"checksum mismatch for {name}")
        subprocess.run(["bsdtar","-xf",str(archive),"-C",str(PREFIX)],check=True)
    (PREFIX/"provenance.json").write_text(json.dumps(records,indent=2)+"\n")
    env=os.environ.copy();env["LD_LIBRARY_PATH"]=str(PREFIX/"usr/lib")
    env["QEMU_MODULE_DIR"]=str(PREFIX/"usr/lib/qemu")
    subprocess.run([str(PREFIX/"usr/bin/qemu-system-x86_64"),"--version"],env=env,check=True)
    print("Local QEMU ready:",PREFIX)

if __name__=="__main__":main()
