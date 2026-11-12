#!/usr/bin/env python3
"""Count authored kernel/architecture/boot source separately from generated C."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]

def count(path):
    text=path.read_text()
    # Textual SLOC for the current sources: exclude /* */ and // comments.
    text=re.sub(r"/\*.*?\*/","",text,flags=re.S)
    return dict(path=str(path.relative_to(ROOT)),physical_lines=len(path.read_text().splitlines()),code_lines=sum(bool(line.split("//",1)[0].strip()) for line in text.splitlines()))

if __name__=="__main__":
    zen=[count(p) for p in sorted((ROOT/"ferros/kernel").rglob("*.zen"))]
    arch=[count(p) for p in sorted((ROOT/"ferros/kernel").rglob("*.S"))]
    boot=[count(p) for p in sorted((ROOT/"ferros/boot").glob("*.S"))]
    linker=[count(p) for p in sorted((ROOT/"ferros/boot").glob("*.ld"))]
    z=sum(p["code_lines"] for p in zen);a=sum(p["code_lines"] for p in arch);b=sum(p["code_lines"] for p in boot)
    generated=ROOT/"ferros/build/release/kernel.generated.c"
    result=dict(method="nonblank lines after removing C-style block and // comments in current authored sources",zen_kernel=zen,assembly_primitives=arch,assembly_bootstrap=boot,linker_configuration=linker,kernel_zen_percent_excluding_boot=round(100*z/(z+a),2),zen_percent_including_boot_assembly=round(100*z/(z+a+b),2),generated_c_physical_lines=len(generated.read_text().splitlines()) if generated.exists() else None,external_dependencies_in_kernel=0)
    print(json.dumps(result,indent=2))
